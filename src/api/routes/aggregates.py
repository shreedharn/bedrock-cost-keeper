"""Daily aggregates endpoints."""

from typing import Annotated
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Path

from ..models.responses import DailyAggregatesResponse, ModelInfo
from ...infrastructure.database.dynamodb_bridge import DynamoDBBridge
from ...domain.services.metering_service import MeteringService
from ...core.exceptions import InvalidConfigException, NotFoundException, InvalidRequestException
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

    # Compute scope and day
    scope = metering_service._compute_scope(org_config, org_id, None)
    day = metering_service._compute_org_day(org_config.get('timezone', 'UTC'))

    # Get actual usage data
    daily_totals = await db.get_daily_totals_batch(scope, day, model_ordering)

    # Get sticky state
    sticky_state = await db.get_sticky_state(scope, day)
    sticky_fallback_active = bool(sticky_state)
    current_active_model = sticky_state.get('fallback_model_label') if sticky_state else None

    # Build models dict
    models = {}
    total_cost = 0
    total_quota = 0
    model_quotas = org_config.get('model_quotas', {})

    for label in model_ordering:
        total_data = daily_totals.get(label, {})
        cost = total_data.get('cost_usd_micros', 0)
        quota = model_quotas.get(label, 0)
        input_tokens = total_data.get('input_tokens', 0)
        output_tokens = total_data.get('output_tokens', 0)
        requests = total_data.get('requests', 0)

        quota_pct = (cost / quota * 100) if quota > 0 else 0
        quota_status = "EXCEEDED" if cost >= quota else "NORMAL"

        models[label] = ModelInfo(
            label=label,
            bedrock_model_id=org_config.get('model_ids', {}).get(label, ''),
            cost_usd_micros=cost,
            quota_usd_micros=quota,
            quota_pct=quota_pct,
            quota_status=quota_status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            requests=requests,
            average_cost_per_request=int(cost / requests) if requests > 0 else 0
        )

        total_cost += cost
        total_quota += quota

    # Return actual data
    return DailyAggregatesResponse(
        org_id=org_id,
        app_id=None,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        timezone=org_config.get('timezone', 'UTC'),
        quota_scope=org_config.get('quota_scope', 'ORG'),
        models=models,
        total_cost_usd_micros=total_cost,
        total_quota_usd_micros=total_quota,
        total_quota_pct=(total_cost / total_quota * 100) if total_quota > 0 else 0,
        sticky_fallback_active=sticky_fallback_active,
        current_active_model=current_active_model,
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

    # Compute scope and day
    scope = metering_service._compute_scope(effective_config, org_id, app_id)
    day = metering_service._compute_org_day(org_config.get('timezone', 'UTC'))

    # Get actual usage data
    daily_totals = await db.get_daily_totals_batch(scope, day, model_ordering)

    # Get sticky state
    sticky_state = await db.get_sticky_state(scope, day)
    sticky_fallback_active = bool(sticky_state)
    current_active_model = sticky_state.get('fallback_model_label') if sticky_state else None

    # Build models dict
    models = {}
    total_cost = 0
    total_quota = 0
    model_quotas = effective_config.get('model_quotas', {})

    for label in model_ordering:
        total_data = daily_totals.get(label, {})
        cost = total_data.get('cost_usd_micros', 0)
        quota = model_quotas.get(label, 0)
        input_tokens = total_data.get('input_tokens', 0)
        output_tokens = total_data.get('output_tokens', 0)
        requests = total_data.get('requests', 0)

        quota_pct = (cost / quota * 100) if quota > 0 else 0
        quota_status = "EXCEEDED" if cost >= quota else "NORMAL"

        models[label] = ModelInfo(
            label=label,
            bedrock_model_id=effective_config.get('model_ids', {}).get(label, ''),
            cost_usd_micros=cost,
            quota_usd_micros=quota,
            quota_pct=quota_pct,
            quota_status=quota_status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            requests=requests,
            average_cost_per_request=int(cost / requests) if requests > 0 else 0
        )

        total_cost += cost
        total_quota += quota

    # Return actual data
    return DailyAggregatesResponse(
        org_id=org_id,
        app_id=app_id,
        app_name=app_config.get('app_name') if app_config else None,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        timezone=org_config.get('timezone', 'UTC'),
        quota_scope=effective_config.get('quota_scope', 'ORG'),
        models=models,
        total_cost_usd_micros=total_cost,
        total_quota_usd_micros=total_quota,
        total_quota_pct=(total_cost / total_quota * 100) if total_quota > 0 else 0,
        sticky_fallback_active=sticky_fallback_active,
        current_active_model=current_active_model,
        updated_at=datetime.now(timezone.utc)
    )


@router.get("/orgs/{org_id}/aggregates/{date}", response_model=DailyAggregatesResponse)
async def get_org_aggregates_historical(
    org_id: Annotated[str, Path(description="Organization UUID")],
    date: Annotated[str, Path(description="Date in YYYY-MM-DD format", pattern=r"^\d{4}-\d{2}-\d{2}$")],
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)],
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """Retrieve historical usage for an organization on specific date."""
    # Verify authorization
    if current_user['org_id'] != org_id:
        raise InvalidConfigException("Org ID mismatch")

    # Validate and parse date
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d")
        if parsed_date > datetime.now(timezone.utc):
            raise InvalidRequestException("Date cannot be in the future", {"date": date})
    except ValueError:
        raise InvalidRequestException("Invalid date format", {"expected": "YYYY-MM-DD"})

    day_key = f"DAY#{parsed_date.strftime('%Y%m%d')}"

    # Get org config
    org_config = await db.get_org_config(org_id)
    if not org_config:
        raise NotFoundException(f"Organization {org_id} not found")

    # Compute scope
    metering_service = MeteringService(db)
    scope = metering_service._compute_scope(org_config, org_id, None)
    model_ordering = org_config.get('model_ordering', [])

    # Query DailyTotal for historical date
    daily_totals = await db.get_daily_totals_batch(scope, day_key, model_ordering)

    if not daily_totals:
        raise NotFoundException(f"No usage data found for date {date}")

    # Get sticky state for that date
    sticky_state = await db.get_sticky_state(scope, day_key)
    sticky_fallback_active = bool(sticky_state)
    current_active_model = sticky_state.get('fallback_model_label') if sticky_state else None

    # Build models dict
    models = {}
    total_cost = 0
    total_quota = 0
    model_quotas = org_config.get('model_quotas', {})

    for label in model_ordering:
        total_data = daily_totals.get(label, {})
        cost = total_data.get('cost_usd_micros', 0)
        quota = model_quotas.get(label, 0)
        input_tokens = total_data.get('input_tokens', 0)
        output_tokens = total_data.get('output_tokens', 0)
        requests = total_data.get('requests', 0)

        quota_pct = (cost / quota * 100) if quota > 0 else 0
        quota_status = "EXCEEDED" if cost >= quota else "NORMAL"

        models[label] = ModelInfo(
            label=label,
            bedrock_model_id=org_config.get('model_ids', {}).get(label, ''),
            cost_usd_micros=cost,
            quota_usd_micros=quota,
            quota_pct=quota_pct,
            quota_status=quota_status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            requests=requests,
            average_cost_per_request=int(cost / requests) if requests > 0 else 0
        )

        total_cost += cost
        total_quota += quota

    # Return actual data
    return DailyAggregatesResponse(
        org_id=org_id,
        app_id=None,
        date=date,
        timezone=org_config.get('timezone', 'UTC'),
        quota_scope=org_config.get('quota_scope', 'ORG'),
        models=models,
        total_cost_usd_micros=total_cost,
        total_quota_usd_micros=total_quota,
        total_quota_pct=(total_cost / total_quota * 100) if total_quota > 0 else 0,
        sticky_fallback_active=sticky_fallback_active,
        current_active_model=current_active_model,
        updated_at=datetime.now(timezone.utc)
    )


