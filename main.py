#!/usr/bin/env python3
import requests
import json
from datetime import datetime
import sys
import subprocess
import os
import argparse
import tempfile
import boto3
from botocore.exceptions import ClientError


# API Configuration
API_BASE_URL = "https://bxp-playouts.amagiengg.io"
API_ENDPOINT = "/api/v1/delivery_views/deliveries"
OUTPUT_FILE = "deliveries_output.json"


def get_secret_from_aws(secret_name: str, region_name: str = 'ap-south-1') -> str:
    """
    Retrieve secret value from AWS Secrets Manager.
    Uses IAM role credentials automatically (no access keys needed).
    
    Args:
        secret_name: Name or ARN of the secret in AWS Secrets Manager
        region_name: AWS region where secret is stored (default: ap-south-1)
        
    Returns:
        Secret value as string
        
    Raises:
        Exception if secret cannot be retrieved
    """
    print(f"🔐 Fetching secret '{secret_name}' from AWS Secrets Manager (region: {region_name})...")
    
    try:
        # Create Secrets Manager client (uses IAM role automatically)
        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name=region_name
        )
        
        # Fetch secret value
        response = client.get_secret_value(SecretId=secret_name)
        
        # Parse secret string
        if 'SecretString' in response:
            secret = response['SecretString']
            print("✓ Successfully retrieved secret from AWS Secrets Manager\n")
            
            # If it's JSON, try to parse it
            try:
                secret_dict = json.loads(secret)
                # If it's a dict with 'api_token' key, return that
                if isinstance(secret_dict, dict) and 'api_token' in secret_dict:
                    return secret_dict['api_token']
                # Otherwise return the whole dict or first value
                elif isinstance(secret_dict, dict):
                    # Return first value if dict
                    return list(secret_dict.values())[0] if secret_dict else secret
                else:
                    return secret
            except json.JSONDecodeError:
                # If not JSON, return as plain string
                return secret
        else:
            # Binary secret (unlikely for API token)
            import base64
            return base64.b64decode(response['SecretBinary']).decode('utf-8')
            
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        
        if error_code == 'ResourceNotFoundException':
            raise Exception(f"❌ Secret '{secret_name}' not found in AWS Secrets Manager (region: {region_name})")
        elif error_code == 'InvalidRequestException':
            raise Exception(f"❌ Invalid request for secret '{secret_name}': {error_msg}")
        elif error_code == 'InvalidParameterException':
            raise Exception(f"❌ Invalid parameter for secret '{secret_name}': {error_msg}")
        elif error_code == 'DecryptionFailure':
            raise Exception(f"❌ Cannot decrypt secret '{secret_name}' - check KMS permissions")
        elif error_code == 'AccessDeniedException':
            raise Exception(f"❌ Access denied to secret '{secret_name}' - check IAM role permissions")
        else:
            raise Exception(f"❌ Error retrieving secret: {error_code} - {error_msg}")
    except Exception as e:
        raise Exception(f"❌ Unexpected error retrieving secret: {str(e)}")


def fetch_deliveries(base_url, endpoint, token, params=None):
    """
    Fetch delivery details from the API.
    
    Args:
        base_url (str): Base URL of the API
        endpoint (str): API endpoint path
        token (str): Bearer token for authentication
        params (dict, optional): Query parameters for the API call
    
    Returns:
        dict: JSON response from the API
    
    Raises:
        requests.exceptions.RequestException: If the API request fails
    """
    url = f"{base_url}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print(f"Fetching deliveries from: {url}")
    if params:
        print(f"Query parameters: {params}")
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()  # Raise exception for bad status codes
        
        print(f"✓ Successfully fetched data (Status: {response.status_code})")
        return response.json()
        
    except requests.exceptions.HTTPError as e:
        print(f"✗ HTTP Error: {e}")
        print(f"Response: {response.text}")
        raise
    except requests.exceptions.ConnectionError as e:
        print(f"✗ Connection Error: {e}")
        raise
    except requests.exceptions.Timeout as e:
        print(f"✗ Timeout Error: {e}")
        raise
    except requests.exceptions.RequestException as e:
        print(f"✗ Request Error: {e}")
        raise


