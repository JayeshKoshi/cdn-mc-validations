# 🚀 Quick Start Guide - Deployment Version

This guide will help you set up and run the CDN Verification Tool with AWS Secrets Manager integration.

---

## ✅ Prerequisites

### 1. AWS Secret Already Created
You mentioned you've already created the secret:
- **Secret Name**: `bxp_token`
- **AWS Region**: `ap-south-1`
- **Content**: Your Bearer token value

### 2. Verify Secret Exists
```bash
aws secretsmanager describe-secret \
    --secret-id bxp_token \
    --region ap-south-1
```

### 3. IAM Role Permissions Required

Your IAM role (attached to EC2 or your environment) needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SecretsManagerAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:ap-south-1:*:secret:bxp_token-*"
    },
    {
      "Sid": "KMSDecrypt",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "secretsmanager.ap-south-1.amazonaws.com"
        }
      }
    },
    {
      "Sid": "MediaConnectAccess",
      "Effect": "Allow",
      "Action": [
        "mediaconnect:DescribeFlow",
        "mediaconnect:ListFlows",
        "mediaconnect:ListTagsForResource",
        "cloudwatch:GetMetricStatistics",
        "tag:GetResources"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## 📦 Step 1: Install Dependencies

```bash
cd deployment/

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required packages
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 🧪 Step 2: Test AWS Configuration

Before running the main script, verify your AWS setup:

```bash
# Run the test script
python3 test_secrets.py
```

**Expected output:**
```
============================================================
TEST 1: AWS Credentials
============================================================
✅ AWS credentials are configured!
   Account: 123456789012
   User/Role ARN: arn:aws:sts::123456789012:assumed-role/YourRole/...
   User ID: AROAXXXXXXXXXXXXX

============================================================
TEST 2: Secrets Manager Access
============================================================
✅ Secret 'bxp_token' exists in region 'ap-south-1'!
   Secret ARN: arn:aws:secretsmanager:ap-south-1:123456789012:secret:bxp_token-XXXXXX
   Created: 2024-12-19 10:30:00+00:00

============================================================
TEST 3: Secret Value Retrieval
============================================================
✅ Successfully retrieved secret (plain text)
   Value: f47ac10b-5...

============================================================
SUMMARY
============================================================
✅ All tests passed! You're ready to run main.py
```

**If tests fail**, follow the error messages to fix your configuration.

---

## 🎯 Step 3: Run the CDN Verification Tool

### Basic Usage:

```bash
# Test both CDN and MediaConnect
python3 main.py AMG00136

# Test CDN only
python3 main.py AMG00136 --cdn

# Test MediaConnect only
python3 main.py AMG00136 --mc
```

### Advanced Options:

```bash
# Custom secret name/region (if different from defaults)
python3 main.py AMG00136 \
    --secret-name your-secret-name \
    --secret-region your-region

# With custom test duration
python3 main.py AMG00136 \
    --cdn \
    --test-duration 180

# Save filtered JSON output
python3 main.py AMG00136 \
    --save-filtered-json

# All options
python3 main.py AMG00136 \
    --cdn \
    --test-duration 120 \
    --test-timeout 15 \
    --secret-name bxp_token \
    --secret-region ap-south-1
```

---

## 📊 Step 4: View Results

### CSV Reports Location:
```
deployment/Reports/
├── CDN_Test_Report_AMG00136_YYYYMMDD_HHMMSS.csv
└── MediaConnect_Report_AMG00136_YYYYMMDD_HHMMSS.csv
```

### Open reports:
```bash
# View in terminal
cat Reports/CDN_Test_Report_*.csv

# Open in Excel/Numbers (macOS)
open Reports/CDN_Test_Report_*.csv
```

---

## 🐛 Troubleshooting

### Issue 1: "Secret not found"
```bash
# Verify secret exists
aws secretsmanager list-secrets --region ap-south-1 | grep bxp_token

# Check the exact name
aws secretsmanager describe-secret --secret-id bxp_token --region ap-south-1
```

### Issue 2: "Access denied"
```bash
# Check your IAM role
aws sts get-caller-identity

# Verify permissions
aws secretsmanager get-secret-value --secret-id bxp_token --region ap-south-1
```

### Issue 3: "Cannot decrypt secret"
- Your IAM role needs `kms:Decrypt` permission
- The KMS key used to encrypt the secret must allow your role to use it

### Issue 4: "AWS credentials not found"
```bash
# If on EC2
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/

# If local development
aws configure
# or
export AWS_PROFILE=your-profile-name
```

---

## 🔄 Updating the Secret

To update the Bearer token without changing code:

```bash
# Update the secret value
aws secretsmanager update-secret \
    --secret-id bxp_token \
    --secret-string 'new-bearer-token-value' \
    --region ap-south-1

# Verify the update
aws secretsmanager get-secret-value \
    --secret-id bxp_token \
    --region ap-south-1 \
    --query 'SecretString' \
    --output text
```

**Note**: The script will automatically use the new value on the next run!

---

## 📝 Command-Line Arguments Reference

| Argument | Default | Description |
|----------|---------|-------------|
| `amgid` | *required* | AMGID to validate (e.g., AMG00136) |
| `--cdn` | both | Test CDN streams only |
| `--mc` | both | Test MediaConnect only |
| `--secret-name` | `bxp_token` | AWS Secrets Manager secret name |
| `--secret-region` | `ap-south-1` | AWS region for secret |
| `--test-duration` | `120` | Test duration in seconds |
| `--test-timeout` | `15` | Request timeout in seconds |
| `--aws-region` | `us-east-1` | MediaConnect AWS region |
| `--save-filtered-json` | `false` | Save filtered deliveries JSON |

---

## 🚀 Jenkins Deployment

Once local testing is successful, deploy to Jenkins:

1. **Push code to Git repository**
2. **Create Jenkins pipeline job**
3. **Configure build parameters**:
   - AMGID (string)
   - TEST_TYPE (choice: both/cdn-only/mc-only)
4. **Pipeline runs automatically** - no credentials needed in Jenkins!

---

## ✨ Benefits of This Deployment Approach

✅ **No hardcoded credentials** - Everything fetched from AWS  
✅ **Automatic credential refresh** - IAM roles handle rotation  
✅ **Secure** - Secrets Manager + KMS encryption  
✅ **Easy updates** - Change secret without touching code  
✅ **Audit trail** - CloudTrail logs all secret access  
✅ **Jenkins-ready** - Zero credential management in CI/CD  

---

## 📞 Need Help?

Run the test script for diagnostic information:
```bash
python3 test_secrets.py
```

The output will tell you exactly what's wrong and how to fix it!

---

**Happy Testing! 🎉**

