"""Cost submission endpoints."""

from typing import Annotated
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path
from ..models.requests import CostSubmissionRequest, BatchCostSubmissionRequest
from ..models.responses import CostSubmissionResponse, BatchCostSubmissionResponse, BatchCostResult
from ...infrastructure.database.dynamodb_bridge import DynamoDBBridge
from ...domain.services.metering_service import MeteringService
from ...core.exceptions import InvalidConfigException
from ..dependencies import get_db_bridge, get_current_user



router = APIRouter()


@router.post("/orgs/{org_id}/apps/{app_id}/costs", response_model=CostSubmissionResponse, status_code=202)
async def submit_cost(
    org_id: Annotated[str, Path(description="Organization UUID")],
    app_id: Annotated[str, Path(description="Application identifier")],
    request: CostSubmissionRequest,
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)],
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """
    Submit request cost and usage data for aggregation.

    The cost submission is accepted asynchronously and queued for processing.
    Submitting the same request_id multiple times is idempotent.
    """
    # Verify authorization
    if current_user['org_id'] != org_id:
        raise InvalidConfigException("Org ID mismatch")

    if current_user.get('app_id') and current_user['app_id'] != app_id:
        raise InvalidConfigException("App ID mismatch")

    # Create metering service
    metering_service = MeteringService(db)

    # Submit cost
    result = await metering_service.submit_cost(
        org_id=org_id,
        app_id=app_id,
        request_id=str(request.request_id),
        model_label=request.model_label,
        bedrock_model_id=request.bedrock_model_id,
        input_tokens=request.input_tokens,
        output_tokens=request.output_tokens,
        cost_usd_micros=request.cost_usd_micros,
        status=request.status,
        timestamp=request.timestamp
    )

    return CostSubmissionResponse(**result)


@router.post("/orgs/{org_id}/apps/{app_id}/costs/batch", response_model=BatchCostSubmissionResponse, status_code=207)
async def submit_costs_batch(
    org_id: Annotated[str, Path(description="Organization UUID")],
    app_id: Annotated[str, Path(description="Application identifier")],
    request: BatchCostSubmissionRequest,
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)],
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """
    Submit multiple cost records in a batch.

    Returns 207 Multi-Status with individual results for each submission.
    """
    # Verify authorization
    if current_user['org_id'] != org_id:
        raise InvalidConfigException("Org ID mismatch")

    if current_user.get('app_id') and current_user['app_id'] != app_id:
        raise InvalidConfigException("App ID mismatch")

    metering_service = MeteringService(db)

    results = []
    accepted = 0
    failed = 0

    for cost_request in request.requests:
        try:
            await metering_service.submit_cost(
                org_id=org_id,
                app_id=app_id,
                request_id=str(cost_request.request_id),
                model_label=cost_request.model_label,
                bedrock_model_id=cost_request.bedrock_model_id,
                input_tokens=cost_request.input_tokens,
                output_tokens=cost_request.output_tokens,
                cost_usd_micros=cost_request.cost_usd_micros,
                status=cost_request.status,
                timestamp=cost_request.timestamp
            )

            results.append(BatchCostResult(
                request_id=str(cost_request.request_id),
                status="accepted"
            ))
            accepted += 1

        except Exception as e:
            results.append(BatchCostResult(
                request_id=str(cost_request.request_id),
                status="failed",
                error=str(e)
            ))
            failed += 1

    return BatchCostSubmissionResponse(
        accepted=accepted,
        failed=failed,
        results=results,
        timestamp=datetime.now(timezone.utc)
    )
