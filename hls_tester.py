#!/usr/bin/env python3
"""
HLS Tester

Comprehensive automation tool for HLS streams using FFmpeg:
- MSN monitoring for loop detection
- Stream accessibility verification  
- Advanced audio analysis and silence detection (FFmpeg)
- Audio distortion detection (FFmpeg)
- Black frames detection (FFmpeg)
- Freeze frames detection (FFmpeg)
- Bitrate validation (FFprobe)
- Structured reporting for multiple URLs
- JSON file input support with channel metadata

Requirements:
- FFmpeg must be installed for quality analysis

Usage: 
  ./hls_quick_tester.py url1 url2 url3 [options]
  ./hls_quick_tester.py --json-file stream_urls.json [options]
"""

import argparse
import sys
import os
import time
import json
import re
import threading
import csv
import subprocess
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict

import requests
import m3u8
import validators
from colorama import init, Fore, Style
from tabulate import tabulate

init(autoreset=True)

# Check if FFmpeg is available
FFMPEG_AVAILABLE = shutil.which('ffmpeg') is not None
FFPROBE_AVAILABLE = shutil.which('ffprobe') is not None

@dataclass
class QuickTestResult:
    """Quick test result for a single stream"""
    url: str
    test_duration: float
    timestamp: datetime
    status: str  # 'pass', 'warning', 'fail'
    msn_status: str  # 'live', 'loop', 'frozen', 'error'
    audio_status: str  # 'ok', 'missing', 'issues', 'silent', 'error'
    
    # Channel information from JSON
    channel_name: str = ""
    channel_key: str = ""
    resolution: str = ""
    stream_type: str = ""
    
    # Overall status
    summary: str = ""
    
    # MSN Analysis
    initial_msn: int = 0
    final_msn: int = 0
    msn_increments: int = 0
    increment_rate: float = 0.0
    
    # Stream Analysis
    stream_count: int = 0
    segments_accessible: int = 0
    segments_tested: int = 0
    
    # Audio Analysis
    audio_streams_count: int = 0
    audio_codecs: List[str] = None
    audio_channels: str = "unknown"
    audio_sample_rate: str = "unknown"
    audio_segments_tested: int = 0
    audio_segments_accessible: int = 0
    silence_detected: bool = False
    silence_percentage: float = 0.0
    audio_distortion_detected: bool = False
    
    # Video Analysis
    black_frames_detected: bool = False
    black_frames_percentage: float = 0.0
    freeze_frames_detected: bool = False
    video_bitrate_issues: bool = False
    
    # FFmpeg Analysis
    ffmpeg_analysis_performed: bool = False
    
    # Issues
    issues: List[str] = None
    warnings: List[str] = None
    error_message: str = ""  # Main error message for failed tests
    
    def __post_init__(self):
        if self.audio_codecs is None:
            self.audio_codecs = []
        if self.issues is None:
            self.issues = []
        if self.warnings is None:
            self.warnings = []

def load_streams_from_json(json_file: str) -> List[Dict]:
    """Load stream URLs and metadata from JSON file"""
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        if 'stream_urls' not in data:
            raise ValueError("JSON file must contain 'stream_urls' array")
        
        return data['stream_urls']
    except FileNotFoundError:
        raise FileNotFoundError(f"JSON file not found: {json_file}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {e}")
    except Exception as e:
        raise ValueError(f"Error loading JSON file: {e}")

