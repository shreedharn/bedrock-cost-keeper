# Bedrock Cost Keeper Test Client

This test client demonstrates the complete end-to-end workflow for using the Bedrock Cost Keeper service.

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

## Usage

### Basic Test

Run the test client with default settings (5 inference requests):

```bash
python bedrock_client.py
```

### Custom Configuration

Use a different configuration file:

```bash
python bedrock_client.py --config my-config.json
```

### Expected Output

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

## Workflow

1. **Authenticate**: Obtains JWT access token via OAuth2
2. **Get Model Selection**: Queries the service for recommended model based on quotas
3. **Invoke Bedrock**: Calls AWS Bedrock with the recommended model
4. **Submit Usage**: Posts token usage to the service (service calculates cost server-side)
5. **Verify**: Retrieves aggregates to confirm tracking

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
