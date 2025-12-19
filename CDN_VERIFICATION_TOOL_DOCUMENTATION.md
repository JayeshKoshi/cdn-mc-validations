# CDN Verification & MediaConnect Validation Tool - Documentation

## What It Does

This tool automatically validates both **CDN streams** and **AWS MediaConnect flows**. It fetches delivery details from the CP-Flows API and performs comprehensive quality checks.

### Two Validation Modes

1. **CDN Stream Testing** - Tests HLS stream quality (audio, video, bitrate)
2. **MediaConnect Validation** - Validates AWS MediaConnect flows (status, metrics, outputs)

### CDN Quality Checks (Using FFmpeg)

✅ **Stream Accessibility** - Verifies streams are reachable  
✅ **MSN Monitoring** - Detects if streams are live, frozen, or looped  
✅ **Audio Silence** - Detects silent audio (≥2 seconds) using FFmpeg  
✅ **Audio Distortion** - Detects clipping, DC offset, abnormal levels using FFmpeg  
✅ **Black Frames** - Detects black or near-black video frames using FFmpeg  
✅ **Freeze Frames** - Detects frozen/static video frames using FFmpeg  
✅ **Bitrate Validation** - Ensures valid bitrate values using FFprobe  

### MediaConnect Validation Checks

✅ **Flow Status** - Checks if flow is ACTIVE/ENABLED  
✅ **Source Health** - Validates source configuration  
✅ **Output Configuration** - Verifies all outputs are configured  
✅ **Entitlement Status** - Checks entitlement states (ENABLED/DISABLED)  
✅ **CloudWatch Metrics** - Analyzes bitrate stability, packet loss, connection status  

### Output

The tool generates **CSV reports**:
- `hls_test_results_YYYYMMDD_HHMMSS.csv` - CDN stream test results
- `Validation_Report_AMGID_YYYYMMDD_HHMMSS.csv` - MediaConnect validation results


## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install FFmpeg (Required for CDN Testing)

FFmpeg is required for CDN stream quality analysis.

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Verify Installation:**
```bash
ffmpeg -version
```

### 3. Configure AWS Credentials (Required for MediaConnect Validation)

AWS credentials are required only if you plan to use MediaConnect validation.

**Configure AWS CLI:**
```bash
aws configure
```

