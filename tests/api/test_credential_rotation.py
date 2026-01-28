"""Tests for credential rotation endpoints."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch


class TestOrgCredentialRotationEndpoint:
    """Tests for POST /orgs/{org_id}/credentials/rotate endpoint."""

    @pytest.mark.asyncio
    async def test_rotate_org_credentials_success(
        self, test_client, mock_db, provisioning_headers, mock_org_config
    ):
        """Test successful organization credential rotation."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.rotate_org_credentials = AsyncMock()
        mock_db.create_secret_retrieval_token = AsyncMock(
            return_value="rotation-token-123"
        )

        response = test_client.post(
            "/api/v1/orgs/test-org-123/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 24}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == "test-org-123"
        assert data["status"] == "rotated"
        assert "new_credentials" in data
        assert "client_id" in data["new_credentials"]
        assert data["new_credentials"]["client_id"] == "org-test-org-123"
        assert "secret_retrieval" in data["new_credentials"]
        assert "grace_period" in data
        assert data["grace_period"]["hours"] == 24
        assert "old_secret_expires_at" in data["grace_period"]

        mock_db.rotate_org_credentials.assert_called_once()
        mock_db.create_secret_retrieval_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_rotate_org_credentials_with_grace_period(
        self, test_client, mock_db, provisioning_headers, mock_org_config
    ):
        """Test credential rotation with custom grace period."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.rotate_org_credentials = AsyncMock()
        mock_db.create_secret_retrieval_token = AsyncMock(
            return_value="rotation-token-123"
        )

        # Test with 48-hour grace period
        response = test_client.post(
            "/api/v1/orgs/test-org-123/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 48}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["grace_period"]["hours"] == 48

    @pytest.mark.asyncio
    async def test_rotate_org_credentials_zero_grace_period(
        self, test_client, mock_db, provisioning_headers, mock_org_config
    ):
        """Test credential rotation with zero grace period (immediate rotation)."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.rotate_org_credentials = AsyncMock()
        mock_db.create_secret_retrieval_token = AsyncMock(
            return_value="rotation-token-123"
        )

        response = test_client.post(
            "/api/v1/orgs/test-org-123/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["grace_period"]["hours"] == 0

    @pytest.mark.asyncio
    async def test_rotate_org_credentials_invalid_grace_period(
        self, test_client, mock_db, provisioning_headers, mock_org_config
    ):
        """Test credential rotation with invalid grace period."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)

        # Negative grace period should fail
        response = test_client.post(
            "/api/v1/orgs/test-org-123/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": -5}
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_rotate_org_credentials_excessive_grace_period(
        self, test_client, mock_db, provisioning_headers, mock_org_config
    ):
        """Test credential rotation with excessive grace period (> 168 hours)."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)

        # Grace period > 7 days should fail
        response = test_client.post(
            "/api/v1/orgs/test-org-123/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 200}
        )

        # Should be rejected (typically max is 168 hours = 7 days)
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_rotate_org_credentials_org_not_found(
        self, test_client, mock_db, provisioning_headers
    ):
        """Test credential rotation for non-existent org."""
        mock_db.get_org_config = AsyncMock(return_value=None)

        response = test_client.post(
            "/api/v1/orgs/nonexistent-org/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 24}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rotate_org_credentials_without_api_key(
        self, test_client
    ):
        """Test credential rotation without provisioning API key."""
        response = test_client.post(
            "/api/v1/orgs/test-org-123/credentials/rotate",
            json={"grace_period_hours": 24}
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_rotate_org_credentials_invalid_api_key(
        self, test_client
    ):
        """Test credential rotation with invalid API key."""
        response = test_client.post(
            "/api/v1/orgs/test-org-123/credentials/rotate",
            headers={"X-API-Key": "invalid-key"},
            json={"grace_period_hours": 24}
        )

        assert response.status_code == 401


class TestAppCredentialRotationEndpoint:
    """Tests for POST /orgs/{org_id}/apps/{app_id}/credentials/rotate endpoint."""

    @pytest.mark.asyncio
    async def test_rotate_app_credentials_success(
        self, test_client, mock_db, provisioning_headers,
        mock_org_config, mock_app_config
    ):
        """Test successful application credential rotation."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.rotate_app_credentials = AsyncMock()
        mock_db.create_secret_retrieval_token = AsyncMock(
            return_value="app-rotation-token-123"
        )

        response = test_client.post(
            "/api/v1/orgs/test-org-123/apps/test-app/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 24}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == "test-org-123"
        assert data["app_id"] == "test-app"
        assert data["status"] == "rotated"
        assert "new_credentials" in data
        assert data["new_credentials"]["client_id"] == "org-test-org-123-app-test-app"
        assert "secret_retrieval" in data["new_credentials"]
        assert data["grace_period"]["hours"] == 24

        mock_db.rotate_app_credentials.assert_called_once()
        mock_db.create_secret_retrieval_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_rotate_app_credentials_org_not_found(
        self, test_client, mock_db, provisioning_headers
    ):
        """Test app credential rotation when org doesn't exist."""
        mock_db.get_org_config = AsyncMock(return_value=None)

        response = test_client.post(
            "/api/v1/orgs/test-org-123/apps/test-app/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 24}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rotate_app_credentials_app_not_found(
        self, test_client, mock_db, provisioning_headers, mock_org_config
    ):
        """Test app credential rotation when app doesn't exist."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=None)

        response = test_client.post(
            "/api/v1/orgs/test-org-123/apps/nonexistent-app/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 24}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rotate_app_credentials_default_grace_period(
        self, test_client, mock_db, provisioning_headers,
        mock_org_config, mock_app_config
    ):
        """Test app credential rotation with default grace period."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.rotate_app_credentials = AsyncMock()
        mock_db.create_secret_retrieval_token = AsyncMock(
            return_value="app-rotation-token-123"
        )

        # No grace_period_hours specified, should use default (e.g., 24)
        response = test_client.post(
            "/api/v1/orgs/test-org-123/apps/test-app/credentials/rotate",
            headers=provisioning_headers,
            json={}
        )

        assert response.status_code == 200
        data = response.json()
        assert "grace_period" in data
        # Default grace period should be present
        assert data["grace_period"]["hours"] >= 0

    @pytest.mark.asyncio
    async def test_rotate_app_credentials_without_api_key(
        self, test_client
    ):
        """Test app credential rotation without provisioning API key."""
        response = test_client.post(
            "/api/v1/orgs/test-org-123/apps/test-app/credentials/rotate",
            json={"grace_period_hours": 24}
        )

        assert response.status_code == 422
