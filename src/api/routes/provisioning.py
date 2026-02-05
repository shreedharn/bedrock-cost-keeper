"""Provisioning endpoints for admin operations."""

from fastapi import APIRouter, Depends, Path
from typing import Annotated
from datetime import datetime, timezone, timedelta

from ..models.requests import OrgRegistrationRequest, AppRegistrationRequest, CredentialRotationRequest
from ..models.responses import (
    OrgRegistrationResponse, AppRegistrationResponse, CredentialRotationResponse,
    CredentialsInfo, ConfigInfo, RotationInfo
)
from ...infrastructure.database.dynamodb_bridge import DynamoDBBridge
from ...infrastructure.security.jwt_handler import JWTHandler
from ...core.config import main_config
from ...core.exceptions import InvalidConfigException
from ..dependencies import get_db_bridge, verify_provisioning_api_key


router = APIRouter()
jwt_handler = JWTHandler()


@router.put("/orgs/{org_id}", response_model=OrgRegistrationResponse)
async def register_or_update_org(
    org_id: Annotated[str, Path(description="Organization UUID")],
    request: OrgRegistrationRequest,
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)],
    _: Annotated[bool, Depends(verify_provisioning_api_key)]
):
    """
    Create or update an organization configuration.

    Generates client credentials on creation. PUT is idempotent for updates.
    """
    # Validate model labels exist in main config
    model_labels = main_config.get('model_labels', {})
    for label in request.model_ordering:
        if label not in model_labels:
            raise InvalidConfigException(
                f"Model label '{label}' not defined in main config",
                details={
                    "invalid_labels": [label],
                    "valid_labels": list(model_labels.keys())
                }
            )

    # Check if org exists
    existing_org = await db.get_org_config(org_id)
    is_new = existing_org is None

    # Generate client credentials
    client_id = f"org-{org_id}"
    client_secret = None

    if is_new:
        client_secret = jwt_handler.generate_secret()
        client_secret_hash = jwt_handler.hash_secret(client_secret)
    else:
        client_secret_hash = existing_org.get('client_secret_hash')

    # Build config
    config_data = {
        'org_name': request.org_name,
        'timezone': request.timezone,
        'quota_scope': request.quota_scope,
        'model_ordering': request.model_ordering,
        'quotas': request.quotas,
        'client_id': client_id,
        'client_secret_hash': client_secret_hash,
        'client_secret_created_at_epoch': int(datetime.now(timezone.utc).timestamp()),
        'created_at_epoch': existing_org.get('created_at_epoch') if existing_org else int(datetime.now(timezone.utc).timestamp())
    }

    # Add overrides
    if request.overrides:
        config_data.update(request.overrides)

    # Save to database
    await db.put_org_config(org_id, config_data)

    # Build response
    response = OrgRegistrationResponse(
        org_id=org_id,
        status="created" if is_new else "updated",
        configuration=ConfigInfo(
            timezone=request.timezone,
            quota_scope=request.quota_scope,
            model_ordering=request.model_ordering,
            agg_shard_count=request.overrides.get('agg_shard_count', 8) if request.overrides else 8
        )
    )

    if is_new:
        response.created_at = datetime.now(timezone.utc)
        response.credentials = CredentialsInfo(
            client_id=client_id,
            client_secret=client_secret
        )
    else:
        response.updated_at = datetime.now(timezone.utc)

    return response


@router.put("/orgs/{org_id}/apps/{app_id}", response_model=AppRegistrationResponse)
async def register_or_update_app(
    org_id: Annotated[str, Path(description="Organization UUID")],
    app_id: Annotated[str, Path(description="Application identifier")],
    request: AppRegistrationRequest,
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)],
    _: Annotated[bool, Depends(verify_provisioning_api_key)]
):
    """
    Create or update an application configuration under an organization.

    Application inherits org settings unless overridden.
    """
    # Verify org exists
    org_config = await db.get_org_config(org_id)
    if not org_config:
        raise InvalidConfigException(f"Organization {org_id} not found")

    # Check if app exists
    existing_app = await db.get_app_config(org_id, app_id)
    is_new = existing_app is None

    # Generate client credentials for app
    client_id = f"org-{org_id}-app-{app_id}"
    client_secret = None

    if is_new:
        client_secret = jwt_handler.generate_secret()
        client_secret_hash = jwt_handler.hash_secret(client_secret)
    else:
        client_secret_hash = existing_app.get('client_secret_hash')

    # Build app config
    app_config_data = {
        'app_name': request.app_name,
        'client_id': client_id,
        'client_secret_hash': client_secret_hash,
        'client_secret_created_at_epoch': int(datetime.now(timezone.utc).timestamp()),
        'created_at_epoch': existing_app.get('created_at_epoch') if existing_app else int(datetime.now(timezone.utc).timestamp())
    }

    if request.model_ordering:
        app_config_data['model_ordering'] = request.model_ordering
    if request.quotas:
        app_config_data['quotas'] = request.quotas
    if request.overrides:
        app_config_data.update(request.overrides)

    await db.put_app_config(org_id, app_id, app_config_data)

    # Build response
    response = AppRegistrationResponse(
        org_id=org_id,
        app_id=app_id,
        status="created" if is_new else "updated",
        configuration={
            'app_name': request.app_name,
            'model_ordering': request.model_ordering,
            'inherited_fields': ['timezone', 'agg_shard_count']
        }
    )

    if is_new:
        response.created_at = datetime.now(timezone.utc)
        response.credentials = CredentialsInfo(
            client_id=client_id,
            client_secret=client_secret
        )
    else:
        response.updated_at = datetime.now(timezone.utc)

    return response


