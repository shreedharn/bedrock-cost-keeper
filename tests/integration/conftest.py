"""Integration test fixtures for DynamoDB Local."""

import pytest
import asyncio
from datetime import datetime, timezone
import os
from fastapi.testclient import TestClient

from src.api.main import app
from src.api import dependencies
from src.infrastructure.database.dynamodb_bridge import DynamoDBBridge
from src.infrastructure.security.jwt_handler import JWTHandler


# Set environment variables for local DynamoDB
os.environ['AWS_ENDPOINT_URL'] = 'http://localhost:8000'
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['AWS_ACCESS_KEY_ID'] = 'fake'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'fake'


@pytest.fixture(scope="function")
def event_loop():
    """Create an instance of the event loop for each test."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    # Close any remaining tasks
    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()
    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()


@pytest.fixture(scope="function")
async def dynamodb_bridge():
    """Create a real DynamoDB bridge connected to local instance."""
    bridge = DynamoDBBridge()
    yield bridge

    # Cleanup: close the dynamodb resource if it was created
    if bridge._dynamodb is not None:
        await bridge._dynamodb.__aexit__(None, None, None)
        bridge._dynamodb = None


@pytest.fixture(autouse=True)
async def clear_usage_data(dynamodb_bridge):
    """Clear usage and aggregates data before each test (not config)."""
    import aioboto3

    session = aioboto3.Session()

    async with session.resource(
        'dynamodb',
        endpoint_url='http://localhost:8000',
        region_name='us-east-1',
        aws_access_key_id='fake',
        aws_secret_access_key='fake'
    ) as dynamodb:

        # Clear usage table
        usage_table = await dynamodb.Table('bedrock-cost-keeper-usage')
        response = await usage_table.scan()
        for item in response.get('Items', []):
            await usage_table.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})

        # Clear aggregates table
        agg_table = await dynamodb.Table('bedrock-cost-keeper-aggregates')
        response = await agg_table.scan()
        for item in response.get('Items', []):
            await agg_table.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})


@pytest.fixture(scope="session")
def test_org_credentials_data():
    """Get test organization credentials from local DynamoDB (cached for session)."""
    import aioboto3

    async def fetch_credentials():
        session = aioboto3.Session()

        async with session.resource(
            'dynamodb',
            endpoint_url='http://localhost:8000',
            region_name='us-east-1',
            aws_access_key_id='fake',
            aws_secret_access_key='fake'
        ) as dynamodb:

            config_table = await dynamodb.Table('bedrock-cost-keeper-config')

            # Get the test org
            test_org_id = '550e8400-e29b-41d4-a716-446655440000'
            response = await config_table.get_item(
                Key={
                    'pk': f'ORG#{test_org_id}',
                    'sk': 'CONFIG'
                }
            )

            if 'Item' not in response:
                raise Exception("Test organization not found. Run: python scripts/init_local_dynamodb.py seed")

            org_config = response['Item']

            # Get the app
            app_response = await config_table.get_item(
                Key={
                    'pk': f'ORG#{test_org_id}',
                    'sk': 'APP#test-app'
                }
            )

            app_config = app_response.get('Item')

            return {
                'org_id': test_org_id,
                'app_id': 'test-app',
                'org_client_id': org_config['client_id'],
                'app_client_id': app_config['client_id'] if app_config else None,
                'org_config': org_config,
                'app_config': app_config
            }

    # Run the async function and return the result
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(fetch_credentials())
        return result
    finally:
        loop.close()


@pytest.fixture
def test_org_credentials(test_org_credentials_data):
    """Provide cached test credentials (synchronous)."""
    return test_org_credentials_data


@pytest.fixture
def jwt_handler():
    """Real JWT handler for integration tests."""
    return JWTHandler()


@pytest.fixture
def integration_auth_headers(test_org_credentials, jwt_handler):
    """Generate valid auth headers for integration tests."""
    access_token, _ = jwt_handler.create_access_token(
        client_id=test_org_credentials['app_client_id'],
        org_id=test_org_credentials['org_id'],
        app_id=test_org_credentials['app_id']
    )

    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def integration_test_client(dynamodb_bridge):
    """FastAPI async test client with real DynamoDB connection."""
    import httpx
    from asgi_lifespan import LifespanManager

    # Set the real db_bridge
    dependencies.db_bridge = dynamodb_bridge

    # Use async client with lifespan support
    async with LifespanManager(app) as manager:
        async with httpx.AsyncClient(app=manager.app, base_url="http://testserver") as client:
            yield client

    # Cleanup
    dependencies.db_bridge = None


@pytest.fixture
def sample_usage_data():
    """Sample usage submission data for integration tests (cost calculated server-side)."""
    return {
        "request_id": "550e8400-e29b-41d4-a716-446655440001",
        "model_label": "premium",
        "bedrock_model_id": "amazon.nova-pro-v1:0",
        "input_tokens": 1000,
        "output_tokens": 500,
        "status": "OK",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# Legacy alias for backward compatibility
@pytest.fixture
def sample_cost_data():
    """Legacy sample cost submission data - use sample_usage_data instead."""
    return {
        "request_id": "550e8400-e29b-41d4-a716-446655440001",
        "model_label": "premium",
        "bedrock_model_id": "amazon.nova-pro-v1:0",
        "input_tokens": 1000,
        "output_tokens": 500,
        "cost_usd_micros": 45000,  # Deprecated - service calculates cost
        "status": "OK",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
