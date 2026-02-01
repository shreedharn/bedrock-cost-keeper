# Getting Started with Bedrock Cost Keeper

This guide covers both quick setup (5 minutes) and detailed manual validation for local development.

**Choose your path:**
- 🚀 **[Quick Start](#quick-start)** - Get running in 5 minutes (experienced users)
- 📖 **[Detailed Setup](#detailed-setup)** - Step-by-step guide with validation (first-time users)

---

# Quick Start

Get up and running with Bedrock Cost Keeper in under 5 minutes!

## Prerequisites

```bash
# Verify you have everything installed
python3 --version    # 3.11+
finch version        # or: docker --version
aws --version
jq --version
```

## 1. Deploy AWS Infrastructure (2 minutes)

```bash
cd cloudformation/dev
./deploy.sh
```

Creates: Application Inference Profile, Secrets Manager secrets, KMS key

## 2. Configure Environment (1 minute)

```bash
cd ../..  # Back to project root

# Create .env from example
cp .env.example .env

# Append CloudFormation outputs
cat cloudformation/dev/.env.cloudformation >> .env

# Verify configuration
grep INFERENCE_PROFILE_ARN .env
```

## 3. Start Local Services (2 minutes)

```bash
# Start DynamoDB Local
./scripts/dynamodb.sh start

# Initialize tables
./scripts/dynamodb.sh init

# Start API service
finch-compose up -d api
# or: docker-compose up -d api

# Verify services are running
curl http://localhost:8080/health
```

Expected response: `{"status":"healthy","timestamp":"..."}`

## 4. Run Manual Tests (5 minutes)

```bash
cd test-client

# Install dependencies
pip install -r requirements.txt

# Run interactive tests
python manual_test.py
```

Follow the prompts to test each API endpoint step-by-step.

## What You'll Test

1. ✅ Create organization (sample-org)
2. ✅ Create application (sample-app)
3. ✅ Authenticate (get JWT token)
4. ✅ Register inference profile
5. ✅ Get model selection
6. ✅ Invoke Bedrock (Amazon Nova Lite)
7. ✅ Submit usage data
8. ✅ Check aggregates

## Quick Troubleshooting

### Port already in use
```bash
# Change ports in docker-compose.yml
ports:
  - "8001:8000"  # DynamoDB
  - "8081:8080"  # API
```

### AWS credentials not found
```bash
aws configure
# Or use environment variables
export AWS_PROFILE=default
export AWS_REGION=us-east-1
```

### Services not responding
```bash
# Check logs
finch logs bedrock-cost-keeper-api-local
./scripts/dynamodb.sh status
```

## Cleanup

```bash
# Stop containers
finch-compose down

# Clear local data
./scripts/dynamodb.sh clear

# Delete AWS resources (optional)
cd cloudformation/dev
./cleanup.sh
```

## Need More Help?

See the [Detailed Setup](#detailed-setup) section below for comprehensive instructions, expected outputs, and troubleshooting.

---

# Detailed Setup

Comprehensive manual validation guide with step-by-step instructions and verification at each stage.

## Table of Contents

1. [Prerequisites](#prerequisites-detailed)
2. [Part 1: AWS Infrastructure Setup](#part-1-aws-infrastructure-setup)
3. [Part 2: Local Environment Setup](#part-2-local-environment-setup)
4. [Part 3: Manual API Testing](#part-3-manual-api-testing)
5. [Part 4: Debugging](#part-4-debugging)
6. [Part 5: Cleanup](#part-5-cleanup)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites (Detailed)

Before starting, ensure you have:

- [ ] Python 3.11 or higher installed
- [ ] Finch or Docker installed and running
- [ ] AWS CLI configured with valid credentials
- [ ] AWS account with Amazon Bedrock access enabled
- [ ] `jq` installed (for JSON parsing in terminal)
- [ ] Git (to clone the repository)

### Verify Prerequisites

```bash
# Check Python version
python3 --version  # Should be 3.11+

# Check Finch/Docker
finch version  # or: docker --version

# Check AWS CLI
aws --version
aws sts get-caller-identity  # Should show your AWS account

# Check jq
jq --version

# Check Bedrock access
aws bedrock list-foundation-models --region us-east-1 | jq '.modelSummaries[] | select(.modelId | contains("nova-lite"))'
```

---

## Part 1: AWS Infrastructure Setup

This section creates the minimal AWS resources needed: Application Inference Profile and Secrets Manager secrets.

### 1.1 Deploy CloudFormation Stack

Navigate to the CloudFormation directory and run the deployment script:

```bash
cd cloudformation/dev
chmod +x deploy.sh
./deploy.sh
```

**Expected Output:**

```
========================================
Bedrock Cost Keeper - Minimal AWS Setup
========================================

✓ AWS Account ID: 123456789012

Generating secrets...
✓ Secrets generated

Deploying CloudFormation stack...

Waiting for changeset to be created..
Waiting for stack create/update to complete
Successfully created/updated stack - bedrock-cost-keeper-dev-minimal

✓ Stack deployed successfully!

========================================
Stack Outputs
========================================

InferenceProfileArn: arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.amazon.nova-lite-v1:0:xxxxx
InferenceProfileId: xxxxx
JWTSecretArn: arn:aws:secretsmanager:us-east-1:123456789012:secret:bedrock-cost-keeper/dev/jwt-secret-xxxxx
JWTSecretName: bedrock-cost-keeper/dev/jwt-secret
ProvisioningAPISecretArn: arn:aws:secretsmanager:us-east-1:123456789012:secret:bedrock-cost-keeper/dev/provisioning-api-key-xxxxx
ProvisioningAPISecretName: bedrock-cost-keeper/dev/provisioning-api-key
KMSKeyArn: arn:aws:kms:us-east-1:123456789012:key/xxxxx
KMSKeyId: xxxxx

========================================
Environment Configuration
========================================

✓ Environment configuration saved to: .env.cloudformation

[Configuration details shown here]

========================================
Verifying Resources
========================================

✓ Inference Profile accessible
✓ JWT Secret accessible
✓ Provisioning API Secret accessible

========================================
Deployment Complete!
========================================
```

### 1.2 Verify AWS Resources

Verify the inference profile exists:

```bash
# Get the profile ID from CloudFormation outputs
PROFILE_ID=$(aws cloudformation describe-stacks \
  --stack-name bedrock-cost-keeper-dev-minimal \
  --query 'Stacks[0].Outputs[?OutputKey==`InferenceProfileId`].OutputValue' \
  --output text)

# Verify profile
aws bedrock get-inference-profile \
  --inference-profile-identifier "$PROFILE_ID" \
  --region us-east-1
```

Verify secrets exist:

```bash
# List secrets
aws secretsmanager list-secrets \
  --filters Key=name,Values=bedrock-cost-keeper/dev \
  --region us-east-1

# Get JWT secret (masked)
aws secretsmanager describe-secret \
  --secret-id bedrock-cost-keeper/dev/jwt-secret \
  --region us-east-1
```

### 1.3 Update Local Configuration

The deployment script automatically creates `.env.cloudformation` with the necessary values. Copy these to your project root `.env` file:

```bash
cd ../..  # Back to project root

# Create .env file from example
cp .env.example .env

# Append CloudFormation outputs
cat cloudformation/dev/.env.cloudformation >> .env

# Edit .env to ensure all values are correct
nano .env  # or use your preferred editor
```

Your `.env` file should include:

```bash
# AWS Configuration
AWS_PROFILE=default
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012

# DynamoDB
DYNAMODB_ENDPOINT=http://localhost:8000
TABLE_PREFIX=bedrock-cost-keeper

# Secrets Manager
JWT_SECRET_NAME=bedrock-cost-keeper/dev/jwt-secret
PROVISIONING_API_KEY_NAME=bedrock-cost-keeper/dev/provisioning-api-key

# Inference Profile (from CloudFormation output)
SAMPLE_APP_INFERENCE_PROFILE_ARN=arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.amazon.nova-lite-v1:0:xxxxx

# Service
SERVICE_URL=http://localhost:8080
ENVIRONMENT=dev
```

---

## Part 2: Local Environment Setup

### 2.1 Start DynamoDB Local

Start the local DynamoDB container:

```bash
./scripts/dynamodb.sh start
```

**Expected Output:**

```
[INFO] Using container runtime: finch
[INFO] Starting DynamoDB Local container...
[INFO] Container started successfully
[INFO] DynamoDB Local is running on http://localhost:8000
```

**Validation:**

```bash
# Check container status
./scripts/dynamodb.sh status

# Expected: Container is running

# Test DynamoDB endpoint
curl http://localhost:8000
# Expected: HTML page or JSON error (proves DynamoDB is responding)
```

### 2.2 Initialize DynamoDB Tables

Create the required tables:

```bash
./scripts/dynamodb.sh init
```

**Expected Output:**

```
[INFO] Initializing DynamoDB tables...
[INFO] Creating table: bedrock-cost-keeper-config
[INFO] Creating table: bedrock-cost-keeper-sticky-state
[INFO] Creating table: bedrock-cost-keeper-usage-agg-sharded
[INFO] Creating table: bedrock-cost-keeper-daily-total
[INFO] Creating table: bedrock-cost-keeper-pricing-cache
[INFO] Creating table: bedrock-cost-keeper-tokens
[INFO] Creating table: bedrock-cost-keeper-secrets
[INFO] Initialization complete!
```

**Validation:**

```bash
# List tables
./scripts/dynamodb.sh list

# Expected output should show all tables:
# - bedrock-cost-keeper-config
# - bedrock-cost-keeper-sticky-state
# - bedrock-cost-keeper-usage-agg-sharded
# - bedrock-cost-keeper-daily-total
# - bedrock-cost-keeper-pricing-cache
# - bedrock-cost-keeper-tokens
# - bedrock-cost-keeper-secrets
```

### 2.3 Build and Start API Service Container

Build the development Docker image and start the API service:

```bash
# Build the image
finch-compose build api
# or: docker-compose build api

# Start the API service
finch-compose up -d api
# or: docker-compose up -d api
```

**Expected Output:**

```
[+] Building 45.2s (10/10) FINISHED
 => [internal] load build definition from Dockerfile.dev
 => => transferring dockerfile: 543B
 => [internal] load .dockerignore
 => ...
 => => naming to docker.io/library/bedrock_metering-api

[+] Running 2/2
 ✔ Network bedrock-cost-keeper-net         Created
 ✔ Container bedrock-cost-keeper-api-local Started
```

**Validation:**

```bash
# Check containers are running
finch ps
# or: docker ps

# Expected: Both containers running:
# - bedrock-cost-keeper-dynamodb-local
# - bedrock-cost-keeper-api-local

# Check API health
curl http://localhost:8080/health

# Expected response:
# {"status":"healthy","timestamp":"2026-01-30T..."}

# Check API logs
finch logs bedrock-cost-keeper-api-local
# or: docker logs bedrock-cost-keeper-api-local

# Expected: No error messages
```

If the health check fails, check the logs for errors:

```bash
# Follow logs in real-time
finch logs -f bedrock-cost-keeper-api-local

# Look for startup errors related to:
# - DynamoDB connection
# - Secrets Manager access
# - Missing configuration
```

---

## Part 3: Manual API Testing

### 3.1 Install Test Client Dependencies

```bash
cd test-client

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**Expected Output:**

```
Collecting boto3>=1.34.0
Collecting requests>=2.31.0
Collecting pyyaml>=6.0
Collecting rich>=13.7.0
...
Successfully installed boto3-... requests-... pyyaml-... rich-...
```

### 3.2 Configure Test Client

The `manual_test_config.json` file should already be updated by the CloudFormation deployment script. Verify it has the correct values:

```bash
cat manual_test_config.json
```

Expected content:

```json
{
  "service_url": "http://localhost:8080",
  "aws_profile": "default",
  "aws_region": "us-east-1",
  "inference_profile_arn": "arn:aws:bedrock:us-east-1:123456789012:inference-profile/...",
  "jwt_secret_name": "bedrock-cost-keeper/dev/jwt-secret",
  "provisioning_api_key_secret_name": "bedrock-cost-keeper/dev/provisioning-api-key",
  "test_org_name": "sample-org",
  "test_org_timezone": "America/New_York",
  "test_app_id": "sample-app",
  "test_app_name": "Sample Application",
  "test_prompt": "Explain what Amazon Bedrock is in one sentence.",
  "model_id": "amazon.nova-lite-v1:0",
  "profile_label": "nova-lite-premium",
  "quotas": {
    "premium": 10000000,
    "standard": 5000000,
    "economy": 2000000
  },
  "model_ordering": ["premium", "standard", "economy"]
}
```

### 3.3 Run Manual Test Script

Start the interactive test:

```bash
python manual_test.py
```

### 3.4 Test Flow Walkthrough

The script will guide you through 8 steps. Here's what to expect at each step:

#### Step 1: Create Organization

**What happens:**
- Fetches provisioning API key from AWS Secrets Manager
- Creates organization "sample-org" with quotas
- Returns org_id, client_id, and client_secret

**What to verify:**
- Status code: `201 Created`
- Response includes all fields: `org_id`, `org_name`, `client_id`, `client_secret`
- Client secret is displayed (save this!)

**Sample Response:**
```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "org_name": "sample-org",
  "timezone": "America/New_York",
  "quota_scope": "APP",
  "model_ordering": ["premium", "standard", "economy"],
  "quotas": {
    "premium": 10000000,
    "standard": 5000000,
    "economy": 2000000
  },
  "client_id": "org-550e8400-e29b-41d4-a716-446655440000",
  "client_secret": "AbCdEfGh1234567890..."
}
```

#### Step 2: Create Application

**What happens:**
- Creates application "sample-app" under the organization
- Registers the app with its configuration

**What to verify:**
- Status code: `201 Created`
- Response includes `app_id`, `app_name`
- Application is linked to the organization

**Sample Response:**
```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "app_id": "sample-app",
  "app_name": "Sample Application",
  "created_at": "2026-01-30T12:00:00Z"
}
```

#### Step 3: Authenticate

**What happens:**
- Exchanges client credentials for JWT access token
- Token is used for subsequent authenticated requests

**What to verify:**
- Status code: `200 OK`
- Response includes `access_token`, `token_type`, `expires_in`
- Token type is "Bearer"

**Sample Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

#### Step 4: Register Inference Profile

**What happens:**
- Registers the AWS Bedrock Application Inference Profile with label
- Links profile to the application

**What to verify:**
- Status code: `201 Created`
- Response confirms profile registration
- Profile ARN matches CloudFormation output

**Sample Response:**
```json
{
  "profile_label": "nova-lite-premium",
  "inference_profile_arn": "arn:aws:bedrock:us-east-1:123456789012:inference-profile/...",
  "description": "Amazon Nova Lite for sample-app",
  "status": "registered"
}
```

#### Step 5: Get Model Selection

**What happens:**
- Requests model selection based on current quotas
- Returns the selected profile label

**What to verify:**
- Status code: `200 OK`
- Selected profile matches registered profile (e.g., "nova-lite-premium")
- Quota information is included

**Sample Response:**
```json
{
  "selected_profile_label": "nova-lite-premium",
  "model_id": "amazon.nova-lite-v1:0",
  "inference_profile_arn": "arn:aws:bedrock:us-east-1:123456789012:inference-profile/...",
  "quota_remaining": 9999500,
  "estimated_cost": 500
}
```

#### Step 6: Invoke Bedrock

**What happens:**
- Invokes Amazon Bedrock directly using the inference profile ARN
- Sends test prompt to Nova Lite model
- Returns AI-generated response and token usage

**What to verify:**
- No errors from Bedrock
- Response text is coherent
- Token usage is reported (input + output tokens)

**Sample Response:**
```
Response Text:
Amazon Bedrock is a fully managed service that offers a choice of high-performing foundation models from leading AI companies through a single API.

Token Usage:
  Input Tokens: 23
  Output Tokens: 28
  Total Tokens: 51
```

**Check AWS CloudTrail:**
```bash
# Verify Bedrock invocation was logged
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=InvokeModel \
  --max-results 5 \
  --region us-east-1
```

#### Step 7: Submit Usage

**What happens:**
- Submits token usage to Cost Keeper service
- Usage is recorded and aggregated
- Cost is calculated based on pricing

**What to verify:**
- Status code: `201 Created`
- Response confirms usage recorded
- Token counts match Bedrock invocation

**Sample Response:**
```json
{
  "usage_id": "usage-123456",
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "app_id": "sample-app",
  "model_id": "amazon.nova-lite-v1:0",
  "input_tokens": 23,
  "output_tokens": 28,
  "cost_usd": 500,
  "calling_region": "us-east-1",
  "timestamp": "2026-01-30T12:00:00Z"
}
```

#### Step 8: Check Aggregates

**What happens:**
- Retrieves usage aggregates for the current day
- Shows total tokens and costs

**What to verify:**
- Status code: `200 OK`
- Aggregates show the submitted usage
- Costs are calculated correctly
- Data is grouped by date and model

**Sample Response:**
```
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Date       ┃ Model                  ┃ Input Tokens ┃ Output Tokens ┃ Cost (USD)   ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ 2026-01-30 │ amazon.nova-lite-v1:0  │ 23           │ 28            │ $0.000500    │
└────────────┴────────────────────────┴──────────────┴───────────────┴──────────────┘
```

### 3.5 Validation Checklist

After completing all steps, verify:

- [ ] Organization created successfully (step 1)
- [ ] Application created successfully (step 2)
- [ ] JWT token received and valid (step 3)
- [ ] Inference profile registered (step 4)
- [ ] Model selection returned correct label (step 5)
- [ ] Bedrock invocation succeeded with valid response (step 6)
- [ ] Usage submission accepted (step 7)
- [ ] Aggregates show correct token counts and costs (step 8)
- [ ] No errors in test logs (`logs/manual_test_*.log`)
- [ ] No errors in API container logs

---

## Part 4: Debugging

### 4.1 Check Service Logs

Monitor the API service logs in real-time:

```bash
finch logs -f bedrock-cost-keeper-api-local
# or: docker logs -f bedrock-cost-keeper-api-local
```

Look for:
- HTTP request/response logs
- Database operations
- AWS service calls
- Error messages or stack traces

### 4.2 Check DynamoDB Data

Inspect data stored in local DynamoDB:

```bash
# List all items in config table
./scripts/dynamodb.sh scan bedrock-cost-keeper-config

# Check organizations
./scripts/dynamodb.sh query bedrock-cost-keeper-config \
  --key-condition-expression "PK = :pk" \
  --expression-attribute-values '{":pk": {"S": "ORG#sample-org"}}'

# Check usage records
./scripts/dynamodb.sh scan bedrock-cost-keeper-usage-agg-sharded

# Check tokens (authentication)
./scripts/dynamodb.sh scan bedrock-cost-keeper-tokens
```

### 4.3 Check AWS Resources

Verify AWS resources are accessible:

```bash
# Verify inference profile
PROFILE_ID=$(aws cloudformation describe-stacks \
  --stack-name bedrock-cost-keeper-dev-minimal \
  --query 'Stacks[0].Outputs[?OutputKey==`InferenceProfileId`].OutputValue' \
  --output text)

aws bedrock get-inference-profile \
  --inference-profile-identifier "$PROFILE_ID" \
  --region us-east-1

# Check Bedrock invocation logs in CloudTrail
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=InvokeModel \
  --max-results 10 \
  --region us-east-1 | jq '.Events[] | .CloudTrailEvent | fromjson'

# Verify secrets are accessible
aws secretsmanager get-secret-value \
  --secret-id bedrock-cost-keeper/dev/jwt-secret \
  --region us-east-1 \
  --query SecretString \
  --output text

aws secretsmanager get-secret-value \
  --secret-id bedrock-cost-keeper/dev/provisioning-api-key \
  --region us-east-1 \
  --query SecretString \
  --output text
```

### 4.4 Interactive Debugging

For step-by-step debugging, you can run individual test steps:

```python
# In Python interactive shell
from manual_test import ManualTester

tester = ManualTester()

# Run specific steps
tester.test_step_1_create_org()
tester.test_step_2_create_app()
# ... etc
```

---

## Part 5: Cleanup

### 5.1 Stop Containers

Stop all running containers:

```bash
finch-compose down
# or: docker-compose down

# Alternative: Stop individual containers
./scripts/dynamodb.sh stop
finch stop bedrock-cost-keeper-api-local
```

### 5.2 Clear Local Data

Remove local DynamoDB data:

```bash
./scripts/dynamodb.sh clear
```

This will delete all tables and their data. You'll need to run `./scripts/dynamodb.sh init` again before the next test.

### 5.3 Delete AWS Resources (Optional)

If you want to completely remove the AWS infrastructure:

```bash
cd cloudformation/dev

aws cloudformation delete-stack \
  --stack-name bedrock-cost-keeper-dev-minimal \
  --region us-east-1

# Wait for deletion to complete
aws cloudformation wait stack-delete-complete \
  --stack-name bedrock-cost-keeper-dev-minimal \
  --region us-east-1

echo "Stack deleted successfully"
```

**Warning:** This will delete the inference profile and secrets. You'll need to redeploy the CloudFormation stack to test again.

---

## Troubleshooting

### Issue: API container can't connect to DynamoDB

**Symptoms:**
- API health check fails
- Logs show "Connection refused" or "Unable to connect to DynamoDB"

**Solution:**

1. Verify both containers are on the same network:
```bash
finch network inspect bedrock-cost-keeper-net
# Both containers should be listed
```

2. Check DynamoDB container is running:
```bash
finch ps | grep dynamodb
```

3. Test DynamoDB from API container:
```bash
finch exec bedrock-cost-keeper-api-local \
  curl http://dynamodb-local:8000
```

### Issue: AWS credentials not found

**Symptoms:**
- Errors like "Unable to locate credentials"
- Secrets Manager or Bedrock calls fail

**Solution:**

1. Verify AWS credentials are mounted:
```bash
finch exec bedrock-cost-keeper-api-local \
  ls -la /root/.aws
# Should show config and credentials files
```

2. Check AWS profile in `.env`:
```bash
grep AWS_PROFILE .env
```

3. Verify credentials work from host:
```bash
aws sts get-caller-identity --profile default
```

4. If needed, update `docker-compose.yml` to mount credentials:
```yaml
volumes:
  - ~/.aws:/root/.aws:ro
```

### Issue: Inference profile not found

**Symptoms:**
- Error: "Could not find inference profile"
- Bedrock invocation fails with 404

**Solution:**

1. Verify ARN is correct in config:
```bash
cat test-client/manual_test_config.json | jq '.inference_profile_arn'
```

2. List available inference profiles:
```bash
aws bedrock list-inference-profiles --region us-east-1
```

3. Verify the specific profile:
```bash
PROFILE_ID=$(aws cloudformation describe-stacks \
  --stack-name bedrock-cost-keeper-dev-minimal \
  --query 'Stacks[0].Outputs[?OutputKey==`InferenceProfileId`].OutputValue' \
  --output text)

aws bedrock get-inference-profile \
  --inference-profile-identifier "$PROFILE_ID" \
  --region us-east-1
```

### Issue: Secrets Manager access denied

**Symptoms:**
- Error: "AccessDeniedException" when fetching secrets
- Test script fails at step 1

**Solution:**

1. Verify IAM permissions:
```bash
aws sts get-caller-identity

# Your IAM user/role needs:
# - secretsmanager:GetSecretValue
# - kms:Decrypt (for the KMS key)
```

2. Check secret exists:
```bash
aws secretsmanager list-secrets \
  --filters Key=name,Values=bedrock-cost-keeper/dev
```

3. Test secret retrieval:
```bash
aws secretsmanager get-secret-value \
  --secret-id bedrock-cost-keeper/dev/jwt-secret
```

### Issue: Port already in use

**Symptoms:**
- Error: "bind: address already in use"
- Cannot start containers

**Solution:**

1. Find process using the port:
```bash
lsof -i :8000  # For DynamoDB
lsof -i :8080  # For API
```

2. Stop conflicting process or change ports in `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"  # Use different host port
```

### Issue: Test script hangs or times out

**Symptoms:**
- Request never completes
- Timeout errors

**Solution:**

1. Check service is running:
```bash
curl http://localhost:8080/health
```

2. Check for network issues:
```bash
finch network ls
```

3. Increase timeout in test script:
```python
# Edit manual_test.py
response = requests.post(url, headers=headers, json=body, timeout=30)  # Increase from 10
```

### Issue: DynamoDB tables not created

**Symptoms:**
- Error: "Cannot do operations on a non-existent table"

**Solution:**

1. List tables:
```bash
./scripts/dynamodb.sh list
```

2. Reinitialize:
```bash
./scripts/dynamodb.sh clear
./scripts/dynamodb.sh init
```

3. Verify table names match configuration in `.env`

---

## Success Criteria

Your local development environment is successfully set up when:

✅ All manual test steps completed without errors
✅ Inference profile successfully registered and used
✅ Usage data correctly calculated and stored
✅ Aggregates match expected values (tokens and costs)
✅ Logs show no errors or warnings
✅ AWS CloudTrail shows Bedrock invocations
✅ DynamoDB contains expected data
✅ API health endpoint returns 200 OK

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Your Computer                          │
│                                                              │
│  ┌──────────────┐         ┌─────────────────┐              │
│  │              │         │                 │              │
│  │  DynamoDB    │◄────────┤   API Service   │              │
│  │  Local       │         │   (Container)   │              │
│  │  (Container) │         │                 │              │
│  │              │         └────────┬────────┘              │
│  └──────────────┘                  │                        │
│       :8000                         │                        │
│                                     │ AWS SDK                │
└─────────────────────────────────────┼────────────────────────┘
                                      │
                                      ▼
                        ┌─────────────────────────┐
                        │       AWS Cloud         │
                        │                         │
                        │  ┌──────────────────┐  │
                        │  │  Secrets Manager │  │
                        │  │  - JWT Secret    │  │
                        │  │  - API Key       │  │
                        │  └──────────────────┘  │
                        │                         │
                        │  ┌──────────────────┐  │
                        │  │  Bedrock         │  │
                        │  │  - Nova Lite     │  │
                        │  │  - Inf. Profile  │  │
                        │  └──────────────────┘  │
                        │                         │
                        └─────────────────────────┘
```

## What's Running Where

| Component | Location | Port | Purpose |
|-----------|----------|------|---------|
| DynamoDB | Local container | 8000 | Data storage |
| API Service | Local container | 8080 | REST API |
| Secrets Manager | AWS | N/A | Secure credential storage |
| Inference Profile | AWS | N/A | Bedrock model access |

---

## Next Steps

Once local validation is complete:

1. **Run Integration Tests**: Execute the full test suite
   ```bash
   ./scripts/dynamodb.sh test
   ```

2. **Test Additional Scenarios**:
   - Multiple applications under one organization
   - Quota exhaustion and model downgrading
   - Different AWS regions
   - Error handling

3. **Deploy to AWS Staging**: Use CloudFormation to deploy full infrastructure

4. **Run Smoke Tests**: Verify staging environment works correctly

---

## Additional Resources

- [API Specification](./api_spec.md)
- [Database Schema](./db_spec.md)
- [Application Specification](./app_spec.md)
- [CloudFormation Templates](../cloudformation/dev/README.md)
- [DynamoDB Scripts](../scripts/dynamodb.sh)

---

## Getting Help

If you encounter issues not covered in this guide:

1. Check API logs: `finch logs bedrock-cost-keeper-api-local`
2. Check test logs: `test-client/logs/manual_test_*.log`
3. Review CloudFormation events: `aws cloudformation describe-stack-events --stack-name bedrock-cost-keeper-dev-minimal`
4. Consult AWS Bedrock documentation: https://docs.aws.amazon.com/bedrock/

---

**Last Updated**: 2026-01-31
**Version**: 1.0.0