@router.post("/orgs/{org_id}/credentials/rotate", response_model=CredentialRotationResponse)
async def rotate_org_credentials(
    org_id: Annotated[str, Path(description="Organization UUID")],
    request: CredentialRotationRequest,
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)],
    _: Annotated[bool, Depends(verify_provisioning_api_key)]
):
    """
    Rotate organization credentials.

    Generates new client_secret while keeping client_id. Old secret remains valid
    during grace period for zero-downtime rotation.
    """
    # Verify org exists
    existing_org = await db.get_org_config(org_id)
    if not existing_org:
        raise InvalidConfigException(f"Organization {org_id} not found")

    # Generate new secret
    new_secret = jwt_handler.generate_secret()
    new_secret_hash = jwt_handler.hash_secret(new_secret)
    old_secret_hash = existing_org.get("client_secret_hash")

    # Calculate grace period expiration
    now = datetime.now(timezone.utc)
    grace_period_seconds = request.grace_period_hours * 3600
    grace_expires_at = now + timedelta(seconds=grace_period_seconds)
    grace_expires_at_epoch = int(grace_expires_at.timestamp())

    # Rotate credentials in database
    await db.rotate_org_credentials(
        org_id=org_id,
        new_secret_hash=new_secret_hash,
        old_secret_hash=old_secret_hash,
        grace_expires_at_epoch=grace_expires_at_epoch
    )

    # Build response
    client_id = f"org-{org_id}"
    response = CredentialRotationResponse(
        org_id=org_id,
        client_id=client_id,
        client_secret=new_secret,
        rotation=RotationInfo(
            rotated_at=now,
            old_secret_expires_at=grace_expires_at,
            grace_period_hours=request.grace_period_hours
        )
    )

    return response


@router.post("/orgs/{org_id}/apps/{app_id}/credentials/rotate", response_model=CredentialRotationResponse)
async def rotate_app_credentials(
    org_id: Annotated[str, Path(description="Organization UUID")],
    app_id: Annotated[str, Path(description="Application identifier")],
    request: CredentialRotationRequest,
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)],
    _: Annotated[bool, Depends(verify_provisioning_api_key)]
):
    """
    Rotate application credentials.

    Generates new client_secret while keeping client_id. Old secret remains valid
    during grace period for zero-downtime rotation.
    """
    # Verify org exists
    org_config = await db.get_org_config(org_id)
    if not org_config:
        raise InvalidConfigException(f"Organization {org_id} not found")

    # Verify app exists
    existing_app = await db.get_app_config(org_id, app_id)
    if not existing_app:
        raise InvalidConfigException(f"Application {app_id} not found in organization {org_id}")

    # Generate new secret
    new_secret = jwt_handler.generate_secret()
    new_secret_hash = jwt_handler.hash_secret(new_secret)
    old_secret_hash = existing_app.get("client_secret_hash")

    # Calculate grace period expiration
    now = datetime.now(timezone.utc)
    grace_period_seconds = request.grace_period_hours * 3600
    grace_expires_at = now + timedelta(seconds=grace_period_seconds)
    grace_expires_at_epoch = int(grace_expires_at.timestamp())

    # Rotate credentials in database
    await db.rotate_app_credentials(
        org_id=org_id,
        app_id=app_id,
        new_secret_hash=new_secret_hash,
        old_secret_hash=old_secret_hash,
        grace_expires_at_epoch=grace_expires_at_epoch
    )

    # Build response
    client_id = f"org-{org_id}-app-{app_id}"
    response = CredentialRotationResponse(
        org_id=org_id,
        app_id=app_id,
        client_id=client_id,
        client_secret=new_secret,
        rotation=RotationInfo(
            rotated_at=now,
            old_secret_expires_at=grace_expires_at,
            grace_period_hours=request.grace_period_hours
        )
    )

    return response

