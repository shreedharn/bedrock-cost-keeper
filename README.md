# Bedrock Cost Keeper

A REST service that helps applications manage Amazon Bedrock model costs through intelligent model selection based on daily spend quotas.

## What is Bedrock Cost Keeper?

Bedrock Cost Keeper is a **client-driven, eventually consistent REST service** that enables applications to:

- Track and aggregate Amazon Bedrock usage costs in real-time
- Select models intelligently based on daily budget quotas
- Support multi-tenant organizations with flexible quota scoping
- Provide usage analytics and cost visibility

**Key Principle**: This is a **helper service, not an enforcer**. Applications make their own decisions about which Bedrock models to use, with the service providing recommendations based on quota awareness.

## Motivation

When building applications powered by Amazon Bedrock, managing costs across multiple models and teams can be challenging:

- **Cost visibility**: Teams need real-time visibility into Bedrock spending
- **Budget management**: Organizations need to enforce daily/monthly budget limits
- **Model flexibility**: Applications should automatically switch to cheaper models when budgets are tight
- **Multi-tenancy**: Different teams/apps need independent quota management

Bedrock Cost Keeper solves these challenges with a lightweight, scalable service that integrates seamlessly with existing Bedrock workflows.

## Architecture Overview

```
┌─────────────────-----┐
│  Application         │
│                      │
│  1. Get model config │◄──┐
│  2. Call Bedrock     │   │
│  3. Submit cost      │   │ REST API
└────────┬────────-----┘   │
         │                 │
         ▼                 │
┌──────────────────────────────┐
│  Bedrock Cost Keeper Service │
│  ┌────────────────────────┐  │
│  │  FastAPI + ECS Fargate │  │
│  └────────┬───────────────┘  │
│           │                  │
│  ┌────────▼───────────────┐  │
│  │  DynamoDB              │  │
│  │  - Config              │  │
│  │  - Usage Aggregates    │  │
│  │  - Daily Totals        │  │
│  │  - Pricing Cache       │  │
│  └────────────────────────┘  │
└──────────────────────────────┘
```

