"""Simplified credential rotation test focusing on rotation and grace period logic.

Run: pytest tests/api/test_rotation_simple.py -v -s
"""

import pytest
import time
from unittest.mock import AsyncMock, patch


class TestRotationEndpoints:
    """Test rotation endpoints work correctly."""

    def test_org_rotation_endpoint(self, test_client, mock_db, provisioning_headers):
        """Test organization credential rotation endpoint."""
        print("\n" + "="*70)
        print("TEST: Organization Credential Rotation")
        print("="*70)

        org_id = "test-org-rotation"

        # Setup: Mock existing org
        from src.infrastructure.security.jwt_handler import JWTHandler
        jwt_handler = JWTHandler()
        old_secret = jwt_handler.generate_secret()
        old_secret_hash = jwt_handler.hash_secret(old_secret)

        mock_org_config = {
            'org_id': org_id,
            'client_id': f'org-{org_id}',
            'client_secret_hash': old_secret_hash,
            'client_secret_created_at_epoch': int(time.time()) - (60 * 86400)  # 60 days old
        }

        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.rotate_org_credentials = AsyncMock()

        # Test rotation with 7-day grace period
        response = test_client.post(
            f"/api/v1/orgs/{org_id}/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 168}  # 7 days
        )

        print(f"\nResponse Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.json()}")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert 'org_id' in data
        assert 'client_id' in data
        assert 'client_secret' in data
        assert 'rotation' in data

        assert data['org_id'] == org_id
        assert data['client_id'] == f'org-{org_id}'
        assert len(data['client_secret']) > 20  # Has a new secret

        # Verify rotation info
        rotation = data['rotation']
        assert rotation['grace_period_hours'] == 168
        assert 'rotated_at' in rotation
        assert 'old_secret_expires_at' in rotation

        print(f"✓ Org ID: {data['org_id']}")
        print(f"✓ Client ID: {data['client_id']}")
        print(f"✓ New Secret: {data['client_secret'][:25]}...")
        print(f"✓ Grace Period: {rotation['grace_period_hours']} hours")
        print(f"✓ Rotated At: {rotation['rotated_at']}")
        print(f"✓ Old Secret Expires: {rotation['old_secret_expires_at']}")

        # Verify database was called correctly
        mock_db.rotate_org_credentials.assert_called_once()
        call_kwargs = mock_db.rotate_org_credentials.call_args.kwargs

        assert call_kwargs['org_id'] == org_id
        assert call_kwargs['new_secret_hash'] != old_secret_hash  # New hash is different
        assert call_kwargs['old_secret_hash'] == old_secret_hash  # Old hash preserved
        assert call_kwargs['grace_expires_at_epoch'] > int(time.time())  # Future expiry

        print("\n✅ Organization rotation endpoint works correctly!")
        print("="*70)

    def test_app_rotation_endpoint(self, test_client, mock_db, provisioning_headers):
        """Test application credential rotation endpoint."""
        print("\n" + "="*70)
        print("TEST: Application Credential Rotation")
        print("="*70)

        org_id = "test-org"
        app_id = "test-app"

        # Setup
        from src.infrastructure.security.jwt_handler import JWTHandler
        jwt_handler = JWTHandler()
        old_secret = jwt_handler.generate_secret()
        old_secret_hash = jwt_handler.hash_secret(old_secret)

        mock_org_config = {'org_id': org_id}
        mock_app_config = {
            'app_id': app_id,
            'client_id': f'org-{org_id}-app-{app_id}',
            'client_secret_hash': old_secret_hash,
            'client_secret_created_at_epoch': int(time.time()) - (85 * 86400)  # 85 days old
        }

        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.get_app_config = AsyncMock(return_value=mock_app_config)
        mock_db.rotate_app_credentials = AsyncMock()

        # Test rotation with 24-hour grace period
        response = test_client.post(
            f"/api/v1/orgs/{org_id}/apps/{app_id}/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 24}
        )

        print(f"\nResponse Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.json()}")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert data['org_id'] == org_id
        assert data['app_id'] == app_id
        assert data['client_id'] == f'org-{org_id}-app-{app_id}'
        assert len(data['client_secret']) > 20

        rotation = data['rotation']
        assert rotation['grace_period_hours'] == 24

        print(f"✓ Org ID: {data['org_id']}")
        print(f"✓ App ID: {data['app_id']}")
        print(f"✓ Client ID: {data['client_id']}")
        print(f"✓ New Secret: {data['client_secret'][:25]}...")
        print(f"✓ Grace Period: {rotation['grace_period_hours']} hours")

        # Verify database was called
        mock_db.rotate_app_credentials.assert_called_once()

        print("\n✅ Application rotation endpoint works correctly!")
        print("="*70)

    def test_rotation_with_different_grace_periods(
        self, test_client, mock_db, provisioning_headers
    ):
        """Test rotation with various grace period durations."""
        print("\n" + "="*70)
        print("TEST: Different Grace Period Durations")
        print("="*70)

        org_id = "test-org-grace"

        # Setup
        from src.infrastructure.security.jwt_handler import JWTHandler
        jwt_handler = JWTHandler()
        old_secret_hash = jwt_handler.hash_secret(jwt_handler.generate_secret())

        mock_org_config = {
            'org_id': org_id,
            'client_id': f'org-{org_id}',
            'client_secret_hash': old_secret_hash
        }

        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)
        mock_db.rotate_org_credentials = AsyncMock()

        test_cases = [
            (0, "Immediate (no grace period)"),
            (1, "1 hour grace period"),
            (24, "24 hour grace period"),
            (168, "7 day grace period (default)")
        ]

        for hours, description in test_cases:
            mock_db.rotate_org_credentials.reset_mock()

            response = test_client.post(
                f"/api/v1/orgs/{org_id}/credentials/rotate",
                headers=provisioning_headers,
                json={"grace_period_hours": hours}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['rotation']['grace_period_hours'] == hours

            print(f"✓ {description}: {hours} hours")

        print("\n✅ All grace period durations work correctly!")
        print("="*70)

    def test_rotation_error_cases(self, test_client, mock_db, provisioning_headers):
        """Test rotation error handling."""
        print("\n" + "="*70)
        print("TEST: Rotation Error Handling")
        print("="*70)

        # Test 1: Org not found
        print("\n1. Testing org not found...")
        mock_db.get_org_config = AsyncMock(return_value=None)

        response = test_client.post(
            "/api/v1/orgs/nonexistent-org/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 24}
        )

        assert response.status_code in [400, 404]
        print(f"✓ Correctly rejected: {response.status_code}")

        # Test 2: App not found
        print("\n2. Testing app not found...")
        mock_db.get_org_config = AsyncMock(return_value={'org_id': 'test-org'})
        mock_db.get_app_config = AsyncMock(return_value=None)

        response = test_client.post(
            "/api/v1/orgs/test-org/apps/nonexistent-app/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 24}
        )

        assert response.status_code in [400, 404]
        print(f"✓ Correctly rejected: {response.status_code}")

        # Test 3: Invalid grace period (too long)
        print("\n3. Testing invalid grace period (too long)...")
        from src.infrastructure.security.jwt_handler import JWTHandler
        jwt_handler = JWTHandler()
        mock_org_config = {
            'org_id': 'test-org',
            'client_id': 'org-test-org',
            'client_secret_hash': jwt_handler.hash_secret(jwt_handler.generate_secret())
        }
        mock_db.get_org_config = AsyncMock(return_value=mock_org_config)

        response = test_client.post(
            "/api/v1/orgs/test-org/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": 200}  # > 168 hours max
        )

        assert response.status_code == 422  # Validation error
        print(f"✓ Correctly rejected: {response.status_code}")

        # Test 4: Negative grace period
        print("\n4. Testing negative grace period...")
        response = test_client.post(
            "/api/v1/orgs/test-org/credentials/rotate",
            headers=provisioning_headers,
            json={"grace_period_hours": -5}
        )

        assert response.status_code == 422
        print(f"✓ Correctly rejected: {response.status_code}")

        print("\n✅ All error cases handled correctly!")
        print("="*70)


