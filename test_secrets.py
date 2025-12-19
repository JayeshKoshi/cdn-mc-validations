#!/usr/bin/env python3
"""
Test script to verify AWS Secrets Manager integration.
Run this before executing main.py to ensure everything is configured correctly.
"""

import boto3
import json
from botocore.exceptions import ClientError

def test_aws_credentials():
    """Test if AWS credentials are available (via IAM role)"""
    print("=" * 70)
    print("TEST 1: AWS Credentials")
    print("=" * 70)
    
    try:
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        
        print("✅ AWS credentials are configured!")
        print(f"   Account: {identity['Account']}")
        print(f"   User/Role ARN: {identity['Arn']}")
        print(f"   User ID: {identity['UserId']}")
        return True
    except Exception as e:
        print(f"❌ AWS credentials not found: {e}")
        print("\n💡 Solutions:")
        print("   1. If on EC2: Attach IAM role to instance")
        print("   2. If local: Run 'aws configure' or set AWS_PROFILE environment variable")
        return False

def test_secrets_manager_access(secret_name='bxp_token', region='ap-south-1'):
    """Test if Secrets Manager can be accessed"""
    print(f"\n{'=' * 70}")
    print("TEST 2: Secrets Manager Access")
    print("=" * 70)
    
    try:
        client = boto3.client('secretsmanager', region_name=region)
        
        # Try to describe the secret (doesn't reveal the value)
        response = client.describe_secret(SecretId=secret_name)
        
        print(f"✅ Secret '{secret_name}' exists in region '{region}'!")
        print(f"   Secret ARN: {response['ARN']}")
        print(f"   Created: {response['CreatedDate']}")
        print(f"   Last accessed: {response.get('LastAccessedDate', 'Never')}")
        
        if 'KmsKeyId' in response:
            print(f"   Encrypted with KMS: Yes")
        
        return True
    except ClientError as e:
        error_code = e.response['Error']['Code']
        
        if error_code == 'ResourceNotFoundException':
            print(f"❌ Secret '{secret_name}' not found in region '{region}'")
            print("\n💡 Create the secret:")
            print(f"   aws secretsmanager create-secret \\")
            print(f"       --name {secret_name} \\")
            print(f"       --secret-string 'your-bearer-token-here' \\")
            print(f"       --region {region}")
        elif error_code == 'AccessDeniedException':
            print(f"❌ Access denied to secret '{secret_name}'")
            print("\n💡 Add these permissions to your IAM role:")
            print("   - secretsmanager:DescribeSecret")
            print("   - secretsmanager:GetSecretValue")
        else:
            print(f"❌ Error: {error_code} - {e.response['Error']['Message']}")
        
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_secret_retrieval(secret_name='bxp_token', region='ap-south-1'):
    """Test if secret value can be retrieved"""
    print(f"\n{'=' * 70}")
    print("TEST 3: Secret Value Retrieval")
    print("=" * 70)
    
    try:
        client = boto3.client('secretsmanager', region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        
        if 'SecretString' in response:
            secret = response['SecretString']
            
            # Try to parse as JSON
            try:
                secret_dict = json.loads(secret)
                print(f"✅ Successfully retrieved secret (JSON format)")
                print(f"   Keys in secret: {list(secret_dict.keys())}")
                
                # Mask the actual value
                for key, value in secret_dict.items():
                    masked = value[:10] + '...' if len(str(value)) > 10 else value
                    print(f"   {key}: {masked}")
                    
            except json.JSONDecodeError:
                # Plain string secret
                print(f"✅ Successfully retrieved secret (plain text)")
                masked = secret[:10] + '...' if len(secret) > 10 else secret
                print(f"   Value: {masked}")
        else:
            print(f"✅ Successfully retrieved secret (binary format)")
        
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        
        if error_code == 'DecryptionFailure':
            print(f"❌ Cannot decrypt secret - check KMS permissions")
            print("\n💡 Add this permission to your IAM role:")
            print("   - kms:Decrypt")
        elif error_code == 'AccessDeniedException':
            print(f"❌ Access denied - missing GetSecretValue permission")
            print("\n💡 Add this permission to your IAM role:")
            print("   - secretsmanager:GetSecretValue")
        else:
            print(f"❌ Error: {error_code} - {e.response['Error']['Message']}")
        
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    """Run all tests"""
    print("\n🔐 AWS Secrets Manager Integration Test")
    print("=" * 70)
    print("This script will verify your AWS configuration for the CDN tool.\n")
    
    # Test 1: AWS Credentials
    test1 = test_aws_credentials()
    
    if not test1:
        print("\n⚠️  Cannot proceed without AWS credentials!")
        return
    
    # Test 2: Secrets Manager Access
    test2 = test_secrets_manager_access()
    
    if not test2:
        print("\n⚠️  Cannot proceed without Secrets Manager access!")
        return
    
    # Test 3: Secret Retrieval
    test3 = test_secret_retrieval()
    
    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    
    if test1 and test2 and test3:
        print("✅ All tests passed! You're ready to run main.py")
        print("\n🚀 Run the tool:")
        print("   python3 main.py AMG00136")
        print("   python3 main.py AMG00136 --cdn")
        print("   python3 main.py AMG00136 --mc")
    else:
        print("❌ Some tests failed. Please fix the issues above before running main.py")
    
    print("=" * 70)

if __name__ == "__main__":
    main()

