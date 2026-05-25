"""
dependencies.py — Reusable FastAPI dependency injectors for JWT bearer auth.

Usage in route:
    @router.get("/protected")
    async def protected(payload: TokenPayload = Depends(require_admin_jwt)):
        ...
"""
import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.jwt_handler import decode_token, TokenPayload
from app.redis_client import is_token_blacklisted
from app.database import get_db, AsyncSession

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=True)


async def _extract_and_validate_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    token_type: str = "access",
) -> TokenPayload:
    """
    Core JWT validation dependency (shared logic).
    Raises HTTP 401 on any validation failure.
    """
    raw_token = credentials.credentials
    try:
        payload = decode_token(raw_token, expected_type=token_type)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (InvalidTokenError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check Redis blacklist (revoked token check)
    if await is_token_blacklisted(payload.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def require_access_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> TokenPayload:
    """Any valid access token (device or admin)."""
    return await _extract_and_validate_token(credentials, "access")


async def require_admin_jwt(
    payload: Annotated[TokenPayload, Depends(require_access_token)],
) -> TokenPayload:
    """Valid access token that belongs to an admin (sub_type == 'admin')."""
    if payload.sub_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return payload


async def require_superadmin_jwt(
    payload: Annotated[TokenPayload, Depends(require_admin_jwt)],
) -> TokenPayload:
    """Admin JWT with role == 'superadmin'."""
    if payload.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin privileges required",
        )
    return payload


async def require_device_jwt(
    payload: Annotated[TokenPayload, Depends(require_access_token)],
) -> TokenPayload:
    """Valid access token that belongs to a registered field device."""
    if payload.sub_type != "device":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device token required",
        )
    return payload


# ── Internal service dependency ───────────────────────────────────────────────
# For the /auth/device/{device_id}/pubkey endpoint called by other microservices.
# Uses a pre-shared internal service API key (not JWT) to avoid circular dependencies.

from fastapi import Header
from app.config import get_settings

settings = get_settings()

async def require_internal_service_key(
    x_internal_api_key: str = Header(..., alias="X-Internal-Api-Key"),
) -> None:
    """
    Lightweight API-key guard for endpoints only called by other backend services
    (e.g., Attendance Service calling /auth/device/{id}/pubkey).
    The shared key is stored in AWS Secrets Manager and injected via environment variable.
    """
    expected = getattr(settings, "INTERNAL_API_KEY", None)
    if not expected or x_internal_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal service API key",
        )