def save_to_json(data, filename):
    """
    Save data to a JSON file with pretty formatting.
    
    Args:
        data (dict): Data to save
        filename (str): Output filename
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Data saved to: {filename}")
        
        # Print summary statistics
        if 'deliveries' in data:
            total = data.get('total', 0)
            shown = data.get('shown', 0)
            print(f"\nSummary:")
            print(f"  Total deliveries: {total}")
            print(f"  Deliveries shown: {shown}")
            print(f"  Deliveries in file: {len(data['deliveries'])}")
        
    except IOError as e:
        print(f"✗ Error saving file: {e}")
        raise


def convert_cname_to_hls_url(cname):
    """
    Convert a cname to HLS URL by adding https:// and /playlist.m3u8.
    
    Args:
        cname (str): The cname value
    
    Returns:
        str: The HLS URL
    """
    if not cname:
        return ""
    
    # Add protocol if not present
    if not cname.startswith('http'):
        cname = f"https://{cname}"
    
    # Add playlist.m3u8 if not already present
    if not cname.endswith('.m3u8'):
        cname = f"{cname}/playlist.m3u8"
    
    return cname


def extract_mediaconnect_arns(deliveries, amgid):
    """
    Extract MediaConnect Flow ARNs and regions from deliveries for the given AMGID.
    
    MediaConnect Flow ARNs are found in the 'prev_destination_id' field.
    
    Args:
        deliveries (list): List of delivery objects
        amgid (str): Target AMG ID
    
    Returns:
        dict: Dictionary with 'arns' (list of unique Flow ARNs) and 'region' (extracted from ARN)
    """
    print(f"\n{'=' * 60}")
    print(f"Extracting MediaConnect Flow ARNs for AMGID: {amgid}")
    print('=' * 60)
    
    # Filter by AMGID
    filtered = [d for d in deliveries if d.get('amg_id') == amgid]
    print(f"✓ Found {len(filtered)} deliveries for {amgid}")
    
    if not filtered:
        print(f"⚠ Warning: No deliveries found for AMGID '{amgid}'")
        return {'arns': [], 'region': None}
    
    # Extract MediaConnect Flow ARNs
    print("\nExtracting MediaConnect Flow ARNs...")
    unique_flow_arns = set()
    extracted_region = None
    flow_count = 0
    
    for idx, delivery in enumerate(filtered, 1):
        # Look at prev_destination_id for MediaConnect Flow ARNs
        prev_dest_id = delivery.get('prev_destination_id', '')
        feed_name = delivery.get('feed_name', 'Unknown')
        
        # Check if prev_destination_id contains a MediaConnect Flow ARN
        # Flow ARN format: arn:aws:mediaconnect:region:account:flow:flow-id:flow-name
        if prev_dest_id and prev_dest_id.strip():
            arn = prev_dest_id.strip()
            
            # Verify it's a MediaConnect Flow ARN (contains :flow:)
            if arn.startswith('arn:aws:mediaconnect:') and ':flow:' in arn:
                # Only add if this is a new flow
                if arn not in unique_flow_arns:
                    unique_flow_arns.add(arn)
                    flow_count += 1
                    
                    # Extract region from ARN (it's at index 3)
                    if not extracted_region:
                        arn_parts = arn.split(':')
                        if len(arn_parts) > 3:
                            extracted_region = arn_parts[3]
                            print(f"  ℹ️  Detected AWS Region: {extracted_region}")
                    
                    # Extract flow name from ARN (last part)
                    flow_name = arn.split(':')[-1] if ':' in arn else 'Unknown'
                    print(f"  [{flow_count}] ✓ Found MediaConnect Flow: {flow_name}")
                    print(f"       Feed: {feed_name}")
    
    mediaconnect_flow_arns = sorted(list(unique_flow_arns))
    
    print(f"\n{'=' * 60}")
    print(f"MEDIACONNECT EXTRACTION SUMMARY")
    print('=' * 60)
    print(f"✓ Total deliveries processed: {len(filtered)}")
    print(f"✓ Unique MediaConnect Flow ARNs: {len(mediaconnect_flow_arns)}")
    if extracted_region:
        print(f"✓ AWS Region: {extracted_region}")
    
    if len(mediaconnect_flow_arns) == 0:
        print(f"\n⚠️  NOTE: No MediaConnect flows found for this AMGID")
    else:
        print(f"\n📋 Flow ARNs found:")
        for i, arn in enumerate(mediaconnect_flow_arns, 1):
            flow_name = arn.split(':')[-1]
            print(f"  {i}. {flow_name}")
    
    return {
        'arns': mediaconnect_flow_arns,
        'region': extracted_region or 'us-east-1'  # Fallback to default if no region found
    }


def run_mediaconnect_validator(arns, amgid, region='us-east-1', profile=None, hours=3, output_file=None, show_progress=True):
    """
    Run the MediaConnect validator script for the given ARNs.
    
    Args:
        arns (list): List of MediaConnect Flow ARNs
        amgid (str): AMG ID for reference
        region (str): AWS region (default: us-east-1)
        profile (str): AWS profile name (optional)
        hours (int): Hours of metric history to analyze (default: 3)
        output_file (str): CSV file to export results (optional)
        show_progress (bool): Whether to show progress bars (default: True)
    
    Returns:
        bool: True if validation completed successfully
    """
    validator_script = os.path.join(os.path.dirname(__file__), "mediaconnect_validator.py")
    
    if not os.path.exists(validator_script):
        print(f"\n⚠ MediaConnect validator script not found: {validator_script}")
        return False
    
    print(f"\n{'=' * 60}")
    print(f"Running MediaConnect Validation")
    print('=' * 60)
    print(f"AMGID: {amgid}")
    print(f"Flow ARNs to validate: {len(arns)}")
    print(f"Region: {region}")
    print(f"Metric History: {hours} hours")
    if output_file:
        print(f"CSV Output: {output_file}")
    print()
    
    try:
        # Build command - pass Flow ARNs directly
        arns_str = ','.join(arns)
        cmd = [
            "python3",
            validator_script,
            "--flow-arns", arns_str,
            "--amgid", amgid,
            "--region", region,
            "--hours", str(hours)
        ]
        
        if profile:
            cmd.extend(["--profile", profile])
        
        if output_file:
            cmd.extend(["--csv", output_file])
        
        if not show_progress:
            cmd.append("--no-progress")
        
        # Run the validator
        result = subprocess.run(cmd, check=False)
        
        if result.returncode == 0:
            print(f"\n✓ MediaConnect validation completed successfully")
            return True
        elif result.returncode == 1:
            print(f"\n⚠ MediaConnect validation completed with some failures")
            return False
        else:
            print(f"\n✗ MediaConnect validation encountered an error")
            return False
            
    except Exception as e:
        print(f"\n✗ Error running MediaConnect validator: {e}")
        return False


def create_hls_tester_json(cname_data, amgid):
    """
    Create temporary JSON file in format compatible with hls_tester.py
    The file will be automatically deleted after testing
    
    Args:
        cname_data (dict): Cname data with details
        amgid (str): AMG ID being processed
    
    Returns:
        str: Path to created temporary file
    """
    if not cname_data or not cname_data.get('cnames_with_details'):
        print(f"⚠ No cname data to create HLS tester file")
        return None
    
    # Convert to HLS tester format (minimal data only)
    stream_urls = []
    for entry in cname_data['cnames_with_details']:
        stream_entry = {
            "stream_url": entry['hls_url']
        }
        stream_urls.append(stream_entry)
    
    # Create the output structure (minimal)
    output_data = {
        "stream_urls": stream_urls
    }
    
    # Create temporary file
    try:
        # Create temporary file that won't be automatically deleted
        temp_fd, temp_path = tempfile.mkstemp(suffix='.json', prefix=f'hls_test_{amgid}_')
        
        # Write data to temporary file
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Created temporary test file (will be deleted after testing)")
        print(f"  Total streams to test: {len(stream_urls)}")
        return temp_path
        
    except IOError as e:
        print(f"✗ Error creating temporary file: {e}")
        return None


def run_hls_tester(json_file, duration=30, timeout=15):
    """
    Run the HLS tester script with the generated JSON file
    Automatically deletes the temporary JSON file after testing
    
    Args:
        json_file (str): Path to JSON file with stream URLs
        duration (int): Test duration per stream in seconds
        timeout (int): Request timeout in seconds
    
    Returns:
        bool: True if test completed successfully
    """
    hls_tester_script = os.path.join(os.path.dirname(__file__), "hls_tester.py")
    
    if not os.path.exists(hls_tester_script):
        print(f"\n⚠ HLS tester script not found: {hls_tester_script}")
        print(f"  Please run manually: python3 hls_tester.py --json-file {json_file}")
        # Clean up temp file even if tester script not found
        if os.path.exists(json_file):
            os.remove(json_file)
            print(f"✓ Cleaned up temporary file")
        return False
    
    print(f"\n{'=' * 60}")
    print(f"Running HLS Stream Tests")
    print('=' * 60)
    print(f"Test duration: {duration}s per stream")
    print(f"Timeout: {timeout}s")
    print(f"Parallel workers: 5 streams at a time\n")
    
    test_success = False
    try:
        # Run the HLS tester (no JSON report output, CSV only)
        # Testing 5 streams in parallel for faster execution
        cmd = [
            "python3",
            hls_tester_script,
            "--json-file", json_file,
            "--duration", str(duration),
            "--timeout", str(timeout),
            "--workers", "5"
        ]
        
        result = subprocess.run(cmd, check=False)
        
        if result.returncode == 0:
            print(f"\n✓ HLS tests completed successfully")
            test_success = True
        else:
            print(f"\n⚠ HLS tests completed with some failures")
            test_success = False
            
    except Exception as e:
        print(f"\n✗ Error running HLS tester: {e}")
        print(f"  Please run manually: python3 hls_tester.py --json-file {json_file}")
        test_success = False
    
    finally:
        # Always clean up the temporary file
        if os.path.exists(json_file):
            try:
                os.remove(json_file)
                print(f"✓ Cleaned up temporary test file")
            except Exception as e:
                print(f"⚠ Could not delete temporary file {json_file}: {e}")
    
    return test_success


def extract_cnames_by_amgid(deliveries, amgid):
    """
    Filter deliveries by AMGID and extract stream URLs.
    Priority: Use stream_url if available, otherwise convert cname to HLS URL.
    
    Args:
        deliveries (list): List of delivery objects
        amgid (str): Target AMG ID
    
    Returns:
        dict: Dictionary with stream URL information and HLS URLs
    """
    print(f"\n{'=' * 60}")
    print(f"Extracting stream URLs for AMGID: {amgid}")
    print('=' * 60)
    
    # Filter by AMGID
    print(f"Filtering deliveries for AMGID: {amgid}...")
    filtered = [d for d in deliveries if d.get('amg_id') == amgid]
    print(f"✓ Found {len(filtered)} deliveries for {amgid}")
    
    if not filtered:
        print(f"⚠ Warning: No deliveries found for AMGID '{amgid}'")
        return None
    
    # Extract stream URLs - prioritize stream_url, fallback to cname conversion
    print("\nExtracting stream URLs (prioritizing stream_url, fallback to cname)...")
    print("=" * 60)
    cnames_with_details = []
    unique_cnames = set()
    unique_hls_urls = set()
    stream_url_used_count = 0
    cname_converted_count = 0
    skipped_count = 0
    
    for idx, delivery in enumerate(filtered, 1):
        stream_url = delivery.get('stream_url', '')
        cname = delivery.get('cname', '')
        feed_name = delivery.get('feed_name', 'Unknown')
        platform = delivery.get('platform', 'Unknown')
        
        # Determine which URL to use
        hls_url = None
        url_source = None
        
        # Priority 1: Use stream_url if present and not empty
        if stream_url and stream_url.strip():
            hls_url = stream_url.strip()
            url_source = 'stream_url'
            stream_url_used_count += 1
            if stream_url_used_count <= 2:  # Show first 2 examples only
                print(f"  [{idx}] ✓ Using stream_url: {feed_name} ({platform})")
            elif stream_url_used_count == 3:
                print(f"  ... (continuing to use stream_url for remaining entries)")
        # Priority 2: Convert cname to HLS URL if stream_url is not available
        elif cname and cname.strip():
            hls_url = convert_cname_to_hls_url(cname)
            url_source = 'cname_converted'
            cname_converted_count += 1
            unique_cnames.add(cname)
            print(f"  [{idx}] ⚠️  stream_url NOT present - Using cname conversion: {feed_name} ({platform})")
            print(f"       Converted: {cname} → {hls_url}")
        else:
            # Skip entries with neither stream_url nor cname
            skipped_count += 1
            print(f"  [{idx}] ❌ SKIPPED - No stream_url or cname: {feed_name} ({platform})")
            continue
        
        unique_hls_urls.add(hls_url)
        
        cnames_with_details.append({
            'cname': cname,
            'hls_url': hls_url,
            'url_source': url_source,  # Track where the URL came from
            'feed_name': delivery.get('feed_name', ''),
            'feed_code': delivery.get('feed_code', ''),
            'platform': delivery.get('platform', ''),
            'host_url': delivery.get('host_url', ''),
            'stream_url': stream_url,
            'final_destination_type': delivery.get('final_destination_type', ''),
            'final_destination_id': delivery.get('final_destination_id', '')
        })
    
    print(f"\n{'=' * 60}")
    print(f"EXTRACTION SUMMARY")
    print('=' * 60)
    print(f"✓ Total deliveries processed: {len(filtered)}")
    print(f"✓ Successfully extracted: {len(cnames_with_details)} stream entries")
    print(f"  - {stream_url_used_count} URLs taken from stream_url field (direct)")
    print(f"  - {cname_converted_count} URLs converted from cname (stream_url missing)")
    if skipped_count > 0:
        print(f"  - {skipped_count} entries skipped (no stream_url or cname)")
    print(f"✓ Total unique HLS URLs: {len(unique_hls_urls)}")
    if cname_converted_count > 0:
        print(f"\n⚠️  NOTE: {cname_converted_count} stream(s) used cname conversion")
        print(f"   (stream_url was not present in API response)")
    
    return {
        'amgid': amgid,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_deliveries': len(filtered),
        'total_stream_entries': len(cnames_with_details),
        'stream_url_used': stream_url_used_count,
        'cname_converted': cname_converted_count,
        'skipped': skipped_count,
        'unique_cnames_count': len(unique_cnames),
        'unique_cnames': sorted(list(unique_cnames)),
        'unique_hls_urls': sorted(list(unique_hls_urls)),
        'cnames_with_details': cnames_with_details
    }


def fetch_all_deliveries(base_url, endpoint, token, base_params=None):
    """
    Fetch all deliveries using pagination.
    
    Args:
        base_url (str): Base URL of the API
        endpoint (str): API endpoint path
        token (str): Bearer token for authentication
        base_params (dict, optional): Base query parameters for filtering
    
    Returns:
        dict: Combined JSON response with all deliveries
    """
    if base_params is None:
        base_params = {}
    
    all_deliveries = []
    offset = 0
    limit = 10000  # Max results per request
    
    print("Fetching all deliveries with pagination...\n")
    
    while True:
        # Update params with current offset
        params = base_params.copy()
        params['limit'] = limit
        params['offset'] = offset
        
        # Fetch batch
        data = fetch_deliveries(base_url, endpoint, token, params)
        
        # Add deliveries to our collection
        batch_deliveries = data.get('deliveries', [])
        all_deliveries.extend(batch_deliveries)
        
        total = data.get('total', 0)
        shown = data.get('shown', 0)
        
        print(f"  Fetched {len(all_deliveries)}/{total} deliveries...")
        
        # Check if we've fetched all deliveries
        if len(all_deliveries) >= total or shown < limit:
            break
        
        # Move to next batch
        offset += limit
    
    # Return combined result
    return {
        'total': data.get('total', 0),
        'shown': len(all_deliveries),
        'deliveries': all_deliveries
    }


def main():
    """Main function to fetch and save delivery data."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Fetch delivery details from BXP Playouts API and generate HLS URLs for testing"
    )
    parser.add_argument(
        "amgid",
        help="AMG ID to filter deliveries (e.g., AMG27125)"
    )
    
    # Test mode selection (mutually exclusive)
    test_mode = parser.add_mutually_exclusive_group()
    test_mode.add_argument(
        "--cdn",
        action="store_true",
        help="Run CDN stream tests only"
    )
    test_mode.add_argument(
        "--mc",
        action="store_true",
        help="Run MediaConnect validation only"
    )
    parser.add_argument(
        "--test-duration",
        type=int,
        default=120,
        help="Duration per stream test in seconds (default: 120)"
    )
    parser.add_argument(
        "--test-timeout",
        type=int,
        default=15,
        help="Request timeout in seconds (default: 15)"
    )
    parser.add_argument(
        "--platform",
        help="Filter by platform (e.g., Roku, Sling, Fubo)"
    )
    parser.add_argument(
        "--env",
        help="Filter by environment (e.g., production)"
    )
    parser.add_argument(
        "--host-url",
        help="Filter by host URL"
    )
    parser.add_argument(
        "--feed-code",
        help="Filter by feed code"
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="Save full API response to JSON file"
    )
    parser.add_argument(
        "--save-filtered-json",
        action="store_true",
        help="Save filtered deliveries (by AMGID) to JSON file"
    )
    parser.add_argument(
        "--aws-region",
        default="us-east-1",
        help="AWS region for MediaConnect validation (default: us-east-1)"
    )
    parser.add_argument(
        "--aws-profile",
        help="AWS profile name for MediaConnect validation (optional)"
    )
    parser.add_argument(
        "--metric-hours",
        type=int,
        default=3,
        help="Hours of CloudWatch metrics to analyze for MediaConnect (default: 3)"
    )
    parser.add_argument(
        "--mediaconnect-csv",
        help="CSV file to export MediaConnect validation results"
    )
    
    # AWS Secrets Manager configuration
    parser.add_argument(
        "--secret-name",
        default="bxp_token",
        help="AWS Secrets Manager secret name for API token (default: bxp_token)"
    )
    parser.add_argument(
        "--secret-region",
        default="ap-south-1",
        help="AWS region where secret is stored (default: ap-south-1)"
    )
    
    args = parser.parse_args()
    
    # Determine which tests to run
    run_cdn = True
    run_mc = True
    
    if args.cdn:
        # CDN only
        run_cdn = True
        run_mc = False
        test_mode_str = "CDN Stream Testing"
    elif args.mc:
        # MediaConnect only
        run_cdn = False
        run_mc = True
        test_mode_str = "MediaConnect Validation"
    else:
        # Default: Both
        run_cdn = True
        run_mc = True
        test_mode_str = "CDN & MediaConnect Validation"
    
    print("=" * 60)
    print(f"{test_mode_str}")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Target AMGID: {args.amgid}")
    if run_cdn and run_mc:
        print(f"Mode: Both CDN and MediaConnect")
    elif run_cdn:
        print(f"Mode: CDN Only")
    elif run_mc:
        print(f"Mode: MediaConnect Only")
    print()
    
    try:
        # Fetch Bearer Token from AWS Secrets Manager
        try:
            bearer_token = get_secret_from_aws(
                secret_name=args.secret_name,
                region_name=args.secret_region
            )
        except Exception as e:
            print(f"\n{str(e)}")
            print("\n⚠️  Make sure:")
            print(f"   1. Secret '{args.secret_name}' exists in AWS Secrets Manager (region: {args.secret_region})")
            print("   2. IAM role has 'secretsmanager:GetSecretValue' permission")
            print("   3. IAM role has 'kms:Decrypt' permission (if secret is encrypted)")
            print("   4. EC2 instance/environment has IAM role attached")
            print("\n💡 To create the secret:")
            print(f"   aws secretsmanager create-secret \\")
            print(f"       --name {args.secret_name} \\")
            print(f"       --secret-string 'your-bearer-token' \\")
            print(f"       --region {args.secret_region}")
            sys.exit(1)
        
        # Configuration
        target_amgid = args.amgid
        test_duration = args.test_duration
        test_timeout = args.test_timeout
        
        # Query parameters for filtering
        base_params = {
            'amgid': target_amgid,  # Filter by AMG ID
        }
        
        # Add optional filters if provided
        if args.platform:
            base_params['platform'] = args.platform
            print(f"Filter: Platform = {args.platform}")
        
        if args.env:
            base_params['env'] = args.env
            print(f"Filter: Environment = {args.env}")
        
        if args.host_url:
            base_params['host_url'] = args.host_url
            print(f"Filter: Host URL = {args.host_url}")
        
        if args.feed_code:
            base_params['feed_code'] = args.feed_code
            print(f"Filter: Feed Code = {args.feed_code}")
        
        print()  # Empty line for readability
        
        # Create Reports directory if it doesn't exist
        reports_dir = os.path.join(os.path.dirname(__file__), "Reports")
        if not os.path.exists(reports_dir):
            os.makedirs(reports_dir)
            print(f"✓ Created Reports directory: {reports_dir}\n")
        
        # Fetch ALL data from API with pagination
        data = fetch_all_deliveries(API_BASE_URL, API_ENDPOINT, bearer_token, base_params)
        
        # Save full API response if requested
        if args.save_json:
            output_file = f"deliveries_{target_amgid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            save_to_json(data, output_file)
        
        # Save filtered deliveries (by AMGID) if requested
        if args.save_filtered_json:
            # Filter deliveries by AMGID
            filtered_deliveries = [d for d in data.get('deliveries', []) if d.get('amg_id') == target_amgid]
            filtered_data = {
                'amgid': target_amgid,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_count': len(filtered_deliveries),
                'deliveries': filtered_deliveries
            }
            filtered_output_file = f"filtered_deliveries_{target_amgid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            print(f"\nSaving filtered deliveries (AMGID: {target_amgid}) to: {filtered_output_file}...")
            save_to_json(filtered_data, filtered_output_file)
            print(f"✓ Saved {len(filtered_deliveries)} deliveries for AMGID '{target_amgid}'")
        
        # CDN Stream Testing
        if run_cdn:
            # Extract cnames for the target AMGID (not saving details to file)
            cname_data = extract_cnames_by_amgid(data.get('deliveries', []), target_amgid)
            
            if cname_data:
                # Create HLS tester input file
                hls_tester_file = create_hls_tester_json(cname_data, target_amgid)
                
                # Run HLS tests
                if hls_tester_file:
                    # Auto-run tests (CSV will be auto-generated with timestamp)
                    run_hls_tester(
                        hls_tester_file, 
                        duration=test_duration, 
                        timeout=test_timeout
                    )
        
        # MediaConnect Validation
        if run_mc:
            # Extract MediaConnect ARNs and region
            mc_data = extract_mediaconnect_arns(data.get('deliveries', []), target_amgid)
            mc_arns = mc_data.get('arns', [])
            mc_region = mc_data.get('region', 'us-east-1')
            
            # Override with user-specified region if provided
            if args.aws_region and args.aws_region != 'us-east-1':
                print(f"  ⚠️  Overriding detected region ({mc_region}) with user-specified region: {args.aws_region}")
                mc_region = args.aws_region
            
            if mc_arns:
                # Determine CSV output file
                mc_csv_file = args.mediaconnect_csv
                if not mc_csv_file:
                    # Generate default filename in Reports folder
                    mc_csv_file = os.path.join(reports_dir, f"MediaConnect_Report_{target_amgid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
                
                # Run MediaConnect validator
                run_mediaconnect_validator(
                    arns=mc_arns,
                    amgid=target_amgid,
                    region=mc_region,
                    profile=args.aws_profile,
                    hours=args.metric_hours,
                    output_file=mc_csv_file,
                    show_progress=True
                )
            else:
                print(f"\n⚠️  No MediaConnect flows found for AMGID {target_amgid}")
                print(f"   Skipping MediaConnect validation")
        
        print("\n" + "=" * 60)
        print("✓ Process completed successfully!")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"✗ Process failed: {e}")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())

