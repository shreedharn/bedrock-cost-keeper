"""FastAPI dependencies for authentication and common operations."""

import hmac
from typing import Annotated
from fastapi import Depends, Header
from ..infrastructure.security.jwt_handler import JWTHandler
from ..infrastructure.database.dynamodb_bridge import DynamoDBBridge
from ..domain.services.inference_profile_service import InferenceProfileService
from ..core.config import settings
from ..core.exceptions import UnauthorizedException


# Global database bridge instance
db_bridge: DynamoDBBridge = None

# Global inference profile service instance
inference_profile_service: InferenceProfileService = None

jwt_handler = JWTHandler()


def get_db_bridge() -> DynamoDBBridge:
    """Dependency to get database bridge."""
    return db_bridge


def get_db() -> DynamoDBBridge:
    """Alias for get_db_bridge for consistency."""
    return db_bridge


def get_inference_profile_service() -> InferenceProfileService:
    """Dependency to get inference profile service."""
    return inference_profile_service


async def verify_jwt_token(
    authorization: Annotated[str, Header()],
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)]
) -> dict:
    """Alias for get_current_user for consistency."""
    return await get_current_user(authorization, db)


async def get_current_user(
    authorization: Annotated[str, Header()],
    db: Annotated[DynamoDBBridge, Depends(get_db_bridge)]
) -> dict:
    """
    Dependency to get current authenticated user from JWT token.

    Args:
        authorization: Authorization header with Bearer token
        db: Database bridge instance

    Returns:
        User information extracted from token

    Raises:
        UnauthorizedException: If token is invalid or revoked
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedException("Missing or invalid authorization header")

    token = authorization[7:]  # Remove "Bearer " prefix

    # Decode and validate token
    payload = jwt_handler.decode_token(token)

    # Verify it's an access token
    jwt_handler.verify_token_type(payload, "access")

    # Check if token is revoked
    token_jti = payload.get("jti")
    if await db.is_token_revoked(token_jti):
        raise UnauthorizedException("Token has been revoked")

    # Return user info
    return {
        "client_id": payload.get("sub"),
        "org_id": payload.get("org_id"),
        "app_id": payload.get("app_id"),
        "scopes": payload.get("scope", [])
    }


def verify_provisioning_api_key(
    x_api_key: Annotated[str, Header(alias="X-API-Key")]
) -> bool:
    """
    Dependency to verify provisioning API key.

    Args:
        x_api_key: API key from header

    Returns:
        True if valid

    Raises:
        UnauthorizedException: If API key is invalid
    """


    # Use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(x_api_key, settings.provisioning_api_key):
        raise UnauthorizedException("Invalid API key")

    return True
