"""Pydantic request models for API endpoints."""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, UUID4, field_validator



class TokenRequest(BaseModel):
    """Request model for token issuance."""
    client_id: str
    client_secret: str
    grant_type: str = Field(..., pattern="^client_credentials$")


class RefreshTokenRequest(BaseModel):
    """Request model for token refresh."""
    refresh_token: str
    grant_type: str = Field(..., pattern="^refresh_token$")


class RevokeTokenRequest(BaseModel):
    """Request model for token revocation."""
    token: str
    token_type_hint: Optional[str] = Field(None, pattern="^(access_token|refresh_token)$")


class OrgRegistrationRequest(BaseModel):
    """Request model for organization registration."""
    org_name: str
    timezone: str
    quota_scope: str = Field(..., pattern="^(ORG|APP)$")
    model_ordering: List[str] = Field(..., min_length=1)
    quotas: Dict[str, int]
    overrides: Optional[Dict[str, Any]] = None

    @field_validator('quotas')
    @classmethod
    def validate_quotas(cls, v, info):
        """Validate that quotas match model_ordering."""
        if 'model_ordering' in info.data:
            for label in info.data['model_ordering']:
                if label not in v:
                    raise ValueError(f"Missing quota for model label: {label}")
        return v


class AppRegistrationRequest(BaseModel):
    """Request model for application registration."""
    app_name: str
    model_ordering: Optional[List[str]] = None
    quotas: Optional[Dict[str, int]] = None
    overrides: Optional[Dict[str, Any]] = None


class CredentialRotationRequest(BaseModel):
    """Request model for credential rotation."""
    grace_period_hours: int = Field(default=24, ge=0, le=168)


class InferenceProfileRegistrationRequest(BaseModel):
    """Request model for registering an AWS Bedrock inference profile.

    Inference profiles enable cost allocation at a granular level by tagging
    requests with custom identifiers. This is useful for multi-tenant scenarios.
    """
    profile_label: str = Field(..., min_length=1, max_length=50)
    inference_profile_arn: str = Field(
        ...,
        pattern=r'^arn:aws:bedrock:[a-z0-9-]+:\d{12}:inference-profile/[\w-]+$'
    )
    description: Optional[str] = None


class UsageSubmissionRequest(BaseModel):
    """Request model for usage submission.

    Note: cost_usd_micros is NOT included - the service calculates cost
    from input_tokens and output_tokens using current pricing data.

    The model_label can point to either:
    1. A traditional bedrock_model_id (from config.yaml)
    2. A registered inference profile (from database)

    If the label points to an inference profile, calling_region is required.
    """
    request_id: UUID4
    model_label: str
    bedrock_model_id: str
    calling_region: Optional[str] = Field(
        None,
        pattern=r'^[a-z]{2}-[a-z]+-\d$'
    )
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    status: str = Field(..., pattern="^(OK|ERROR)$")
    timestamp: datetime

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v):
        """Ensure timestamp is not in the future."""
        if v > datetime.now(timezone.utc):
            raise ValueError("Timestamp cannot be in the future")
        return v


# Legacy alias for backward compatibility during transition
CostSubmissionRequest = UsageSubmissionRequest


class BatchUsageSubmissionRequest(BaseModel):
    """Request model for batch usage submission."""
    requests: List[UsageSubmissionRequest] = Field(..., min_length=1, max_length=100)


# Legacy alias for backward compatibility during transition
BatchCostSubmissionRequest = BatchUsageSubmissionRequest
