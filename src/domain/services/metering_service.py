"""Metering service for cost submission and usage tracking."""

import hashlib
from typing import Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime, timezone
import pytz

from ...infrastructure.database.bridge import DatabaseBridge
from ...core.exceptions import InvalidConfigException, InvalidRequestException
from ...core.config import main_config
from .pricing_service import PricingService

if TYPE_CHECKING:
    from .inference_profile_service import InferenceProfileService


class MeteringService:
    """Service for handling metering operations."""

    def __init__(
        self,
        db_bridge: DatabaseBridge,
        pricing_service: Optional[PricingService] = None,
        profile_service: Optional['InferenceProfileService'] = None,
        config: Optional[dict] = None
    ):
        """
        Initialize metering service.

        Args:
            db_bridge: Database bridge instance
            pricing_service: Optional pricing service instance for cost calculation
            profile_service: Optional inference profile service for profile resolution
            config: Optional configuration dict for model label lookups
        """
        self.db = db_bridge
        self.pricing_service = pricing_service
        self.profile_service = profile_service
        self.config = config or main_config

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
        timestamp: datetime,
        calling_region: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submit usage data for a request and calculate cost server-side.

        Calculates cost using current pricing from config.yaml or PricingCache table.
        The model_label can point to either a traditional bedrock_model_id or a
        registered inference profile.

        Args:
            org_id: Organization UUID
            app_id: Application identifier
            request_id: Request UUID
            model_label: Model label used (points to model or inference profile)
            bedrock_model_id: Bedrock model ID (for backward compatibility)
            input_tokens: Input token count
            output_tokens: Output token count
            status: Request status (OK or ERROR)
            timestamp: When request occurred
            calling_region: AWS region where request was made (required for inference profiles)

        Returns:
            Submission result with processing info and calculated cost

        Raises:
            InvalidConfigException: If model label not configured
            InvalidRequestException: If timestamp out of range
            ValueError: If pricing not found for model or calling_region missing for profile
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

        # Resolve label to get actual model ID and type
        label_info = await self._resolve_label(org_id, app_id, model_label)

        # Get actual model ID for pricing based on label type
        if label_info['type'] == 'profile':
            # Inference profile - need calling_region
            if not calling_region:
                raise InvalidRequestException(
                    f"calling_region is required when using inference profile label: {model_label}",
                    details={'model_label': model_label, 'label_type': 'profile'}
                )

            # Get model for the calling region
            actual_model_id = await self.profile_service.get_model_for_region(
                org_id=org_id,
                app_id=app_id,
                profile_label=model_label,
                calling_region=calling_region
            )
            pricing_region = calling_region
        else:
            # Traditional model - use bedrock_model_id
            actual_model_id = bedrock_model_id
            pricing_region = None

        # Calculate cost from usage using PricingService
        date = timestamp.strftime('%Y-%m-%d')
        if self.pricing_service:
            pricing = await self.pricing_service.get_pricing(
                bedrock_model_id=actual_model_id,
                date=date,
                region=pricing_region
            )
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
                details={'bedrock_model_id': actual_model_id}
            )

        # Compute scope and day
        scope = self._compute_scope(org_config, org_id, app_id)
        day = self._compute_org_day(effective_config['timezone'])

        # Validate timestamp is within acceptable range
        now = datetime.now(timezone.utc)
        time_diff_seconds = (timestamp - now).total_seconds()

        # Reject if > 5 minutes in future
        if time_diff_seconds > 300:  # 5 minutes
            raise InvalidRequestException(
                "Timestamp too far in future",
                {
                    "timestamp": timestamp.isoformat(),
                    "current_time": now.isoformat(),
                    "max_future_seconds": 300
                }
            )

        # Reject if > 24 hours in past
        if time_diff_seconds < -86400:  # 24 hours
            raise InvalidRequestException(
                "Timestamp too far in past",
                {
                    "timestamp": timestamp.isoformat(),
                    "current_time": now.isoformat(),
                    "max_past_seconds": 86400
                }
            )

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

    async def _resolve_label(
        self,
        org_id: str,
        app_id: str,
        model_label: str
    ) -> Dict[str, Any]:
        """Resolve a model label to either a model_id or inference_profile_arn.

        Priority order:
        1. Check registered inference profiles (database)
        2. Check config.yaml model_labels

        Args:
            org_id: Organization ID
            app_id: Application ID
            model_label: Label to resolve

        Returns:
            Dict with keys:
                - type: "model" or "profile"
                - identifier: bedrock_model_id or inference_profile_arn
                - label: the original label

        Raises:
            InvalidConfigException: If label not found in either location
        """
        # Check database for registered inference profile
        if self.profile_service:
            profile = await self.db.get_inference_profile(org_id, app_id, model_label)
            if profile:
                return {
                    'type': 'profile',
                    'identifier': profile['inference_profile_arn'],
                    'label': model_label
                }

        # Check config.yaml for model or profile
        model_config = self.config.get('model_labels', {}).get(model_label)
        if model_config:
            label_type = model_config.get('type', 'model')  # Default to 'model' for backward compatibility
            return {
                'type': label_type,
                'identifier': model_config['id'],  # Now using 'id' instead of 'bedrock_model_id'
                'label': model_label
            }

        raise InvalidConfigException(
            f"Unknown model_label: {model_label}. Not found in registered profiles or config.yaml",
            details={'model_label': model_label}
        )

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
