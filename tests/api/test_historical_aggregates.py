"""Tests for historical aggregates endpoints."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch


class TestOrgHistoricalAggregatesEndpoint:
    """Tests for GET /orgs/{org_id}/aggregates/{date} endpoint."""

    @pytest.mark.asyncio
    async def test_get_org_historical_aggregates_success(
        self, test_client, mock_db, auth_headers, mock_org_config
    ):
        """Test successful retrieval of org historical aggregates."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        # Mock historical data retrieval
        historical_date = "20260125"
        with patch('src.domain.services.metering_service.MeteringService') as MockService:
            mock_service = MockService.return_value
            mock_service.get_historical_usage = AsyncMock(return_value={
                'date': historical_date,
                'premium': {'cost_usd_micros': 850000, 'input_tokens': 100000, 'output_tokens': 50000},
                'standard': {'cost_usd_micros': 320000, 'input_tokens': 80000, 'output_tokens': 40000},
                'economy': {'cost_usd_micros': 45000, 'input_tokens': 50000, 'output_tokens': 20000}
            })

            response = test_client.get(
                f"/api/v1/orgs/test-org-123/aggregates/{historical_date}",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == "test-org-123"
        assert data["date"] == historical_date
        assert data["timezone"] == "America/New_York"
        assert data["quota_scope"] == "ORG"
        assert "models" in data
        assert "total_cost_usd_micros" in data
        # Historical data should have all three models
        assert "premium" in data["models"]
        assert "standard" in data["models"]
        assert "economy" in data["models"]

    @pytest.mark.asyncio
    async def test_get_org_historical_aggregates_yesterday(
        self, test_client, mock_db, auth_headers, mock_org_config
    ):
        """Test retrieval of yesterday's aggregates."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        # Calculate yesterday's date
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y%m%d")

        with patch('src.domain.services.metering_service.MeteringService') as MockService:
            mock_service = MockService.return_value
            mock_service.get_historical_usage = AsyncMock(return_value={
                'date': yesterday,
                'premium': {'cost_usd_micros': 500000},
                'standard': {'cost_usd_micros': 200000}
            })

            response = test_client.get(
                f"/api/v1/orgs/test-org-123/aggregates/{yesterday}",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["date"] == yesterday

    @pytest.mark.asyncio
    async def test_get_org_historical_aggregates_invalid_date_format(
        self, test_client, mock_db, auth_headers, mock_org_config
    ):
        """Test historical aggregates with invalid date format."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        # Invalid date formats
        invalid_dates = [
            "2026-01-25",      # Wrong format (should be YYYYMMDD)
            "01/25/2026",      # Wrong format
            "20261325",        # Invalid month (13)
            "20260230",        # Invalid day (Feb 30)
            "invalid",         # Not a date
        ]

        for invalid_date in invalid_dates:
            response = test_client.get(
                f"/api/v1/orgs/test-org-123/aggregates/{invalid_date}",
                headers=auth_headers
            )
            # Should return 400 Bad Request for invalid date format
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_org_historical_aggregates_future_date(
        self, test_client, mock_db, auth_headers, mock_org_config
    ):
        """Test historical aggregates with future date (should fail)."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        # Future date (tomorrow)
        future_date = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y%m%d")

        response = test_client.get(
            f"/api/v1/orgs/test-org-123/aggregates/{future_date}",
            headers=auth_headers
        )

        # Should reject future dates
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_org_historical_aggregates_beyond_retention(
        self, test_client, mock_db, auth_headers, mock_org_config
    ):
        """Test historical aggregates beyond TTL retention period."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        # Date from 2 years ago (likely beyond retention)
        old_date = (datetime.now(timezone.utc) - timedelta(days=730)).strftime("%Y%m%d")

        with patch('src.domain.services.metering_service.MeteringService') as MockService:
            mock_service = MockService.return_value
            # No data found (TTL expired)
            mock_service.get_historical_usage = AsyncMock(return_value=None)

            response = test_client.get(
                f"/api/v1/orgs/test-org-123/aggregates/{old_date}",
                headers=auth_headers
            )

        # Should return 404 when data not found due to TTL
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_org_historical_aggregates_org_not_found(
        self, test_client, mock_db, auth_headers
    ):
        """Test historical aggregates for non-existent org."""
        mock_db.get_org_config = AsyncMock(return_value=None)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        historical_date = "20260125"
        response = test_client.get(
            f"/api/v1/orgs/nonexistent-org/aggregates/{historical_date}",
            headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_org_historical_aggregates_unauthorized(
        self, test_client, mock_db, jwt_handler, mock_org_config
    ):
        """Test historical aggregates request with wrong org credentials."""
        # Create token for different org
        access_token, _ = jwt_handler.create_access_token(
            client_id="org-different-org",
            org_id="different-org",
            app_id=None
        )
        headers = {"Authorization": f"Bearer {access_token}"}

        mock_db.is_token_revoked = AsyncMock(return_value=False)
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)

        historical_date = "20260125"
        response = test_client.get(
            f"/api/v1/orgs/test-org-123/aggregates/{historical_date}",
            headers=headers
        )

        assert response.status_code == 400


class TestAppHistoricalAggregatesEndpoint:
    """Tests for GET /orgs/{org_id}/apps/{app_id}/aggregates/{date} endpoint."""

    @pytest.mark.asyncio
    async def test_get_app_historical_aggregates_success(
        self, test_client, mock_db, auth_headers,
        mock_org_config, mock_app_config
    ):
        """Test successful retrieval of app-specific historical aggregates."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        historical_date = "20260125"
        with patch('src.domain.services.metering_service.MeteringService') as MockService:
            mock_service = MockService.return_value
            mock_service.get_historical_usage = AsyncMock(return_value={
                'date': historical_date,
                'premium': {'cost_usd_micros': 400000, 'input_tokens': 50000, 'output_tokens': 25000},
                'standard': {'cost_usd_micros': 150000, 'input_tokens': 40000, 'output_tokens': 20000}
            })

            response = test_client.get(
                f"/api/v1/orgs/test-org-123/apps/test-app/aggregates/{historical_date}",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == "test-org-123"
        assert data["app_id"] == "test-app"
        assert data["date"] == historical_date
        assert "models" in data
        # App only has premium and standard in config
        assert "premium" in data["models"]
        assert "standard" in data["models"]

    @pytest.mark.asyncio
    async def test_get_app_historical_aggregates_invalid_date(
        self, test_client, mock_db, auth_headers,
        mock_org_config, mock_app_config
    ):
        """Test app historical aggregates with invalid date."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        response = test_client.get(
            "/api/v1/orgs/test-org-123/apps/test-app/aggregates/invalid-date",
            headers=auth_headers
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_app_historical_aggregates_future_date(
        self, test_client, mock_db, auth_headers,
        mock_org_config, mock_app_config
    ):
        """Test app historical aggregates with future date."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        # Future date
        future_date = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y%m%d")

        response = test_client.get(
            f"/api/v1/orgs/test-org-123/apps/test-app/aggregates/{future_date}",
            headers=auth_headers
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_app_historical_aggregates_no_data(
        self, test_client, mock_db, auth_headers,
        mock_org_config, mock_app_config
    ):
        """Test app historical aggregates when no data exists for date."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        historical_date = "20260120"
        with patch('src.domain.services.metering_service.MeteringService') as MockService:
            mock_service = MockService.return_value
            # No data for this date
            mock_service.get_historical_usage = AsyncMock(return_value=None)

            response = test_client.get(
                f"/api/v1/orgs/test-org-123/apps/test-app/aggregates/{historical_date}",
                headers=auth_headers
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_app_historical_aggregates_org_not_found(
        self, test_client, mock_db, auth_headers
    ):
        """Test app historical aggregates when org doesn't exist."""
        mock_db.get_org_config = AsyncMock(return_value=None)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        historical_date = "20260125"
        response = test_client.get(
            f"/api/v1/orgs/test-org-123/apps/test-app/aggregates/{historical_date}",
            headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_app_historical_aggregates_app_not_found(
        self, test_client, mock_db, auth_headers, mock_org_config
    ):
        """Test app historical aggregates when app doesn't exist."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=None)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        historical_date = "20260125"
        response = test_client.get(
            f"/api/v1/orgs/test-org-123/apps/nonexistent-app/aggregates/{historical_date}",
            headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_app_historical_aggregates_week_range(
        self, test_client, mock_db, auth_headers,
        mock_org_config, mock_app_config
    ):
        """Test retrieval of multiple historical dates (e.g., last 7 days)."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        # Test last 7 days
        for days_ago in range(1, 8):
            historical_date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y%m%d")

            with patch('src.domain.services.metering_service.MeteringService') as MockService:
                mock_service = MockService.return_value
                mock_service.get_historical_usage = AsyncMock(return_value={
                    'date': historical_date,
                    'premium': {'cost_usd_micros': 100000 * days_ago},
                    'standard': {'cost_usd_micros': 50000 * days_ago}
                })

                response = test_client.get(
                    f"/api/v1/orgs/test-org-123/apps/test-app/aggregates/{historical_date}",
                    headers=auth_headers
                )

            assert response.status_code == 200
            data = response.json()
            assert data["date"] == historical_date

    @pytest.mark.asyncio
    async def test_get_app_historical_aggregates_unauthorized(
        self, test_client, mock_db, jwt_handler,
        mock_org_config, mock_app_config
    ):
        """Test app historical aggregates with wrong app credentials."""
        # Create token for different app
        access_token, _ = jwt_handler.create_access_token(
            client_id="org-test-org-123-app-different-app",
            org_id="test-org-123",
            app_id="different-app"
        )
        headers = {"Authorization": f"Bearer {access_token}"}

        mock_db.is_token_revoked = AsyncMock(return_value=False)
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)

        historical_date = "20260125"
        response = test_client.get(
            f"/api/v1/orgs/test-org-123/apps/test-app/aggregates/{historical_date}",
            headers=headers
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_date_format_validation(
        self, test_client, mock_db, auth_headers,
        mock_org_config, mock_app_config
    ):
        """Test strict date format validation (YYYYMMDD)."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        # Valid format
        valid_date = "20260125"
        with patch('src.domain.services.metering_service.MeteringService') as MockService:
            mock_service = MockService.return_value
            mock_service.get_historical_usage = AsyncMock(return_value={
                'date': valid_date,
                'premium': {'cost_usd_micros': 100000}
            })

            response = test_client.get(
                f"/api/v1/orgs/test-org-123/apps/test-app/aggregates/{valid_date}",
                headers=auth_headers
            )
            assert response.status_code == 200

        # Invalid formats should all fail
        invalid_formats = ["2026-01-25", "01-25-2026", "26012026"]
        for invalid in invalid_formats:
            response = test_client.get(
                f"/api/v1/orgs/test-org-123/apps/test-app/aggregates/{invalid}",
                headers=auth_headers
            )
            assert response.status_code == 400
