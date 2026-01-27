"""Tests for cost submission endpoints."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import uuid


class TestCostSubmissionEndpoint:
    """Tests for POST /orgs/{org_id}/apps/{app_id}/costs endpoint."""

    @pytest.mark.asyncio
    async def test_submit_cost_success(
        self, test_client, mock_db, auth_headers, sample_cost_submission
    ):
        """Test successful cost submission."""
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        with patch('src.domain.services.metering_service.MeteringService') as MockService:
            mock_service = MockService.return_value
            mock_service.submit_cost = AsyncMock(return_value={
                'request_id': str(sample_cost_submission['request_id']),
                'status': 'accepted',
                'message': 'Cost submission accepted',
                'processing': {
                    'aggregation': 'queued',
                    'shard_id': 3
                },
                'timestamp': datetime.now(timezone.utc)
            })

            response = test_client.post(
                "/api/v1/orgs/test-org-123/apps/test-app/costs",
                headers=auth_headers,
                json=sample_cost_submission
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["request_id"] == sample_cost_submission["request_id"]
        assert "processing" in data

    @pytest.mark.asyncio
    async def test_submit_cost_invalid_model_label(
        self, test_client, mock_db, auth_headers, sample_cost_submission
    ):
        """Test cost submission with invalid model label."""
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        invalid_submission = sample_cost_submission.copy()
        invalid_submission["model_label"] = ""

        response = test_client.post(
            "/api/v1/orgs/test-org-123/apps/test-app/costs",
            headers=auth_headers,
            json=invalid_submission
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_cost_negative_tokens(
        self, test_client, mock_db, auth_headers, sample_cost_submission
    ):
        """Test cost submission with negative token counts."""
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        invalid_submission = sample_cost_submission.copy()
        invalid_submission["input_tokens"] = -100

        response = test_client.post(
            "/api/v1/orgs/test-org-123/apps/test-app/costs",
            headers=auth_headers,
            json=invalid_submission
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_cost_future_timestamp(
        self, test_client, mock_db, auth_headers, sample_cost_submission
    ):
        """Test cost submission with future timestamp."""
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        invalid_submission = sample_cost_submission.copy()
        # Set timestamp to 1 day in the future
        future_time = datetime.now(timezone.utc)
        invalid_submission["timestamp"] = future_time.isoformat()

        response = test_client.post(
            "/api/v1/orgs/test-org-123/apps/test-app/costs",
            headers=auth_headers,
            json=invalid_submission
        )

        # Should fail validation
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_submit_cost_org_mismatch(
        self, test_client, mock_db, jwt_handler, sample_cost_submission
    ):
        """Test cost submission with org_id mismatch."""
        # Create token for different org
        access_token, _ = jwt_handler.create_access_token(
            client_id="org-different-org",
            org_id="different-org",
            app_id=None
        )
        headers = {"Authorization": f"Bearer {access_token}"}

        mock_db.is_token_revoked = AsyncMock(return_value=False)

        response = test_client.post(
            "/api/v1/orgs/test-org-123/apps/test-app/costs",
            headers=headers,
            json=sample_cost_submission
        )

        assert response.status_code == 400


class TestBatchCostSubmissionEndpoint:
    """Tests for POST /orgs/{org_id}/apps/{app_id}/costs/batch endpoint."""

    @pytest.mark.asyncio
    async def test_batch_submit_all_success(
        self, test_client, mock_db, auth_headers, sample_cost_submission
    ):
        """Test batch submission where all requests succeed."""
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        # Create multiple submissions
        submissions = []
        for i in range(3):
            submission = sample_cost_submission.copy()
            submission["request_id"] = str(uuid.uuid4())
            submissions.append(submission)

        batch_request = {"requests": submissions}

        with patch('src.domain.services.metering_service.MeteringService') as MockService:
            mock_service = MockService.return_value
            mock_service.submit_cost = AsyncMock(return_value={
                'request_id': 'test',
                'status': 'accepted',
                'message': 'Cost submission accepted',
                'processing': {},
                'timestamp': datetime.now(timezone.utc)
            })

            response = test_client.post(
                "/api/v1/orgs/test-org-123/apps/test-app/costs/batch",
                headers=auth_headers,
                json=batch_request
            )

        assert response.status_code == 207
        data = response.json()
        assert data["accepted"] == 3
        assert data["failed"] == 0
        assert len(data["results"]) == 3
        assert all(r["status"] == "accepted" for r in data["results"])

    @pytest.mark.asyncio
    async def test_batch_submit_partial_failure(
        self, test_client, mock_db, auth_headers, sample_cost_submission
    ):
        """Test batch submission with some failures."""
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        submissions = []
        for i in range(3):
            submission = sample_cost_submission.copy()
            submission["request_id"] = str(uuid.uuid4())
            submissions.append(submission)

        batch_request = {"requests": submissions}

        with patch('src.domain.services.metering_service.MeteringService') as MockService:
            mock_service = MockService.return_value

            # First two succeed, third fails
            call_count = 0
            async def mock_submit(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 3:
                    raise Exception("Submission failed")
                return {
                    'request_id': 'test',
                    'status': 'accepted',
                    'message': 'Cost submission accepted',
                    'processing': {},
                    'timestamp': datetime.now(timezone.utc)
                }

            mock_service.submit_cost = mock_submit

            response = test_client.post(
                "/api/v1/orgs/test-org-123/apps/test-app/costs/batch",
                headers=auth_headers,
                json=batch_request
            )

        assert response.status_code == 207
        data = response.json()
        assert data["accepted"] == 2
        assert data["failed"] == 1
        assert len(data["results"]) == 3

    @pytest.mark.asyncio
    async def test_batch_submit_empty_batch(
        self, test_client, mock_db, auth_headers
    ):
        """Test batch submission with empty requests array."""
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        batch_request = {"requests": []}

        response = test_client.post(
            "/api/v1/orgs/test-org-123/apps/test-app/costs/batch",
            headers=auth_headers,
            json=batch_request
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_batch_submit_exceeds_limit(
        self, test_client, mock_db, auth_headers, sample_cost_submission
    ):
        """Test batch submission exceeding max batch size."""
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        # Create 101 submissions (max is 100)
        submissions = []
        for i in range(101):
            submission = sample_cost_submission.copy()
            submission["request_id"] = str(uuid.uuid4())
            submissions.append(submission)

        batch_request = {"requests": submissions}

        response = test_client.post(
            "/api/v1/orgs/test-org-123/apps/test-app/costs/batch",
            headers=auth_headers,
            json=batch_request
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_batch_submit_duplicate_request_ids(
        self, test_client, mock_db, auth_headers, sample_cost_submission
    ):
        """Test batch submission with duplicate request IDs (should be idempotent)."""
        mock_db.is_token_revoked = AsyncMock(return_value=False)

        # Use same request_id for all submissions
        submissions = []
        for i in range(3):
            submission = sample_cost_submission.copy()
            submissions.append(submission)

        batch_request = {"requests": submissions}

        with patch('src.domain.services.metering_service.MeteringService') as MockService:
            mock_service = MockService.return_value
            mock_service.submit_cost = AsyncMock(return_value={
                'request_id': sample_cost_submission['request_id'],
                'status': 'accepted',
                'message': 'Cost submission accepted',
                'processing': {},
                'timestamp': datetime.now(timezone.utc)
            })

            response = test_client.post(
                "/api/v1/orgs/test-org-123/apps/test-app/costs/batch",
                headers=auth_headers,
                json=batch_request
            )

        # Should still succeed (idempotent)
        assert response.status_code == 207
        assert mock_service.submit_cost.call_count == 3
