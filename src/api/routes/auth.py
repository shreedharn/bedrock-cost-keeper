"""Authentication endpoints."""

from typing import Annotated
from fastapi import APIRouter, Depends, Header

from ..models.requests import TokenRequest, RefreshTokenRequest, RevokeTokenRequest
from ..models.responses import TokenResponse, RefreshTokenResponse
from ...infrastructure.database.dynamodb_bridge import DynamoDBBridge
from ...infrastructure.security.jwt_handler import JWTHandler
from ...core.exceptions import UnauthorizedException
from ...core.config import settings
from ..dependencies import get_db_bridge


router = APIRouter()
jwt_handler = JWTHandler()


@router.post("/token", response_model=TokenResponse)
async def obtain_token(
    request: TokenRequest,
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)]
):
    """
    Obtain JWT access and refresh tokens using client credentials.

    Implements OAuth2 client_credentials flow.
    """
    # Parse client_id to extract org_id and app_id
    # Expected format: "org-{org_id}-app-{app_id}" or "org-{org_id}"
    if not request.client_id.startswith('org-'):
        raise UnauthorizedException("Invalid client_id format")

    # Remove 'org-' prefix
    remaining = request.client_id[4:]

    # Check if this is an app-level client
    app_id = None
    if '-app-' in remaining:
        app_idx = remaining.find('-app-')
        org_id = remaining[:app_idx]
        app_id = remaining[app_idx + 5:]  # Everything after "-app-"
    else:
        org_id = remaining

    # Get configuration to verify credentials
    if app_id:
        config = await db.get_app_config(org_id, app_id)
        if not config:
            raise UnauthorizedException("Invalid client credentials")
    else:
        config = await db.get_org_config(org_id)
        if not config:
            raise UnauthorizedException("Invalid client credentials")

    # Verify client_id matches
    if config.get('client_id') != request.client_id:
        raise UnauthorizedException("Invalid client credentials")

    # Verify client_secret
    stored_secret_hash = config.get('client_secret_hash')
    if not stored_secret_hash:
        raise UnauthorizedException("Invalid client credentials")

    if not jwt_handler.verify_secret(request.client_secret, stored_secret_hash):
        raise UnauthorizedException("Invalid client credentials")

    # Check if rotation grace period active
    grace_expires = config.get('client_secret_rotation_grace_expires_at_epoch')
    if grace_expires:
        # During grace period, verify against old secret if new secret doesn't match
        # (Implementation would need old secret hash stored)
        pass

    # Generate tokens
    access_token, _ = jwt_handler.create_access_token(
        client_id=request.client_id,
        org_id=org_id,
        app_id=app_id
    )

    refresh_token, _ = jwt_handler.create_refresh_token(
        client_id=request.client_id
    )

    # Build scope string
    scope_parts = [f"org:{org_id}"]
    if app_id:
        scope_parts.append(f"app:{app_id}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=settings.jwt_access_token_expire_seconds,
        refresh_expires_in=settings.jwt_refresh_token_expire_seconds,
        scope=" ".join(scope_parts)
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)]
):
    """
    Obtain a new access token using a refresh token.
    """
    # Decode and validate refresh token
    payload = jwt_handler.decode_token(request.refresh_token)
    jwt_handler.verify_token_type(payload, "refresh")

    # Check if token is revoked
    token_jti = payload.get("jti")
    if await db.is_token_revoked(token_jti):
        raise UnauthorizedException("Token has been revoked")

    # Extract client info
    client_id = payload.get("sub")
    client_parts = client_id.split('-')
    org_id = client_parts[1]

    app_id = None
    if 'app' in client_id:
        app_idx = client_id.find('-app-')
        if app_idx > 0:
            app_id = client_id[app_idx + 5:]

    # Generate new access token
    access_token, access_exp = jwt_handler.create_access_token(
        client_id=client_id,
        org_id=org_id,
        app_id=app_id
    )

    return RefreshTokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=settings.jwt_access_token_expire_seconds
    )


@router.post("/revoke", status_code=204)
async def revoke_token(
    request: RevokeTokenRequest,
    authorization: Annotated[str, Header()],
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)]
):
    """
    Revoke an access or refresh token immediately.
    """
    # Verify the authorization token
    if not authorization.startswith("Bearer "):
        raise UnauthorizedException("Invalid authorization header")

    auth_token = authorization[7:]
    auth_payload = jwt_handler.decode_token(auth_token)

    # Decode the token to be revoked
    revoke_payload = jwt_handler.decode_token(request.token)

    # Ensure requester is revoking their own token
    if auth_payload.get("sub") != revoke_payload.get("sub"):
        raise UnauthorizedException("Cannot revoke tokens for other clients")

    # Revoke the token
    token_jti = revoke_payload.get("jti")
    token_type = revoke_payload.get("token_type", "access")
    client_id = revoke_payload.get("sub")
    expiry = revoke_payload.get("exp")

    await db.revoke_token(
        token_jti=token_jti,
        token_type=token_type,
        client_id=client_id,
        original_expiry_epoch=expiry
    )

    return None  # 204 No Content