For detailed client integration flow diagrams including Normal Mode and Tight Mode operation, see [Client Integration Flow](./docs/app_spec.md#client-integration-flow).

## Core Features

### Intelligent Model Selection
- Recommends Bedrock models based on current quota status
- Automatic fallback to cheaper alternatives when budgets exceeded
- Sticky fallback prevents oscillation between models

### Real-time Cost Tracking
- Post-request metering with eventual consistency
- Sharded aggregation prevents hot DynamoDB partitions
- Sub-minute aggregation lag

### Multi-tenant Support
- Organization and application hierarchy
- Flexible quota scoping (org-wide or per-app)
- Independent configurations per tenant

### Secure Authentication
- JWT-based authentication (OAuth2 client credentials)
- Token revocation support
- Credential rotation with grace periods

### Usage Analytics
- Daily and historical usage queries
- Cost breakdown by model and application
- Real-time quota status

## Goals

1. **Cost Efficiency**: Enable organizations to optimize Bedrock spending through intelligent model selection
2. **Scalability**: Handle high-throughput workloads with minimal infrastructure cost
3. **Simplicity**: Provide a simple REST API that integrates easily into existing applications
4. **Reliability**: Eventual consistency with acceptable overrun tolerance (<5% of quota)
5. **Flexibility**: Support N models with label-based configuration for easy model upgrades

## Design Principles

- **Client-driven**: Applications make final decisions; service provides guidance
- **Eventually consistent**: Accept small overruns for better performance
- **Horizontally scalable**: Stateless service design with sharded data
- **Cost-conscious**: Minimize infrastructure costs while maintaining reliability
- **Simple integration**: REST API with standard OAuth2 authentication

## Documentation

### Core Specifications
- **[Application Specification](./docs/app_spec.md)** - System architecture, operating modes, client integration
- **[Database Schema](./docs/db_spec.md)** - DynamoDB table design, access patterns, anti-hot-partition techniques
- **[API Reference](./docs/api_spec.md)** - Complete REST API documentation with examples

### Deployment & Operations
- **[Deployment Guide](./docs/DEPLOYMENT.md)** - Step-by-step AWS deployment instructions
- **[CloudFormation Templates](./cloudformation/README.md)** - IaC templates for AWS deployment

### Testing & Development
- **[Integration Testing](./docs/integration_testing.md)** - Integration test guide
- **[Test Client](./test-client/README.md)** - End-to-end test client usage

## Quick Start

### Prerequisites

- Python 3.12+
- Docker (for local development)
- AWS CLI v2 (for deployment)
- DynamoDB Local (for testing)

### Local Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd bedrock_metering
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Run database migrations** (if using PostgreSQL)
   ```bash
   # For local testing with DynamoDB Local
   docker run -p 8000:8000 amazon/dynamodb-local
   ```

5. **Start the service**
   ```bash
   python run.py
   ```

   The service will be available at `http://localhost:8000`

### Running Tests

#### Unit Tests
```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ -v --cov=src --cov-report=html
```

#### Integration Tests
```bash
# Run integration tests (requires DynamoDB Local or AWS credentials)
pytest tests/integration/ -v

# Run specific test module
pytest tests/integration/test_cost_submission.py -v
```

#### API Tests
```bash
# Start the service locally first
python run.py &

# Run API tests
pytest tests/api/ -v

# Or use the test client
cd test-client
python bedrock_client.py
```

See [Integration Testing Guide](./docs/integration_testing.md) for detailed testing instructions.

### Local Development with Docker

```bash
# Build Docker image
docker build -t bedrock-cost-keeper -f deployment/Dockerfile .

# Run container
docker run -p 8000:8000 \
  -e DEBUG=true \
  -e AWS_REGION=us-east-1 \
  bedrock-cost-keeper
```

## AWS Deployment

### Prerequisites
- Existing VPC with public and private subnets
- ACM certificate for HTTPS
- AWS account with appropriate permissions

### Deploy Infrastructure

```bash
# 1. Generate secrets
cd deployment/scripts
./create-secrets.sh dev

# 2. Update parameters
vi cloudformation/parameters/dev.json

# 3. Deploy CloudFormation stack
./deploy.sh dev
```

See [DEPLOYMENT.md](./docs/DEPLOYMENT.md) for complete deployment instructions.

## Usage Example

### 1. Register Organization
```bash
curl -X PUT https://api.example.com/api/v1/orgs/{org_id} \
  -H "X-API-Key: <provisioning-key>" \
  --data '{
    "org_name": "my-org",
    "timezone": "America/New_York",
    "quota_scope": "APP",
    "model_ordering": ["premium", "standard", "economy"],
    "quotas": {
      "premium": 10000000,
      "standard": 5000000,
      "economy": 2000000
    }
  }'
```

### 2. Authenticate
```python
import requests

response = requests.post('https://api.example.com/auth/token', json={
    'client_id': 'org-xxx-app-yyy',
    'client_secret': 'secret',
    'grant_type': 'client_credentials'
})
access_token = response.json()['access_token']
```

### 3. Get Model Recommendation
```python
response = requests.get(
    f'https://api.example.com/api/v1/orgs/{org_id}/apps/{app_id}/model-selection',
    headers={'Authorization': f'Bearer {access_token}'}
)
model = response.json()['recommended_model']['bedrock_model_id']
```

### 4. Call Bedrock
```python
import boto3

bedrock = boto3.client('bedrock-runtime')
response = bedrock.converse(
    modelId=model,
    messages=[{'role': 'user', 'content': [{'text': 'Hello'}]}]
)
```

### 5. Submit Cost
```python
requests.post(
    f'https://api.example.com/api/v1/orgs/{org_id}/apps/{app_id}/costs',
    headers={'Authorization': f'Bearer {access_token}'},
    json={
        'request_id': str(uuid.uuid4()),
        'model_label': 'premium',
        'bedrock_model_id': model,
        'input_tokens': response['usage']['inputTokens'],
        'output_tokens': response['usage']['outputTokens'],
        'cost_usd_micros': calculated_cost,
        'status': 'OK',
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
)
```

See [API Reference](./docs/api_spec.md) for complete API documentation.

## Project Structure

```
bedrock_metering/
├── src/                          # Application source code
│   ├── api/                      # FastAPI endpoints
│   ├── models/                   # Data models
│   ├── services/                 # Business logic
│   └── utils/                    # Utilities
├── tests/                        # Test suite
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   └── api/                      # API tests
├── cloudformation/               # Infrastructure as Code
│   ├── master-stack.yaml         # Main CloudFormation template
│   ├── stacks/                   # Nested stack templates
│   └── parameters/               # Environment configurations
├── deployment/                   # Deployment files
│   ├── Dockerfile                # Container definition
│   ├── buildspec.yml             # CI/CD build spec
│   └── scripts/                  # Deployment scripts
├── test-client/                  # End-to-end test client
│   └── bedrock_client.py         # Test client implementation
├── docs/                         # Documentation
│   └── DEPLOYMENT.md             # Deployment guide
├── config.yaml                   # Service configuration
├── requirements.txt              # Python dependencies
└── run.py                        # Application entry point
```

## Configuration

### Main Configuration (`config.yaml`)
- Model label definitions and Bedrock ID mappings
- Default pricing (fallback)
- System-wide defaults (shard count, thresholds)
- REST API settings

### Organization Configuration (DynamoDB)
- Timezone and quota scope
- Model ordering (fallback chain)
- Daily quotas per model
- App-specific overrides

See [Application Specification](./docs/app_spec.md) for configuration details.

See [DEPLOYMENT.md](./docs/DEPLOYMENT.md) for detailed cost breakdown.

## Security
- JWT-based authentication with token revocation
- Credential rotation 
- One-time secret retrieval tokens with expiry
- All data encrypted at rest (DynamoDB, Secrets Manager)
- Private subnet deployment (no public IPs for tasks)
- HTTPS-only API (enforced by ALB)


### Development Guidelines

- Follow PEP 8 style guide
- Write docstrings for all public functions
- Update documentation for API changes
- Add integration tests for new endpoints

## Troubleshooting

See [DEPLOYMENT.md](./docs/DEPLOYMENT.md#troubleshooting) for detailed troubleshooting.


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---
## Support
- **Documentation**: See [docs/](./docs/) directory
- **Issues**: Report bugs via GitHub Issues
- **Questions**: Open a GitHub Discussion
---
