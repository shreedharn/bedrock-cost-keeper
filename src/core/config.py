"""Application configuration."""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import yaml
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings."""

    # API Settings
    app_name: str = "Bedrock Cost Keeper"
    version: str = "1.0.0"
    api_prefix: str = "/api/v1"

    # Server Settings
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False

    # AWS Settings
    aws_region: str = Field(default="us-east-1", validation_alias="AWS_REGION")
    aws_account_id: Optional[str] = Field(default=None, validation_alias="AWS_ACCOUNT_ID")
    aws_access_key_id: Optional[str] = Field(default=None, validation_alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, validation_alias="AWS_SECRET_ACCESS_KEY")

    # DynamoDB endpoint (for DynamoDB Local in development)
    dynamodb_endpoint_url: Optional[str] = Field(default=None, validation_alias="DYNAMODB_ENDPOINT_URL")

    # DynamoDB Table Names
    dynamodb_config_table: str = Field(default="bedrock-cost-keeper-config")
    dynamodb_sticky_state_table: str = Field(default="bedrock-cost-keeper-usage")
    dynamodb_usage_agg_sharded_table: str = Field(default="bedrock-cost-keeper-aggregates")
    dynamodb_daily_total_table: str = Field(default="bedrock-cost-keeper-aggregates")
    dynamodb_pricing_cache_table: str = Field(default="bedrock-cost-keeper-config")
    dynamodb_revoked_tokens_table: str = Field(default="bedrock-cost-keeper-tokens", validation_alias="DYNAMODB_TOKENS_TABLE")
    dynamodb_secret_retrieval_tokens_table: str = Field(default="bedrock-cost-keeper-secrets", validation_alias="DYNAMODB_SECRETS_TABLE")

    # AWS Secrets Manager
    jwt_secret_name: Optional[str] = Field(default=None, validation_alias="JWT_SECRET_NAME")
    provisioning_api_key_name: Optional[str] = Field(default=None, validation_alias="PROVISIONING_API_KEY_NAME")

    # JWT Settings
    jwt_secret_key: Optional[str] = Field(default=None, validation_alias="JWT_SECRET_KEY")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_seconds: int = 3600  # 1 hour
    jwt_refresh_token_expire_seconds: int = 2592000  # 30 days

    # Provisioning API Key
    provisioning_api_key: Optional[str] = Field(default=None, validation_alias="PROVISIONING_API_KEY")

    # Environment
    environment: str = Field(default="dev", validation_alias="ENVIRONMENT")

    # Config File Path
    main_config_path: str = "config.yaml"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


# Global settings instance
settings = Settings()


def _load_secrets_from_manager():
    """Load secrets from AWS Secrets Manager if secret names are configured."""
    from .secrets import get_secret

    # Load JWT secret from Secrets Manager if configured
    if settings.jwt_secret_name:
        logger.info(f"Loading JWT secret from Secrets Manager: {settings.jwt_secret_name}")
        secret_value = get_secret(settings.jwt_secret_name, settings.aws_region)
        if secret_value:
            settings.jwt_secret_key = secret_value
            logger.info("JWT secret loaded successfully from Secrets Manager")
        else:
            raise RuntimeError(f"Failed to load JWT secret from Secrets Manager: {settings.jwt_secret_name}")

    # Load provisioning API key from Secrets Manager if configured
    if settings.provisioning_api_key_name:
        logger.info(f"Loading provisioning API key from Secrets Manager: {settings.provisioning_api_key_name}")
        secret_value = get_secret(settings.provisioning_api_key_name, settings.aws_region)
        if secret_value:
            settings.provisioning_api_key = secret_value
            logger.info("Provisioning API key loaded successfully from Secrets Manager")
        else:
            raise RuntimeError(f"Failed to load provisioning API key from Secrets Manager: {settings.provisioning_api_key_name}")


def _validate_secrets():
    """Validate that required secrets are configured."""
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT secret key is not configured. Set JWT_SECRET_KEY env var or JWT_SECRET_NAME for Secrets Manager")

    if not settings.provisioning_api_key:
        raise RuntimeError("Provisioning API key is not configured. Set PROVISIONING_API_KEY env var or PROVISIONING_API_KEY_NAME for Secrets Manager")


# Load secrets from Secrets Manager if configured
_load_secrets_from_manager()

# Validate that all required secrets are set
_validate_secrets()


def load_main_config() -> dict:
    """Load the main configuration from config.yaml."""
    config_path = Path(settings.main_config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Main config file not found: {settings.main_config_path}")

    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


# Load main config at startup
main_config = load_main_config()
