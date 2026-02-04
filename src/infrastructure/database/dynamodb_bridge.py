"""DynamoDB implementation of the database bridge."""

import time
from typing import Optional, Dict, Any, List
import aioboto3
from botocore.exceptions import ClientError

from .bridge import DatabaseBridge
from ...core.config import settings


class DynamoDBBridge(DatabaseBridge):
    """DynamoDB implementation of database operations."""

    def __init__(self):
        """Initialize DynamoDB bridge."""
        self.session = aioboto3.Session()
        self._dynamodb = None

    async def _get_dynamodb(self):
        """Get DynamoDB resource (lazy initialization)."""
        if self._dynamodb is None:
            kwargs = {
                'region_name': settings.aws_region,
                'aws_access_key_id': settings.aws_access_key_id,
                'aws_secret_access_key': settings.aws_secret_access_key
            }
            if settings.dynamodb_endpoint_url:
                kwargs['endpoint_url'] = settings.dynamodb_endpoint_url

            self._dynamodb = await self.session.resource('dynamodb', **kwargs).__aenter__()
        return self._dynamodb

    # ==================== Config Operations ====================

    async def get_org_config(self, org_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve organization configuration."""
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_config_table)

        try:
            response = await table.get_item(
                Key={'org_key': f'ORG#{org_id}', 'resource_key': '#'}
            )
            return response.get('Item')
        except ClientError:
            return None

    async def get_app_config(self, org_id: str, app_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve application configuration."""
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_config_table)

        try:
            response = await table.get_item(
                Key={'org_key': f'ORG#{org_id}', 'resource_key': f'APP#{app_id}'}
            )
            return response.get('Item')
        except ClientError:
            return None

    async def put_org_config(self, org_id: str, config: Dict[str, Any]) -> None:
        """Create or update organization configuration."""
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_config_table)

        item = {
            'org_key': f'ORG#{org_id}',
            'resource_key': '#',  # Root config marker
            **config,
            'updated_at_epoch': int(time.time())
        }

        await table.put_item(Item=item)

    async def put_app_config(self, org_id: str, app_id: str, config: Dict[str, Any]) -> None:
        """Create or update application configuration."""
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_config_table)

        item = {
            'org_key': f'ORG#{org_id}',
            'resource_key': f'APP#{app_id}',
            **config,
            'updated_at_epoch': int(time.time())
        }

        await table.put_item(Item=item)

    # ==================== Sticky State Operations ====================

    async def get_sticky_state(self, scope: str, day: str) -> Optional[Dict[str, Any]]:
        """Get sticky fallback state for a scope and day."""
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_sticky_state_table)

        try:
            response = await table.get_item(
                Key={'scope_key': scope, 'date_key': day}
            )
            return response.get('Item')
        except ClientError:
            return None

    async def put_sticky_state(
        self,
        scope: str,
        day: str,
        active_model_label: str,
        active_model_index: int,
        reason: str,
        previous_model_label: Optional[str] = None
    ) -> bool:
        """Set sticky fallback state with conditional write."""
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_sticky_state_table)

        now = int(time.time())
        item = {
            'scope_key': scope,
            'date_key': day,
            'active_model_label': active_model_label,
            'active_model_index': active_model_index,
            'reason': reason,
            'activated_at_epoch': now
        }

        if previous_model_label:
            item['previous_model_label'] = previous_model_label

        try:
            # Conditional write: only advance to higher index
            await table.put_item(
                Item=item,
                ConditionExpression='attribute_not_exists(active_model_label) OR active_model_index < :new_index',
                ExpressionAttributeValues={':new_index': active_model_index}
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                return False
            raise

    # ==================== Usage Aggregation Operations ====================

    async def update_usage_shard(
        self,
        scope: str,
        day: str,
        model_label: str,
        shard_id: int,
        cost_usd_micros: int,
        input_tokens: int,
        output_tokens: int,
        requests: int,
        request_id: str
    ) -> None:
        """Atomically update usage counters for a shard."""
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_usage_agg_sharded_table)

        pk = f'{scope}#LABEL#{model_label}#SH#{shard_id}'

        # Use conditional expression for idempotency - only update if request_id not in set
        try:
            await table.update_item(
                Key={'shard_key': pk, 'date_key': day},
                UpdateExpression='ADD cost_usd_micros :c, input_tokens :i, output_tokens :o, requests :r, request_ids :rid SET updated_at_epoch = :t',
                ConditionExpression='NOT contains(request_ids, :req_id) OR attribute_not_exists(request_ids)',
                ExpressionAttributeValues={
                    ':c': cost_usd_micros,
                    ':i': input_tokens,
                    ':o': output_tokens,
                    ':r': requests,
                    ':rid': {request_id},
                    ':req_id': request_id,
                    ':t': int(time.time())
                }
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                # Request already processed - this is idempotent behavior
                pass
            else:
                raise

    async def get_usage_shards(
        self,
        scope: str,
        day: str,
        model_label: str,
        shard_count: int
    ) -> List[Dict[str, Any]]:
        """Get all usage shards for a scope/day/model."""
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_usage_agg_sharded_table)

        # Build keys for batch get
        keys = [
            {'shard_key': f'{scope}#LABEL#{model_label}#SH#{i}', 'date_key': day}
            for i in range(shard_count)
        ]

        response = await dynamodb.batch_get_item(
            RequestItems={
                settings.dynamodb_usage_agg_sharded_table: {'Keys': keys}
            }
        )

        return response.get('Responses', {}).get(settings.dynamodb_usage_agg_sharded_table, [])

    # ==================== Daily Total Operations ====================

    async def get_daily_total(
        self,
        scope: str,
        day: str,
        model_label: str
    ) -> Optional[Dict[str, Any]]:
        """Get aggregated daily total for a scope/day/model."""
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_daily_total_table)

        try:
            response = await table.get_item(
                Key={'usage_key': f'{scope}#LABEL#{model_label}', 'date_key': day}
            )
            return response.get('Item')
        except ClientError:
            return None

    async def get_daily_totals_batch(
        self,
        scope: str,
        day: str,
        model_labels: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Get daily totals for multiple models in one batch."""
        dynamodb = await self._get_dynamodb()

        # Build keys for batch get
        keys = [
            {'usage_key': f'{scope}#LABEL#{label}', 'date_key': day}
            for label in model_labels
        ]

        response = await dynamodb.batch_get_item(
            RequestItems={
                settings.dynamodb_daily_total_table: {'Keys': keys}
            }
        )

        items = response.get('Responses', {}).get(settings.dynamodb_daily_total_table, [])

        # Map items by model label
        result = {}
        for item in items:
            # Extract label from usage_key
            pk_parts = item['usage_key'].split('#LABEL#')
            if len(pk_parts) == 2:
                label = pk_parts[1]
                result[label] = item

        return result

    async def put_daily_total(
        self,
        scope: str,
        day: str,
        model_label: str,
        cost_usd_micros: int,
        input_tokens: int,
        output_tokens: int,
        requests: int
    ) -> None:
        """Write aggregated daily total (overwrite)."""
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_daily_total_table)

        item = {
            'usage_key': f'{scope}#LABEL#{model_label}',
            'date_key': day,
            'cost_usd_micros': cost_usd_micros,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'requests': requests,
            'updated_at_epoch': int(time.time())
        }

        await table.put_item(Item=item)

    # ==================== Pricing Cache Operations ====================

    async def get_pricing(
        self,
        bedrock_model_id: str,
        date: str,
        region: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get pricing for a model on a specific date, optionally region-specific.

        Args:
            bedrock_model_id: The AWS Bedrock model ID
            date: Date string (YYYY-MM-DD)
            region: Optional AWS region for region-specific pricing

        Returns:
            Pricing data or None if not found
        """
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_pricing_cache_table)

        # Build key - include region in price_key if provided
        model_id_val = bedrock_model_id
        price_key_val = f"{date}#{region}" if region else date

        try:
            response = await table.get_item(
                Key={'model_id': model_id_val, 'price_key': price_key_val}
            )
            return response.get('Item')
        except ClientError:
            return None

    async def put_pricing(
        self,
        bedrock_model_id: str,
        date: str,
        pricing_data: Dict[str, Any]
    ) -> None:
        """Store pricing data for a model."""
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_pricing_cache_table)

        item = {
            'model_id': bedrock_model_id,
            'price_key': date,
            **pricing_data,
            'fetched_at_epoch': int(time.time())
        }

        await table.put_item(Item=item)

    # ==================== Token Revocation Operations ====================

    async def is_token_revoked(self, token_jti: str) -> bool:
        """Check if a token has been revoked."""
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_revoked_tokens_table)

        try:
            response = await table.get_item(
                Key={'token_jti': token_jti}
            )
            return 'Item' in response
        except ClientError:
            return False

    async def revoke_token(
        self,
        token_jti: str,
        token_type: str,
        client_id: str,
        original_expiry_epoch: int
    ) -> None:
        """Revoke a token."""
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_revoked_tokens_table)

        item = {
            'token_jti': token_jti,
            'token_type': token_type,
            'client_id': client_id,
            'revoked_at_epoch': int(time.time()),
            'original_expiry_epoch': original_expiry_epoch,
            'expires_at_epoch': original_expiry_epoch  # TTL attribute
        }

        await table.put_item(Item=item)

    # ==================== Secret Retrieval Token Operations (DEPRECATED) ====================
    # NOTE: SecretRetrievalTokens table is deprecated. Secrets are now returned directly
    # in registration/rotation responses instead of requiring a separate retrieval step.
    # The table can be removed in a future migration.

    # ==================== Inference Profile Operations ====================

    async def register_inference_profile(
        self,
        org_id: str,
        app_id: str,
        profile_label: str,
        inference_profile_arn: str,
        model_arns: Dict[str, str],
        description: Optional[str] = None,
        created_at: Optional[Any] = None
    ) -> None:
        """Register an inference profile for an app.

        Args:
            org_id: Organization ID
            app_id: Application ID
            profile_label: Label to use for this profile
            inference_profile_arn: AWS Bedrock inference profile ARN
            model_arns: Dict mapping region -> model_id
            description: Optional description
            created_at: Creation timestamp
        """
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_config_table)

        item = {
            'org_key': f'ORG#{org_id}#APP#{app_id}',
            'resource_key': f'PROFILE#{profile_label}',
            'inference_profile_arn': inference_profile_arn,
            'model_arns': model_arns,
            'description': description,
            'created_at': created_at.isoformat() if created_at else None,
            'updated_at_epoch': int(time.time())
        }

        await table.put_item(Item=item)

    async def get_inference_profile(
        self,
        org_id: str,
        app_id: str,
        profile_label: str
    ) -> Optional[Dict[str, Any]]:
        """Get a registered inference profile.

        Args:
            org_id: Organization ID
            app_id: Application ID
            profile_label: Profile label

        Returns:
            Profile data or None if not found
        """
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_config_table)

        try:
            response = await table.get_item(
                Key={
                    'org_key': f'ORG#{org_id}#APP#{app_id}',
                    'resource_key': f'PROFILE#{profile_label}'
                }
            )
            return response.get('Item')
        except ClientError:
            return None

    async def list_inference_profiles(
        self,
        org_id: str,
        app_id: str
    ) -> List[Dict[str, Any]]:
        """List all registered inference profiles for an app.

        Args:
            org_id: Organization ID
            app_id: Application ID

        Returns:
            List of profile registrations
        """
        dynamodb = await self._get_dynamodb()
        table = await dynamodb.Table(settings.dynamodb_config_table)

        try:
            response = await table.query(
                KeyConditionExpression='org_key = :pk AND begins_with(resource_key, :sk_prefix)',
                ExpressionAttributeValues={
                    ':pk': f'ORG#{org_id}#APP#{app_id}',
                    ':sk_prefix': 'PROFILE#'
                }
            )
            return response.get('Items', [])
        except ClientError:
            return []

    # ==================== Health Check ====================

    async def health_check(self) -> bool:
        """Check if database connection is healthy."""
        try:
            dynamodb = await self._get_dynamodb()
            # Simple list tables call to verify connection
            await dynamodb.tables.all()
            return True
        except Exception:
            return False
