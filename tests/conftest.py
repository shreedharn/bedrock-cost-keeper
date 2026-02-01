"""Pytest configuration and shared fixtures."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.api.main import app
from src.api import dependencies
from src.infrastructure.database.dynamodb_bridge import DynamoDBBridge
from src.infrastructure.security.jwt_handler import JWTHandler


@pytest.fixture
def mock_db():
    """Mock DynamoDB bridge."""
    mock = AsyncMock(spec=DynamoDBBridge)
    mock.health_check = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def jwt_handler():
    """Real JWT handler for testing."""
    return JWTHandler()


@pytest.fixture
def mock_org_config():
    """Mock organization configuration."""
    return {
        'org_name': 'Test Organization',
        'timezone': 'America/New_York',
        'quota_scope': 'ORG',
        'model_ordering': ['premium', 'standard', 'economy'],
        'quotas': {
            'premium': 1000000,
            'standard': 500000,
            'economy': 100000
        },
        'client_id': 'org-test-org-123',
        'client_secret_hash': 'hashed_secret',
        'client_secret_created_at_epoch': int(datetime.now(timezone.utc).timestamp()),
        'created_at_epoch': int(datetime.now(timezone.utc).timestamp())
    }


@pytest.fixture
def mock_app_config():
    """Mock application configuration."""
    return {
        'app_name': 'Test Application',
        'model_ordering': ['premium', 'standard'],
        'quotas': {
            'premium': 500000,
            'standard': 250000
        },
        'client_id': 'org-test-org-123-app-test-app',
        'client_secret_hash': 'hashed_secret',
        'client_secret_created_at_epoch': int(datetime.now(timezone.utc).timestamp()),
        'created_at_epoch': int(datetime.now(timezone.utc).timestamp())
    }


@pytest.fixture
def test_client(mock_db):
    """FastAPI test client with mocked dependencies."""
    # Set the mock db_bridge
    dependencies.db_bridge = mock_db

    client = TestClient(app)
    yield client

    # Cleanup
    dependencies.db_bridge = None


@pytest.fixture
def auth_headers(jwt_handler):
    """Generate valid authentication headers."""
    access_token, _ = jwt_handler.create_access_token(
        client_id="org-test-org-123-app-test-app",
        org_id="test-org-123",
        app_id="test-app"
    )
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def provisioning_headers():
    """Generate provisioning API key headers."""
    # This should match the provisioning_api_key in settings
    return {"X-API-Key": "change-me-in-production"}


@pytest.fixture
def mock_metering_service():
    """Mock metering service."""
    with patch('src.domain.services.metering_service.MeteringService') as mock:
        service_instance = MagicMock()
        mock.return_value = service_instance
        yield service_instance


@pytest.fixture
def sample_usage_submission():
    """Sample usage submission data (without cost - calculated server-side)."""
    return {
        "request_id": "550e8400-e29b-41d4-a716-446655440000",
        "model_label": "premium",
        "bedrock_model_id": "amazon.nova-pro-v1:0",
        "input_tokens": 1000,
        "output_tokens": 500,
        "status": "OK",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# Legacy alias for backward compatibility during transition
@pytest.fixture
def sample_cost_submission():
    """Legacy sample cost submission data - use sample_usage_submission instead."""
    return {
        "request_id": "550e8400-e29b-41d4-a716-446655440000",
        "model_label": "premium",
        "bedrock_model_id": "amazon.nova-pro-v1:0",
        "input_tokens": 1000,
        "output_tokens": 500,
        "cost_usd_micros": 45000,  # Deprecated - service calculates cost
        "status": "OK",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@pytest.fixture
def sample_org_registration():
    """Sample organization registration data."""
    return {
        "org_name": "Test Organization",
        "timezone": "America/New_York",
        "quota_scope": "ORG",
        "model_ordering": ["premium", "standard", "economy"],
        "quotas": {
            "premium": 1000000,
            "standard": 500000,
            "economy": 100000
        },
        "overrides": {
            "agg_shard_count": 8,
            "tight_mode_threshold_pct": 95
        }
    }


@pytest.fixture
def sample_app_registration():
    """Sample application registration data."""
    return {
        "app_name": "Test Application",
        "model_ordering": ["premium", "standard"],
        "quotas": {
            "premium": 500000,
            "standard": 250000
        },
        "overrides": {
            "tight_mode_threshold_pct": 90
        }
    }
