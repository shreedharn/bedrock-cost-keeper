"""Model selection endpoints."""

from typing import Annotated
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Path, Query

from ..models.responses import ModelSelectionResponse, RecommendedModel, QuotaStatus, PricingInfo, ClientGuidance, ModelStatusInfo
from ...infrastructure.database.dynamodb_bridge import DynamoDBBridge
from ...domain.services.metering_service import MeteringService
from ...core.config import main_config
from ...core.exceptions import InvalidConfigException, QuotaExceededException
from ..dependencies import get_db_bridge, get_current_user


router = APIRouter()


@router.get("/orgs/{org_id}/apps/{app_id}/model-selection", response_model=ModelSelectionResponse)
async def get_model_selection(
    org_id: Annotated[str, Path(description="Organization UUID")],
    app_id: Annotated[str, Path(description="Application identifier")],
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)],
    current_user: Annotated[dict, Depends(get_current_user)],
    force_check: Annotated[bool, Query(description="Force real-time quota check")] = False
):
    """
    Get current recommended model based on quota status and sticky fallback state.

    Returns the best model to use considering:
    - Current quota consumption
    - Sticky fallback state
    - Model ordering preferences
    """
    # Verify authorization
    if current_user['org_id'] != org_id:
        raise InvalidConfigException("Org ID mismatch")

    if current_user.get('app_id') and current_user['app_id'] != app_id:
        raise InvalidConfigException("App ID mismatch")

    # Get configs
    org_config = await db.get_org_config(org_id)
    if not org_config:
        raise InvalidConfigException(f"Organization {org_id} not found")

    app_config = await db.get_app_config(org_id, app_id)
    effective_config = {**org_config}
    if app_config:
        effective_config.update(app_config)

    # Get model ordering and quotas
    model_ordering = effective_config.get('model_ordering', [])
    quotas = effective_config.get('quotas', {})

    # Create metering service
    metering_service = MeteringService(db)

    # Get current usage for all models
    usage = await metering_service.get_current_usage(org_id, app_id, model_ordering)

    # Check sticky state
    scope = metering_service._compute_scope(org_config, org_id, app_id)
    day = metering_service._compute_org_day(effective_config['timezone'])
    sticky_state = await db.get_sticky_state(scope, day)

    # Determine recommended model
    recommended_label = None
    reason = "NORMAL"
    sticky_active = False

    if sticky_state:
        # Use sticky state
        recommended_label = sticky_state['active_model_label']
        reason = "STICKY_FALLBACK"
        sticky_active = True
    else:
        # Find first model under quota
        for label in model_ordering:
            quota = quotas.get(label, 0)
            usage_data = usage.get(label, {})
            spend = usage_data.get('cost_usd_micros', 0)

            if spend < quota:
                recommended_label = label
                reason = "NORMAL"
                break

    if not recommended_label:
        # All quotas exceeded
        raise QuotaExceededException(
            "All model quotas exceeded for today",
            details={
                "org_id": org_id,
                "app_id": app_id,
                "date": day.replace("DAY#", ""),
                "models": {
                    label: {
                        "quota_pct": (usage.get(label, {}).get('cost_usd_micros', 0) / quotas.get(label, 1)) * 100,
                        "exceeded": True
                    }
                    for label in model_ordering
                }
            }
        )

    # Get model details from main config
    model_labels = main_config.get('model_labels', {})
    model_info = model_labels.get(recommended_label, {})
    bedrock_model_id = model_info.get('bedrock_model_id', '')

    # Calculate quota status
    current_quota = quotas.get(recommended_label, 0)
    current_spend = usage.get(recommended_label, {}).get('cost_usd_micros', 0)
    quota_pct = (current_spend / current_quota * 100) if current_quota > 0 else 0

    # Determine mode
    tight_threshold = effective_config.get('tight_mode_threshold_pct', 95)
    mode = "TIGHT" if quota_pct >= tight_threshold else "NORMAL"

    # Build response
    return ModelSelectionResponse(
        org_id=org_id,
        app_id=app_id,
        recommended_model=RecommendedModel(
            label=recommended_label,
            bedrock_model_id=bedrock_model_id,
            reason=reason,
            description=model_info.get('description', '')
        ),
        quota_status=QuotaStatus(
            scope=org_config.get('quota_scope', 'ORG'),
            mode=mode,
            current_model=recommended_label,
            spend_usd_micros=current_spend,
            quota_usd_micros=current_quota,
            quota_pct=quota_pct,
            sticky_fallback_active=sticky_active,
            models_status={
                label: ModelStatusInfo(
                    spend_usd_micros=usage.get(label, {}).get('cost_usd_micros', 0),
                    quota_usd_micros=quotas.get(label, 0),
                    quota_pct=(usage.get(label, {}).get('cost_usd_micros', 0) / quotas.get(label, 1)) * 100,
                    status="EXCEEDED" if usage.get(label, {}).get('cost_usd_micros', 0) >= quotas.get(label, 0) else "NORMAL"
                )
                for label in model_ordering
            }
        ),
        pricing=PricingInfo(
            input_price_usd_micros_per_1m=model_info.get('input_price_usd_micros_per_1m', 0),
            output_price_usd_micros_per_1m=model_info.get('output_price_usd_micros_per_1m', 0),
            version=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            source="CONFIG_FALLBACK"
        ),
        client_guidance=ClientGuidance(
            check_frequency="PERIODIC_60S" if mode == "TIGHT" else "PERIODIC_300S",
            cache_duration_secs=60 if mode == "TIGHT" else 300,
            explanation=f"In {mode} mode - check every {'60 seconds' if mode == 'TIGHT' else '5 minutes'}"
        ),
        checked_at=datetime.now(timezone.utc),
        org_day=day.replace("DAY#", ""),
        org_local_time=datetime.now(timezone.utc).isoformat()
    )
