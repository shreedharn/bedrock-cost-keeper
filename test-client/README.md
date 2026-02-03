# Bedrock Cost Keeper Test Client

This directory contains test clients for the Bedrock Cost Keeper service.

## Quick Reference

**Which tool should I use?**

- 🔧 **Setting up a new deployment?** → Use `manual_test.py`
- 🐛 **Debugging API issues?** → Use `manual_test.py`
- 🧪 **Testing inference profiles?** → Use `manual_test.py`
- ✅ **Testing existing deployment?** → Use `bedrock_client.py`
- 🔄 **Building automation/integration?** → Use `bedrock_client.py`

## Features

- OAuth2 client_credentials authentication
- Model selection based on quotas
- AWS Bedrock invocation via boto3
- Cost calculation from token usage
- Cost submission to the service
- Aggregate verification

## Prerequisites

1. Python 3.9 or higher
2. AWS credentials configured (for Bedrock access)
3. Bedrock Cost Keeper service deployed
4. Client credentials from the seed script

## Installation

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Configure AWS credentials:

```bash
aws configure
# or set environment variables:
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_REGION=us-east-1
```

## Configuration

### Manual Test Configuration (manual_test_config.json)

For manual testing with inference profiles:

1. **Copy the example configuration to the project root:**
   ```bash
   # From the project root directory
   cp test-client/manual_test_config.json.example manual_test_config.json
   ```

   **Note:** The config file must be in the project root.

2. **Update with your actual values:**

   Get your deployment values from `cloudformation/dev/.env.cloudformation`:

   - `inference_profile_arn`: Use `SAMPLE_APP_INFERENCE_PROFILE_ARN` from .env.cloudformation
   - `jwt_secret_name`: Use `JWT_SECRET_NAME` from .env.cloudformation
   - `provisioning_api_key_secret_name`: Use `PROVISIONING_API_KEY_NAME` from .env.cloudformation
   - `aws_region`: Use `AWS_REGION` from .env.cloudformation

   Example:
   ```json
   {
     "inference_profile_arn": "arn:aws:bedrock:us-east-1:YOUR_ACCOUNT_ID:application-inference-profile/YOUR_PROFILE_ID",
     "jwt_secret_name": "bedrock-cost-keeper/dev/jwt-secret",
     "provisioning_api_key_secret_name": "bedrock-cost-keeper/dev/provisioning-api-key"
   }
   ```


### Standard Configuration (config.json)

Edit `config.json` with your credentials:

```json
{
  "service_url": "https://your-alb-dns-name",
  "client_id": "org-XXXXXX-app-test-app",
  "client_secret": "your_client_secret_from_seed_script",
  "org_id": "your_org_id_from_seed_script",
  "app_id": "test-app",
  "aws_region": "us-east-1",
  "test_prompt": "What is the capital of France?"
}
```

### Getting Credentials

After running the seed script:

```bash
cd deployment/scripts
python seed-dynamodb.py dev
```

You'll receive output like:

```
Organization ID: 550e8400-e29b-41d4-a716-446655440000
Client ID: org-550e8400-e29b-41d4-a716-446655440000-app-test-app
Client Secret: AbCdEfGhIjKlMnOpQrStUvWxYz0123456789
```

Use these values to update your `config.json`.

## Test Clients Overview

This directory contains two different test clients for different use cases:

### 1. manual_test.py - Interactive Manual Testing

**Purpose:** Step-by-step interactive testing of the complete API workflow

**Configuration:** Uses `manual_test_config.json`

**Features:**
- Interactive prompts at each step
- Visual output with tables and panels (uses `rich` library)
- Tests the full provisioning workflow:
  1. Create Organization (via provisioning API)
  2. Create Application
  3. Authenticate
  4. Register Inference Profile
  5. Get Model Selection
  6. Invoke Bedrock
  7. Submit Usage
  8. Check Aggregates
- Logs saved to `logs/manual_test_YYYYMMDD_HHMMSS.log`
- Pause/resume capability for debugging

**When to use:**
- Setting up a new deployment
- Debugging API issues
- Understanding the complete workflow
- Testing inference profile registration