class HLSQuickTester:
    """Quick HLS tester without FFmpeg dependencies"""
    
    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'HLS-QuickTester/1.0'})
    
    def test_stream(self, url: str, duration: int = 30, channel_info: Dict = None) -> QuickTestResult:
        """
        Quick test of an HLS stream
        
        Args:
            url: HLS stream URL
            duration: Test duration in seconds
            channel_info: Dictionary containing channel metadata
        """
        channel_name = channel_info.get('channel_name', '') if channel_info else ''
        channel_key = channel_info.get('channel_key', '') if channel_info else ''
        resolution = channel_info.get('resolution', '') if channel_info else ''
        stream_type = channel_info.get('type', '') if channel_info else ''
        
        # Always display the URL
        print(f"{Fore.CYAN}⚡ Testing: {url}")
        
        start_time = datetime.now()
        result = QuickTestResult(
            url=url,
            test_duration=0,
            timestamp=start_time,
            status='fail',
            msn_status='error',
            audio_status='error',
            channel_name=channel_name,
            channel_key=channel_key,
            resolution=resolution,
            stream_type=stream_type,
            summary='',
            initial_msn=0,
            final_msn=0,
            msn_increments=0,
            increment_rate=0.0,
            stream_count=0,
            segments_accessible=0,
            segments_tested=0,
            audio_streams_count=0,
            audio_codecs=[],
            audio_channels='unknown',
            audio_sample_rate='unknown',
            audio_segments_tested=0,
            audio_segments_accessible=0,
            silence_detected=False,
            silence_percentage=0.0,
            audio_distortion_detected=False,
            black_frames_detected=False,
            black_frames_percentage=0.0,
            freeze_frames_detected=False,
            video_bitrate_issues=False,
            ffmpeg_analysis_performed=False,
            issues=[],
            warnings=[],
            error_message=""
        )
        
        try:
            # Step 1: Validate URL and get stream info
            stream_info = self._analyze_streams(url, result)
            if not stream_info:
                result.summary = "Failed to access stream"
                result.error_message = result.issues[0] if result.issues else "Failed to access stream"
                return result
            
            media_url, stream_count = stream_info
            result.stream_count = stream_count
            
            # Step 2: Test segment accessibility
            print(f"  {Fore.YELLOW}→ Testing segments...")
            self._test_segments(media_url, result)
            
            # Step 3: Analyze audio streams
            print(f"  {Fore.YELLOW}→ Analyzing audio...")
            self._analyze_audio(url, result)
            
            # Step 4: Analyze video quality (black frames, freeze frames) using FFmpeg
            print(f"  {Fore.YELLOW}→ Analyzing video quality...")
            self._analyze_video_quality(media_url, result)
            
            # Step 5: Monitor MSN
            print(f"  {Fore.YELLOW}→ Monitoring MSN for {duration}s...")
            self._monitor_msn_quick(media_url, duration, result)
            
            # Step 6: Determine overall status
            self._determine_status(result)
            
        except Exception as e:
            error_msg = str(e)
            result.issues.append(f"Test failed: {error_msg}")
            result.summary = f"Test error: {error_msg}"
            result.error_message = error_msg
        
        result.test_duration = (datetime.now() - start_time).total_seconds()
        
        # Set error message from first critical issue if not already set
        if not result.error_message and result.issues:
            result.error_message = result.issues[0]
        
        return result
    
    def _analyze_streams(self, url: str, result: QuickTestResult) -> Optional[Tuple[str, int]]:
        """Analyze stream structure"""
        if not validators.url(url):
            result.issues.append("Invalid URL format")
            return None
        
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            if not response.text.strip().startswith('#EXTM3U'):
                result.issues.append("Not a valid M3U8 file")
                return None
            
            manifest = m3u8.loads(response.text, uri=url)
            
            if manifest.is_variant:
                stream_count = len(manifest.playlists)
                print(f"    Found {stream_count} quality streams")
                
                # Get the highest quality stream for testing
                best_stream = max(manifest.playlists, key=lambda p: p.stream_info.bandwidth)
                return best_stream.absolute_uri, stream_count
            else:
                print(f"    Single media playlist")
                return url, 1
                
        except requests.exceptions.RequestException as e:
            result.issues.append(f"Cannot access manifest: {str(e)}")
            return None
        except Exception as e:
            result.issues.append(f"Manifest parsing error: {str(e)}")
            return None
    
    def _test_segments(self, media_url: str, result: QuickTestResult):
        """Test segment accessibility"""
        try:
            response = self.session.get(media_url, timeout=self.timeout)
            response.raise_for_status()
            
            playlist = m3u8.loads(response.text, uri=media_url)
            segments = playlist.segments
            
            if not segments:
                result.issues.append("No segments found in playlist")
                return
            
            # Test first 3 segments
            segments_to_test = min(3, len(segments))
            accessible_count = 0
            
            for segment in segments[:segments_to_test]:
                try:
                    seg_response = self.session.head(segment.absolute_uri, timeout=self.timeout)
                    if seg_response.status_code == 200:
                        accessible_count += 1
                except:
                    pass
            
            result.segments_tested = segments_to_test
            result.segments_accessible = accessible_count
            
            if accessible_count == 0:
                result.issues.append("No segments are accessible")
            elif accessible_count < segments_to_test:
                result.warnings.append(f"Only {accessible_count}/{segments_to_test} segments accessible")
            else:
                print(f"    ✓ All {accessible_count} test segments accessible")
                
        except Exception as e:
            result.warnings.append(f"Could not test segments: {str(e)}")
    
    def _monitor_msn_quick(self, media_url: str, duration: int, result: QuickTestResult):
        """Quick MSN monitoring"""
        try:
            msn_readings = []
            start_time = time.time()
            check_interval = max(2, duration // 10)  # At least 10 checks or every 2 seconds
            
            check_count = 0
            while (time.time() - start_time) < duration and check_count < 15:  # Max 15 checks
                try:
                    response = self.session.get(media_url, timeout=self.timeout)
                    response.raise_for_status()
                    
                    # Extract MSN
                    msn_match = re.search(r'#EXT-X-MEDIA-SEQUENCE:(\d+)', response.text)
                    if msn_match:
                        msn = int(msn_match.group(1))
                        msn_readings.append((time.time(), msn))
                        print(f"    MSN: {msn}")
                        check_count += 1
                    
                except Exception:
                    pass
                
                if check_count < 15:  # Don't sleep after last check
                    time.sleep(check_interval)
            
            if len(msn_readings) < 2:
                result.msn_status = 'error'
                result.warnings.append("Insufficient MSN readings")
                return
            
            # Analyze MSN progression
            result.initial_msn = msn_readings[0][1]
            result.final_msn = msn_readings[-1][1]
            result.msn_increments = result.final_msn - result.initial_msn
            
            # Calculate rate
            time_span = msn_readings[-1][0] - msn_readings[0][0]
            result.increment_rate = (result.msn_increments / time_span) * 60 if time_span > 0 else 0
            
            # Determine MSN status
            if result.msn_increments == 0:
                if len(msn_readings) >= 5:  # Enough samples
                    result.msn_status = 'frozen'
                    result.issues.append("Stream appears frozen - MSN not updating")
                else:
                    result.msn_status = 'loop'
                    result.warnings.append("Possible loop - MSN not changing")
            elif result.msn_increments > 0:
                result.msn_status = 'live'
                print(f"    ✓ MSN increased {result.msn_increments} times (rate: {result.increment_rate:.1f}/min)")
            else:
                result.msn_status = 'error'
                result.issues.append("MSN decreased - unusual behavior")
                
        except Exception as e:
            result.msn_status = 'error'
            result.warnings.append(f"MSN monitoring failed: {str(e)}")
    
    def _analyze_audio(self, url: str, result: QuickTestResult):
        """Analyze audio streams and detect silence without FFmpeg"""
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            manifest = m3u8.loads(response.text, uri=url)
            
            # Initialize audio analysis
            result.audio_streams_count = 0
            result.audio_codecs = []
            audio_streams = []
            
            if manifest.is_variant:
                # Collect audio streams from variant playlist
                for playlist in manifest.playlists:
                    stream_info = playlist.stream_info
                    if stream_info.codecs:
                        # Extract audio codecs (typically mp4a.* or ac-3, ec-3)
                        codecs = stream_info.codecs.split(',')
                        audio_codecs = [codec.strip() for codec in codecs if 'mp4a' in codec or 'ac-3' in codec or 'ec-3' in codec]
                        if audio_codecs:
                            result.audio_codecs.extend(audio_codecs)
                            audio_streams.append(playlist.absolute_uri)
                
                # Also check for dedicated audio streams
                if manifest.media:
                    for media in manifest.media:
                        if media.type == 'AUDIO':
                            result.audio_streams_count += 1
                            if media.uri:
                                audio_streams.append(media.uri)
                            # Extract audio properties
                            if hasattr(media, 'channels'):
                                result.audio_channels = media.channels
                            if hasattr(media, 'language'):
                                print(f"    Audio language: {media.language}")
                
                # Use highest quality stream for testing if no dedicated audio
                if not audio_streams and manifest.playlists:
                    best_stream = max(manifest.playlists, key=lambda p: p.stream_info.bandwidth)
                    audio_streams.append(best_stream.absolute_uri)
            else:
                # Single media playlist - assume it contains audio
                audio_streams.append(url)
            
            if not audio_streams:
                result.audio_status = 'missing'
                result.issues.append("No audio streams found")
                print(f"    ❌ No audio streams detected")
                return
            
            result.audio_streams_count = len(audio_streams)
            if result.audio_codecs:
                print(f"    Audio codecs: {', '.join(set(result.audio_codecs))}")
            
            # Test audio stream using FFmpeg for silence and distortion
            self._analyze_audio_quality_ffmpeg(audio_streams[0], result)
            
        except Exception as e:
            result.audio_status = 'error'
            result.warnings.append(f"Audio analysis failed: {str(e)}")
    
    def _analyze_audio_quality_ffmpeg(self, audio_url: str, result: QuickTestResult):
        """Analyze audio quality using FFmpeg for both silence and distortion"""
        try:
            response = self.session.get(audio_url, timeout=self.timeout)
            response.raise_for_status()
            
            playlist = m3u8.loads(response.text, uri=audio_url)
            segments = playlist.segments
            
            if not segments:
                result.audio_status = 'missing'
                result.warnings.append("No audio segments found")
                return
            
            print(f"    Analyzing audio quality with FFmpeg (60 seconds)...")
            
            # Test first 3 audio segments
            segments_to_test = min(3, len(segments))
            silence_count = 0
            distortion_count = 0
            accessible_segments = 0
            
            for i, segment in enumerate(segments[:segments_to_test]):
                try:
                    # Check if segment is accessible first
                    seg_check = self.session.head(segment.absolute_uri, timeout=self.timeout)
                    if seg_check.status_code != 200:
                        continue
                    
                    accessible_segments += 1
                    
                    # 1. Check for audio silence using FFmpeg silencedetect
                    silence_cmd = [
                        'ffmpeg', '-i', segment.absolute_uri,
                        '-af', 'silencedetect=noise=-50dB:d=2.0',
                        '-f', 'null', '-',
                        '-t', '60'  # Analyze first 60 seconds
                    ]
                    
                    silence_result = subprocess.run(
                        silence_cmd,
                        capture_output=True,
                        text=True,
                        timeout=70
                    )
                    
                    # Check if silence was detected
                    if 'silence_start' in silence_result.stderr:
                        silence_count += 1
                    
                    # 2. Check for audio distortion using FFmpeg astats
                    astats_cmd = [
                        'ffmpeg', '-i', segment.absolute_uri,
                        '-af', 'astats=metadata=1:reset=1',
                        '-f', 'null', '-',
                        '-t', '60'  # Analyze first 60 seconds
                    ]
                    
                    astats_result = subprocess.run(
                        astats_cmd,
                        capture_output=True,
                        text=True,
                        timeout=70
                    )
                    
                    output = astats_result.stderr
                    
                    # Check for audio clipping (peak level at or above 0 dB)
                    if 'Peak level dB' in output:
                        for line in output.split('\n'):
                            if 'Peak level dB' in line:
                                try:
                                    peak_db = float(line.split(':')[1].strip())
                                    if peak_db >= -0.1:  # At or near 0 dB indicates clipping
                                        distortion_count += 1
                                        break
                                except:
                                    pass
                    
                    # Check for DC offset (indicates audio corruption)
                    if 'DC offset' in output:
                        for line in output.split('\n'):
                            if 'DC offset' in line:
                                try:
                                    dc_offset = float(line.split(':')[1].strip())
                                    if abs(dc_offset) > 0.1:  # Significant DC offset
                                        distortion_count += 1
                                        break
                                except:
                                    pass
                    
                    # Check for abnormal RMS levels
                    if 'RMS level dB' in output:
                        for line in output.split('\n'):
                            if 'RMS level dB' in line:
                                try:
                                    rms_db = float(line.split(':')[1].strip())
                                    if rms_db > -3.0 or rms_db < -60.0:
                                        distortion_count += 1
                                        break
                                except:
                                    pass
                    
                except subprocess.TimeoutExpired:
                    continue
                except Exception:
                    continue
            
            result.audio_segments_tested = segments_to_test
            result.audio_segments_accessible = accessible_segments
            
            if accessible_segments == 0:
                result.audio_status = 'missing'
                result.issues.append("No audio segments are accessible")
                print(f"    ❌ No audio segments accessible")
                return
            
            # Set silence detection results
            if segments_to_test > 0:
                result.silence_percentage = (silence_count / segments_to_test) * 100
                result.silence_detected = silence_count > 0
                
                if result.silence_detected:
                    result.audio_status = 'silent'
                    result.issues.append(f"Audio silence detected in {silence_count}/{segments_to_test} segments ({result.silence_percentage:.1f}%)")
                    print(f"    ⚠️  Silence detected: {result.silence_percentage:.1f}%")
                else:
                    result.audio_status = 'ok'
                    print(f"    ✓ No audio silence detected")
            
            # Set distortion detection results
            if distortion_count > 0:
                result.audio_distortion_detected = True
                distortion_percentage = (distortion_count / segments_to_test) * 100
                result.warnings.append(f"Audio distortion detected in {distortion_count}/{segments_to_test} segments ({distortion_percentage:.1f}%)")
                print(f"    ⚠️  Audio distortion detected: {distortion_percentage:.1f}%")
            else:
                print(f"    ✓ No audio distortion detected")
                
        except Exception as e:
            result.audio_status = 'error'
            result.warnings.append(f"Audio quality analysis failed: {str(e)}")
    
    
    def _analyze_video_quality(self, media_url: str, result: QuickTestResult):
        """Advanced video analysis using FFmpeg/FFprobe"""
        try:
            result.ffmpeg_analysis_performed = True
            
            response = self.session.get(media_url, timeout=self.timeout)
            response.raise_for_status()
            
            playlist = m3u8.loads(response.text, uri=media_url)
            segments = playlist.segments
            
            if not segments:
                result.warnings.append("No video segments for analysis")
                return
            
            # Analyze first few segments with FFprobe
            segments_to_test = min(3, len(segments))
            black_frame_count = 0
            freeze_detected = False
            distortion_detected = False
            
            for i, segment in enumerate(segments[:segments_to_test]):
                try:
                    # Download segment to temp location
                    seg_response = self.session.get(segment.absolute_uri, timeout=self.timeout, stream=True)
                    
                    if seg_response.status_code == 200:
                        # Use FFprobe to analyze segment
                        if FFPROBE_AVAILABLE:
                            # Check bitrate with FFprobe
                            try:
                                bitrate_cmd = [
                                    'ffprobe', '-v', 'error',
                                    '-select_streams', 'v:0',
                                    '-show_entries', 'stream=bit_rate',
                                    '-of', 'default=noprint_wrappers=1:nokey=1',
                                    segment.absolute_uri
                                ]
                                
                                bitrate_result = subprocess.run(
                                    bitrate_cmd,
                                    capture_output=True,
                                    text=True,
                                    timeout=5
                                )
                                
                                if bitrate_result.stdout.strip():
                                    bitrate = int(bitrate_result.stdout.strip())
                                    if bitrate <= 0:
                                        result.video_bitrate_issues = True
                                        result.issues.append(f"Invalid bitrate detected: {bitrate} bps")
                                        
                            except Exception:
                                pass
                            
                            # Check for black frames
                            black_cmd = [
                                'ffmpeg', '-i', segment.absolute_uri,
                                '-vf', 'blackdetect=d=0.5:pix_th=0.10',
                                '-f', 'null', '-',
                                '-t', '60'  # Analyze first 60 seconds
                            ]
                            
                            try:
                                result_cmd = subprocess.run(
                                    black_cmd,
                                    capture_output=True,
                                    text=True,
                                    timeout=70  # Increased timeout for 60 second analysis
                                )
                                
                                # Check output for black frame detection
                                if 'black_start' in result_cmd.stderr:
                                    black_frame_count += 1
                                    
                                # Check for freeze frames by analyzing frame duplication
                                freeze_cmd = [
                                    'ffmpeg', '-i', segment.absolute_uri,
                                    '-vf', 'freezedetect=n=-60dB:d=2',
                                    '-f', 'null', '-',
                                    '-t', '60'  # Analyze first 60 seconds
                                ]
                                
                                freeze_result = subprocess.run(
                                    freeze_cmd,
                                    capture_output=True,
                                    text=True,
                                    timeout=70  # Increased timeout for 60 second analysis
                                )
                                
                                if 'freeze_start' in freeze_result.stderr:
                                    freeze_detected = True
                                    
                            except subprocess.TimeoutExpired:
                                pass
                            except Exception:
                                pass
                
                except Exception:
                    continue
            
            # Set results based on analysis
            if black_frame_count > 0:
                result.black_frames_detected = True
                result.black_frames_percentage = (black_frame_count / segments_to_test) * 100
                result.issues.append(f"Black frames detected in {black_frame_count}/{segments_to_test} segments")
                print(f"    ❌ Black frames detected: {result.black_frames_percentage:.1f}%")
            else:
                print(f"    ✓ No black frames detected")
            
            if freeze_detected:
                result.freeze_frames_detected = True
                result.issues.append("Freeze frames detected in video")
                print(f"    ❌ Freeze frames detected")
            else:
                print(f"    ✓ No freeze frames detected")
            
            if result.video_bitrate_issues:
                print(f"    ❌ Bitrate issues detected")
            else:
                print(f"    ✓ Bitrate OK")
                
        except Exception as e:
            result.warnings.append(f"FFmpeg video analysis failed: {str(e)}")
    
    def _determine_status(self, result: QuickTestResult):
        """Determine overall test status"""
        critical_issues = len(result.issues)
        warnings = len(result.warnings)
        
        # Additional checks for audio status
        if result.audio_status == 'silent':
            critical_issues += 1  # Treat silence as critical
        elif result.audio_status == 'missing':
            critical_issues += 1  # Treat missing audio as critical
        elif result.audio_status == 'issues':
            warnings += 1
        
        # Check for video issues
        if result.black_frames_detected and result.black_frames_percentage > 20:
            critical_issues += 1  # More than 20% black frames is critical
        elif result.black_frames_detected:
            warnings += 1  # Some black frames is a warning
        
        if result.freeze_frames_detected:
            critical_issues += 1  # Freeze frames are critical
        
        if result.audio_distortion_detected:
            warnings += 1  # Audio distortion is a warning
        
        if critical_issues > 0:
            result.status = 'fail'
            result.summary = f"FAILED - {critical_issues} critical issues"
        elif warnings > 0:
            result.status = 'warning'
            result.summary = f"WARNING - {warnings} minor issues"
        else:
            result.status = 'pass'
            result.summary = "PASSED - All checks successful"

def test_multiple_streams_quick(urls: List[str] = None, json_file: str = None, duration: int = 30, max_workers: int = 5) -> List[QuickTestResult]:
    """Test multiple streams quickly - Requires FFmpeg"""
    
    # Check for FFmpeg - it's now mandatory
    if not FFMPEG_AVAILABLE or not FFPROBE_AVAILABLE:
        print(f"{Fore.RED}❌ ERROR: FFmpeg is required for quality analysis")
        print(f"{Fore.YELLOW}Please install FFmpeg:")
        print(f"  macOS:  brew install ffmpeg")
        print(f"  Linux:  sudo apt install ffmpeg")
        print(f"\nVerify installation: ffmpeg -version")
        sys.exit(1)
    
    tester = HLSQuickTester()
    results = []
    
    # Load streams from JSON file or use provided URLs
    if json_file:
        try:
            stream_data = load_streams_from_json(json_file)
            print(f"{Style.BRIGHT}{Fore.CYAN}⚡ HLS Quick Tester - JSON Mode{Style.RESET_ALL}")
            print(f"Loaded {len(stream_data)} stream(s) from {json_file}")
            print(f"Testing for {duration} seconds each...")
            print(f"{Fore.CYAN}⚡ Processing up to {max_workers} streams in parallel for faster testing")
            print(f"{Fore.GREEN}✓ FFmpeg detected - Advanced video & audio analysis enabled")
            print()
            
        except Exception as e:
            print(f"{Fore.RED}❌ Error loading JSON file: {e}")
            return []
    else:
        if not urls:
            print(f"{Fore.RED}❌ No URLs or JSON file provided")
            return []
        stream_data = [{'stream_url': url} for url in urls]
        print(f"{Style.BRIGHT}{Fore.CYAN}⚡ HLS Quick Tester{Style.RESET_ALL}")
        print(f"Testing {len(urls)} stream(s) for {duration} seconds each...")
        print(f"{Fore.CYAN}⚡ Processing {max_workers} streams in parallel for faster testing")
        print(f"{Fore.GREEN}✓ FFmpeg detected - Advanced video & audio analysis enabled")
        print()
    
    # Test streams in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_data = {}
        
        for stream_info in stream_data:
            url = stream_info['stream_url']
            future = executor.submit(tester.test_stream, url, duration, stream_info)
            future_to_data[future] = stream_info
        
        for future in as_completed(future_to_data):
            stream_info = future_to_data[future]
            url = stream_info['stream_url']
            try:
                result = future.result()
                results.append(result)
                status_emoji = {'pass': '✅', 'warning': '⚠️', 'fail': '❌'}.get(result.status, '❓')
                print(f"  {status_emoji} Completed: {url}")
            except Exception as e:
                print(f"  ❌ Failed: {url} - {str(e)}")
    
    return results

def print_quick_results(results: List[QuickTestResult]):
    """Print quick test results"""
    print(f"\n{Style.BRIGHT}⚡ QUICK TEST RESULTS")
    print("=" * 80)
    
    # Overall statistics
    passed = sum(1 for r in results if r.status == 'pass')
    warnings = sum(1 for r in results if r.status == 'warning') 
    failed = sum(1 for r in results if r.status == 'fail')
    
    print(f"Total Streams: {len(results)}")
    print(f"{Fore.GREEN}✅ Passed: {passed}")
    print(f"{Fore.YELLOW}⚠️  Warnings: {warnings}")
    print(f"{Fore.RED}❌ Failed: {failed}")
    print()
    
    # Results table
    table_data = []
    for i, result in enumerate(results, 1):
        status_emoji = {'pass': '✅', 'warning': '⚠️', 'fail': '❌'}.get(result.status, '❓')
        
        msn_display = f"{result.msn_increments:+d}" if result.msn_increments != 0 else "0"
        if result.msn_status == 'live':
            msn_display = f"🟢 {msn_display}"
        elif result.msn_status == 'frozen':
            msn_display = f"🔴 {msn_display}"
        elif result.msn_status == 'loop':
            msn_display = f"🔄 {msn_display}"
        else:
            msn_display = f"❓ {msn_display}"
        
        # Segments status
        if result.segments_tested > 0:
            segments_display = f"{result.segments_accessible}/{result.segments_tested}"
            if result.segments_accessible == result.segments_tested:
                segments_display = f"✅ {segments_display}"
            elif result.segments_accessible == 0:
                segments_display = f"❌ {segments_display}"
            else:
                segments_display = f"⚠️ {segments_display}"
        else:
            segments_display = "❓ N/A"
        
        # Audio status
        audio_display = {
            'ok': '🔊 OK',
            'missing': '🔇 Missing',
            'silent': '🔇 Silent',
            'issues': '⚠️ Issues',
            'error': '❓ Error'
        }.get(result.audio_status, '❓ Unknown')
        
        if result.silence_detected:
            audio_display += f" ({result.silence_percentage:.0f}%)"
        elif result.audio_status == 'ok' and result.audio_streams_count > 0:
            audio_display = f"🔊 OK ({result.audio_streams_count})"
        
        # Video quality status
        video_issues = []
        if result.black_frames_detected:
            video_issues.append("⬛ Black")
        if result.freeze_frames_detected:
            video_issues.append("🧊 Freeze")
        if result.video_bitrate_issues:
            video_issues.append("📉 Bitrate")
        
        video_display = ", ".join(video_issues) if video_issues else "✅ OK"
        
        # Display URL (truncate if too long for better table formatting)
        display_url = result.url
        if len(display_url) > 60:
            display_url = display_url[:57] + "..."
        
        # Error message (truncate if too long)
        error_display = result.error_message if result.error_message else "-"
        if len(error_display) > 40:
            error_display = error_display[:37] + "..."
        
        table_data.append([
            i,
            status_emoji,
            display_url,
            result.stream_count,
            msn_display,
            segments_display,
            audio_display,
            video_display,
            f"{result.test_duration:.1f}s",
            error_display
        ])
    
    headers = ["#", "Status", "HLS URL", "Streams", "MSN Change", "Segments", "Audio", "Video", "Duration", "Error"]
    # Table output disabled - results saved to CSV
    # print(tabulate(table_data, headers=headers, tablefmt="grid"))
    
    # Issues and warnings
    all_issues = []
    all_warnings = []
    
    for result in results:
        all_issues.extend(result.issues)
        all_warnings.extend(result.warnings)
    
    if all_issues:
        print(f"\n{Style.BRIGHT}{Fore.RED}🚨 CRITICAL ISSUES:")
        for i, issue in enumerate(set(all_issues), 1):
            count = all_issues.count(issue)
            print(f"  {i}. {issue} ({count} stream{'s' if count > 1 else ''})")
    
    if all_warnings:
        print(f"\n{Style.BRIGHT}{Fore.YELLOW}⚠️  WARNINGS:")
        for i, warning in enumerate(set(all_warnings), 1):
            count = all_warnings.count(warning)
            print(f"  {i}. {warning} ({count} stream{'s' if count > 1 else ''})")

def save_quick_report(results: List[QuickTestResult], filename: str):
    """Save quick test report"""
    report_data = {
        'test_timestamp': datetime.now().isoformat(),
        'total_streams': len(results),
        'summary': {
            'passed': sum(1 for r in results if r.status == 'pass'),
            'warnings': sum(1 for r in results if r.status == 'warning'),
            'failed': sum(1 for r in results if r.status == 'fail')
        },
        'results': []
    }
    
    for result in results:
        result_dict = asdict(result)
        result_dict['timestamp'] = result.timestamp.isoformat()
        
        # Add simplified boolean flags for key criteria
        result_dict['audio_silence'] = result.silence_detected
        result_dict['video_in_loop'] = result.msn_status in ['loop', 'frozen']
        result_dict['status'] = 'passed' if result.status == 'pass' else 'failed'
        
        report_data['results'].append(result_dict)
    
    with open(filename, 'w') as f:
        json.dump(report_data, f, indent=2)
    
    print(f"\n📄 Quick test report saved to: {filename}")


def save_results_to_csv(results: List[QuickTestResult], filename: str):
    """Save test results to CSV file (simplified columns)"""
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            # Simplified fieldnames as requested
            fieldnames = [
                'HLS URL',
                'Status',
                'MSN Status',
                'Audio Silence',
                'Audio Distortion',
                'Black Frames',
                'Freeze Frames'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for i, result in enumerate(results, 1):
                # Determine status text
                status_text = {
                    'pass': 'PASS',
                    'warning': 'WARNING',
                    'fail': 'FAIL'
                }.get(result.status, 'UNKNOWN')
                
                # MSN status text
                msn_status_text = {
                    'live': 'LIVE',
                    'loop': 'LOOP',
                    'frozen': 'FROZEN',
                    'error': 'ERROR'
                }.get(result.msn_status, 'UNKNOWN')
                
                writer.writerow({
                    'HLS URL': result.url,
                    'Status': status_text,
                    'MSN Status': msn_status_text,
                    'Audio Silence': 'YES' if result.silence_detected else 'NO',
                    'Audio Distortion': 'YES' if result.audio_distortion_detected else 'NO',
                    'Black Frames': 'YES' if result.black_frames_detected else 'NO',
                    'Freeze Frames': 'YES' if result.freeze_frames_detected else 'NO'
                })
        
        print(f"📊 CSV report saved to: {filename}")
        return True
        
    except Exception as e:
        print(f"❌ Error saving CSV: {e}")
        return False

def main():
    """Main CLI function"""
    parser = argparse.ArgumentParser(description="HLS Quick Tester - Automatically saves CSV report")
    parser.add_argument("urls", nargs="*", help="HLS URLs to test (optional if using --json-file)")
    parser.add_argument("--json-file", help="JSON file containing stream URLs and metadata")
    parser.add_argument("--duration", type=int, default=30,
                       help="Test duration per stream in seconds (default: 30)")
    parser.add_argument("--workers", type=int, default=5,
                       help="Maximum parallel workers (default: 5)")
    parser.add_argument("--output", help="Save detailed JSON report to file (CSV always saved automatically)")
    parser.add_argument("--timeout", type=int, default=15,
                       help="Request timeout in seconds (default: 15)")
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.json_file and not args.urls:
        parser.error("Either provide URLs as arguments or use --json-file option")
    
    if args.json_file and args.urls:
        parser.error("Cannot use both URLs and --json-file. Choose one option.")
    
    # Test all streams
    results = test_multiple_streams_quick(
        urls=args.urls if not args.json_file else None,
        json_file=args.json_file,
        duration=args.duration,
        max_workers=args.workers
    )
    
    # Print results
    print_quick_results(results)
    
    # Save reports
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Save JSON report if requested
    if args.output:
        save_quick_report(results, args.output)
    
    # Always save CSV report in Reports folder
    reports_dir = os.path.join(os.path.dirname(__file__), "Reports")
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)
    
    csv_filename = os.path.join(reports_dir, f"CDN_Test_Report_{timestamp}.csv")
    save_results_to_csv(results, csv_filename)
    
    # Exit with appropriate code
    failed_count = sum(1 for r in results if r.status == 'fail')
    sys.exit(1 if failed_count > 0 else 0)

if __name__ == "__main__":
    main()
