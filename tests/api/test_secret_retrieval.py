"""Tests for secret retrieval endpoints."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch


class TestOrgSecretRetrievalEndpoint:
    """Tests for GET /orgs/{org_id}/credentials/secret endpoint."""

    @pytest.mark.asyncio
    async def test_retrieve_org_secret_success(
        self, test_client, mock_db, provisioning_headers, mock_org_config
    ):
        """Test successful org secret retrieval with valid token."""
        # Mock the token validation and secret retrieval
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.validate_secret_retrieval_token = AsyncMock(return_value={
            'token': 'valid-token-123',
            'scope': 'org',
            'org_id': 'test-org-123',
            'app_id': None,
            'expires_at_epoch': int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
            'used': False
        })
        mock_db.mark_token_as_used = AsyncMock()
        mock_db.get_org_secret = AsyncMock(return_value="actual-secret-value-base64")

        response = test_client.get(
            "/api/v1/orgs/test-org-123/credentials/secret",
            headers=provisioning_headers,
            params={"token": "valid-token-123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == "test-org-123"
        assert "client_secret" in data
        assert data["client_secret"] == "actual-secret-value-base64"
        assert "expires_at" in data
        assert "retrieved_at" in data

        # Verify token was marked as used
        mock_db.mark_token_as_used.assert_called_once_with("valid-token-123")

    @pytest.mark.asyncio
    async def test_retrieve_org_secret_token_expired(
        self, test_client, mock_db, provisioning_headers, mock_org_config
    ):
        """Test secret retrieval with expired token."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)

        # Token expired 5 minutes ago
        mock_db.validate_secret_retrieval_token = AsyncMock(return_value={
            'token': 'expired-token-123',
            'scope': 'org',
            'org_id': 'test-org-123',
            'app_id': None,
            'expires_at_epoch': int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp()),
            'used': False
        })

        response = test_client.get(
            "/api/v1/orgs/test-org-123/credentials/secret",
            headers=provisioning_headers,
            params={"token": "expired-token-123"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "expired" in data["error"].lower() or "expired" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_retrieve_org_secret_token_already_used(
        self, test_client, mock_db, provisioning_headers, mock_org_config
    ):
        """Test secret retrieval with already-used token (single-use constraint)."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)

        # Token already used
        mock_db.validate_secret_retrieval_token = AsyncMock(return_value={
            'token': 'used-token-123',
            'scope': 'org',
            'org_id': 'test-org-123',
            'app_id': None,
            'expires_at_epoch': int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
            'used': True
        })

        response = test_client.get(
            "/api/v1/orgs/test-org-123/credentials/secret",
            headers=provisioning_headers,
            params={"token": "used-token-123"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "used" in data["error"].lower() or "used" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_retrieve_org_secret_invalid_token(
        self, test_client, mock_db, provisioning_headers, mock_org_config
    ):
        """Test secret retrieval with invalid/malformed token."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.validate_secret_retrieval_token = AsyncMock(return_value=None)

        response = test_client.get(
            "/api/v1/orgs/test-org-123/credentials/secret",
            headers=provisioning_headers,
            params={"token": "invalid-token"}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_retrieve_org_secret_missing_token(
        self, test_client, mock_db, provisioning_headers
    ):
        """Test secret retrieval without token parameter."""
        response = test_client.get(
            "/api/v1/orgs/test-org-123/credentials/secret",
            headers=provisioning_headers
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_retrieve_org_secret_wrong_scope(
        self, test_client, mock_db, provisioning_headers, mock_org_config
    ):
        """Test secret retrieval with token for different org."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)

        # Token is valid but for different org
        mock_db.validate_secret_retrieval_token = AsyncMock(return_value={
            'token': 'wrong-org-token',
            'scope': 'org',
            'org_id': 'different-org-id',
            'app_id': None,
            'expires_at_epoch': int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
            'used': False
        })

        response = test_client.get(
            "/api/v1/orgs/test-org-123/credentials/secret",
            headers=provisioning_headers,
            params={"token": "wrong-org-token"}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_retrieve_org_secret_without_api_key(
        self, test_client
    ):
        """Test secret retrieval without provisioning API key."""
        response = test_client.get(
            "/api/v1/orgs/test-org-123/credentials/secret",
            params={"token": "some-token"}
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_retrieve_org_secret_invalid_api_key(
        self, test_client
    ):
        """Test secret retrieval with invalid API key."""
        response = test_client.get(
            "/api/v1/orgs/test-org-123/credentials/secret",
            headers={"X-API-Key": "invalid-key"},
            params={"token": "some-token"}
        )

        assert response.status_code == 401


class TestAppSecretRetrievalEndpoint:
    """Tests for GET /orgs/{org_id}/apps/{app_id}/credentials/secret endpoint."""

    @pytest.mark.asyncio
    async def test_retrieve_app_secret_success(
        self, test_client, mock_db, provisioning_headers,
        mock_org_config, mock_app_config
    ):
        """Test successful app secret retrieval with valid token."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)

        # Mock token validation for app scope
        mock_db.validate_secret_retrieval_token = AsyncMock(return_value={
            'token': 'app-token-123',
            'scope': 'app',
            'org_id': 'test-org-123',
            'app_id': 'test-app',
            'expires_at_epoch': int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
            'used': False
        })
        mock_db.mark_token_as_used = AsyncMock()
        mock_db.get_app_secret = AsyncMock(return_value="app-secret-value-base64")

        response = test_client.get(
            "/api/v1/orgs/test-org-123/apps/test-app/credentials/secret",
            headers=provisioning_headers,
            params={"token": "app-token-123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == "test-org-123"
        assert data["app_id"] == "test-app"
        assert "client_secret" in data
        assert data["client_secret"] == "app-secret-value-base64"
        assert "expires_at" in data
        assert "retrieved_at" in data

        mock_db.mark_token_as_used.assert_called_once_with("app-token-123")

    @pytest.mark.asyncio
    async def test_retrieve_app_secret_token_expired(
        self, test_client, mock_db, provisioning_headers,
        mock_org_config, mock_app_config
    ):
        """Test app secret retrieval with expired token (> 10 minutes)."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)

        # Token expired 11 minutes ago
        mock_db.validate_secret_retrieval_token = AsyncMock(return_value={
            'token': 'expired-app-token',
            'scope': 'app',
            'org_id': 'test-org-123',
            'app_id': 'test-app',
            'expires_at_epoch': int((datetime.now(timezone.utc) - timedelta(minutes=11)).timestamp()),
            'used': False
        })

        response = test_client.get(
            "/api/v1/orgs/test-org-123/apps/test-app/credentials/secret",
            headers=provisioning_headers,
            params={"token": "expired-app-token"}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_retrieve_app_secret_token_already_used(
        self, test_client, mock_db, provisioning_headers,
        mock_org_config, mock_app_config
    ):
        """Test app secret retrieval with already-used token."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)

        mock_db.validate_secret_retrieval_token = AsyncMock(return_value={
            'token': 'used-app-token',
            'scope': 'app',
            'org_id': 'test-org-123',
            'app_id': 'test-app',
            'expires_at_epoch': int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
            'used': True
        })

        response = test_client.get(
            "/api/v1/orgs/test-org-123/apps/test-app/credentials/secret",
            headers=provisioning_headers,
            params={"token": "used-app-token"}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_retrieve_app_secret_org_not_found(
        self, test_client, mock_db, provisioning_headers
    ):
        """Test app secret retrieval when org doesn't exist."""
        mock_db.get_org_config = AsyncMock(return_value=None)

        response = test_client.get(
            "/api/v1/orgs/test-org-123/apps/test-app/credentials/secret",
            headers=provisioning_headers,
            params={"token": "some-token"}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_retrieve_app_secret_app_not_found(
        self, test_client, mock_db, provisioning_headers, mock_org_config
    ):
        """Test app secret retrieval when app doesn't exist."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=None)

        response = test_client.get(
            "/api/v1/orgs/test-org-123/apps/nonexistent-app/credentials/secret",
            headers=provisioning_headers,
            params={"token": "some-token"}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_retrieve_app_secret_wrong_app_scope(
        self, test_client, mock_db, provisioning_headers,
        mock_org_config, mock_app_config
    ):
        """Test app secret retrieval with token for different app."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)

        # Token is for different app
        mock_db.validate_secret_retrieval_token = AsyncMock(return_value={
            'token': 'wrong-app-token',
            'scope': 'app',
            'org_id': 'test-org-123',
            'app_id': 'different-app',
            'expires_at_epoch': int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
            'used': False
        })

        response = test_client.get(
            "/api/v1/orgs/test-org-123/apps/test-app/credentials/secret",
            headers=provisioning_headers,
            params={"token": "wrong-app-token"}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_retrieve_app_secret_missing_token(
        self, test_client, mock_db, provisioning_headers
    ):
        """Test app secret retrieval without token parameter."""
        response = test_client.get(
            "/api/v1/orgs/test-org-123/apps/test-app/credentials/secret",
            headers=provisioning_headers
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_token_replay_attack_prevention(
        self, test_client, mock_db, provisioning_headers,
        mock_org_config, mock_app_config
    ):
        """Test that token replay attacks are prevented (single-use tokens)."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)

        # First request - token is valid
        mock_db.validate_secret_retrieval_token = AsyncMock(return_value={
            'token': 'replay-token',
            'scope': 'app',
            'org_id': 'test-org-123',
            'app_id': 'test-app',
            'expires_at_epoch': int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
            'used': False
        })
        mock_db.mark_token_as_used = AsyncMock()
        mock_db.get_app_secret = AsyncMock(return_value="secret-value")

        # First retrieval should succeed
        response1 = test_client.get(
            "/api/v1/orgs/test-org-123/apps/test-app/credentials/secret",
            headers=provisioning_headers,
            params={"token": "replay-token"}
        )
        assert response1.status_code == 200

        # Token now marked as used
        mock_db.validate_secret_retrieval_token = AsyncMock(return_value={
            'token': 'replay-token',
            'scope': 'app',
            'org_id': 'test-org-123',
            'app_id': 'test-app',
            'expires_at_epoch': int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
            'used': True
        })

        # Second retrieval with same token should fail
        response2 = test_client.get(
            "/api/v1/orgs/test-org-123/apps/test-app/credentials/secret",
            headers=provisioning_headers,
            params={"token": "replay-token"}
        )
        assert response2.status_code == 400
