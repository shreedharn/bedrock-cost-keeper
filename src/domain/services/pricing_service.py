"""Pricing service for cost calculations and pricing data management.

This service provides:
1. Three-tier pricing lookup (in-memory cache → DynamoDB → config.yaml)
2. Cost calculation from token usage
3. Centralized pricing management
"""

import time
from typing import Dict, Any, Optional
from datetime import datetime

from src.infrastructure.database.dynamodb_bridge import DynamoDBBridge


class PricingService:
    """Service for managing pricing data and cost calculations."""

    def __init__(self, db: DynamoDBBridge, config: dict):
        """Initialize the pricing service.

        Args:
            db: DynamoDB bridge for pricing cache lookups
            config: Configuration dict containing model_labels pricing data
        """
        self.db = db
        self.config = config
        self._cache: Dict[str, tuple[Dict[str, Any], float]] = {}
        self._cache_ttl = 300  # 5 minutes

    async def get_pricing(self, bedrock_model_id: str, date: str) -> Dict[str, Any]:
        """Get pricing for a model on a specific date.

        Priority order:
        1. In-memory cache (5-minute TTL)
        2. DynamoDB PricingCache table
        3. config.yaml fallback

        Args:
            bedrock_model_id: The Bedrock model ID (e.g., "anthropic.claude-3-5-sonnet-20241022-v2:0")
            date: Date string in YYYY-MM-DD format

        Returns:
            Dict containing pricing data with keys:
                - input_price_usd_micros_per_1m: Input token price per 1M tokens
                - output_price_usd_micros_per_1m: Output token price per 1M tokens

        Raises:
            ValueError: If no pricing found for the model
        """
        # Check in-memory cache
        cache_key = f"{bedrock_model_id}:{date}"
        if cache_key in self._cache:
            cached_data, cached_time = self._cache[cache_key]
            if time.time() - cached_time < self._cache_ttl:
                return cached_data

        # Check DynamoDB PricingCache
        pricing = await self.db.get_pricing(bedrock_model_id, date)
        if pricing:
            # Store in in-memory cache
            self._cache[cache_key] = (pricing, time.time())
            return pricing

        # Fallback to config.yaml
        pricing = self._get_pricing_from_config(bedrock_model_id)
        if pricing:
            # Cache config pricing too
            self._cache[cache_key] = (pricing, time.time())
            return pricing

        raise ValueError(f"No pricing found for model {bedrock_model_id}")

    def _get_pricing_from_config(self, bedrock_model_id: str) -> Optional[Dict[str, Any]]:
        """Extract pricing from config.yaml for a bedrock_model_id.

        Args:
            bedrock_model_id: The Bedrock model ID to look up

        Returns:
            Dict with pricing data if found, None otherwise
        """
        model_labels = self.config.get('model_labels', {})
        for label, model_config in model_labels.items():
            if model_config.get('bedrock_model_id') == bedrock_model_id:
                return {
                    'input_price_usd_micros_per_1m': model_config['input_price_usd_micros_per_1m'],
                    'output_price_usd_micros_per_1m': model_config['output_price_usd_micros_per_1m']
                }
        return None

    def calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        input_price_per_1m: int,
        output_price_per_1m: int
    ) -> int:
        """Calculate cost in USD micros from token usage and pricing.

        Formula:
            cost = (input_tokens × input_price_per_1m / 1M) + (output_tokens × output_price_per_1m / 1M)

        Uses integer division to prevent floating-point errors.

        Args:
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens used
            input_price_per_1m: Price per 1M input tokens in USD micros
            output_price_per_1m: Price per 1M output tokens in USD micros

        Returns:
            Cost in USD micros (1 USD = 1,000,000 micro-USD)

        Example:
            >>> service.calculate_cost(
            ...     input_tokens=1500,
            ...     output_tokens=800,
            ...     input_price_per_1m=3000000,
            ...     output_price_per_1m=15000000
            ... )
            16500000  # $16.50
        """
        input_cost_micros = (input_tokens * input_price_per_1m) // 1_000_000
        output_cost_micros = (output_tokens * output_price_per_1m) // 1_000_000
        return input_cost_micros + output_cost_micros
