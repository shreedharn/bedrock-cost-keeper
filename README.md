# Bedrock Cost Keeper

A lightweight REST service for managing Amazon Bedrock costs through quota-aware model selection and usage tracking.

## What is Bedrock Cost Keeper?

Bedrock Cost Keeper helps applications optimize Amazon Bedrock spending by providing intelligent model recommendations based on daily budget quotas. The service tracks usage across multiple models and organizations, enabling automatic fallback to more cost-effective alternatives when quotas are exceeded.

**Architecture**: Client-driven REST service with eventually consistent usage aggregation (30-60s lag). Applications retain full control over model selection while receiving quota-aware recommendations.

**Key Capabilities:**
- Track usage and costs across multiple Bedrock models with label-based configuration
- Automatically recommend fallback models when daily quotas are exceeded
- Support multi-tenant deployments with organization and application-level quota scoping
- Provide usage analytics with daily and historical aggregate queries

**Design Philosophy**: This is an advisory service, not an enforcement layer. Applications make final model selection decisions based on service recommendations. The eventually consistent design accepts small quota overruns (typically <5%) in exchange for horizontal scalability and low operational overhead.

## Motivation

Organizations deploying Amazon Bedrock at scale face several cost management challenges:

**Cost Control**: Without centralized tracking, Bedrock spending can grow unpredictably across teams and applications. Daily quota limits help prevent budget overruns while maintaining service availability.

**Model Economics**: Bedrock offers models at different price points (e.g., Claude Opus vs Haiku). Applications should intelligently select cheaper alternatives when premium model quotas are exhausted, but building this logic into every application creates duplication and maintenance burden.

**Multi-Tenancy**: Different teams require independent budgets and quota policies. A shared metering service provides consistent quota management without coupling applications to a specific implementation.

**Operational Visibility**: Teams need usage metrics and cost breakdowns by model, application, and organization to understand spending patterns and optimize model selection strategies.

Bedrock Cost Keeper addresses these challenges through a lightweight, horizontally scalable service that integrates with existing Bedrock workflows via a simple REST API.

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

### Quota-Aware Model Selection
- Returns recommended Bedrock model based on current quota consumption
- Automatic fallback to next model in configured ordering when quotas exceeded
- Sticky fallback behavior prevents model oscillation within same day

### Eventually Consistent Usage Tracking
- Async cost submission with 30-60 second aggregation lag
- Sharded counter architecture prevents DynamoDB hot partitions at scale
- Acceptable quota overruns (<5%) in exchange for horizontal scalability

### Multi-Tenant Quota Management
- Organization and application hierarchy for quota isolation
- Flexible scoping: organization-wide quotas or per-application quotas
- Label-based model configuration allows model upgrades without client changes

### OAuth2 Client Credentials Authentication
- JWT access tokens (1 hour) and refresh tokens (30 days)
- Token revocation for immediate access removal
- Zero-downtime credential rotation with configurable grace periods

### Usage Analytics and Reporting
- Daily aggregate queries by organization, application, and model
- Historical data retention with configurable TTL
- Quota status and cost breakdown endpoints

## Design Goals

1. **Cost Optimization**: Enable budget-conscious model selection across multiple Bedrock models with configurable daily quotas
2. **Horizontal Scalability**: Stateless architecture with sharded data layer supports high-throughput workloads 
3. **Simple Integration**: Standard REST API with OAuth2 authentication requires minimal client-side changes
4. **Operational Reliability**: Eventual consistency design accepts small quota overruns (<5%) to avoid coordination overhead
5. **Configuration Flexibility**: Label-based model abstraction allows model version upgrades without application redeployment

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