**Run:**
```bash
python manual_test.py
```

The script will prompt you at each step. You can:
- Review request/response details
- Skip steps if needed
- Continue after errors for debugging

### 2. bedrock_client.py - Automated Client

**Purpose:** Automated testing and integration example

**Configuration:** Uses `config.json`

**Features:**
- Runs 5 inference requests automatically
- Demonstrates OAuth2 authentication
- Shows model selection based on quotas
- Submits usage and verifies aggregation
- Suitable for CI/CD integration

**When to use:**
- Testing an already-configured deployment
- Integration testing
- Load testing (by modifying request count)
- Example for client implementation

**Run:**
```bash
python bedrock_client.py
```

Or with custom config:
```bash
python bedrock_client.py --config my-config.json
```

## Usage Examples

### Quick Start - Manual Testing

For first-time setup or debugging:

```bash
# 1. Setup config (from project root)
cp test-client/manual_test_config.json.example manual_test_config.json
# Edit manual_test_config.json with your values

# 2. Run interactive test from project root
python project-root/test-client/manual_test.py
```

Or with VS Code debugger: Use the "Debug Test Client" launch configuration.

The script will guide you through each step with prompts and visual feedback.

### Quick Start - Automated Testing

For pre-configured deployments:

```bash
# 1. Setup config (requires existing org/app credentials)
cp config.json.example config.json  # If example exists
# Edit config.json with your credentials

# 2. Run automated test
python bedrock_client.py
```

Or with custom configuration:

```bash
python bedrock_client.py --config my-config.json
```

### Expected Output (bedrock_client.py)

```
============================================================
Running 5 inference requests
============================================================

--- Request 1/5 ---
[INFO] Authenticating with Bedrock Cost Keeper...
[INFO] Authenticated successfully. Token expires in 3600 seconds
[INFO] Getting model selection recommendation...
[INFO] Recommended model: claude-3-5-sonnet-20241022-v2
[INFO] Model ID: anthropic.claude-3-5-sonnet-20241022-v2:0
[INFO] Invoking Bedrock model: anthropic.claude-3-5-sonnet-20241022-v2:0
[INFO] Bedrock invocation successful
[INFO] Response: The capital of France is Paris.
[INFO] Input tokens: 15, Output tokens: 8
[INFO] Cost: $0.000345 (345 USD micros)
[INFO] Submitting cost data for request abc123...
[INFO] Cost submitted successfully

--- Request 2/5 ---
...

============================================================
Final Summary
============================================================
Successful requests: 5/5
Total cost (calculated): $0.001725

Verifying with service...
[INFO] Getting aggregates for date: 2024-01-15
[INFO] Total cost today: $0.001725
[INFO] Total requests: 5

============================================================
Service Aggregates
============================================================
{
  "date": "2024-01-15",
  "total_cost_usd": 0.001725,
  "total_requests": 5,
  "by_model": {
    "claude-3-5-sonnet-20241022-v2": {
      "requests": 5,
      "input_tokens": 75,
      "output_tokens": 40,
      "cost_usd": 0.001725
    }
  }
}

[INFO] Test completed successfully!
```

### Expected Output (manual_test.py)

```
╭─────────────────────────────────────────────────────╮
│ Bedrock Cost Keeper - Manual API Test              │
│ Service URL: http://localhost:8080                  │
│ AWS Profile: default                                │
│ AWS Region: us-east-1                               │
│ Log File: logs/manual_test_20260202_143022.log     │
╰─────────────────────────────────────────────────────╯

────────────── Step 1/8: Create Organization ──────────────

Run this step? [Y/n]: y

REQUEST
Method: POST
URL: http://localhost:8080/api/v1/admin/orgs
Headers: {...}
Body: {...}

Press Enter to send request...

RESPONSE (201)
Status: 201 Created
Body: {
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "client_id": "org-550e8400-...",
  "client_secret": "AbCdEf..."
}

✓ Organization created successfully

Press Enter to continue...

────────────── Step 2/8: Create Application ───────────────
...
```

The script provides:
- Colored, formatted output using the `rich` library
- Pause points to review each step
- Detailed request/response logging
- Option to skip or retry steps
- Final summary with log file location

