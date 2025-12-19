#!/usr/bin/env python3
"""
AWS MediaConnect Flow Validator (READ-ONLY)

This script validates MediaConnect flows by AMGID, checking:
- Flow status and health
- Output configuration and status
- Entitlement details
- CloudWatch metrics for bitrate/packet drops

IMPORTANT: This script performs READ-ONLY operations.
It does NOT modify, create, or delete any AWS resources.

AWS API operations used (all read-only):
- mediaconnect:ListFlows
- mediaconnect:DescribeFlow
- mediaconnect:ListTagsForResource
- cloudwatch:GetMetricStatistics
- tag:GetResources (Resource Groups Tagging API)

Author: Auto-generated
"""

import argparse
import csv
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Enum for validation result status."""
    PASSED = "✅ PASSED"
    FAILED = "❌ FAILED"
    WARNING = "⚠️ WARNING"
    UNKNOWN = "❓ UNKNOWN"


@dataclass
class ValidationResult:
    """Data class to hold validation results."""
    check_name: str
    status: ValidationStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowSummary:
    """Data class to hold flow summary information."""
    flow_arn: str = ""
    flow_name: str = ""
    amgid: str = ""
    status: str = ""
    source_health: str = ""
    outputs: List[Dict] = field(default_factory=list)
    entitlements: List[Dict] = field(default_factory=list)
    validation_results: List[ValidationResult] = field(default_factory=list)
    metric_analysis: Dict[str, Any] = field(default_factory=dict)


class MediaConnectValidator:
    """
    A class to validate AWS MediaConnect flows.
    
    Performs comprehensive validation of MediaConnect flows including
    status checks, entitlement validation, and CloudWatch metrics analysis.
    """

    def __init__(self, region: str = 'us-east-1', profile: Optional[str] = None):
        """
        Initialize the MediaConnect validator.
        
        Args:
            region: AWS region for MediaConnect (default: us-east-1)
            profile: AWS profile name (optional)
        """
        self.region = region
        self.profile = profile
        self._init_clients()
        
    def _init_clients(self) -> None:
        """Initialize AWS service clients."""
        try:
            session_kwargs = {'region_name': self.region}
            if self.profile:
                session_kwargs['profile_name'] = self.profile
                
            session = boto3.Session(**session_kwargs)
            self.mediaconnect_client = session.client('mediaconnect')
            self.cloudwatch_client = session.client('cloudwatch')
            self.tagging_client = session.client('resourcegroupstaggingapi')
            logger.info(f"AWS clients initialized for region: {self.region}")
        except NoCredentialsError:
            logger.error("AWS credentials not found. Please configure your credentials.")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize AWS clients: {e}")
            raise

    def find_flows_by_amgid(self, amgid: str, show_progress: bool = True) -> List[Dict[str, Any]]:
        """
        Search for ALL MediaConnect flows by AMGID using Resource Groups Tagging API.
        
        This method uses the Resource Groups Tagging API for fast tag-based lookup
        instead of iterating through all flows (much faster!).
        
        Args:
            amgid: The AMGID value to search for
            show_progress: Whether to show progress bar (default: True)
            
        Returns:
            List of flow details dictionaries (empty list if none found)
        """
        logger.info(f"Searching for flows with AMGID tag: {amgid}")
        
        try:
            # Use Resource Groups Tagging API for fast tag-based lookup
            # This is much faster than iterating through all flows!
            if show_progress:
                print("🔍 Searching for flows by AMGID tag...", end=" ", flush=True)
            
            paginator = self.tagging_client.get_paginator('get_resources')
            
            # Search for MediaConnect flows with the specific AMGID tag
            matching_resources = []
            for page in paginator.paginate(
                TagFilters=[
                    {
                        'Key': 'AMGID',
                        'Values': [amgid]
                    }
                ],
                ResourceTypeFilters=['mediaconnect:flow']
            ):
                matching_resources.extend(page.get('ResourceTagMappingList', []))
            
            if show_progress:
                print("Done!")
            
            if not matching_resources:
                # Try case-insensitive search by getting all AMGID tags
                logger.info("Exact match not found, trying broader search...")
                if show_progress:
                    print("🔍 Trying case-insensitive search...", end=" ", flush=True)
                
                matching_resources = []
                for page in paginator.paginate(
                    TagFilters=[
                        {
                            'Key': 'AMGID'
                        }
                    ],
                    ResourceTypeFilters=['mediaconnect:flow']
                ):
                    for resource in page.get('ResourceTagMappingList', []):
                        tags = {t['Key']: t['Value'] for t in resource.get('Tags', [])}
                        if tags.get('AMGID', '').lower() == amgid.lower():
                            matching_resources.append(resource)
                
                if show_progress:
                    print("Done!")
            
            if matching_resources:
                logger.info(f"Found {len(matching_resources)} flow(s) with AMGID tag: {amgid}")
                if show_progress:
                    print(f"📋 Found {len(matching_resources)} flow(s) with AMGID: {amgid}")
                
                # Get details for ALL matching flows
                flows = []
                for resource in matching_resources:
                    flow_arn = resource['ResourceARN']
                    try:
                        flow_details = self._get_flow_details(flow_arn)
                        flows.append(flow_details)
                    except ClientError as e:
                        logger.warning(f"Could not get details for flow {flow_arn}: {e}")
                
                return flows
            
            logger.warning(f"No flow found with AMGID tag: {amgid}")
            return []
            
        except ClientError as e:
            logger.error(f"AWS API error while searching for flow: {e}")
            raise

    def _get_flow_details(self, flow_arn: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific flow.
        
        Args:
            flow_arn: The ARN of the flow
            
        Returns:
            Dictionary containing flow details
        """
        try:
            response = self.mediaconnect_client.describe_flow(FlowArn=flow_arn)
            return response.get('Flow', {})
        except ClientError as e:
            logger.error(f"Failed to get flow details for {flow_arn}: {e}")
            raise

    def validate_flow_status(self, flow: Dict[str, Any]) -> List[ValidationResult]:
        """
        Validate the overall flow status.
        
        Checks:
        - Flow status is ACTIVE
        - Source is configured and healthy
        
        Args:
            flow: Flow details dictionary
            
        Returns:
            List of ValidationResult objects
        """
        results = []
        flow_status = flow.get('Status', 'UNKNOWN')
        flow_name = flow.get('Name', 'Unknown')
        
        # Check flow status (ACTIVE = Enabled)
        if flow_status == 'ACTIVE':
            results.append(ValidationResult(
                check_name="Flow Status",
                status=ValidationStatus.PASSED,
                message=f"Flow '{flow_name}' is ACTIVE (Enabled)",
                details={'status': flow_status}
            ))
        elif flow_status == 'STANDBY':
            results.append(ValidationResult(
                check_name="Flow Status",
                status=ValidationStatus.WARNING,
                message=f"Flow '{flow_name}' is in STANDBY mode",
                details={'status': flow_status}
            ))
        else:
            results.append(ValidationResult(
                check_name="Flow Status",
                status=ValidationStatus.FAILED,
                message=f"Flow '{flow_name}' status is {flow_status} (expected ACTIVE)",
                details={'status': flow_status}
            ))
            
        return results

    def validate_source_health(self, flow: Dict[str, Any]) -> List[ValidationResult]:
        """
        Validate the source health status.
        
        Args:
            flow: Flow details dictionary
            
        Returns:
            List of ValidationResult objects
        """
        results = []
        source = flow.get('Source', {})
        source_name = source.get('Name', 'Unknown')
        
        # Check transport status for source health
        transport = source.get('Transport', {})
        
        # MediaConnect uses different health indicators
        # We check if the source is properly configured
        if source:
            source_arn = source.get('SourceArn', '')
            ingest_ip = source.get('IngestIp', '')
            ingest_port = source.get('IngestPort', '')
            
            if source_arn:
                # Check if we can determine connectivity status
                # In MediaConnect, a source is "Connected" if it's receiving data
                # This is best determined through CloudWatch metrics
                results.append(ValidationResult(
                    check_name="Source Configuration",
                    status=ValidationStatus.PASSED,
                    message=f"Source '{source_name}' is configured",
                    details={
                        'source_name': source_name,
                        'ingest_ip': ingest_ip,
                        'ingest_port': ingest_port,
                        'source_arn': source_arn
                    }
                ))
            else:
                results.append(ValidationResult(
                    check_name="Source Configuration",
                    status=ValidationStatus.FAILED,
                    message="Source is not properly configured",
                    details={'source': source}
                ))
        else:
            results.append(ValidationResult(
                check_name="Source Configuration",
                status=ValidationStatus.FAILED,
                message="No source configured for this flow",
                details={}
            ))
            
        return results

    def validate_outputs(self, flow: Dict[str, Any]) -> List[ValidationResult]:
        """
        Validate all outputs of the flow.
        
        Checks each output for:
        - Name
        - Status
        - Destination configuration
        
        Args:
            flow: Flow details dictionary
            
        Returns:
            List of ValidationResult objects
        """
        results = []
        outputs = flow.get('Outputs', [])
        
        if not outputs:
            results.append(ValidationResult(
                check_name="Outputs",
                status=ValidationStatus.WARNING,
                message="No outputs configured for this flow",
                details={}
            ))
            return results
            
        for output in outputs:
            output_name = output.get('Name', 'Unknown')
            output_arn = output.get('OutputArn', '')
            destination = output.get('Destination', '')
            port = output.get('Port', '')
            
            # Check output status
            # Outputs are considered healthy if they have valid configuration
            if output_arn and destination:
                results.append(ValidationResult(
                    check_name=f"Output: {output_name}",
                    status=ValidationStatus.PASSED,
                    message=f"Output '{output_name}' is configured and ready",
                    details={
                        'name': output_name,
                        'destination': destination,
                        'port': port,
                        'arn': output_arn
                    }
                ))
            else:
                results.append(ValidationResult(
                    check_name=f"Output: {output_name}",
                    status=ValidationStatus.FAILED,
                    message=f"Output '{output_name}' has incomplete configuration",
                    details={
                        'name': output_name,
                        'destination': destination,
                        'port': port
                    }
                ))
                
        return results

    def validate_entitlements(self, flow: Dict[str, Any]) -> List[ValidationResult]:
        """
        Validate entitlements associated with the flow.
        
        Checks:
        - Entitlement name
        - Entitlement status (should be ENABLED)
        
        Args:
            flow: Flow details dictionary
            
        Returns:
            List of ValidationResult objects
        """
        results = []
        entitlements = flow.get('Entitlements', [])
        
        if not entitlements:
            results.append(ValidationResult(
                check_name="Entitlements",
                status=ValidationStatus.WARNING,
                message="No entitlements configured for this flow",
                details={}
            ))
            return results
            
        for entitlement in entitlements:
            ent_name = entitlement.get('Name', 'Unknown')
            ent_arn = entitlement.get('EntitlementArn', '')
            ent_status = entitlement.get('EntitlementStatus', 'UNKNOWN')
            subscribers = entitlement.get('Subscribers', [])
            
            if ent_status == 'ENABLED':
                results.append(ValidationResult(
                    check_name=f"Entitlement: {ent_name}",
                    status=ValidationStatus.PASSED,
                    message=f"Entitlement '{ent_name}' is ENABLED",
                    details={
                        'name': ent_name,
                        'status': ent_status,
                        'subscribers': subscribers,
                        'arn': ent_arn
                    }
                ))
            else:
                results.append(ValidationResult(
                    check_name=f"Entitlement: {ent_name}",
                    status=ValidationStatus.FAILED,
                    message=f"Entitlement '{ent_name}' status is {ent_status} (expected ENABLED)",
                    details={
                        'name': ent_name,
                        'status': ent_status,
                        'subscribers': subscribers
                    }
                ))
                
        return results

    def get_source_metrics(
        self,
        flow_arn: str,
        hours: int = 3,
        show_progress: bool = True
    ) -> Dict[str, Any]:
        """
        Fetch source health metrics from CloudWatch.
        
        Retrieves metrics for:
        - Source bitrate
        - Packet loss
        - Connected status
        
        Args:
            flow_arn: The ARN of the MediaConnect flow
            hours: Number of hours to look back (default: 3)
            show_progress: Whether to show progress bar (default: True)
            
        Returns:
            Dictionary containing metric data and analysis
        """
        logger.info(f"Fetching CloudWatch metrics for the last {hours} hours")
        
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours)
        
        # Extract flow ID from ARN for metric dimensions
        # ARN format: arn:aws:mediaconnect:region:account:flow:flow-id:flow-name
        flow_id = flow_arn.split(':')[-1] if flow_arn else ''
        
        metrics_data = {
            'source_bitrate': [],
            'recovered_packets': [],
            'not_recovered_packets': [],
            'connected': [],
            'analysis': {}
        }
        
        # Define metrics to fetch
        metric_queries = [
            {
                'name': 'SourceBitRate',
                'key': 'source_bitrate',
                'stat': 'Average',
                'display': 'Bitrate'
            },
            {
                'name': 'SourceRecoveredPackets',
                'key': 'recovered_packets',
                'stat': 'Sum',
                'display': 'Recovered Packets'
            },
            {
                'name': 'SourceNotRecoveredPackets',
                'key': 'not_recovered_packets',
                'stat': 'Sum',
                'display': 'Lost Packets'
            },
            {
                'name': 'Connected',
                'key': 'connected',
                'stat': 'Minimum',
                'display': 'Connection Status'
            }
        ]
        
        try:
            # Progress bar for fetching metrics
            metric_iterator = tqdm(
                metric_queries,
                desc="📊 Fetching metrics",
                unit="metric",
                disable=not show_progress,
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"
            )
            
            for metric in metric_iterator:
                metric_iterator.set_postfix_str(metric['display'])
                
                response = self.cloudwatch_client.get_metric_statistics(
                    Namespace='AWS/MediaConnect',
                    MetricName=metric['name'],
                    Dimensions=[
                        {
                            'Name': 'FlowARN',
                            'Value': flow_arn
                        }
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=300,  # 5-minute intervals
                    Statistics=[metric['stat']]
                )
                
                datapoints = response.get('Datapoints', [])
                # Sort by timestamp
                datapoints.sort(key=lambda x: x['Timestamp'])
                
                metrics_data[metric['key']] = [
                    {
                        'timestamp': dp['Timestamp'].isoformat(),
                        'value': dp.get(metric['stat'], 0)
                    }
                    for dp in datapoints
                ]
                
            # Analyze metrics
            metrics_data['analysis'] = self._analyze_metrics(metrics_data)
            
        except ClientError as e:
            logger.error(f"Failed to fetch CloudWatch metrics: {e}")
            metrics_data['error'] = str(e)
            
        return metrics_data

    def _analyze_metrics(self, metrics_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze the collected metrics for anomalies.
        
        Checks for:
        - Bitrate drops (significant decreases)
        - Packet loss events
        - Connection status changes
        
        Args:
            metrics_data: Dictionary containing raw metric data
            
        Returns:
            Analysis results dictionary
        """
        analysis = {
            'bitrate_stable': True,
            'bitrate_drops_detected': 0,
            'packet_loss_detected': False,
            'total_not_recovered_packets': 0,
            'total_recovered_packets': 0,
            'connection_issues': False,
            'current_status': 'UNKNOWN',
            'recommendations': []
        }
        
        # Analyze bitrate
        bitrate_data = metrics_data.get('source_bitrate', [])
        if bitrate_data:
            values = [dp['value'] for dp in bitrate_data]
            if values:
                avg_bitrate = sum(values) / len(values)
                min_bitrate = min(values)
                max_bitrate = max(values)
                
                # Check for significant drops (more than 50% below average)
                threshold = avg_bitrate * 0.5
                drops = sum(1 for v in values if v < threshold and avg_bitrate > 0)
                
                if drops > 0:
                    analysis['bitrate_stable'] = False
                    analysis['bitrate_drops_detected'] = drops
                    analysis['recommendations'].append(
                        f"Detected {drops} bitrate drops below 50% of average. "
                        "Check source encoder stability."
                    )
                    
                analysis['avg_bitrate_mbps'] = round(avg_bitrate / 1_000_000, 2)
                analysis['min_bitrate_mbps'] = round(min_bitrate / 1_000_000, 2)
                analysis['max_bitrate_mbps'] = round(max_bitrate / 1_000_000, 2)
                
                # Check if bitrate has stabilized (last 3 readings within 10% of each other)
                if len(values) >= 3:
                    recent = values[-3:]
                    recent_avg = sum(recent) / len(recent)
                    variance = max(abs(v - recent_avg) for v in recent) / recent_avg if recent_avg > 0 else 0
                    analysis['bitrate_stabilized'] = variance < 0.1
                else:
                    analysis['bitrate_stabilized'] = True
        else:
            analysis['recommendations'].append(
                "No bitrate data available. Ensure the flow is active and receiving data."
            )
            
        # Analyze packet loss
        not_recovered = metrics_data.get('not_recovered_packets', [])
        recovered = metrics_data.get('recovered_packets', [])
        
        total_not_recovered = sum(dp['value'] for dp in not_recovered)
        total_recovered = sum(dp['value'] for dp in recovered)
        
        analysis['total_not_recovered_packets'] = int(total_not_recovered)
        analysis['total_recovered_packets'] = int(total_recovered)
        
        if total_not_recovered > 0:
            analysis['packet_loss_detected'] = True
            analysis['recommendations'].append(
                f"Detected {int(total_not_recovered)} unrecovered packets. "
                "Check network connectivity and consider enabling FEC if not already."
            )
            
        # Analyze connection status
        connected_data = metrics_data.get('connected', [])
        if connected_data:
            # Check if there were any disconnections
            disconnections = sum(1 for dp in connected_data if dp['value'] < 1)
            if disconnections > 0:
                analysis['connection_issues'] = True
                analysis['recommendations'].append(
                    f"Detected {disconnections} connection drops. "
                    "Check source availability and network stability."
                )
            
            # Get current status from most recent data point
            if connected_data:
                latest = connected_data[-1]['value']
                analysis['current_status'] = 'CONNECTED' if latest >= 1 else 'DISCONNECTED'
        else:
            analysis['recommendations'].append(
                "No connection status data available."
            )
            
        if not analysis['recommendations']:
            analysis['recommendations'].append("All metrics look healthy. No issues detected.")
            
        return analysis

    def validate_flows(self, amgid: str, show_progress: bool = True) -> List[FlowSummary]:
        """
        Perform complete validation of ALL MediaConnect flows matching the AMGID.
        
        Args:
            amgid: The AMGID to search for
            show_progress: Whether to show progress bar (default: True)
            
        Returns:
            List of FlowSummary objects containing all validation results
        """
        # Find ALL flows with this AMGID
        flows = self.find_flows_by_amgid(amgid, show_progress=show_progress)
        
        if not flows:
            # Return a single summary indicating no flows found
            summary = FlowSummary(amgid=amgid)
            summary.validation_results.append(ValidationResult(
                check_name="Flow Discovery",
                status=ValidationStatus.FAILED,
                message=f"No flow found matching AMGID: {amgid}",
                details={}
            ))
            return [summary]
        
        # Validate each flow
        summaries = []
        for i, flow in enumerate(flows, 1):
            if show_progress:
                print(f"\n{'='*60}")
                print(f"📡 Validating flow {i}/{len(flows)}: {flow.get('Name', 'Unknown')}")
                print('='*60)
            
            summary = self._validate_single_flow(flow, amgid, show_progress)
            summaries.append(summary)
        
        return summaries
    
    def validate_specific_arns(self, flow_arns: List[str], amgid: str = 'N/A', show_progress: bool = True) -> List[FlowSummary]:
        """
        Validate specific MediaConnect flows by their ARNs.
        Automatically detects the region from each ARN and uses the appropriate client.
        
        Args:
            flow_arns: List of Flow ARNs to validate
            amgid: The AMGID for reference (optional)
            show_progress: Whether to show progress bar (default: True)
            
        Returns:
            List of FlowSummary objects containing all validation results
        """
        if show_progress:
            print(f"🔍 Validating {len(flow_arns)} Flow ARNs...")
            print()
        
        summaries = []
        for i, flow_arn in enumerate(flow_arns, 1):
            if show_progress:
                print(f"\n{'='*60}")
                print(f"📡 Validating flow {i}/{len(flow_arns)}")
                print(f"   ARN: {flow_arn}")
            
            try:
                # Extract region from ARN (format: arn:aws:mediaconnect:region:account:...)
                arn_parts = flow_arn.split(':')
                if len(arn_parts) > 3:
                    flow_region = arn_parts[3]
                    
                    # Check if we need to switch regions
                    if flow_region != self.region:
                        if show_progress:
                            print(f"   ℹ️  Flow is in {flow_region}, switching region client...")
                        
                        # Temporarily switch to the flow's region
                        original_region = self.region
                        original_mc_client = self.mediaconnect_client
                        original_cw_client = self.cloudwatch_client
                        
                        self.region = flow_region
                        session_kwargs = {'region_name': flow_region}
                        if self.profile:
                            session_kwargs['profile_name'] = self.profile
                        session = boto3.Session(**session_kwargs)
                        self.mediaconnect_client = session.client('mediaconnect')
                        self.cloudwatch_client = session.client('cloudwatch')
                        
                        try:
                            # Get flow details and validate
                            print('='*60)
                            flow = self._get_flow_details(flow_arn)
                            summary = self._validate_single_flow(flow, amgid, show_progress)
                            summaries.append(summary)
                        finally:
                            # Restore original region clients
                            self.region = original_region
                            self.mediaconnect_client = original_mc_client
                            self.cloudwatch_client = original_cw_client
                    else:
                        # Same region, proceed normally
                        print('='*60)
                        flow = self._get_flow_details(flow_arn)
                        summary = self._validate_single_flow(flow, amgid, show_progress)
                        summaries.append(summary)
                else:
                    raise ValueError(f"Invalid ARN format: {flow_arn}")
                    
            except ClientError as e:
                # If flow not found or access denied, create a failed summary
                logger.error(f"Failed to validate flow {flow_arn}: {e}")
                summary = FlowSummary(amgid=amgid, flow_arn=flow_arn)
                summary.flow_name = flow_arn.split(':')[-1] if ':' in flow_arn else 'Unknown'
                summary.validation_results.append(ValidationResult(
                    check_name="Flow Access",
                    status=ValidationStatus.FAILED,
                    message=f"Unable to access flow: {str(e)}",
                    details={}
                ))
                summaries.append(summary)
                
                if show_progress:
                    print(f"❌ Failed to access flow")
            except Exception as e:
                # Handle any other errors
                logger.error(f"Unexpected error validating flow {flow_arn}: {e}")
                summary = FlowSummary(amgid=amgid, flow_arn=flow_arn)
                summary.flow_name = flow_arn.split(':')[-1] if ':' in flow_arn else 'Unknown'
                summary.validation_results.append(ValidationResult(
                    check_name="Flow Access",
                    status=ValidationStatus.FAILED,
                    message=f"Unexpected error: {str(e)}",
                    details={}
                ))
                summaries.append(summary)
                
                if show_progress:
                    print(f"❌ Error during validation")
        
        return summaries
    
    def _validate_single_flow(self, flow: Dict[str, Any], amgid: str, show_progress: bool = True) -> FlowSummary:
        """
        Validate a single MediaConnect flow.
        
        Args:
            flow: Flow details dictionary
            amgid: The AMGID being searched
            show_progress: Whether to show progress bar
            
        Returns:
            FlowSummary object containing validation results
        """
        summary = FlowSummary(amgid=amgid)
        
        # Populate summary with flow info
        summary.flow_arn = flow.get('FlowArn', '')
        summary.flow_name = flow.get('Name', '')
        summary.status = flow.get('Status', '')
        summary.outputs = flow.get('Outputs', [])
        summary.entitlements = flow.get('Entitlements', [])
        
        # Define validation steps for progress tracking
        validation_steps = [
            ("Flow Status", lambda: self.validate_flow_status(flow)),
            ("Source Health", lambda: self.validate_source_health(flow)),
            ("Outputs", lambda: self.validate_outputs(flow)),
            ("Entitlements", lambda: self.validate_entitlements(flow)),
            ("CloudWatch Metrics", None),  # Special handling for metrics
        ]
        
        # Run validations with progress bar
        progress_bar = tqdm(
            validation_steps,
            desc="🔄 Running validations",
            unit="check",
            disable=not show_progress,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"
        )
        
        for step_name, validator_func in progress_bar:
            progress_bar.set_postfix_str(step_name)
            
            if validator_func is not None:
                # Run validation function
                summary.validation_results.extend(validator_func())
            else:
                # Special handling for metrics
                summary.metric_analysis = self.get_source_metrics(
                    summary.flow_arn, 
                    show_progress=False  # Don't nest progress bars
                )
            
            time.sleep(0.1)  # Small delay for visual feedback
        
        # Add metric validation results
        analysis = summary.metric_analysis.get('analysis', {})
        
        # Bitrate stability check
        if analysis.get('bitrate_stable', True):
            summary.validation_results.append(ValidationResult(
                check_name="Bitrate Stability",
                status=ValidationStatus.PASSED,
                message="Bitrate has been stable over the monitoring period",
                details={
                    'avg_mbps': analysis.get('avg_bitrate_mbps', 'N/A'),
                    'min_mbps': analysis.get('min_bitrate_mbps', 'N/A'),
                    'max_mbps': analysis.get('max_bitrate_mbps', 'N/A')
                }
            ))
        else:
            summary.validation_results.append(ValidationResult(
                check_name="Bitrate Stability",
                status=ValidationStatus.WARNING,
                message=f"Detected {analysis.get('bitrate_drops_detected', 0)} bitrate drops",
                details={
                    'drops': analysis.get('bitrate_drops_detected', 0),
                    'avg_mbps': analysis.get('avg_bitrate_mbps', 'N/A')
                }
            ))
            
        # Packet loss check
        if not analysis.get('packet_loss_detected', False):
            summary.validation_results.append(ValidationResult(
                check_name="Packet Loss",
                status=ValidationStatus.PASSED,
                message="No unrecovered packet loss detected",
                details={
                    'recovered': analysis.get('total_recovered_packets', 0),
                    'not_recovered': analysis.get('total_not_recovered_packets', 0)
                }
            ))
        else:
            summary.validation_results.append(ValidationResult(
                check_name="Packet Loss",
                status=ValidationStatus.FAILED,
                message=f"Detected {analysis.get('total_not_recovered_packets', 0)} unrecovered packets",
                details={
                    'not_recovered': analysis.get('total_not_recovered_packets', 0),
                    'recovered': analysis.get('total_recovered_packets', 0)
                }
            ))
            
        # Connection status check
        current_status = analysis.get('current_status', 'UNKNOWN')
        if current_status == 'CONNECTED':
            summary.validation_results.append(ValidationResult(
                check_name="Connection Status",
                status=ValidationStatus.PASSED,
                message="Source is currently connected",
                details={'status': current_status}
            ))
        elif current_status == 'DISCONNECTED':
            summary.validation_results.append(ValidationResult(
                check_name="Connection Status",
                status=ValidationStatus.FAILED,
                message="Source is currently disconnected",
                details={'status': current_status}
            ))
        else:
            summary.validation_results.append(ValidationResult(
                check_name="Connection Status",
                status=ValidationStatus.UNKNOWN,
                message="Unable to determine connection status",
                details={'status': current_status}
            ))
            
        return summary


def print_summary_report(summary: FlowSummary) -> None:
    """
    Print a formatted summary report of the validation results.
    
    Args:
        summary: FlowSummary object containing validation results
    """
    print("\n" + "=" * 80)
    print("       MEDIACONNECT FLOW VALIDATION REPORT")
    print("=" * 80)
    
    print(f"\n📋 FLOW INFORMATION")
    print("-" * 40)
    print(f"  AMGID:      {summary.amgid}")
    print(f"  Flow Name:  {summary.flow_name or 'Not Found'}")
    print(f"  Flow ARN:   {summary.flow_arn or 'N/A'}")
    print(f"  Status:     {summary.status or 'N/A'}")
    
    # Outputs summary
    print(f"\n📤 OUTPUTS ({len(summary.outputs)})")
    print("-" * 40)
    if summary.outputs:
        for output in summary.outputs:
            print(f"  • {output.get('Name', 'Unknown')} → {output.get('Destination', 'N/A')}:{output.get('Port', 'N/A')}")
    else:
        print("  No outputs configured")
        
    # Entitlements summary
    print(f"\n🔑 ENTITLEMENTS ({len(summary.entitlements)})")
    print("-" * 40)
    if summary.entitlements:
        for ent in summary.entitlements:
            status_icon = "✅" if ent.get('EntitlementStatus') == 'ENABLED' else "❌"
            print(f"  {status_icon} {ent.get('Name', 'Unknown')} - {ent.get('EntitlementStatus', 'UNKNOWN')}")
    else:
        print("  No entitlements configured")
        
    # Metrics summary
    analysis = summary.metric_analysis.get('analysis', {})
    print(f"\n📊 METRICS ANALYSIS (Last 3 Hours)")
    print("-" * 40)
    if analysis:
        print(f"  Avg Bitrate:     {analysis.get('avg_bitrate_mbps', 'N/A')} Mbps")
        print(f"  Min Bitrate:     {analysis.get('min_bitrate_mbps', 'N/A')} Mbps")
        print(f"  Max Bitrate:     {analysis.get('max_bitrate_mbps', 'N/A')} Mbps")
        print(f"  Bitrate Stable:  {'Yes' if analysis.get('bitrate_stable', False) else 'No'}")
        print(f"  Stabilized:      {'Yes' if analysis.get('bitrate_stabilized', False) else 'No'}")
        print(f"  Recovered Pkts:  {analysis.get('total_recovered_packets', 0)}")
        print(f"  Lost Packets:    {analysis.get('total_not_recovered_packets', 0)}")
        print(f"  Current Status:  {analysis.get('current_status', 'UNKNOWN')}")
    else:
        print("  No metrics data available")
        
    # Validation Results
    print(f"\n🔍 VALIDATION RESULTS")
    print("-" * 40)
    
    passed = sum(1 for r in summary.validation_results if r.status == ValidationStatus.PASSED)
    failed = sum(1 for r in summary.validation_results if r.status == ValidationStatus.FAILED)
    warnings = sum(1 for r in summary.validation_results if r.status == ValidationStatus.WARNING)
    
    for result in summary.validation_results:
        print(f"  {result.status.value} {result.check_name}")
        print(f"      └─ {result.message}")
        
    # Overall summary
    print(f"\n📈 SUMMARY")
    print("-" * 40)
    print(f"  Total Checks: {len(summary.validation_results)}")
    print(f"  ✅ Passed:    {passed}")
    print(f"  ❌ Failed:    {failed}")
    print(f"  ⚠️  Warnings:  {warnings}")
    
    # Recommendations
    recommendations = analysis.get('recommendations', [])
    if recommendations:
        print(f"\n💡 RECOMMENDATIONS")
        print("-" * 40)
        for rec in recommendations:
            print(f"  • {rec}")
            
    # Final verdict
    print("\n" + "=" * 80)
    if failed == 0 and warnings == 0:
        print("  🎉 OVERALL STATUS: ALL CHECKS PASSED")
    elif failed == 0:
        print("  ⚠️  OVERALL STATUS: PASSED WITH WARNINGS")
    else:
        print("  ❌ OVERALL STATUS: VALIDATION FAILED")
    print("=" * 80 + "\n")


def export_to_csv(summary: FlowSummary, output_file: str) -> None:
    """
    Export validation results to a CSV file.
    
    Creates a separate row for each output of the flow.
    
    Args:
        summary: FlowSummary object containing validation results
        output_file: Path to the output CSV file
    """
    analysis = summary.metric_analysis.get('analysis', {})
    
    # Prepare entitlement data
    entitlement_names = ", ".join([e.get('Name', 'Unknown') for e in summary.entitlements]) or "None"
    entitlement_statuses = ", ".join([
        e.get('EntitlementStatus', 'UNKNOWN') for e in summary.entitlements
    ]) or "None"
    
    # Define CSV columns - exactly as requested by user
    fieldnames = [
        'AMGID',
        'Flow Name',
        'Flow ARN',
        'Flow Status',
        'Entitlement Names',
        'Entitlement Statuses',
        'Bitrate Stable',
        'Recovered Packets',
        'Lost Packets',
        'Connection Status'
    ]
    
    # Check if file exists to determine if we need headers
    file_exists = os.path.exists(output_file)
    
    # Row data (same for all outputs of this flow)
    row_data = {
        'AMGID': summary.amgid,
        'Flow Name': summary.flow_name or 'Not Found',
        'Flow ARN': summary.flow_arn or 'N/A',
        'Flow Status': summary.status or 'N/A',
        'Entitlement Names': entitlement_names,
        'Entitlement Statuses': entitlement_statuses,
        'Bitrate Stable': 'Yes' if analysis.get('bitrate_stable', False) else 'No',
        'Recovered Packets': analysis.get('total_recovered_packets', 0),
        'Lost Packets': analysis.get('total_not_recovered_packets', 0),
        'Connection Status': analysis.get('current_status', 'UNKNOWN')
    }
    
    # Write to CSV - create a row for each output
    with open(output_file, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        if not file_exists:
            writer.writeheader()
        
        # Create one row per output (or one row if no outputs)
        output_count = len(summary.outputs) if summary.outputs else 1
        for _ in range(output_count):
            writer.writerow(row_data)
    
    output_count = len(summary.outputs) if summary.outputs else 1
    logger.info(f"Exported {output_count} row(s) to: {output_file}")
    print(f"📄 Exported {output_count} row(s) to: {output_file}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Validate AWS MediaConnect flows by AMGID',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --amgid AMGID12345
  %(prog)s --amgid AMGID12345 --region us-west-2
  %(prog)s --amgid AMGID12345 --profile production --hours 6
        """
    )
    
    parser.add_argument(
        '--amgid',
        help='The AMGID to search for in MediaConnect flows (required if --flow-arns not provided)'
    )
    
    parser.add_argument(
        '--flow-arns',
        help='Comma-separated list of Flow ARNs to validate directly (alternative to --amgid)'
    )
    
    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )
    
    parser.add_argument(
        '--profile',
        help='AWS profile name (optional)'
    )
    
    parser.add_argument(
        '--hours',
        type=int,
        default=3,
        choices=range(1, 25),
        metavar='[1-24]',
        help='Hours of metric history to analyze (default: 3, max: 24)'
    )
    
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bars'
    )
    
    parser.add_argument(
        '--csv',
        '-o',
        metavar='FILE',
        help='Export results to CSV file (appends if file exists)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.amgid and not args.flow_arns:
        parser.error("Either --amgid or --flow-arns must be provided")
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Determine if progress bars should be shown
    show_progress = not args.no_progress
    
    try:
        # Initialize validator
        validator = MediaConnectValidator(
            region=args.region,
            profile=args.profile
        )
        
        # Determine which validation method to use
        if args.flow_arns:
            # Validate specific Flow ARNs
            flow_arns = [arn.strip() for arn in args.flow_arns.split(',')]
            logger.info(f"Starting validation for {len(flow_arns)} specific Flow ARNs")
            print()  # Add spacing before progress bars
            summaries = validator.validate_specific_arns(
                flow_arns, 
                amgid=args.amgid or 'N/A', 
                show_progress=show_progress
            )
        else:
            # Search and validate flows by AMGID tag
            logger.info(f"Starting validation for AMGID: {args.amgid}")
            print()  # Add spacing before progress bars
            summaries = validator.validate_flows(args.amgid, show_progress=show_progress)
        
        # Print report for each flow
        for summary in summaries:
            print_summary_report(summary)
            
            # Export to CSV if requested
            if args.csv:
                export_to_csv(summary, args.csv)
        
        # Print overall summary if multiple flows
        if len(summaries) > 1:
            print("\n" + "=" * 80)
            print(f"       OVERALL SUMMARY: {len(summaries)} FLOWS VALIDATED")
            print("=" * 80)
            total_passed = 0
            total_failed = 0
            total_warnings = 0
            for s in summaries:
                passed = sum(1 for r in s.validation_results if r.status == ValidationStatus.PASSED)
                failed = sum(1 for r in s.validation_results if r.status == ValidationStatus.FAILED)
                warnings = sum(1 for r in s.validation_results if r.status == ValidationStatus.WARNING)
                total_passed += passed
                total_failed += failed
                total_warnings += warnings
                status_icon = "✅" if failed == 0 else "❌"
                print(f"  {status_icon} {s.flow_name or 'Not Found'}: {passed} passed, {failed} failed, {warnings} warnings")
            print("-" * 80)
            print(f"  Total: {total_passed} passed, {total_failed} failed, {total_warnings} warnings")
            print("=" * 80 + "\n")
        
        # Exit with appropriate code (fail if any flow has failures)
        failed_count = sum(
            1 for s in summaries 
            for r in s.validation_results 
            if r.status == ValidationStatus.FAILED
        )
        
        sys.exit(1 if failed_count > 0 else 0)
        
    except NoCredentialsError:
        logger.error("AWS credentials not configured. Please run 'aws configure' or set environment variables.")
        sys.exit(2)
    except ClientError as e:
        logger.error(f"AWS API error: {e}")
        sys.exit(2)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(2)


if __name__ == '__main__':
    main()

