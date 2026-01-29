# Integration Testing with Local DynamoDB

This guide explains how to run integration tests against a real DynamoDB Local instance.

## Overview

The integration tests use:
- **DynamoDB Local** running in Docker
- **Real DynamoDB tables** with actual data persistence
- **Real API endpoints** with full request/response flow
- **No mocks** - tests against actual database operations

## Quick Start

### 1. Complete Setup (Recommended)

```bash
# One command to set everything up
./scripts/dynamodb.sh setup
```

This will:
- Start DynamoDB Local in Docker
- Create all required tables
- Seed test data (test org and app)

### 2. Run Integration Tests

```bash
# Run all integration tests
./scripts/dynamodb.sh test

# Or use pytest directly
pytest tests/integration -v -m integration
```

### 3. Stop When Done

```bash
./scripts/dynamodb.sh stop
```

---

## Detailed Setup

### Prerequisites

- **Docker**: Must be installed and running
- **Python 3.12+**: With virtualenv activated
- **Dependencies**: `pip install -r requirements-dev.txt`

### Manual Setup Steps

```bash
# 1. Start DynamoDB Local
./scripts/dynamodb.sh start

# 2. Initialize tables
./scripts/dynamodb.sh init

# 3. Seed test data
./scripts/dynamodb.sh seed

# 4. Verify setup
./scripts/dynamodb.sh status
```

---

## DynamoDB Management Commands

### Container Management

```bash
# Start DynamoDB Local
./scripts/dynamodb.sh start

# Stop DynamoDB Local
./scripts/dynamodb.sh stop

# Restart DynamoDB Local
./scripts/dynamodb.sh restart

# Check status
./scripts/dynamodb.sh status
```

### Data Management

```bash
# Initialize tables (first time only)
./scripts/dynamodb.sh init

# Seed test data
./scripts/dynamodb.sh seed

# Clear all data (keep tables)
./scripts/dynamodb.sh clear

# Reset (clear + seed)
./scripts/dynamodb.sh reset
```

### Inspecting Data

```bash
# List all tables
./scripts/dynamodb.sh list

# View table contents
./scripts/dynamodb.sh scan bedrock-cost-keeper-config
./scripts/dynamodb.sh scan bedrock-cost-keeper-usage
./scripts/dynamodb.sh scan bedrock-cost-keeper-aggregates
```

---

## Test Data

After running `seed`, you'll have:

### Test Organization
- **Org ID**: `550e8400-e29b-41d4-a716-446655440000`
- **Client ID**: `org-550e8400-e29b-41d4-a716-446655440000`
- **Models**: premium, standard, economy
- **Quotas**:
  - Premium: $1.00 daily
  - Standard: $0.50 daily
  - Economy: $0.10 daily

### Test Application
- **App ID**: `test-app`
- **Client ID**: `org-550e8400-e29b-41d4-a716-446655440000-app-test-app`
- **Models**: premium, standard
- **Quotas**:
  - Premium: $0.50 daily
  - Standard: $0.25 daily

**Note**: Client secrets are generated randomly on seed. Check the seed command output for the actual secrets.

---

## Running Tests

### Run All Integration Tests

```bash
pytest tests/integration -v -m integration
```

### Run Specific Test File

```bash
pytest tests/integration/test_usage_integration.py -v
```

### Run Specific Test

```bash
pytest tests/integration/test_usage_integration.py::TestUsageSubmissionIntegration::test_submit_single_usage_to_db -v
```

### Run with Coverage

```bash
pytest tests/integration -v -m integration --cov=src --cov-report=html
```

### Run All Tests (Unit + Integration)

```bash
pytest tests/ -v
```

---

## Integration Test Features

### What's Tested

1. **Usage Submission**
   - Single usage submission to DynamoDB (service calculates cost)
   - Batch usage submission
   - Data persistence verification
   - Idempotency (duplicate request_id)
   - Multiple model support

2. **Aggregation**
   - Daily aggregate updates
   - Multi-model aggregation
   - Aggregate retrieval API

3. **Data Integrity**
   - Correct data format in DynamoDB
   - All required fields present
   - Proper partition/sort key structure

### Test Fixtures

- `dynamodb_bridge`: Real DynamoDB bridge connected to local instance
- `test_org_credentials`: Actual test org/app credentials from DB
- `integration_auth_headers`: Valid JWT tokens for API calls
- `integration_test_client`: FastAPI client with real DB connection
- `sample_usage_data`: Sample usage submission payload (no cost - calculated server-side)

### Test Data Cleanup

Each test automatically clears usage and aggregates data (not config) before running. This ensures:
- Clean state for each test
- No interference between tests
- Predictable test results

---

## Troubleshooting

### DynamoDB Not Starting

```bash
# Check Docker is running
docker ps

# Check logs
docker logs bedrock-metering-dynamodb-local

# Restart Docker and try again
./scripts/dynamodb.sh restart
```