## Workflows

### manual_test.py - Full Provisioning Workflow

1. **Create Organization**: Register org via provisioning API (requires API key from Secrets Manager)
2. **Create Application**: Register app under the org
3. **Authenticate**: Get OAuth2 JWT access token using org/app credentials
4. **Register Inference Profile**: (Optional) Register AWS Bedrock inference profile for the app
5. **Get Model Selection**: Query service for recommended model based on quotas
6. **Invoke Bedrock**: Call AWS Bedrock with selected model or inference profile
7. **Submit Usage**: Post token usage to service (cost calculated server-side)
8. **Check Aggregates**: Verify usage tracking and aggregation

### bedrock_client.py - Client Usage Workflow

1. **Authenticate**: Obtains JWT access token via OAuth2 (assumes org/app exist)
2. **Get Model Selection**: Queries the service for recommended model based on quotas
3. **Invoke Bedrock**: Calls AWS Bedrock with the recommended model
4. **Submit Usage**: Posts token usage to the service (service calculates cost server-side)
5. **Verify**: Retrieves aggregates to confirm tracking

### Comparison

| Feature | manual_test.py | bedrock_client.py |
|---------|---------------|-------------------|
| Provisioning | ✅ Creates org/app | ❌ Requires existing setup |
| Inference Profiles | ✅ Registers profiles | ❌ Uses pre-configured models |
| Interaction | Interactive prompts | Fully automated |
| Output | Rich formatted UI | Simple console logs |
| Logging | File + console | Console only |
| Use Case | Setup & debugging | Integration & testing |

## Troubleshooting

### Authentication Failed

**Error**: `Authentication failed: 401 Unauthorized`

**Solution**:
- Verify client_id and client_secret are correct
- Check that the organization/app was created in DynamoDB
- Ensure the service_url is correct and accessible

### Bedrock Access Denied

**Error**: `Bedrock invocation failed: AccessDeniedException`

**Solution**:
- Verify AWS credentials are configured
- Check that your AWS account has Bedrock access enabled
- Ensure the model is available in your region

### Connection Refused

**Error**: `Connection refused` or `Connection timeout`

**Solution**:
- Verify the service is running (check ECS tasks)
- Check ALB health checks are passing
- Verify security groups allow traffic
- Ensure ALB DNS name is correct

### Model Not Available

**Error**: `Model selection failed: No models available`

**Solution**:
- Check that model preferences are configured in DynamoDB
- Verify quotas are not exhausted
- Ensure pricing cache is populated

## Advanced Usage

### Modify Test Prompt

Edit the `test_prompt` in `config.json`:

```json
{
  "test_prompt": "Explain quantum computing in simple terms."
}
```

### Run More Requests

Modify the `run_inference_loop` call in the script:

```python
client.run_inference_loop(count=10)  # Run 10 requests
```

### Test Different Models

Configure different model preferences in DynamoDB:

```python
# In seed-dynamodb.py
'model_preferences': {
    'preferred_models': ['anthropic.claude-3-5-haiku-20241022-v1:0'],
    'fallback_models': ['anthropic.claude-3-5-sonnet-20241022-v2:0'],
    'blocked_models': []
}
```

## Integration with Your Application

To integrate this client into your application:

```python
from bedrock_client import BedrockCostKeeperClient

# Initialize client
client = BedrockCostKeeperClient('config.json')

# Authenticate
client.authenticate()

# Get model recommendation
model = client.get_model_selection()

# Invoke Bedrock
messages = [{'role': 'user', 'content': [{'text': 'Your prompt here'}]}]
response = client.invoke_bedrock(model['model_id'], messages)

# Submit usage (service calculates cost from tokens)
client.submit_usage(
    response['ResponseMetadata']['RequestId'],
    model['model_label'],
    model['model_id'],
    response['usage']['inputTokens'],
    response['usage']['outputTokens']
)
```

## Support

For issues or questions:
- Check CloudWatch logs: `/ecs/bedrock-cost-keeper-{environment}`
- Review DynamoDB tables for configuration
- Verify ECS task health and logs
