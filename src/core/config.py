"""Application configuration."""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field
import yaml
from pathlib import Path


class Settings(BaseSettings):
    """Application settings."""

    # API Settings
    app_name: str = "Bedrock Cost Keeper"
    version: str = "1.0.0"
    api_prefix: str = "/api/v1"

    # Server Settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # AWS Settings
    aws_region: str = Field(default="us-east-1", env="AWS_REGION")
    aws_access_key_id: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    aws_endpoint_url: Optional[str] = Field(default=None, env="AWS_ENDPOINT_URL")

    # DynamoDB Table Names
    dynamodb_config_table: str = Field(default="bedrock-cost-keeper-config")
    dynamodb_sticky_state_table: str = Field(default="bedrock-cost-keeper-usage")
    dynamodb_usage_agg_sharded_table: str = Field(default="bedrock-cost-keeper-aggregates")
    dynamodb_daily_total_table: str = Field(default="bedrock-cost-keeper-aggregates")
    dynamodb_pricing_cache_table: str = Field(default="bedrock-cost-keeper-config")
    dynamodb_revoked_tokens_table: str = Field(default="bedrock-cost-keeper-tokens")
    dynamodb_secret_retrieval_tokens_table: str = Field(default="bedrock-cost-keeper-secrets")

    # JWT Settings
    jwt_secret_key: str = Field(default="your-secret-key-change-in-production", env="JWT_SECRET_KEY")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_seconds: int = 3600  # 1 hour
    jwt_refresh_token_expire_seconds: int = 2592000  # 30 days

    # Provisioning API Key
    provisioning_api_key: str = Field(default="change-me-in-production", env="PROVISIONING_API_KEY")

    # Rate Limiting
    rate_limit_enabled: bool = True

    # Config File Path
    main_config_path: str = "config.yaml"

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()


def load_main_config() -> dict:
    """Load the main configuration from config.yaml."""
    config_path = Path(settings.main_config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Main config file not found: {settings.main_config_path}")

    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


# Load main config at startup
main_config = load_main_config()