Or set environment variables:
```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

**Verify AWS Access:**
```bash
aws sts get-caller-identity
```

---

## How to Run

### CDN Stream Testing (Default)

Test all CDN streams for a specific AMGID:

```bash
python3 main.py AMGXXXXX
```

This will:
1. Fetch all deliveries for the AMGID
2. Extract HLS stream URLs
3. Test each stream (default: 2 minutes per stream)
4. Generate a CSV report: `hls_test_results_YYYYMMDD_HHMMSS.csv`

### MediaConnect Validation

Validate MediaConnect flows for a specific AMGID:

```bash
python3 main.py AMGXXXXX --validate-mediaconnect --no-auto-test
```

This will:
1. Fetch all deliveries for the AMGID
2. Extract MediaConnect Flow ARNs (AWS region is auto-detected from ARN)
3. Validate each flow (status, outputs, entitlements, CloudWatch metrics)
4. Generate a CSV report: `Validation_Report_AMGXXXXX_YYYYMMDD_HHMMSS.csv`

### Both CDN and MediaConnect

Run both CDN and MediaConnect validation:

```bash
python3 main.py AMGXXXXX --validate-mediaconnect
```

### Custom Test Duration (CDN)

Test streams for a custom duration (e.g., 5 minutes):

```bash
python3 main.py AMGXXXXX --test-duration 300
```

### Adjust Timeout (CDN)

Increase timeout for slower streams (e.g., 30 seconds):

```bash
python3 main.py AMGXXXXX --test-timeout 30
```

---

## Command-Line Options

```bash
python3 main.py <AMGID> [OPTIONS]
```

### General Options

| Option | Description | Default |
|--------|-------------|---------|
| `AMGID` | Amagi ID to filter deliveries (required, positional) | None |
| `--save-json` | Save full API response to JSON file | False |
| `--platform` | Filter by platform (e.g., Roku, Samsung) | None |
| `--env` | Filter by environment | None |
| `--host-url` | Filter by host URL | None |
| `--feed-code` | Filter by feed code | None |

### CDN Testing Options

| Option | Description | Default |
|--------|-------------|---------|
| `--test-duration` | Test duration per stream in seconds | 120 |
| `--test-timeout` | Timeout for operations in seconds | 15 |
| `--no-auto-test` | Skip HLS stream testing | False (tests run by default) |

### MediaConnect Validation Options

| Option | Description | Default |
|--------|-------------|---------|
| `--validate-mediaconnect` | Enable MediaConnect flow validation | False (disabled by default) |
| `--aws-region` | AWS region (optional, auto-detected from ARN) | Auto-detected from ARN |
| `--aws-profile` | AWS profile name (optional) | None |
| `--metric-hours` | Hours of CloudWatch metrics to analyze | 3 |
| `--mediaconnect-csv` | Custom CSV filename for MediaConnect results | `Validation_Report_<AMGID>_<DATE>.csv` |

---

## Examples

### Example 1: CDN Stream Testing Only
```bash
python3 main.py AMGXXXXX
```

**Output:**
- Console: Real-time progress and test results
- CSV File: `hls_test_results_YYYYMMDD_HHMMSS.csv`

### Example 2: MediaConnect Validation Only
```bash
python3 main.py AMGXXXXX --validate-mediaconnect --no-auto-test
```

**Output:**
- Console: Flow validation details (AWS region auto-detected from ARN)
- CSV File: `Validation_Report_AMGXXXXX_YYYYMMDD_HHMMSS.csv`

### Example 3: Both CDN and MediaConnect
```bash
python3 main.py AMGXXXXX --validate-mediaconnect
```

**Output:**
- Console: CDN test results + MediaConnect validation
- CSV Files: Both CDN and MediaConnect reports

### Example 4: Extended CDN Test
```bash
python3 main.py AMGXXXXX --test-duration 300 --test-timeout 30
```

Tests each stream for 5 minutes with 30-second timeout.

### Example 5: MediaConnect with Custom Metric Duration
```bash
python3 main.py AMGXXXXX --validate-mediaconnect --no-auto-test --metric-hours 6
```

Analyzes 6 hours of CloudWatch metrics instead of default 3 hours.

### Example 6: Save API Response
```bash
python3 main.py AMGXXXXX --save-json
```

Saves the full API response in addition to running tests.

### Example 7: Different AWS Region
```bash
python3 main.py AMGXXXXX --validate-mediaconnect --no-auto-test --aws-region us-west-2
```

Validates MediaConnect flows in the us-west-2 region.

---

## Understanding Results

### CDN Stream Test Results

**Status:**
- `PASS` - All tests passed ✅
- `WARNING` - Minor issues detected ⚠️
- `FAIL` - Critical issues detected ❌

**MSN Status:**
- `LIVE` - Stream is updating normally ✅
- `FROZEN` - Stream not updating ❌
- `LOOP` - Stream is repeating content ⚠️
- `ERROR` - Unable to determine status ❌

**Quality Checks:**
- `YES` - Issue detected
- `NO` - No issues found

**CDN CSV Columns:**
- HLS URL, Status, MSN Status, Audio Silence, Audio Distortion, Black Frames, Freeze Frames, Error

### MediaConnect Validation Results

**Flow Status:**
- `ACTIVE` - Flow is enabled and running ✅
- `STANDBY` - Flow is in standby mode ⚠️
- Other states - Flow may have issues ❌

**Connection Status:**
- `CONNECTED` - Source is connected and sending data ✅
- `DISCONNECTED` - Source is not connected ❌
- `UNKNOWN` - Unable to determine status ❓

**Bitrate Stable:**
- `Yes` - No significant bitrate fluctuations ✅
- `No` - Bitrate drops detected ⚠️

**MediaConnect CSV Columns:**
- AMGID, Flow Name, Flow ARN, Flow Status, Entitlement Names, Entitlement Statuses, Bitrate Stable, Recovered Packets, Lost Packets, Connection Status

---

## Performance

**Test Duration:** ~5-10 minutes for 10 streams (default settings)

**Parallel Processing:** Tests 5 streams simultaneously for faster results

**Analysis Duration:** Each stream analyzed for 60 seconds using FFmpeg

---

## Technical Details

### How CDN Testing Works

1. **Fetch Deliveries**: Connects to CP-Flows API with Bearer token
2. **Extract URLs**: Filters by AMGID, prioritizes stream_url, falls back to CNAME conversion
3. **Test Streams**: Runs parallel quality checks (5 streams at a time)
4. **Generate Report**: Saves comprehensive results to CSV

### How MediaConnect Validation Works

1. **Extract ARNs**: Filters deliveries by AMGID and extracts MediaConnect Flow ARNs
2. **AWS Connection**: Uses boto3 to connect to AWS MediaConnect and CloudWatch
3. **Validate Flows**: Checks flow status, source, outputs, entitlements
4. **Analyze Metrics**: Fetches CloudWatch metrics (bitrate, packet loss, connection status)
5. **Generate Report**: Saves validation results to CSV

### API Configuration

**API URL:** `https://bxp-playouts.amagiengg.io`  
**Token:** `You can get from the BOSS Team`  
**Endpoint:** `/api/v1/delivery_views/deliveries`

### FFmpeg Analysis

The tool uses FFmpeg for all quality checks:

**Audio Analysis (60 seconds per segment):**
- Silence detection: `silencedetect=noise=-50dB:d=2.0`
- Distortion: `astats` filter for peak levels, DC offset, RMS

**Video Analysis (60 seconds per segment):**
- Black frames: `blackdetect=d=0.5:pix_th=0.10`
- Freeze frames: `freezedetect=n=-60dB:d=2`
- Bitrate validation: Using FFprobe to check valid bitrate values

---

## Troubleshooting

### Issue: "Cannot access manifest"
**Solution:** Check if the stream URL is correct and the stream is published.

### Issue: No deliveries found
**Solution:** Verify the AMGID exists and has active deliveries.

### Issue: FFmpeg not found
**Solution:** Install FFmpeg (required for the tool to work). See Installation section above.

### Issue: Tests timing out
**Solution:** Increase timeout: `--test-timeout 30`

### Issue: All streams showing errors
**Solution:** Check your network connectivity and firewall settings.

---

## Notes

- The tool automatically creates a temporary JSON file for testing and deletes it after completion
- Tests run in parallel (5 streams at a time) for efficiency
- All quality checks require FFmpeg - the tool will not work without it
- Results are appended to timestamped CSV files
- If `stream_url` is not present in API response, the tool will convert `cname` to HLS URL