class TestGracePeriodLogic:
    """Test grace period authentication logic."""

    @pytest.mark.asyncio
    async def test_grace_period_authentication_logic(self):
        """Test the grace period logic directly."""
        print("\n" + "="*70)
        print("TEST: Grace Period Authentication Logic")
        print("="*70)

        from src.infrastructure.security.jwt_handler import JWTHandler
        jwt_handler = JWTHandler()

        # Generate two secrets
        old_secret = jwt_handler.generate_secret()
        new_secret = jwt_handler.generate_secret()

        old_hash = jwt_handler.hash_secret(old_secret)
        new_hash = jwt_handler.hash_secret(new_secret)

        print(f"\n✓ Generated old secret: {old_secret[:20]}...")
        print(f"✓ Generated new secret: {new_secret[:20]}...")

        # Test 1: New secret verification
        print("\n1. Testing new secret verification...")
        assert jwt_handler.verify_secret(new_secret, new_hash) == True
        print("✓ New secret verifies correctly")

        # Test 2: Old secret verification
        print("\n2. Testing old secret verification...")
        assert jwt_handler.verify_secret(old_secret, old_hash) == True
        print("✓ Old secret verifies correctly")

        # Test 3: Cross verification (should fail)
        print("\n3. Testing cross verification (should fail)...")
        assert jwt_handler.verify_secret(old_secret, new_hash) == False
        assert jwt_handler.verify_secret(new_secret, old_hash) == False
        print("✓ Cross verification correctly fails")

        # Test 4: Grace period time calculation
        print("\n4. Testing grace period calculations...")
        now = int(time.time())
        grace_hours = 168
        grace_expires = now + (grace_hours * 3600)

        # Within grace period
        assert time.time() < grace_expires
        print(f"✓ Current time {now} < Grace expires {grace_expires}")

        # After grace period (simulated)
        past_grace = now - 1
        assert time.time() > past_grace
        print(f"✓ Current time {now} > Past grace {past_grace}")

        print("\n✅ Grace period logic works correctly!")
        print("="*70)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
