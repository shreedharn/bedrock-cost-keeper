"""Unit tests for MeteringService."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from src.domain.services.metering_service import MeteringService
from src.domain.services.pricing_service import PricingService


@pytest.fixture
def mock_db():
    """Create a mock database bridge."""
    db = MagicMock()
    db.get_org_config = AsyncMock(return_value={
        'timezone': 'America/New_York',
        'quota_scope': 'APP',
        'model_ordering': ['premium', 'standard', 'economy'],
        'agg_shard_count': 8
    })
    db.get_app_config = AsyncMock(return_value=None)
    db.update_usage_shard = AsyncMock()
    db.get_daily_total = AsyncMock(return_value={
        'total_cost_usd_micros': 50000,
        'total_requests': 10
    })
    return db


@pytest.fixture
def mock_pricing_service():
    """Create a mock pricing service."""
    pricing_service = MagicMock(spec=PricingService)
    pricing_service.get_pricing = AsyncMock(return_value={
        'input_price_usd_micros_per_1m': 3000000,
        'output_price_usd_micros_per_1m': 15000000
    })
    pricing_service.calculate_cost = MagicMock(return_value=16500)
    return pricing_service


@pytest.fixture
def metering_service(mock_db, mock_pricing_service):
    """Create a MeteringService instance."""
    return MeteringService(mock_db, mock_pricing_service)


class TestSubmitUsage:
    """Tests for submit_usage method."""

    @pytest.mark.asyncio
    async def test_submit_usage_calculates_cost_from_pricing(self, metering_service, mock_pricing_service):
        """Test that submit_usage calls pricing service to calculate cost."""
        result = await metering_service.submit_usage(
            org_id='550e8400-e29b-41d4-a716-446655440000',
            app_id='test-app',
            request_id='a1b2c3d4-e5f6-7890-abcd-ef1234567890',
            model_label='premium',
            bedrock_model_id='anthropic.claude-3-5-sonnet-20241022-v2:0',
            input_tokens=1500,
            output_tokens=800,
            status='OK',
            timestamp=datetime.now(timezone.utc)
        )

        # Verify pricing service was called
        mock_pricing_service.get_pricing.assert_called_once()
        mock_pricing_service.calculate_cost.assert_called_once_with(
            input_tokens=1500,
            output_tokens=800,
            input_price_per_1m=3000000,
            output_price_per_1m=15000000
        )

        # Verify result contains calculated cost
        assert result['status'] == 'accepted'
        assert result['processing']['cost_usd_micros'] == 16500

    @pytest.mark.asyncio
    async def test_submit_usage_stores_calculated_cost(self, metering_service, mock_db):
        """Test that calculated cost is stored in usage shard."""
        await metering_service.submit_usage(
            org_id='550e8400-e29b-41d4-a716-446655440000',
            app_id='test-app',
            request_id='a1b2c3d4-e5f6-7890-abcd-ef1234567890',
            model_label='premium',
            bedrock_model_id='anthropic.claude-3-5-sonnet-20241022-v2:0',
            input_tokens=1500,
            output_tokens=800,
            status='OK',
            timestamp=datetime.now(timezone.utc)
        )

        # Verify update_usage_shard was called with calculated cost
        mock_db.update_usage_shard.assert_called_once()
        call_args = mock_db.update_usage_shard.call_args
        assert call_args.kwargs['cost_usd_micros'] == 16500
        assert call_args.kwargs['input_tokens'] == 1500
        assert call_args.kwargs['output_tokens'] == 800

    @pytest.mark.asyncio
    async def test_submit_usage_invalid_model_label(self, metering_service):
        """Test that invalid model label raises exception."""
        from src.core.exceptions import InvalidConfigException

        with pytest.raises(InvalidConfigException, match="not configured"):
            await metering_service.submit_usage(
                org_id='550e8400-e29b-41d4-a716-446655440000',
                app_id='test-app',
                request_id='a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                model_label='invalid_label',
                bedrock_model_id='anthropic.claude-3-5-sonnet-20241022-v2:0',
                input_tokens=1500,
                output_tokens=800,
                status='OK',
                timestamp=datetime.now(timezone.utc)
            )

    @pytest.mark.asyncio
    async def test_submit_usage_org_not_found(self, metering_service, mock_db):
        """Test that missing org raises exception."""
        from src.core.exceptions import InvalidConfigException

        mock_db.get_org_config.return_value = None

        with pytest.raises(InvalidConfigException, match="not found"):
            await metering_service.submit_usage(
                org_id='invalid-org',
                app_id='test-app',
                request_id='a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                model_label='premium',
                bedrock_model_id='anthropic.claude-3-5-sonnet-20241022-v2:0',
                input_tokens=1500,
                output_tokens=800,
                status='OK',
                timestamp=datetime.now(timezone.utc)
            )

    @pytest.mark.asyncio
    async def test_submit_usage_without_pricing_service(self, mock_db):
        """Test that missing pricing service raises exception."""
        from src.core.exceptions import InvalidConfigException

        metering_service = MeteringService(mock_db, pricing_service=None)

        with pytest.raises(InvalidConfigException, match="PricingService required"):
            await metering_service.submit_usage(
                org_id='550e8400-e29b-41d4-a716-446655440000',
                app_id='test-app',
                request_id='a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                model_label='premium',
                bedrock_model_id='anthropic.claude-3-5-sonnet-20241022-v2:0',
                input_tokens=1500,
                output_tokens=800,
                status='OK',
                timestamp=datetime.now(timezone.utc)
            )


class TestLegacySubmitCost:
    """Tests for legacy submit_cost method."""

    @pytest.mark.asyncio
    async def test_submit_cost_delegates_to_submit_usage(self, metering_service, mock_pricing_service):
        """Test that submit_cost delegates to submit_usage."""
        result = await metering_service.submit_cost(
            org_id='550e8400-e29b-41d4-a716-446655440000',
            app_id='test-app',
            request_id='a1b2c3d4-e5f6-7890-abcd-ef1234567890',
            model_label='premium',
            bedrock_model_id='anthropic.claude-3-5-sonnet-20241022-v2:0',
            input_tokens=1500,
            output_tokens=800,
            cost_usd_micros=99999,  # This should be ignored
            status='OK',
            timestamp=datetime.now(timezone.utc)
        )

        # Verify pricing service was still called (cost_usd_micros ignored)
        mock_pricing_service.calculate_cost.assert_called_once()

        # Verify server-calculated cost used, not client-provided
        assert result['processing']['cost_usd_micros'] == 16500
        assert result['processing']['cost_usd_micros'] != 99999
