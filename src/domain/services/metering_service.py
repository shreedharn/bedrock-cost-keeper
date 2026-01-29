"""Metering service for cost submission and usage tracking."""

import hashlib
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import pytz

from ...infrastructure.database.bridge import DatabaseBridge
from ...core.exceptions import InvalidConfigException, InvalidRequestException
from ...core.config import main_config
from .pricing_service import PricingService


class MeteringService:
    """Service for handling metering operations."""

    def __init__(self, db_bridge: DatabaseBridge, pricing_service: Optional[PricingService] = None):
        """
        Initialize metering service.

        Args:
            db_bridge: Database bridge instance
            pricing_service: Optional pricing service instance for cost calculation
        """
        self.db = db_bridge
        self.pricing_service = pricing_service

    def _compute_scope(self, org_config: Dict[str, Any], org_id: str, app_id: str) -> str:
        """
        Compute scope key for database operations.

        Args:
            org_config: Organization configuration
            org_id: Organization UUID
            app_id: Application identifier

        Returns:
            Scope key string
        """
        quota_scope = org_config.get('quota_scope', 'ORG')

        if quota_scope == 'ORG':
            return f'ORG#{org_id}'
        else:  # APP
            return f'ORG#{org_id}#APP#{app_id}'

    def _compute_org_day(self, org_timezone: str) -> str:
        """
        Compute current day in organization's timezone.

        Args:
            org_timezone: IANA timezone string

        Returns:
            Day string in format "DAY#YYYYMMDD"
        """
        tz = pytz.timezone(org_timezone)
        now = datetime.now(timezone.utc).astimezone(tz)
        return f'DAY#{now.strftime("%Y%m%d")}'

    def _select_shard(self, request_id: str, shard_count: int) -> int:
        """
        Select shard based on request ID hash.

        Args:
            request_id: Request UUID
            shard_count: Total number of shards

        Returns:
            Shard ID (0 to shard_count-1)
        """
        hash_value = int(hashlib.sha256(request_id.encode()).hexdigest(), 16)
        return hash_value % shard_count

    async def submit_usage(
        self,
        org_id: str,
        app_id: str,
        request_id: str,
        model_label: str,
        bedrock_model_id: str,
        input_tokens: int,
        output_tokens: int,
        status: str,
        timestamp: datetime
    ) -> Dict[str, Any]:
        """
        Submit usage data for a request and calculate cost server-side.

        Calculates cost using current pricing from config.yaml or PricingCache table.

        Args:
            org_id: Organization UUID
            app_id: Application identifier
            request_id: Request UUID
            model_label: Model label used
            bedrock_model_id: Bedrock model ID
            input_tokens: Input token count
            output_tokens: Output token count
            status: Request status (OK or ERROR)
            timestamp: When request occurred

        Returns:
            Submission result with processing info and calculated cost

        Raises:
            InvalidConfigException: If model label not configured
            InvalidRequestException: If timestamp out of range
            ValueError: If pricing not found for model
        """
        # Get org config
        org_config = await self.db.get_org_config(org_id)
        if not org_config:
            raise InvalidConfigException(
                f"Organization {org_id} not found",
                details={'org_id': org_id}
            )

        # Get app config (may be None)
        app_config = await self.db.get_app_config(org_id, app_id)

        # Merge configs (app overrides org)
        effective_config = {**org_config}
        if app_config:
            effective_config.update(app_config)

        # Validate model label
        model_ordering = effective_config.get('model_ordering', [])
        if model_label not in model_ordering:
            raise InvalidConfigException(
                f"Model label '{model_label}' not configured for this application",
                details={
                    'model_label': model_label,
                    'configured_labels': model_ordering,
                    'app_id': app_id
                }
            )

        # Calculate cost from usage using PricingService
        date = timestamp.strftime('%Y-%m-%d')
        if self.pricing_service:
            pricing = await self.pricing_service.get_pricing(bedrock_model_id, date)
            cost_usd_micros = self.pricing_service.calculate_cost(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_price_per_1m=pricing['input_price_usd_micros_per_1m'],
                output_price_per_1m=pricing['output_price_usd_micros_per_1m']
            )
        else:
            # Fallback if pricing_service not provided (for backward compatibility)
            raise InvalidConfigException(
                "PricingService required for cost calculation",
                details={'bedrock_model_id': bedrock_model_id}
            )

        # Compute scope and day
        scope = self._compute_scope(org_config, org_id, app_id)
        day = self._compute_org_day(effective_config['timezone'])

        # Validate timestamp is within acceptable range (±24 hours of org day)
        # TODO: Implement timestamp validation

        # Select shard
        shard_count = effective_config.get('agg_shard_count', 8)
        shard_id = self._select_shard(request_id, shard_count)

        # Update usage shard (idempotent)
        await self.db.update_usage_shard(
            scope=scope,
            day=day,
            model_label=model_label,
            shard_id=shard_id,
            cost_usd_micros=cost_usd_micros,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            requests=1,
            request_id=request_id
        )

        # Get current daily total for response
        daily_total = await self.db.get_daily_total(scope, day, model_label)

        return {
            'request_id': request_id,
            'status': 'accepted',
            'message': 'Usage data queued for processing',
            'processing': {
                'shard_id': shard_id,
                'expected_aggregation_lag_secs': 60,
                'cost_usd_micros': cost_usd_micros
            },
            'daily_total': daily_total,
            'timestamp': datetime.now(timezone.utc)
        }

    # Legacy alias for backward compatibility
    async def submit_cost(
        self,
        org_id: str,
        app_id: str,
        request_id: str,
        model_label: str,
        bedrock_model_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd_micros: int,
        status: str,
        timestamp: datetime
    ) -> Dict[str, Any]:
        """
        Legacy method - use submit_usage instead.

        This method is deprecated and will be removed in a future version.
        """
        # Ignore the provided cost_usd_micros and calculate server-side
        return await self.submit_usage(
            org_id=org_id,
            app_id=app_id,
            request_id=request_id,
            model_label=model_label,
            bedrock_model_id=bedrock_model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            status=status,
            timestamp=timestamp
        )

    async def get_current_usage(
        self,
        org_id: str,
        app_id: str,
        model_labels: list[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get current usage for specified models.

        Args:
            org_id: Organization UUID
            app_id: Application identifier
            model_labels: List of model labels to query

        Returns:
            Dict mapping model label to usage data
        """
        # Get org config
        org_config = await self.db.get_org_config(org_id)
        if not org_config:
            return {}

        # Compute scope and day
        scope = self._compute_scope(org_config, org_id, app_id)
        day = self._compute_org_day(org_config['timezone'])

        # Get daily totals for all labels
        totals = await self.db.get_daily_totals_batch(scope, day, model_labels)

        return totals

    async def check_quota_status(
        self,
        org_id: str,
        app_id: str,
        model_label: str
    ) -> Dict[str, Any]:
        """
        Check quota status for a specific model.

        Args:
            org_id: Organization UUID
            app_id: Application identifier
            model_label: Model label to check

        Returns:
            Quota status information
        """
        # Get org and app configs
        org_config = await self.db.get_org_config(org_id)
        if not org_config:
            return {'exceeded': True, 'quota_pct': 0}

        app_config = await self.db.get_app_config(org_id, app_id)
        effective_config = {**org_config}
        if app_config:
            effective_config.update(app_config)

        # Get quota for this model
        quotas = effective_config.get('quotas', {})
        quota = quotas.get(model_label, 0)

        if quota == 0:
            return {'exceeded': True, 'quota_pct': 0}

        # Get current spend
        scope = self._compute_scope(org_config, org_id, app_id)
        day = self._compute_org_day(effective_config['timezone'])
        daily_total = await self.db.get_daily_total(scope, day, model_label)

        if not daily_total:
            return {
                'exceeded': False,
                'quota_pct': 0.0,
                'spend': 0,
                'quota': quota
            }

        spend = daily_total.get('cost_usd_micros', 0)
        quota_pct = (spend / quota) * 100 if quota > 0 else 0

        return {
            'exceeded': spend >= quota,
            'quota_pct': quota_pct,
            'spend': spend,
            'quota': quota
        }