### Tables Not Created

```bash
# Manually initialize
python scripts/init_local_dynamodb.py init

# Check tables exist
./scripts/dynamodb.sh list
```

### Test Failures Due to Missing Data

```bash
# Reset database
./scripts/dynamodb.sh reset

# Verify data was seeded
./scripts/dynamodb.sh scan bedrock-cost-keeper-config
```

### Connection Errors

Make sure DynamoDB Local is accessible:
```bash
# Test connection
curl http://localhost:8000

# Check if port 8000 is in use
lsof -i :8000
```

### AWS CLI Commands

If you have AWS CLI installed:

```bash
# List tables
aws dynamodb list-tables \
    --endpoint-url http://localhost:8000 \
    --region us-east-1

# Describe table
aws dynamodb describe-table \
    --table-name bedrock-cost-keeper-usage \
    --endpoint-url http://localhost:8000 \
    --region us-east-1

# Query specific item
aws dynamodb get-item \
    --table-name bedrock-cost-keeper-config \
    --key '{"pk":{"S":"ORG#550e8400-e29b-41d4-a716-446655440000"},"sk":{"S":"CONFIG"}}' \
    --endpoint-url http://localhost:8000 \
    --region us-east-1
```

---

## Writing New Integration Tests

### Test Template

```python
import pytest


@pytest.mark.integration
class TestMyIntegration:
    """Integration tests for my feature."""

    @pytest.mark.asyncio
    async def test_my_feature(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        dynamodb_bridge
    ):
        """Test description."""
        creds = await test_org_credentials

        # 1. Make API call
        response = integration_test_client.post(
            f"/api/v1/orgs/{creds['org_id']}/my-endpoint",
            headers=await integration_auth_headers,
            json={"data": "test"}
        )

        assert response.status_code == 200

        # 2. Verify data in DynamoDB
        import aioboto3

        session = aioboto3.Session()

        async with session.resource(
            'dynamodb',
            endpoint_url='http://localhost:8000',
            region_name='us-east-1',
            aws_access_key_id='fake',
            aws_secret_access_key='fake'
        ) as dynamodb:

            table = await dynamodb.Table('bedrock-cost-keeper-usage')
            response = await table.scan()
            items = response.get('Items', [])

            # Verify data
            assert len(items) > 0
```

### Best Practices

1. **Always mark with `@pytest.mark.integration`**
2. **Use `@pytest.mark.asyncio` for async tests**
3. **Verify both API response AND database state**
4. **Use fixtures for common setup**
5. **Clean up is automatic** (handled by fixtures)

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  integration-tests:
    runs-on: ubuntu-latest

    services:
      dynamodb:
        image: amazon/dynamodb-local:latest
        ports:
          - 8000:8000

    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -r requirements-dev.txt

      - name: Initialize DynamoDB
        run: |
          python scripts/init_local_dynamodb.py init
          python scripts/init_local_dynamodb.py seed

      - name: Run integration tests
        run: |
          pytest tests/integration -v -m integration

      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

---

## Architecture

### Tables Created

1. **bedrock-cost-keeper-config** (pk, sk)
   - Organization configurations
   - Application configurations
   - Client credentials

2. **bedrock-cost-keeper-usage** (pk, sk)
   - Individual cost submissions
   - Request-level details

3. **bedrock-cost-keeper-aggregates** (pk, sk)
   - Daily aggregates
   - Model-level summaries

4. **bedrock-cost-keeper-tokens** (token_jti + TTL)
   - Revoked tokens
   - Auto-expires via TTL

5. **bedrock-cost-keeper-secrets** (token + TTL)
   - One-time secret retrieval tokens
   - Auto-expires via TTL

### Data Flow

```
API Request
    ↓
FastAPI Endpoint
    ↓
DynamoDB Bridge (real)
    ↓
DynamoDB Local (Docker)
    ↓
Verify in Test
```

---

## Performance

Integration tests are slower than unit tests because they:
- Write to actual database
- Wait for I/O operations
- Start/stop transactions

**Expected Times**:
- Single test: 0.5-2 seconds
- Full integration suite: 10-30 seconds

Use `-m integration` to run only integration tests or `-m "not integration"` to skip them.

---

## Next Steps

1. Run the setup: `./scripts/dynamodb.sh setup`
2. Run tests: `./scripts/dynamodb.sh test`
3. Inspect data: `./scripts/dynamodb.sh scan bedrock-cost-keeper-usage`
4. Write your own integration tests
5. Stop when done: `./scripts/dynamodb.sh stop`

---

## Resources

- [DynamoDB Local Documentation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html)
- [aioboto3 Documentation](https://aioboto3.readthedocs.io/)
- [Pytest Documentation](https://docs.pytest.org/)

---

**Questions or issues?** Check the troubleshooting section or review the test examples in `tests/integration/`.
