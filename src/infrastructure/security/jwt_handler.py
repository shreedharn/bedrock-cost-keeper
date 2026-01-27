"""JWT token handling for authentication."""

import time
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext

from ...core.config import settings
from ...core.exceptions import UnauthorizedException


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class JWTHandler:
    """Handler for JWT token operations."""

    @staticmethod
    def create_access_token(
        client_id: str,
        org_id: str,
        app_id: Optional[str] = None
    ) -> tuple[str, int]:
        """
        Create an access token.

        Args:
            client_id: Client identifier
            org_id: Organization UUID
            app_id: Application identifier (optional)

        Returns:
            Tuple of (token, expires_at_epoch)
        """
        now = int(time.time())
        expires_at = now + settings.jwt_access_token_expire_seconds

        payload = {
            "sub": client_id,
            "org_id": org_id,
            "token_type": "access",
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": expires_at,
            "iss": "bedrock-cost-keeper"
        }

        if app_id:
            payload["app_id"] = app_id

        # Add scopes
        scopes = ["read:aggregates", "write:costs", "read:model-selection"]
        payload["scope"] = scopes

        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

        return token, expires_at

    @staticmethod
    def create_refresh_token(client_id: str) -> tuple[str, int]:
        """
        Create a refresh token.

        Args:
            client_id: Client identifier

        Returns:
            Tuple of (token, expires_at_epoch)
        """
        now = int(time.time())
        expires_at = now + settings.jwt_refresh_token_expire_seconds

        payload = {
            "sub": client_id,
            "token_type": "refresh",
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": expires_at,
            "iss": "bedrock-cost-keeper"
        }

        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

        return token, expires_at

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """
        Decode and validate a JWT token.

        Args:
            token: JWT token string

        Returns:
            Token payload

        Raises:
            UnauthorizedException: If token is invalid or expired
        """
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )
            return payload
        except JWTError as e:
            raise UnauthorizedException(
                message="Invalid or expired token",
                details={"error": str(e)}
            )

    @staticmethod
    def verify_token_type(payload: Dict[str, Any], expected_type: str) -> None:
        """
        Verify token is of expected type.

        Args:
            payload: Decoded token payload
            expected_type: Expected token type ("access" or "refresh")

        Raises:
            UnauthorizedException: If token type doesn't match
        """
        token_type = payload.get("token_type")
        if token_type != expected_type:
            raise UnauthorizedException(
                message=f"Invalid token type. Expected {expected_type}, got {token_type}",
                details={"expected": expected_type, "actual": token_type}
            )

    @staticmethod
    def hash_secret(secret: str) -> str:
        """
        Hash a client secret using bcrypt.

        Args:
            secret: Plain text secret

        Returns:
            Bcrypt hash
        """
        return pwd_context.hash(secret)

    @staticmethod
    def verify_secret(plain_secret: str, hashed_secret: str) -> bool:
        """
        Verify a client secret against its hash.

        Args:
            plain_secret: Plain text secret
            hashed_secret: Bcrypt hash

        Returns:
            True if secret matches, False otherwise
        """
        return pwd_context.verify(plain_secret, hashed_secret)

    @staticmethod
    def generate_secret() -> str:
        """
        Generate a cryptographically secure random secret.

        Returns:
            Base64-encoded 32-byte random string
        """
        import secrets
        import base64
        return base64.b64encode(secrets.token_bytes(32)).decode('utf-8')
