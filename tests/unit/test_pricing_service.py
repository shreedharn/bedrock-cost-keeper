"""Unit tests for PricingService."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.domain.services.pricing_service import PricingService


@pytest.fixture
def mock_db():
    """Create a mock database bridge."""
    db = MagicMock()
    db.get_pricing = AsyncMock(return_value=None)
    return db


@pytest.fixture
def test_config():
    """Create test configuration with model pricing."""
    return {
        'model_labels': {
            'premium': {
                'bedrock_model_id': 'anthropic.claude-3-5-sonnet-20241022-v2:0',
                'input_price_usd_micros_per_1m': 3000000,
                'output_price_usd_micros_per_1m': 15000000
            },
            'standard': {
                'bedrock_model_id': 'anthropic.claude-3-5-haiku-20241022-v1:0',
                'input_price_usd_micros_per_1m': 800000,
                'output_price_usd_micros_per_1m': 4000000
            },
            'economy': {
                'bedrock_model_id': 'anthropic.claude-3-haiku-20240307-v1:0',
                'input_price_usd_micros_per_1m': 250000,
                'output_price_usd_micros_per_1m': 1250000
            }
        }
    }


@pytest.fixture
def pricing_service(mock_db, test_config):
    """Create a PricingService instance."""
    return PricingService(mock_db, test_config)


class TestGetPricingFromConfig:
    """Tests for _get_pricing_from_config method."""

    def test_get_pricing_from_config_yaml(self, pricing_service):
        """Test pricing lookup from config.yaml."""
        pricing = pricing_service._get_pricing_from_config(
            'anthropic.claude-3-5-sonnet-20241022-v2:0'
        )

        assert pricing is not None
        assert pricing['input_price_usd_micros_per_1m'] == 3000000
        assert pricing['output_price_usd_micros_per_1m'] == 15000000

    def test_get_pricing_from_config_standard_model(self, pricing_service):
        """Test pricing lookup for standard model."""
        pricing = pricing_service._get_pricing_from_config(
            'anthropic.claude-3-5-haiku-20241022-v1:0'
        )

        assert pricing is not None
        assert pricing['input_price_usd_micros_per_1m'] == 800000
        assert pricing['output_price_usd_micros_per_1m'] == 4000000

    def test_get_pricing_missing_model_returns_none(self, pricing_service):
        """Test that missing model returns None."""
        pricing = pricing_service._get_pricing_from_config(
            'anthropic.claude-unknown-model'
        )

        assert pricing is None


class TestGetPricing:
    """Tests for get_pricing method."""

    @pytest.mark.asyncio
    async def test_get_pricing_cache_hit(self, pricing_service):
        """Test that in-memory cache returns cached data."""
        # Populate cache
        bedrock_model_id = 'anthropic.claude-3-5-sonnet-20241022-v2:0'
        date = '2026-01-29'

        # First call should populate cache from config
        pricing1 = await pricing_service.get_pricing(bedrock_model_id, date)

        # Second call should hit cache (verify db not called again)
        pricing_service.db.get_pricing.reset_mock()
        pricing2 = await pricing_service.get_pricing(bedrock_model_id, date)

        assert pricing1 == pricing2
        pricing_service.db.get_pricing.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_pricing_cache_miss_queries_dynamodb(self, pricing_service):
        """Test that cache miss queries DynamoDB."""
        bedrock_model_id = 'anthropic.claude-3-5-sonnet-20241022-v2:0'
        date = '2026-01-29'

        # Mock DynamoDB response
        dynamodb_pricing = {
            'input_price_usd_micros_per_1m': 3500000,
            'output_price_usd_micros_per_1m': 16000000
        }
        pricing_service.db.get_pricing.return_value = dynamodb_pricing

        # Clear cache to force DynamoDB lookup
        pricing_service._cache = {}

        pricing = await pricing_service.get_pricing(bedrock_model_id, date)

        assert pricing == dynamodb_pricing
        pricing_service.db.get_pricing.assert_called_once_with(bedrock_model_id, date)

    @pytest.mark.asyncio
    async def test_get_pricing_cache_stores_in_memory(self, pricing_service):
        """Test that pricing is stored in in-memory cache."""
        bedrock_model_id = 'anthropic.claude-3-5-sonnet-20241022-v2:0'
        date = '2026-01-29'

        # First call should populate cache
        await pricing_service.get_pricing(bedrock_model_id, date)

        # Check cache was populated
        cache_key = f"{bedrock_model_id}:{date}"
        assert cache_key in pricing_service._cache

    @pytest.mark.asyncio
    async def test_get_pricing_fallback_to_config(self, pricing_service):
        """Test fallback to config.yaml when DynamoDB has no data."""
        bedrock_model_id = 'anthropic.claude-3-5-sonnet-20241022-v2:0'
        date = '2026-01-29'

        # DynamoDB returns None
        pricing_service.db.get_pricing.return_value = None

        pricing = await pricing_service.get_pricing(bedrock_model_id, date)

        assert pricing is not None
        assert pricing['input_price_usd_micros_per_1m'] == 3000000
        assert pricing['output_price_usd_micros_per_1m'] == 15000000

    @pytest.mark.asyncio
    async def test_get_pricing_missing_model_raises_error(self, pricing_service):
        """Test that missing model raises ValueError."""
        # DynamoDB returns None
        pricing_service.db.get_pricing.return_value = None

        with pytest.raises(ValueError, match="No pricing found for model"):
            await pricing_service.get_pricing('unknown-model', '2026-01-29')


class TestCalculateCost:
    """Tests for calculate_cost method."""

    def test_calculate_cost_correct_formula(self, pricing_service):
        """Test cost calculation with known values."""
        # Premium model: $3 input, $15 output per 1M tokens
        # 1500 input tokens, 800 output tokens
        cost = pricing_service.calculate_cost(
            input_tokens=1500,
            output_tokens=800,
            input_price_per_1m=3000000,
            output_price_per_1m=15000000
        )

        # Expected: (1500 * 3000000 / 1M) + (800 * 15000000 / 1M)
        #         = 4500 + 12000 = 16500 micro-USD = $0.0165
        assert cost == 16500

    def test_calculate_cost_zero_tokens(self, pricing_service):
        """Test calculation with zero tokens."""
        cost = pricing_service.calculate_cost(
            input_tokens=0,
            output_tokens=0,
            input_price_per_1m=3000000,
            output_price_per_1m=15000000
        )

        assert cost == 0

    def test_calculate_cost_only_input_tokens(self, pricing_service):
        """Test calculation with only input tokens."""
        cost = pricing_service.calculate_cost(
            input_tokens=1000000,  # 1M tokens
            output_tokens=0,
            input_price_per_1m=3000000,
            output_price_per_1m=15000000
        )

        # 1M * $3 / 1M = $3.00 = 3,000,000 micro-USD
        assert cost == 3000000

    def test_calculate_cost_only_output_tokens(self, pricing_service):
        """Test calculation with only output tokens."""
        cost = pricing_service.calculate_cost(
            input_tokens=0,
            output_tokens=1000000,  # 1M tokens
            input_price_per_1m=3000000,
            output_price_per_1m=15000000
        )

        # 1M * $15 / 1M = $15.00 = 15,000,000 micro-USD
        assert cost == 15000000

    def test_calculate_cost_large_numbers(self, pricing_service):
        """Test calculation with large token counts."""
        cost = pricing_service.calculate_cost(
            input_tokens=10000000,  # 10M tokens
            output_tokens=5000000,   # 5M tokens
            input_price_per_1m=3000000,
            output_price_per_1m=15000000
        )

        # (10M * 3 / 1) + (5M * 15 / 1) = 30 + 75 = 105 USD = 105M micro-USD
        assert cost == 105000000

    def test_calculate_cost_economy_model(self, pricing_service):
        """Test calculation with economy model pricing."""
        cost = pricing_service.calculate_cost(
            input_tokens=1500,
            output_tokens=800,
            input_price_per_1m=250000,  # $0.25 per 1M
            output_price_per_1m=1250000  # $1.25 per 1M
        )

        # (1500 * 250000 / 1M) + (800 * 1250000 / 1M)
        # = 375 + 1000 = 1375 micro-USD
        assert cost == 1375

    def test_calculate_cost_integer_division_precision(self, pricing_service):
        """Test that integer division works correctly for small values."""
        # Very small token counts
        cost = pricing_service.calculate_cost(
            input_tokens=1,
            output_tokens=1,
            input_price_per_1m=3000000,
            output_price_per_1m=15000000
        )

        # (1 * 3000000 / 1M) + (1 * 15000000 / 1M) = 3 + 15 = 18 micro-USD
        assert cost == 18

    def test_calculate_cost_various_inputs(self, pricing_service):
        """Test calculation with various realistic input/output ratios."""
        test_cases = [
            # (input_tokens, output_tokens, expected_cost)
            (1000, 100, 4500),     # Typical completion
            (500, 1500, 24000),    # Long response
            (10000, 500, 37500),   # Long prompt
        ]

        for input_tokens, output_tokens, expected_cost in test_cases:
            cost = pricing_service.calculate_cost(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_price_per_1m=3000000,
                output_price_per_1m=15000000
            )
            assert cost == expected_cost, f"Failed for {input_tokens} input, {output_tokens} output"
