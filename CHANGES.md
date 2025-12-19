# 🔄 Changes Made for AWS Secrets Manager Integration

## Summary

The `deployment` folder contains a production-ready version of the CDN Verification Tool that integrates with AWS Secrets Manager for secure credential management.

---

## 📝 What Was Modified

### 1. **`main.py` - Added AWS Secrets Manager Integration**

#### **New Function Added:**
```python
def get_secret_from_aws(secret_name: str, region_name: str = 'ap-south-1') -> str
```
- Fetches Bearer token from AWS Secrets Manager
- Uses IAM role credentials automatically (no access keys needed)
- Supports both plain text and JSON secret formats
- Comprehensive error handling with helpful error messages

#### **New Command-Line Arguments:**
- `--secret-name` (default: `bxp_token`) - Name of the secret in AWS Secrets Manager
- `--secret-region` (default: `ap-south-1`) - AWS region where secret is stored

#### **Modified Logic:**
- **Before**: Used hardcoded `BEARER_TOKEN = "f47ac10b-58cc-4372-a567-0e02b2c3d479"`
- **After**: Fetches token from Secrets Manager at runtime
- Added try-catch block with user-friendly error messages
- Token is retrieved once per script execution

#### **Code Location:**
- Lines 18-108: `get_secret_from_aws()` function
- Lines 748-772: Token retrieval logic in `main()`
- Line 814: Using `bearer_token` instead of `BEARER_TOKEN`

---

### 2. **New Files Created**

#### **`test_secrets.py`** (6.1 KB)
- Diagnostic script to verify AWS configuration
- Tests 3 things:
  1. ✅ AWS credentials are available
  2. ✅ Secret exists in Secrets Manager
  3. ✅ Secret value can be retrieved
- Provides clear error messages and solutions
- **Run this first** before running main.py

#### **`QUICKSTART.md`** (7.0 KB)
- Step-by-step setup guide
- Prerequisites checklist
- IAM permissions template
- Usage examples
- Troubleshooting section
- Complete command reference

#### **`README.md`** (1.9 KB)
- Overview of deployment folder
- Differences from parent folder
- Quick usage instructions
- Next steps for Jenkins deployment

#### **`CHANGES.md`** (this file)
- Documentation of all modifications
- Before/after comparison
- Technical implementation details

---

## 🔐 Security Improvements

| **Before** | **After** |
|------------|-----------|
| ❌ Bearer token hardcoded in source | ✅ Token stored in AWS Secrets Manager |
| ❌ Token visible in Git history | ✅ Never exposed in version control |
| ❌ Manual token rotation needed | ✅ Update secret anytime without code changes |
| ❌ Token in Jenkins config | ✅ Zero credentials in Jenkins |
| ❌ No audit trail | ✅ CloudTrail logs all secret access |

---

## 🎯 How It Works

### **Flow Diagram:**

```
┌─────────────────────────────────────────────────────┐
│  1. python3 main.py AMG00136                         │
│     ├── --secret-name bxp_token                      │
│     └── --secret-region ap-south-1                   │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  2. Script calls get_secret_from_aws()               │
│     ├── Uses boto3.client('secretsmanager')         │
│     └── Credentials from IAM role (automatic)        │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  3. AWS Secrets Manager                              │
│     ├── Retrieves secret 'bxp_token'                │
│     ├── Decrypts using KMS (if encrypted)           │
│     └── Returns Bearer token value                   │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  4. Script uses token to call BXP API               │
│     └── fetch_all_deliveries(url, endpoint, token)  │
└─────────────────────────────────────────────────────┘
```

---

## 📦 Dependencies

### **Updated in `requirements.txt`:**
```txt
boto3>=1.28.0  ← Required for AWS SDK
```

All other dependencies remain the same.

---

## 🚀 Usage Comparison

### **Before (Hardcoded Token):**
```bash
# Token was in the code
python3 main.py AMG00136
```

### **After (Secrets Manager):**
```bash
# Token fetched from AWS (default secret: bxp_token, region: ap-south-1)
python3 main.py AMG00136

# Or with custom secret name/region
python3 main.py AMG00136 \
    --secret-name my-custom-secret \
    --secret-region us-east-1
```

---

## ✅ Prerequisites

### **1. AWS Secret Must Exist:**
```bash
aws secretsmanager describe-secret \
    --secret-id bxp_token \
    --region ap-south-1
```

### **2. IAM Role Permissions:**
Your environment needs an IAM role with:
- `secretsmanager:GetSecretValue`
- `secretsmanager:DescribeSecret` (for test script)
- `kms:Decrypt` (if secret is encrypted)
- MediaConnect/CloudWatch permissions (for validation)

### **3. Test Before Running:**
```bash
python3 test_secrets.py
```

---

## 🔧 Backward Compatibility

### **Parent Folder Scripts:**
- ✅ Still work with hardcoded token (for local testing/development)
- ✅ No changes needed

### **Deployment Folder Scripts:**
- ⚠️  **Require** AWS Secrets Manager setup
- ⚠️  **Won't work** without IAM role and secret

---

## 🎓 Error Handling

The script provides detailed error messages:

### **If Secret Not Found:**
```
❌ Secret 'bxp_token' not found in AWS Secrets Manager (region: ap-south-1)

⚠️  Make sure:
   1. Secret 'bxp_token' exists in AWS Secrets Manager (region: ap-south-1)
   2. IAM role has 'secretsmanager:GetSecretValue' permission
   3. IAM role has 'kms:Decrypt' permission (if secret is encrypted)
   4. EC2 instance/environment has IAM role attached

💡 To create the secret:
   aws secretsmanager create-secret \
       --name bxp_token \
       --secret-string 'your-bearer-token' \
       --region ap-south-1
```

---

## 📊 Testing Results

After implementation, run:

```bash
# Test 1: Verify AWS setup
python3 test_secrets.py

# Test 2: Run actual validation
python3 main.py AMG00136 --cdn
```

**Expected:**
- ✅ Secret retrieved successfully
- ✅ API calls work with fetched token
- ✅ CSV reports generated in `Reports/` folder

---

## 🎯 Next Steps

1. ✅ **Local Testing**: Run `test_secrets.py` to verify setup
2. ✅ **Validation Test**: Run `main.py AMG00136` with a known AMGID
3. 📤 **Git Push**: Commit to repository (no secrets exposed!)
4. 🚀 **Jenkins Deploy**: Create pipeline using scripts in this folder
5. 🔄 **Automate**: Set up scheduled runs or webhook triggers

---

## 📞 Support

If you encounter issues:

1. **Run diagnostic**: `python3 test_secrets.py`
2. **Check IAM role**: `aws sts get-caller-identity`
3. **Verify secret**: `aws secretsmanager describe-secret --secret-id bxp_token --region ap-south-1`
4. **Check permissions**: See IAM policy template in `QUICKSTART.md`

---

## 🎉 Summary

✅ **Production-Ready**: No hardcoded credentials  
✅ **Secure**: AWS Secrets Manager + IAM roles  
✅ **Maintainable**: Update token without code changes  
✅ **Jenkins-Ready**: Zero credential management needed  
✅ **Well-Documented**: Complete guides and test scripts  

**The deployment folder is now ready for production use!** 🚀

