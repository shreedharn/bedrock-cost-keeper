"""Tests for provisioning endpoints."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch


class TestOrgRegistrationEndpoint:
    """Tests for PUT /orgs/{org_id} endpoint."""

    @pytest.mark.asyncio
    async def test_register_new_org_success(
        self, test_client, mock_db, provisioning_headers, sample_org_registration
    ):
        """Test successful new organization registration."""
        mock_db.get_org_config = AsyncMock(return_value=None)
        mock_db.put_org_config = AsyncMock()
        mock_db.create_secret_retrieval_token = AsyncMock()

        with patch('src.core.config.main_config', {
            'model_labels': {
                'premium': {'bedrock_model_id': 'model-1'},
                'standard': {'bedrock_model_id': 'model-2'},
                'economy': {'bedrock_model_id': 'model-3'}
            }
        }):
            response = test_client.put(
                "/api/v1/orgs/test-org-123",
                headers=provisioning_headers,
                json=sample_org_registration
            )

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == "test-org-123"
        assert data["status"] == "created"
        assert "credentials" in data
        assert "client_id" in data["credentials"]
        assert "secret_retrieval" in data["credentials"]
        assert data["credentials"]["client_id"] == "org-test-org-123"
        mock_db.put_org_config.assert_called_once()
        mock_db.create_secret_retrieval_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_existing_org(
        self, test_client, mock_db, provisioning_headers,
        sample_org_registration, mock_org_config
    ):
        """Test updating an existing organization."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.put_org_config = AsyncMock()

        with patch('src.core.config.main_config', {
            'model_labels': {
                'premium': {'bedrock_model_id': 'model-1'},
                'standard': {'bedrock_model_id': 'model-2'},
                'economy': {'bedrock_model_id': 'model-3'}
            }
        }):
            response = test_client.put(
                "/api/v1/orgs/test-org-123",
                headers=provisioning_headers,
                json=sample_org_registration
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert "updated_at" in data
        assert "credentials" not in data  # No new credentials for update
        mock_db.put_org_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_org_invalid_model_label(
        self, test_client, mock_db, provisioning_headers, sample_org_registration
    ):
        """Test org registration with invalid model label."""
        invalid_registration = sample_org_registration.copy()
        invalid_registration["model_ordering"] = ["premium", "invalid_model"]

        mock_db.get_org_config = AsyncMock(return_value=None)

        with patch('src.core.config.main_config', {
            'model_labels': {
                'premium': {'bedrock_model_id': 'model-1'}
            }
        }):
            response = test_client.put(
                "/api/v1/orgs/test-org-123",
                headers=provisioning_headers,
                json=invalid_registration
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_register_org_missing_quota(
        self, test_client, mock_db, provisioning_headers, sample_org_registration
    ):
        """Test org registration with missing quota for model."""
        invalid_registration = sample_org_registration.copy()
        del invalid_registration["quotas"]["economy"]

        response = test_client.put(
            "/api/v1/orgs/test-org-123",
            headers=provisioning_headers,
            json=invalid_registration
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_org_without_api_key(
        self, test_client, sample_org_registration
    ):
        """Test org registration without provisioning API key."""
        response = test_client.put(
            "/api/v1/orgs/test-org-123",
            json=sample_org_registration
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_org_invalid_api_key(
        self, test_client, sample_org_registration
    ):
        """Test org registration with invalid API key."""
        response = test_client.put(
            "/api/v1/orgs/test-org-123",
            headers={"X-API-Key": "invalid-key"},
            json=sample_org_registration
        )

        assert response.status_code == 401


class TestAppRegistrationEndpoint:
    """Tests for PUT /orgs/{org_id}/apps/{app_id} endpoint."""

    @pytest.mark.asyncio
    async def test_register_new_app_success(
        self, test_client, mock_db, provisioning_headers,
        sample_app_registration, mock_org_config
    ):
        """Test successful new application registration."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=None)
        mock_db.put_app_config = AsyncMock()
        mock_db.create_secret_retrieval_token = AsyncMock()

        response = test_client.put(
            "/api/v1/orgs/test-org-123/apps/test-app",
            headers=provisioning_headers,
            json=sample_app_registration
        )

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == "test-org-123"
        assert data["app_id"] == "test-app"
        assert data["status"] == "created"
        assert "credentials" in data
        assert data["credentials"]["client_id"] == "org-test-org-123-app-test-app"
        mock_db.put_app_config.assert_called_once()
        mock_db.create_secret_retrieval_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_existing_app(
        self, test_client, mock_db, provisioning_headers,
        sample_app_registration, mock_org_config, mock_app_config
    ):
        """Test updating an existing application."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.put_app_config = AsyncMock()

        response = test_client.put(
            "/api/v1/orgs/test-org-123/apps/test-app",
            headers=provisioning_headers,
            json=sample_app_registration
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert "updated_at" in data
        assert "credentials" not in data
        mock_db.put_app_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_app_org_not_found(
        self, test_client, mock_db, provisioning_headers, sample_app_registration
    ):
        """Test app registration when org doesn't exist."""
        mock_db.get_org_config = AsyncMock(return_value=None)

        response = test_client.put(
            "/api/v1/orgs/test-org-123/apps/test-app",
            headers=provisioning_headers,
            json=sample_app_registration
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_register_app_with_overrides(
        self, test_client, mock_db, provisioning_headers,
        sample_app_registration, mock_org_config
    ):
        """Test app registration with configuration overrides."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=None)
        mock_db.put_app_config = AsyncMock()
        mock_db.create_secret_retrieval_token = AsyncMock()

        # Add overrides
        sample_app_registration["overrides"] = {
            "tight_mode_threshold_pct": 90
        }

        response = test_client.put(
            "/api/v1/orgs/test-org-123/apps/test-app",
            headers=provisioning_headers,
            json=sample_app_registration
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"

        # Verify overrides were passed to put_app_config
        call_args = mock_db.put_app_config.call_args
        assert call_args[0][0] == "test-org-123"
        assert call_args[0][1] == "test-app"
        assert "tight_mode_threshold_pct" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_register_app_minimal_config(
        self, test_client, mock_db, provisioning_headers, mock_org_config
    ):
        """Test app registration with minimal config (inherits from org)."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=None)
        mock_db.put_app_config = AsyncMock()
        mock_db.create_secret_retrieval_token = AsyncMock()

        minimal_registration = {
            "app_name": "Minimal App"
        }

        response = test_client.put(
            "/api/v1/orgs/test-org-123/apps/test-app",
            headers=provisioning_headers,
            json=minimal_registration
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        assert "inherited_fields" in data["configuration"]
