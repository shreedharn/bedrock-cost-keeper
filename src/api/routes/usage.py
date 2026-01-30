"""Usage submission endpoints."""

from typing import Annotated
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path
from ..models.requests import UsageSubmissionRequest, BatchUsageSubmissionRequest
from ..models.responses import UsageSubmissionResponse, BatchUsageSubmissionResponse, BatchUsageResult
from ...infrastructure.database.dynamodb_bridge import DynamoDBBridge
from ...domain.services.metering_service import MeteringService
from ...domain.services.pricing_service import PricingService
from ...domain.services.inference_profile_service import InferenceProfileService
from ...core.exceptions import InvalidConfigException
from ...core.config import main_config
from ..dependencies import get_db_bridge, get_current_user



router = APIRouter()


@router.post("/orgs/{org_id}/apps/{app_id}/usage", response_model=UsageSubmissionResponse, status_code=202)
async def submit_usage(
    org_id: Annotated[str, Path(description="Organization UUID")],
    app_id: Annotated[str, Path(description="Application identifier")],
    request: UsageSubmissionRequest,
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)],
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """
    Submit request usage data for aggregation.

    The service calculates cost from input_tokens and output_tokens using current pricing.
    Usage submission is accepted asynchronously and queued for processing.
    Submitting the same request_id multiple times is idempotent.
    """
    # Verify authorization
    if current_user['org_id'] != org_id:
        raise InvalidConfigException("Org ID mismatch")

    if current_user.get('app_id') and current_user['app_id'] != app_id:
        raise InvalidConfigException("App ID mismatch")

    # Create pricing service
    pricing_service = PricingService(db, main_config)

    # Create inference profile service (imported at function level to avoid circular import)
    from ...domain.services.inference_profile_service import InferenceProfileService
    profile_service = InferenceProfileService(db)

    # Create metering service with pricing and profile services
    metering_service = MeteringService(
        db_bridge=db,
        pricing_service=pricing_service,
        profile_service=profile_service,
        config=main_config
    )

    # Submit usage (cost calculated server-side)
    result = await metering_service.submit_usage(
        org_id=org_id,
        app_id=app_id,
        request_id=str(request.request_id),
        model_label=request.model_label,
        bedrock_model_id=request.bedrock_model_id,
        input_tokens=request.input_tokens,
        output_tokens=request.output_tokens,
        status=request.status,
        timestamp=request.timestamp,
        calling_region=request.calling_region
    )

    return UsageSubmissionResponse(**result)


@router.post("/orgs/{org_id}/apps/{app_id}/usage/batch", response_model=BatchUsageSubmissionResponse, status_code=207)
async def submit_usage_batch(
    org_id: Annotated[str, Path(description="Organization UUID")],
    app_id: Annotated[str, Path(description="Application identifier")],
    request: BatchUsageSubmissionRequest,
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)],
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """
    Submit multiple usage records in a batch.

    Returns 207 Multi-Status with individual results for each submission.
    """
    # Verify authorization
    if current_user['org_id'] != org_id:
        raise InvalidConfigException("Org ID mismatch")

    if current_user.get('app_id') and current_user['app_id'] != app_id:
        raise InvalidConfigException("App ID mismatch")

    # Create pricing service
    pricing_service = PricingService(db, main_config)

    # Create inference profile service
    profile_service = InferenceProfileService(db)

    # Create metering service with pricing and profile services
    metering_service = MeteringService(
        db_bridge=db,
        pricing_service=pricing_service,
        profile_service=profile_service,
        config=main_config
    )

    results = []
    accepted = 0
    failed = 0

    for usage_request in request.requests:
        try:
            await metering_service.submit_usage(
                org_id=org_id,
                app_id=app_id,
                request_id=str(usage_request.request_id),
                model_label=usage_request.model_label,
                bedrock_model_id=usage_request.bedrock_model_id,
                input_tokens=usage_request.input_tokens,
                output_tokens=usage_request.output_tokens,
                status=usage_request.status,
                timestamp=usage_request.timestamp,
                calling_region=usage_request.calling_region
            )

            results.append(BatchUsageResult(
                request_id=str(usage_request.request_id),
                status="accepted"
            ))
            accepted += 1

        except Exception as e:
            results.append(BatchUsageResult(
                request_id=str(usage_request.request_id),
                status="failed",
                error=str(e)
            ))
            failed += 1

    return BatchUsageSubmissionResponse(
        accepted=accepted,
        failed=failed,
        results=results,
        timestamp=datetime.now(timezone.utc)
    )
