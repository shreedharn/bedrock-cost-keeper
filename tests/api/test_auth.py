"""Tests for authentication endpoints."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock


class TestTokenEndpoint:
    """Tests for POST /auth/token endpoint."""

    @pytest.mark.asyncio
    async def test_obtain_token_success_org_level(self, test_client, mock_db, jwt_handler):
        """Test successful token issuance for org-level client."""
        # Setup mock
        client_secret = jwt_handler.generate_secret()
        secret_hash = jwt_handler.hash_secret(client_secret)

        mock_db.get_org_config = AsyncMock(return_value={
            'client_id': 'org-test-org-123',
            'client_secret_hash': secret_hash,
            'created_at_epoch': int(datetime.now(timezone.utc).timestamp())
        })

        # Make request
        response = test_client.post(
            "/auth/token",
            json={
                "client_id": "org-test-org-123",
                "client_secret": client_secret,
                "grant_type": "client_credentials"
            }
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "Bearer"
        assert "expires_in" in data
        assert "refresh_expires_in" in data
        assert "org:test-org-123" in data["scope"]

    @pytest.mark.asyncio
    async def test_obtain_token_success_app_level(self, test_client, mock_db, jwt_handler):
        """Test successful token issuance for app-level client."""
        client_secret = jwt_handler.generate_secret()
        secret_hash = jwt_handler.hash_secret(client_secret)

        mock_db.get_app_config = AsyncMock(return_value={
            'client_id': 'org-test-org-123-app-test-app',
            'client_secret_hash': secret_hash,
            'created_at_epoch': int(datetime.now(timezone.utc).timestamp())
        })

        response = test_client.post(
            "/auth/token",
            json={
                "client_id": "org-test-org-123-app-test-app",
                "client_secret": client_secret,
                "grant_type": "client_credentials"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "org:test-org-123" in data["scope"]
        assert "app:test-app" in data["scope"]

    @pytest.mark.asyncio
    async def test_obtain_token_invalid_client_id(self, test_client, mock_db):
        """Test token request with invalid client_id format."""
        mock_db.get_org_config = AsyncMock(return_value=None)

        response = test_client.post(
            "/auth/token",
            json={
                "client_id": "invalid-format",
                "client_secret": "secret",
                "grant_type": "client_credentials"
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_obtain_token_invalid_credentials(self, test_client, mock_db, jwt_handler):
        """Test token request with wrong client_secret."""
        client_secret = jwt_handler.generate_secret()
        secret_hash = jwt_handler.hash_secret(client_secret)

        mock_db.get_org_config = AsyncMock(return_value={
            'client_id': 'org-test-org-123',
            'client_secret_hash': secret_hash
        })

        response = test_client.post(
            "/auth/token",
            json={
                "client_id": "org-test-org-123",
                "client_secret": "wrong-secret",
                "grant_type": "client_credentials"
            }
        )

        assert response.status_code == 401


class TestRefreshEndpoint:
    """Tests for POST /auth/refresh endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, test_client, mock_db, jwt_handler):
        """Test successful token refresh."""
        # Create a valid refresh token
        refresh_token, _ = jwt_handler.create_refresh_token(
            client_id="org-test-org-123-app-test-app"
        )

        mock_db.is_token_revoked = AsyncMock(return_value=False)

        response = test_client.post(
            "/auth/refresh",
            json={
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "Bearer"
        assert "expires_in" in data

    @pytest.mark.asyncio
    async def test_refresh_token_revoked(self, test_client, mock_db, jwt_handler):
        """Test refresh with revoked token."""
        refresh_token, _ = jwt_handler.create_refresh_token(
            client_id="org-test-org-123"
        )

        mock_db.is_token_revoked = AsyncMock(return_value=True)

        response = test_client.post(
            "/auth/refresh",
            json={
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_invalid_token(self, test_client, mock_db):
        """Test refresh with malformed token."""
        response = test_client.post(
            "/auth/refresh",
            json={
                "refresh_token": "invalid.token.here",
                "grant_type": "refresh_token"
            }
        )

        assert response.status_code == 401


class TestRevokeEndpoint:
    """Tests for POST /auth/revoke endpoint."""

    @pytest.mark.asyncio
    async def test_revoke_token_success(self, test_client, mock_db, jwt_handler):
        """Test successful token revocation."""
        access_token, _ = jwt_handler.create_access_token(
            client_id="org-test-org-123",
            org_id="test-org-123",
            app_id=None
        )

        mock_db.is_token_revoked = AsyncMock(return_value=False)
        mock_db.revoke_token = AsyncMock()

        response = test_client.post(
            "/auth/revoke",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "token": access_token,
                "token_type_hint": "access_token"
            }
        )

        assert response.status_code == 204
        mock_db.revoke_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_other_client_token(self, test_client, mock_db, jwt_handler):
        """Test attempting to revoke another client's token."""
        auth_token, _ = jwt_handler.create_access_token(
            client_id="org-test-org-123",
            org_id="test-org-123",
            app_id=None
        )

        other_token, _ = jwt_handler.create_access_token(
            client_id="org-other-org-456",
            org_id="other-org-456",
            app_id=None
        )

        mock_db.is_token_revoked = AsyncMock(return_value=False)

        response = test_client.post(
            "/auth/revoke",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "token": other_token
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_revoke_without_authorization(self, test_client):
        """Test revoke without authorization header."""
        response = test_client.post(
            "/auth/revoke",
            json={
                "token": "some.token.here"
            }
        )

        assert response.status_code == 422
