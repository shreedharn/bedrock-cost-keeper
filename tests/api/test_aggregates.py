"""Tests for daily aggregates endpoints."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch


class TestOrgAggregatesEndpoint:
    """Tests for GET /orgs/{org_id}/aggregates/today endpoint."""

    @pytest.mark.asyncio
    async def test_get_org_aggregates_success(
        self, test_client, mock_db, auth_headers, mock_org_config
    ):
        """Test successful retrieval of org aggregates."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        with patch('src.domain.services.metering_service.MeteringService') as MockService:
            mock_service = MockService.return_value
            mock_service.get_current_usage = AsyncMock(return_value={
                'premium': {'cost_usd_micros': 100000},
                'standard': {'cost_usd_micros': 50000},
                'economy': {'cost_usd_micros': 10000}
            })

            response = test_client.get(
                "/api/v1/orgs/test-org-123/aggregates/today",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == "test-org-123"
        assert "date" in data
        assert data["timezone"] == "America/New_York"
        assert data["quota_scope"] == "ORG"
        assert "models" in data
        assert "total_cost_usd_micros" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_get_org_aggregates_unauthorized(
        self, test_client, mock_db, jwt_handler, mock_org_config
    ):
        """Test aggregates request with wrong org."""
        # Create token for different org
        access_token, _ = jwt_handler.create_access_token(
            client_id="org-different-org",
            org_id="different-org",
            app_id=None
        )
        headers = {"Authorization": f"Bearer {access_token}"}

        mock_db.is_token_revoked = AsyncMock(return_value=False)
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)

        response = test_client.get(
            "/api/v1/orgs/test-org-123/aggregates/today",
            headers=headers
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_org_aggregates_org_not_found(
        self, test_client, mock_db, auth_headers
    ):
        """Test aggregates for non-existent org."""
        mock_db.get_org_config = AsyncMock(return_value=None)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        response = test_client.get(
            "/api/v1/orgs/test-org-123/aggregates/today",
            headers=auth_headers
        )

        assert response.status_code == 404


class TestAppAggregatesEndpoint:
    """Tests for GET /orgs/{org_id}/apps/{app_id}/aggregates/today endpoint."""

    @pytest.mark.asyncio
    async def test_get_app_aggregates_success(
        self, test_client, mock_db, auth_headers,
        mock_org_config, mock_app_config
    ):
        """Test successful retrieval of app-specific aggregates."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        with patch('src.domain.services.metering_service.MeteringService') as MockService:
            mock_service = MockService.return_value
            mock_service.get_current_usage = AsyncMock(return_value={
                'premium': {'cost_usd_micros': 100000},
                'standard': {'cost_usd_micros': 50000}
            })

            response = test_client.get(
                "/api/v1/orgs/test-org-123/apps/test-app/aggregates/today",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == "test-org-123"
        assert data["app_id"] == "test-app"
        assert data["app_name"] == "Test Application"
        assert "date" in data
        assert "models" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_get_app_aggregates_app_mismatch(
        self, test_client, mock_db, jwt_handler,
        mock_org_config, mock_app_config
    ):
        """Test app aggregates with app_id mismatch."""
        # Create token for different app
        access_token, _ = jwt_handler.create_access_token(
            client_id="org-test-org-123-app-different-app",
            org_id="test-org-123",
            app_id="different-app"
        )
        headers = {"Authorization": f"Bearer {access_token}"}

        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        response = test_client.get(
            "/api/v1/orgs/test-org-123/apps/test-app/aggregates/today",
            headers=headers
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_app_aggregates_without_app_config(
        self, test_client, mock_db, auth_headers, mock_org_config
    ):
        """Test app aggregates when app has no specific config (inherits org)."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=None)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        with patch('src.domain.services.metering_service.MeteringService') as MockService:
            mock_service = MockService.return_value
            mock_service.get_current_usage = AsyncMock(return_value={
                'premium': {'cost_usd_micros': 100000},
                'standard': {'cost_usd_micros': 50000},
                'economy': {'cost_usd_micros': 10000}
            })

            response = test_client.get(
                "/api/v1/orgs/test-org-123/apps/test-app/aggregates/today",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["app_id"] == "test-app"
        assert data["app_name"] is None  # No app config

    @pytest.mark.asyncio
    async def test_get_app_aggregates_org_not_found(
        self, test_client, mock_db, auth_headers
    ):
        """Test app aggregates when org doesn't exist."""
        mock_db.get_org_config = AsyncMock(return_value=None)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        response = test_client.get(
            "/api/v1/orgs/test-org-123/apps/test-app/aggregates/today",
            headers=auth_headers
        )

        assert response.status_code == 404
