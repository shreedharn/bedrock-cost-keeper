"""Pydantic response models for API endpoints."""
from datetime import datetime
from typing import Optional, Dict, List, Any
from pydantic import BaseModel



class TokenResponse(BaseModel):
    """Response model for token issuance."""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_expires_in: int
    scope: str


class RefreshTokenResponse(BaseModel):
    """Response model for token refresh."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class SecretRetrievalInfo(BaseModel):
    """Information about secret retrieval."""
    url: str
    token: str
    expires_at: datetime


class CredentialsInfo(BaseModel):
    """Client credentials information."""
    client_id: str
    secret_retrieval: SecretRetrievalInfo


class ConfigInfo(BaseModel):
    """Configuration information."""
    timezone: Optional[str] = None
    quota_scope: Optional[str] = None
    model_ordering: Optional[List[str]] = None
    agg_shard_count: Optional[int] = None


class OrgRegistrationResponse(BaseModel):
    """Response model for organization registration."""
    org_id: str
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    credentials: Optional[CredentialsInfo] = None
    configuration: ConfigInfo


class AppRegistrationResponse(BaseModel):
    """Response model for application registration."""
    org_id: str
    app_id: str
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    credentials: Optional[CredentialsInfo] = None
    configuration: Dict


class RotationInfo(BaseModel):
    """Credential rotation information."""
    rotated_at: datetime
    old_secret_expires_at: datetime
    grace_period_hours: int


class CredentialRotationResponse(BaseModel):
    """Response model for credential rotation."""
    org_id: str
    app_id: Optional[str] = None
    client_id: str
    secret_retrieval: SecretRetrievalInfo
    rotation: RotationInfo


class InferenceProfileResponse(BaseModel):
    """Response model for inference profile registration."""
    profile_label: str
    inference_profile_arn: str
    supported_regions: List[str]
    status: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None


class SecretRetrievalResponse(BaseModel):
    """Response model for secret retrieval."""
    client_id: str
    client_secret: str
    retrieved_at: datetime
    expires_at: datetime
    note: str = "This secret will not be shown again. Store securely."


class ModelInfo(BaseModel):
    """Model information."""
    label: str
    bedrock_model_id: str
    cost_usd_micros: int
    quota_usd_micros: int
    quota_pct: float
    quota_status: str
    input_tokens: int
    output_tokens: int
    requests: int
    average_cost_per_request: int


class DailyAggregatesResponse(BaseModel):
    """Response model for daily aggregates."""
    org_id: str
    app_id: Optional[str] = None
    app_name: Optional[str] = None
    date: str
    timezone: str
    quota_scope: str
    models: Dict[str, ModelInfo]
    total_cost_usd_micros: int
    total_quota_usd_micros: int
    total_quota_pct: float
    sticky_fallback_active: bool
    current_active_model: Optional[str] = None
    updated_at: datetime


class RecommendedModel(BaseModel):
    """Recommended model information."""
    label: str
    bedrock_model_id: str
    reason: str
    description: str


class ModelStatusInfo(BaseModel):
    """Status of a specific model."""
    spend_usd_micros: int
    quota_usd_micros: int
    quota_pct: float
    status: str


class QuotaStatus(BaseModel):
    """Quota status information."""
    scope: str
    mode: str
    current_model: str
    spend_usd_micros: int
    quota_usd_micros: int
    quota_pct: float
    sticky_fallback_active: bool
    models_status: Dict[str, ModelStatusInfo]


class PricingInfo(BaseModel):
    """Pricing information."""
    input_price_usd_micros_per_1m: int
    output_price_usd_micros_per_1m: int
    version: str
    source: str


class ClientGuidance(BaseModel):
    """Client guidance for caching and checking."""
    check_frequency: str
    cache_duration_secs: int
    explanation: str


class ModelSelectionResponse(BaseModel):
    """Response model for model selection."""
    org_id: str
    app_id: str
    recommended_model: RecommendedModel
    quota_status: QuotaStatus
    pricing: PricingInfo
    client_guidance: ClientGuidance
    checked_at: datetime
    org_day: str
    org_local_time: str


class UsageSubmissionResponse(BaseModel):
    """Response model for usage submission.

    Returns the service-calculated cost along with usage data.
    """
    request_id: str
    status: str
    message: str
    processing: Dict[str, Any]
    timestamp: datetime


# Legacy alias for backward compatibility during transition
CostSubmissionResponse = UsageSubmissionResponse


class BatchUsageResult(BaseModel):
    """Result for a single usage submission in a batch."""
    request_id: str
    status: str
    error: Optional[str] = None


# Legacy alias for backward compatibility during transition
BatchCostResult = BatchUsageResult


class BatchUsageSubmissionResponse(BaseModel):
    """Response model for batch usage submission."""
    accepted: int
    failed: int
    results: List[BatchUsageResult]
    timestamp: datetime


# Legacy alias for backward compatibility during transition
BatchCostSubmissionResponse = BatchUsageSubmissionResponse


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    message: str
    details: Optional[Dict] = None
    timestamp: datetime
    request_id: Optional[str] = None
