"""Custom exceptions for the application."""

from typing import Optional, Dict, Any
from fastapi import HTTPException, status


class BaseAPIException(HTTPException):
    """Base exception for all API errors."""

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        self.error_code = error_code
        self.details = details or {}
        super().__init__(
            status_code=status_code,
            detail={
                "error": error_code,
                "message": message,
                "details": self.details
            }
        )


# Authentication Exceptions
class UnauthorizedException(BaseAPIException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Unauthorized", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED",
            message=message,
            details=details
        )


class ForbiddenException(BaseAPIException):
    """Raised when user lacks permissions."""

    def __init__(self, message: str = "Forbidden", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN",
            message=message,
            details=details
        )


# Resource Exceptions
class NotFoundException(BaseAPIException):
    """Raised when resource is not found."""

    def __init__(self, message: str = "Resource not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND",
            message=message,
            details=details
        )


class AlreadyExistsException(BaseAPIException):
    """Raised when resource already exists."""

    def __init__(self, message: str = "Resource already exists", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            error_code="ALREADY_EXISTS",
            message=message,
            details=details
        )


# Validation Exceptions
class InvalidRequestException(BaseAPIException):
    """Raised when request is invalid."""

    def __init__(self, message: str = "Invalid request", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_REQUEST",
            message=message,
            details=details
        )


class InvalidConfigException(BaseAPIException):
    """Raised when configuration is invalid."""

    def __init__(self, message: str = "Invalid configuration", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_CONFIG",
            message=message,
            details=details
        )


class InvalidModelLabelException(BaseAPIException):
    """Raised when model label is not defined."""

    def __init__(self, message: str = "Invalid model label", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_MODEL_LABEL",
            message=message,
            details=details
        )


# Quota Exceptions
class QuotaExceededException(BaseAPIException):
    """Raised when all quotas are exceeded."""

    def __init__(self, message: str = "All quotas exceeded", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="QUOTA_EXCEEDED",
            message=message,
            details=details
        )


class RateLimitExceededException(BaseAPIException):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_EXCEEDED",
            message=message,
            details=details
        )


# Server Exceptions
class InternalErrorException(BaseAPIException):
    """Raised for internal server errors."""

    def __init__(self, message: str = "Internal server error", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="INTERNAL_ERROR",
            message=message,
            details=details
        )


class ServiceUnavailableException(BaseAPIException):
    """Raised when service is temporarily unavailable."""

    def __init__(self, message: str = "Service unavailable", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="SERVICE_UNAVAILABLE",
            message=message,
            details=details
        )
