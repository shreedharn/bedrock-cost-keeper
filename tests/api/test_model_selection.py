"""Tests for model selection endpoints."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestModelSelectionEndpoint:
    """Tests for GET /orgs/{org_id}/apps/{app_id}/model-selection endpoint."""

    def test_model_selection_normal_mode(
        self, test_client, mock_db, auth_headers, mock_org_config, mock_app_config
    ):
        """Test model selection in normal mode."""
        # Setup mocks
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.get_sticky_state = AsyncMock(return_value=None)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        with patch('src.api.routes.model_selection.MeteringService') as MockService:
            mock_service = MockService.return_value
            mock_service.get_current_usage = AsyncMock(return_value={
                'premium': {'cost_usd_micros': 100000},
                'standard': {'cost_usd_micros': 50000}
            })
            mock_service._compute_scope = lambda *args: "ORG#test-org-123"
            mock_service._compute_org_day = lambda tz: "DAY#2026-01-27"

            response = test_client.get(
                "/api/v1/orgs/test-org-123/apps/test-app/model-selection",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["org_id"] == "test-org-123"
        assert data["app_id"] == "test-app"
        assert "recommended_model" in data
        assert data["recommended_model"]["reason"] == "NORMAL"
        assert data["quota_status"]["mode"] == "NORMAL"
        assert data["client_guidance"]["check_frequency"] == "PERIODIC_300S"

    def test_model_selection_tight_mode(
        self, test_client, mock_db, auth_headers, mock_org_config, mock_app_config
    ):
        """Test model selection when quota is tight."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.get_sticky_state = AsyncMock(return_value=None)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        with patch('src.api.routes.model_selection.MeteringService') as MockService:
            mock_service = MockService.return_value
            # 96% of quota used - should trigger TIGHT mode
            mock_service.get_current_usage = AsyncMock(return_value={
                'premium': {'cost_usd_micros': 480000},  # 96% of 500000
                'standard': {'cost_usd_micros': 50000}
            })
            mock_service._compute_scope = lambda *args: "ORG#test-org-123"
            mock_service._compute_org_day = lambda tz: "DAY#2026-01-27"

            response = test_client.get(
                "/api/v1/orgs/test-org-123/apps/test-app/model-selection",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["quota_status"]["mode"] == "TIGHT"
        assert data["client_guidance"]["check_frequency"] == "PERIODIC_60S"
        assert data["client_guidance"]["cache_duration_secs"] == 60

    def test_model_selection_sticky_fallback(
        self, test_client, mock_db, auth_headers, mock_org_config, mock_app_config
    ):
        """Test model selection with sticky fallback active."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.get_sticky_state = AsyncMock(return_value={
            'active_model_label': 'economy',
            'entered_at_epoch': int(datetime.now(timezone.utc).timestamp())
        })
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        with patch('src.api.routes.model_selection.MeteringService') as MockService:
            mock_service = MockService.return_value
            mock_service.get_current_usage = AsyncMock(return_value={
                'premium': {'cost_usd_micros': 600000},
                'standard': {'cost_usd_micros': 550000},
                'economy': {'cost_usd_micros': 50000}
            })
            mock_service._compute_scope = lambda *args: "ORG#test-org-123"
            mock_service._compute_org_day = lambda tz: "DAY#2026-01-27"

            response = test_client.get(
                "/api/v1/orgs/test-org-123/apps/test-app/model-selection",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["recommended_model"]["label"] == "economy"
        assert data["recommended_model"]["reason"] == "STICKY_FALLBACK"
        assert data["quota_status"]["sticky_fallback_active"] is True

    def test_model_selection_all_quotas_exceeded(
        self, test_client, mock_db, auth_headers, mock_org_config, mock_app_config
    ):
        """Test model selection when all quotas are exceeded."""
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.get_sticky_state = AsyncMock(return_value=None)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        with patch('src.api.routes.model_selection.MeteringService') as MockService:
            mock_service = MockService.return_value
            mock_service.get_current_usage = AsyncMock(return_value={
                'premium': {'cost_usd_micros': 600000},
                'standard': {'cost_usd_micros': 300000}
            })
            mock_service._compute_scope = lambda *args: "ORG#test-org-123"
            mock_service._compute_org_day = lambda tz: "DAY#2026-01-27"

            response = test_client.get(
                "/api/v1/orgs/test-org-123/apps/test-app/model-selection",
                headers=auth_headers
            )

        assert response.status_code == 429
        data = response.json()
        assert data["error"] == "QUOTA_EXCEEDED"

    def test_model_selection_unauthorized_org(
        self, test_client, mock_db, jwt_handler, mock_org_config
    ):
        """Test model selection with mismatched org_id."""
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
            "/api/v1/orgs/test-org-123/apps/test-app/model-selection",
            headers=headers
        )

        assert response.status_code == 400

    def test_model_selection_org_not_found(
        self, test_client, mock_db, auth_headers
    ):
        """Test model selection when organization doesn't exist."""
        mock_db.get_org_config = AsyncMock(return_value=None)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        response = test_client.get(
            "/api/v1/orgs/test-org-123/apps/test-app/model-selection",
            headers=auth_headers
        )

        assert response.status_code == 400
