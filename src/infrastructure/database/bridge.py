"""Database bridge interface - Abstraction layer for database operations.

This interface decouples the application from specific database implementations.
Uses the Bridge pattern to allow switching between different database backends
(DynamoDB, in-memory for testing, etc.) without changing business logic.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List



class DatabaseBridge(ABC):
    """Abstract base class for database operations."""

    # ==================== Config Operations ====================

    @abstractmethod
    async def get_org_config(self, org_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve organization configuration.

        Args:
            org_id: Organization UUID

        Returns:
            Organization config dict or None if not found
        """
        pass

    @abstractmethod
    async def get_app_config(self, org_id: str, app_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve application configuration.

        Args:
            org_id: Organization UUID
            app_id: Application identifier

        Returns:
            Application config dict or None if not found
        """
        pass

    @abstractmethod
    async def put_org_config(self, org_id: str, config: Dict[str, Any]) -> None:
        """
        Create or update organization configuration.

        Args:
            org_id: Organization UUID
            config: Configuration data
        """
        pass

    @abstractmethod
    async def put_app_config(self, org_id: str, app_id: str, config: Dict[str, Any]) -> None:
        """
        Create or update application configuration.

        Args:
            org_id: Organization UUID
            app_id: Application identifier
            config: Configuration data
        """
        pass

    # ==================== Sticky State Operations ====================

    @abstractmethod
    async def get_sticky_state(self, scope: str, day: str) -> Optional[Dict[str, Any]]:
        """
        Get sticky fallback state for a scope and day.

        Args:
            scope: Scope identifier (e.g., "ORG#uuid" or "ORG#uuid#APP#app-id")
            day: Day in format "DAY#YYYYMMDD"

        Returns:
            Sticky state dict or None if not found
        """
        pass

    @abstractmethod
    async def put_sticky_state(
        self,
        scope: str,
        day: str,
        active_model_label: str,
        active_model_index: int,
        reason: str,
        previous_model_label: Optional[str] = None
    ) -> bool:
        """
        Set sticky fallback state with conditional write.

        Args:
            scope: Scope identifier
            day: Day in format "DAY#YYYYMMDD"
            active_model_label: Model label to activate
            active_model_index: Index in model_ordering
            reason: Reason for activation (e.g., "QUOTA_EXCEEDED")
            previous_model_label: Previously active model

        Returns:
            True if write succeeded, False if condition failed
        """
        pass

    # ==================== Usage Aggregation Operations ====================

    @abstractmethod
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
        """
        Atomically update usage counters for a shard.

        Args:
            scope: Scope identifier
            day: Day in format "DAY#YYYYMMDD"
            model_label: Model label
            shard_id: Shard number
            cost_usd_micros: Cost to add
            input_tokens: Input tokens to add
            output_tokens: Output tokens to add
            requests: Request count to add (typically 1)
            request_id: Request UUID for idempotency
        """
        pass

    @abstractmethod
    async def get_usage_shards(
        self,
        scope: str,
        day: str,
        model_label: str,
        shard_count: int
    ) -> List[Dict[str, Any]]:
        """
        Get all usage shards for a scope/day/model.

        Args:
            scope: Scope identifier
            day: Day in format "DAY#YYYYMMDD"
            model_label: Model label
            shard_count: Number of shards to read

        Returns:
            List of shard data dicts
        """
        pass

    # ==================== Daily Total Operations ====================

    @abstractmethod
    async def get_daily_total(
        self,
        scope: str,
        day: str,
        model_label: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get aggregated daily total for a scope/day/model.

        Args:
            scope: Scope identifier
            day: Day in format "DAY#YYYYMMDD"
            model_label: Model label

        Returns:
            Daily total dict or None if not found
        """
        pass

    @abstractmethod
    async def get_daily_totals_batch(
        self,
        scope: str,
        day: str,
        model_labels: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get daily totals for multiple models in one batch.

        Args:
            scope: Scope identifier
            day: Day in format "DAY#YYYYMMDD"
            model_labels: List of model labels

        Returns:
            Dict mapping model_label to daily total data
        """
        pass

    @abstractmethod
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
        """
        Write aggregated daily total (overwrite).

        Args:
            scope: Scope identifier
            day: Day in format "DAY#YYYYMMDD"
            model_label: Model label
            cost_usd_micros: Total cost
            input_tokens: Total input tokens
            output_tokens: Total output tokens
            requests: Total request count
        """
        pass

    # ==================== Pricing Cache Operations ====================

    @abstractmethod
    async def get_pricing(self, bedrock_model_id: str, date: str) -> Optional[Dict[str, Any]]:
        """
        Get pricing for a model on a specific date.

        Args:
            bedrock_model_id: Bedrock model identifier
            date: Date in YYYY-MM-DD format

        Returns:
            Pricing data dict or None if not found
        """
        pass

    @abstractmethod
    async def put_pricing(
        self,
        bedrock_model_id: str,
        date: str,
        pricing_data: Dict[str, Any]
    ) -> None:
        """
        Store pricing data for a model.

        Args:
            bedrock_model_id: Bedrock model identifier
            date: Date in YYYY-MM-DD format
            pricing_data: Pricing information
        """
        pass

    # ==================== Token Revocation Operations ====================

    @abstractmethod
    async def is_token_revoked(self, token_jti: str) -> bool:
        """
        Check if a token has been revoked.

        Args:
            token_jti: JWT ID claim

        Returns:
            True if token is revoked, False otherwise
        """
        pass

    @abstractmethod
    async def revoke_token(
        self,
        token_jti: str,
        token_type: str,
        client_id: str,
        original_expiry_epoch: int
    ) -> None:
        """
        Revoke a token.

        Args:
            token_jti: JWT ID claim
            token_type: "access" or "refresh"
            client_id: Client identifier
            original_expiry_epoch: Original token expiration timestamp
        """
        pass

    # ==================== Secret Retrieval Token Operations ====================

    @abstractmethod
    async def create_secret_retrieval_token(
        self,
        token_uuid: str,
        org_id: str,
        app_id: Optional[str],
        secret_type: str,
        client_id: str,
        expires_at_epoch: int
    ) -> None:
        """
        Create a one-time secret retrieval token.

        Args:
            token_uuid: Token UUID
            org_id: Organization UUID
            app_id: Application identifier (optional)
            secret_type: "org" or "app"
            client_id: Client identifier
            expires_at_epoch: Expiration timestamp
        """
        pass

    @abstractmethod
    async def use_secret_retrieval_token(self, token_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Mark a secret retrieval token as used (first-use-wins).

        Args:
            token_uuid: Token UUID

        Returns:
            Token data if successful, None if already used or expired
        """
        pass

    # ==================== Health Check ====================

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if database connection is healthy.

        Returns:
            True if healthy, False otherwise
        """
        pass
