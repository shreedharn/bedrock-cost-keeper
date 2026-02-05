"""Manual test for credential rotation with grace period.

Run this test to verify the complete rotation flow:
1. Create org with initial credentials
2. Authenticate with initial credentials
3. Rotate credentials with grace period
4. Verify both old and new credentials work during grace period
5. Verify old credentials fail after grace period expires

Usage:
    pytest tests/api/test_credential_rotation_manual.py -v -s
"""

import pytest
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch


class TestCredentialRotationFlow:
    """End-to-end test for credential rotation."""

    @pytest.mark.asyncio
    async def test_complete_rotation_flow(
        self, test_client, mock_db, provisioning_headers
    ):
        """Test complete credential rotation flow with grace period."""

        # Setup
        org_id = "test-org-rotation"

        # ==================== Step 1: Create Organization ====================
        print("\n" + "="*60)
        print("STEP 1: Create Organization")
        print("="*60)

        mock_db.get_org_config = AsyncMock(return_value=None)
        mock_db.put_org_config = AsyncMock()

        with patch('src.core.config.main_config', {
            'model_labels': {
                'premium': {'bedrock_model_id': 'model-1'},
                'standard': {'bedrock_model_id': 'model-2'}
            }
        }):
            response = test_client.put(
                f"/api/v1/orgs/{org_id}",
                headers=provisioning_headers,
                json={
                    "org_name": "Test Rotation Org",
                    "timezone": "America/New_York",
                    "quota_scope": "ORG",
                    "model_ordering": ["premium", "standard"],
                    "quotas": {
                        "premium": 1000000,
                        "standard": 500000
                    }
                }
            )

        assert response.status_code == 200
        data = response.json()

        initial_client_id = data['credentials']['client_id']
        initial_client_secret = data['credentials']['client_secret']

        print(f"✓ Organization created: {org_id}")
        print(f"✓ Client ID: {initial_client_id}")
        print(f"✓ Initial Secret: {initial_client_secret[:20]}...")

        # Store initial secret hash for mock
        from src.infrastructure.security.jwt_handler import JWTHandler
        jwt_handler = JWTHandler()
        initial_secret_hash = jwt_handler.hash_secret(initial_client_secret)

        # ==================== Step 2: Authenticate with Initial Credentials ====================
        print("\n" + "="*60)
        print("STEP 2: Authenticate with Initial Credentials")
        print("="*60)

        # Mock the org config with initial secret
        mock_org_config = {
            'org_id': org_id,
            'client_id': initial_client_id,
            'client_secret_hash': initial_secret_hash,
            'client_secret_created_at_epoch': int(time.time())
        }
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=None)
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        response = test_client.post(
            "/auth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": initial_client_id,
                "client_secret": initial_client_secret
            }
        )

        assert response.status_code == 200
        token_data = response.json()
        assert 'access_token' in token_data
        print(f"✓ Authentication successful with initial credentials")
        print(f"✓ Access token received: {token_data['access_token'][:30]}...")

        # ==================== Step 3: Rotate Credentials ====================
        print("\n" + "="*60)
        print("STEP 3: Rotate Credentials (7-day grace period)")
        print("="*60)

        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.rotate_org_credentials = AsyncMock()

        rotation_response = test_client.post(
            f"/api/v1/orgs/{org_id}/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 168}  # 7 days
        )

        assert rotation_response.status_code == 200
        rotation_data = rotation_response.json()

        new_client_secret = rotation_data['client_secret']
        new_secret_hash = jwt_handler.hash_secret(new_client_secret)

        print(f"✓ Credentials rotated")
        print(f"✓ New Secret: {new_client_secret[:20]}...")
        print(f"✓ Grace Period: {rotation_data['rotation']['grace_period_hours']} hours")
        print(f"✓ Old Secret Expires: {rotation_data['rotation']['old_secret_expires_at']}")

        # Verify rotation was called with correct parameters
        mock_db.rotate_org_credentials.assert_called_once()
        call_args = mock_db.rotate_org_credentials.call_args
        assert call_args.kwargs['org_id'] == org_id
        assert call_args.kwargs['new_secret_hash'] == new_secret_hash
        assert call_args.kwargs['old_secret_hash'] == initial_secret_hash

        # ==================== Step 4: Authenticate with NEW Credentials ====================
        print("\n" + "="*60)
        print("STEP 4: Authenticate with NEW Credentials")
        print("="*60)

        # Update mock config with new secret and grace period
        grace_expires_at = int(time.time()) + (168 * 3600)  # 7 days from now
        mock_org_config_rotated = {
            'org_id': org_id,
            'client_id': initial_client_id,
            'client_secret_hash': new_secret_hash,
            'client_secret_hash_old': initial_secret_hash,
            'client_secret_rotation_grace_expires_at_epoch': grace_expires_at,
            'client_secret_created_at_epoch': int(time.time())
        }
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config_rotated)

        response = test_client.post(
            "/auth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": initial_client_id,
                "client_secret": new_client_secret
            }
        )

        assert response.status_code == 200
        print(f"✓ Authentication successful with NEW credentials")

        # ==================== Step 5: Authenticate with OLD Credentials (During Grace Period) ====================
        print("\n" + "="*60)
        print("STEP 5: Authenticate with OLD Credentials (During Grace Period)")
        print("="*60)

        response = test_client.post(
            "/auth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": initial_client_id,
                "client_secret": initial_client_secret  # Using OLD secret
            }
        )

        assert response.status_code == 200
        print(f"✓ Authentication successful with OLD credentials (grace period active)")
        print(f"✓ Zero-downtime rotation confirmed!")

        # ==================== Step 6: Authenticate with OLD Credentials (After Grace Period) ====================
        print("\n" + "="*60)
        print("STEP 6: Authenticate with OLD Credentials (After Grace Period)")
        print("="*60)

        # Update mock config - grace period expired
        mock_org_config_expired = {
            'org_id': org_id,
            'client_id': initial_client_id,
            'client_secret_hash': new_secret_hash,
            'client_secret_hash_old': initial_secret_hash,
            'client_secret_rotation_grace_expires_at_epoch': int(time.time()) - 1,  # Expired
            'client_secret_created_at_epoch': int(time.time())
        }
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config_expired)

        response = test_client.post(
            "/auth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": initial_client_id,
                "client_secret": initial_client_secret  # Using OLD secret
            }
        )

        assert response.status_code == 401
        print(f"✓ Authentication REJECTED with OLD credentials (grace period expired)")
        print(f"✓ Security confirmed - old credentials properly invalidated")

        # ==================== Step 7: Verify NEW Credentials Still Work ====================
        print("\n" + "="*60)
        print("STEP 7: Verify NEW Credentials Still Work After Grace Period")
        print("="*60)

        response = test_client.post(
            "/auth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": initial_client_id,
                "client_secret": new_client_secret  # Using NEW secret
            }
        )

        assert response.status_code == 200
        print(f"✓ Authentication successful with NEW credentials")

        # ==================== Summary ====================
        print("\n" + "="*60)
        print("TEST SUMMARY - ALL CHECKS PASSED ✅")
        print("="*60)
        print("✓ Organization creation")
        print("✓ Initial authentication")
        print("✓ Credential rotation with grace period")
        print("✓ New credentials work immediately")
        print("✓ Old credentials work during grace period")
        print("✓ Old credentials rejected after grace period")
        print("✓ New credentials continue working after grace period")
        print("\n🎉 ZERO-DOWNTIME CREDENTIAL ROTATION VERIFIED!")
        print("="*60 + "\n")

    @pytest.mark.asyncio
    async def test_rotation_with_zero_grace_period(
        self, test_client, mock_db, provisioning_headers
    ):
        """Test immediate rotation (0-hour grace period)."""

        print("\n" + "="*60)
        print("TEST: Immediate Rotation (0-hour grace period)")
        print("="*60)

        org_id = "test-org-immediate"

        # Setup initial org
        from src.infrastructure.security.jwt_handler import JWTHandler
        jwt_handler = JWTHandler()
        initial_secret = jwt_handler.generate_secret()
        initial_secret_hash = jwt_handler.hash_secret(initial_secret)

        mock_org_config = {
            'org_id': org_id,
            'client_id': f'org-{org_id}',
            'client_secret_hash': initial_secret_hash
        }

        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.rotate_org_credentials = AsyncMock()

        # Rotate with 0-hour grace period
        response = test_client.post(
            f"/api/v1/orgs/{org_id}/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 0}  # Immediate rotation
        )

        assert response.status_code == 200
        data = response.json()

        print(f"✓ Rotation completed")
        print(f"✓ Grace Period: {data['rotation']['grace_period_hours']} hours (immediate)")
        print(f"✓ Old Secret Expires: {data['rotation']['old_secret_expires_at']}")

        # Verify grace period is 0
        assert data['rotation']['grace_period_hours'] == 0

        # Verify rotation was called
        mock_db.rotate_org_credentials.assert_called_once()

        print("✓ Immediate rotation (no grace period) works correctly")
        print("="*60 + "\n")

    @pytest.mark.asyncio
    async def test_app_credential_rotation(
        self, test_client, mock_db, provisioning_headers
    ):
        """Test application credential rotation."""

        print("\n" + "="*60)
        print("TEST: Application Credential Rotation")
        print("="*60)

        org_id = "test-org-app-rotation"
        app_id = "test-app"

        # Setup
        from src.infrastructure.security.jwt_handler import JWTHandler
        jwt_handler = JWTHandler()
        initial_secret = jwt_handler.generate_secret()
        initial_secret_hash = jwt_handler.hash_secret(initial_secret)

        mock_org_config = {'org_id': org_id}
        mock_app_config = {
            'app_id': app_id,
            'client_id': f'org-{org_id}-app-{app_id}',
            'client_secret_hash': initial_secret_hash
        }

        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.rotate_app_credentials = AsyncMock()

        # Rotate app credentials
        response = test_client.post(
            f"/api/v1/orgs/{org_id}/apps/{app_id}/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 24}
        )

        assert response.status_code == 200
        data = response.json()

        print(f"✓ App credentials rotated")
        print(f"✓ Org ID: {data['org_id']}")
        print(f"✓ App ID: {data['app_id']}")
        print(f"✓ Client ID: {data['client_id']}")
        print(f"✓ Grace Period: {data['rotation']['grace_period_hours']} hours")

        assert data['org_id'] == org_id
        assert data['app_id'] == app_id
        assert 'client_secret' in data

        # Verify rotation was called
        mock_db.rotate_app_credentials.assert_called_once()

        print("✓ Application credential rotation works correctly")
        print("="*60 + "\n")
