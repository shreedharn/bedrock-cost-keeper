"""Daily aggregates endpoints."""

from typing import Annotated
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Path

from ..models.responses import DailyAggregatesResponse
from ...infrastructure.database.dynamodb_bridge import DynamoDBBridge
from ...domain.services.metering_service import MeteringService
from ...core.exceptions import InvalidConfigException, NotFoundException
from ..dependencies import get_db_bridge, get_current_user



router = APIRouter()


@router.get("/orgs/{org_id}/aggregates/today", response_model=DailyAggregatesResponse)
async def get_org_aggregates_today(
    org_id: Annotated[str, Path(description="Organization UUID")],
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)],
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """
    Retrieve today's usage summary for an organization across all models.
    """
    # Verify authorization
    if current_user['org_id'] != org_id:
        raise InvalidConfigException("Org ID mismatch")

    # Get org config
    org_config = await db.get_org_config(org_id)
    if not org_config:
        raise NotFoundException(f"Organization {org_id} not found")

    metering_service = MeteringService(db)

    # Get model ordering
    model_ordering = org_config.get('model_ordering', [])

    # Get current usage
    usage = await metering_service.get_current_usage(org_id, None, model_ordering)

    # Build response (simplified)
    # TODO: Implement full aggregate calculation with quota status
    return DailyAggregatesResponse(
        org_id=org_id,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        timezone=org_config.get('timezone', 'UTC'),
        quota_scope=org_config.get('quota_scope', 'ORG'),
        models={},
        total_cost_usd_micros=0,
        total_quota_usd_micros=0,
        total_quota_pct=0.0,
        sticky_fallback_active=False,
        updated_at=datetime.now(timezone.utc)
    )


@router.get("/orgs/{org_id}/apps/{app_id}/aggregates/today", response_model=DailyAggregatesResponse)
async def get_app_aggregates_today(
    org_id: Annotated[str, Path(description="Organization UUID")],
    app_id: Annotated[str, Path(description="Application identifier")],
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)],
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """
    Retrieve today's usage for a specific application.
    """
    # Verify authorization
    if current_user['org_id'] != org_id:
        raise InvalidConfigException("Org ID mismatch")

    if current_user.get('app_id') and current_user['app_id'] != app_id:
        raise InvalidConfigException("App ID mismatch")

    # Get configs
    org_config = await db.get_org_config(org_id)
    if not org_config:
        raise NotFoundException(f"Organization {org_id} not found")

    app_config = await db.get_app_config(org_id, app_id)

    metering_service = MeteringService(db)

    # Get effective config
    effective_config = {**org_config}
    if app_config:
        effective_config.update(app_config)

    model_ordering = effective_config.get('model_ordering', [])

    # Get current usage
    usage = await metering_service.get_current_usage(org_id, app_id, model_ordering)

    # Build response (simplified)
    return DailyAggregatesResponse(
        org_id=org_id,
        app_id=app_id,
        app_name=app_config.get('app_name') if app_config else None,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        timezone=org_config.get('timezone', 'UTC'),
        quota_scope=org_config.get('quota_scope', 'ORG'),
        models={},
        total_cost_usd_micros=0,
        total_quota_usd_micros=0,
        total_quota_pct=0.0,
        sticky_fallback_active=False,
        updated_at=datetime.now(timezone.utc)
    )
