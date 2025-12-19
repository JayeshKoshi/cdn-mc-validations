# Deployment Version - AWS Secrets Manager Integration

This folder contains the deployment-ready version of the CDN Verification Tool that integrates with:
- **AWS IAM Roles** for MediaConnect/CloudWatch access
- **AWS Secrets Manager** for secure API token storage

## What's Different from Parent Folder?

- ✅ Fetches Bearer token from AWS Secrets Manager (no hardcoded credentials)
- ✅ Uses IAM Role for AWS service access (no AWS keys needed)
- ✅ Ready for Jenkins deployment on EC2 instances
- ✅ Production-ready security best practices

## Files in This Folder

- `main.py` - Main orchestrator script (will be modified for Secrets Manager)
- `hls_tester.py` - CDN HLS stream validation tool
- `mediaconnect_validator.py` - MediaConnect flow validation tool
- `requirements.txt` - Python dependencies
- `CDN_VERIFICATION_TOOL_DOCUMENTATION.md` - User documentation
- `Reports/` - Output folder for CSV reports

## Prerequisites

1. **AWS Secret Created**:
   ```bash
   aws secretsmanager create-secret \
       --name cdn-automation/config \
       --secret-string '{"api_token": "your-bearer-token-here"}' \
       --region us-east-1
   ```

2. **IAM Role with Permissions**:
   - MediaConnect read access
   - CloudWatch GetMetricStatistics
   - Secrets Manager GetSecretValue
   - Resource Groups Tagging API

3. **EC2 Instance** with IAM role attached (for Jenkins)

## Usage

```bash
# Fetch token from Secrets Manager automatically
python3 main.py AMG00136 --secret-name cdn-automation/config

# CDN only
python3 main.py AMG00136 --cdn --secret-name cdn-automation/config

# MediaConnect only
python3 main.py AMG00136 --mc --secret-name cdn-automation/config
```

## Next Steps

1. Modify `main.py` to add Secrets Manager integration
2. Test locally with AWS credentials
3. Deploy to Jenkins EC2 instance
4. Create Jenkinsfile for pipeline automation

---

**Note**: This is the deployment version. For development/testing, use the scripts in the parent folder.