@router.get("/orgs/{org_id}/apps/{app_id}/aggregates/{date}", response_model=DailyAggregatesResponse)
async def get_app_aggregates_historical(
    org_id: Annotated[str, Path(description="Organization UUID")],
    app_id: Annotated[str, Path(description="Application identifier")],
    date: Annotated[str, Path(description="Date in YYYY-MM-DD format", pattern=r"^\d{4}-\d{2}-\d{2}$")],
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)],
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """Retrieve historical usage for a specific application on specific date."""
    # Verify authorization
    if current_user['org_id'] != org_id:
        raise InvalidConfigException("Org ID mismatch")

    if current_user.get('app_id') and current_user['app_id'] != app_id:
        raise InvalidConfigException("App ID mismatch")

    # Validate and parse date
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d")
        if parsed_date > datetime.now(timezone.utc):
            raise InvalidRequestException("Date cannot be in the future", {"date": date})
    except ValueError:
        raise InvalidRequestException("Invalid date format", {"expected": "YYYY-MM-DD"})

    day_key = f"DAY#{parsed_date.strftime('%Y%m%d')}"

    # Get configs
    org_config = await db.get_org_config(org_id)
    if not org_config:
        raise NotFoundException(f"Organization {org_id} not found")

    app_config = await db.get_app_config(org_id, app_id)

    # Get effective config
    effective_config = {**org_config}
    if app_config:
        effective_config.update(app_config)

    # Compute scope
    metering_service = MeteringService(db)
    scope = metering_service._compute_scope(effective_config, org_id, app_id)
    model_ordering = effective_config.get('model_ordering', [])

    # Query DailyTotal for historical date
    daily_totals = await db.get_daily_totals_batch(scope, day_key, model_ordering)

    if not daily_totals:
        raise NotFoundException(f"No usage data found for app {app_id} on date {date}")

    # Get sticky state for that date
    sticky_state = await db.get_sticky_state(scope, day_key)
    sticky_fallback_active = bool(sticky_state)
    current_active_model = sticky_state.get('fallback_model_label') if sticky_state else None

    # Build models dict
    models = {}
    total_cost = 0
    total_quota = 0
    model_quotas = effective_config.get('model_quotas', {})

    for label in model_ordering:
        total_data = daily_totals.get(label, {})
        cost = total_data.get('cost_usd_micros', 0)
        quota = model_quotas.get(label, 0)
        input_tokens = total_data.get('input_tokens', 0)
        output_tokens = total_data.get('output_tokens', 0)
        requests = total_data.get('requests', 0)

        quota_pct = (cost / quota * 100) if quota > 0 else 0
        quota_status = "EXCEEDED" if cost >= quota else "NORMAL"

        models[label] = ModelInfo(
            label=label,
            bedrock_model_id=effective_config.get('model_ids', {}).get(label, ''),
            cost_usd_micros=cost,
            quota_usd_micros=quota,
            quota_pct=quota_pct,
            quota_status=quota_status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            requests=requests,
            average_cost_per_request=int(cost / requests) if requests > 0 else 0
        )

        total_cost += cost
        total_quota += quota

    # Return actual data
    return DailyAggregatesResponse(
        org_id=org_id,
        app_id=app_id,
        app_name=app_config.get('app_name') if app_config else None,
        date=date,
        timezone=org_config.get('timezone', 'UTC'),
        quota_scope=effective_config.get('quota_scope', 'ORG'),
        models=models,
        total_cost_usd_micros=total_cost,
        total_quota_usd_micros=total_quota,
        total_quota_pct=(total_cost / total_quota * 100) if total_quota > 0 else 0,
        sticky_fallback_active=sticky_fallback_active,
        current_active_model=current_active_model,
        updated_at=datetime.now(timezone.utc)
    )
