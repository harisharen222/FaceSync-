"""
routes/token.py — Token lifecycle: refresh and revocation.
"""
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import TokenRefreshRequest, TokenRefreshResponse, TokenRevokeRequest, MessageResponse
from app.jwt_handler import decode_token, create_access_token, TokenPayload
from app.redis_client import blacklist_token, is_token_blacklisted
from app.models import TokenBlacklist
from app.config import get_settings
from app.dependencies import require_access_token

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/auth/token", tags=["Token Management"])


# ── POST /auth/token/refresh ──────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    body: TokenRefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Exchange a valid refresh token for a new access token.
    The refresh token is NOT invalidated here — it can be used multiple times
    until it expires or is explicitly revoked.

    This is a stateless refresh — no refresh token rotation to keep
    offline-first devices compatible (they may miss rotation windows).
    """
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {e}",
        )

    # Check blacklist (device may have been deactivated)
    if await is_token_blacklisted(payload.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
        )

    # Issue new access token with same claims
    extra_claims = {}
    if payload.site_code:
        extra_claims["site_code"] = payload.site_code
    if payload.role:
        extra_claims["role"] = payload.role

    new_access_token, _ = create_access_token(
        subject=payload.sub,
        subject_type=payload.sub_type,
        extra_claims=extra_claims or None,
    )

    logger.info(f"Token refreshed for subject: {payload.sub} ({payload.sub_type})")

    return TokenRefreshResponse(
        access_token=new_access_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── POST /auth/token/revoke ───────────────────────────────────────────────────

@router.post("/revoke", response_model=MessageResponse)
async def revoke_token(
    body: TokenRevokeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Annotated[TokenPayload, Depends(require_access_token)],
):
    """
    Revoke a specific token by blacklisting its JTI.
    Both the Redis fast-path and the PostgreSQL durable record are written.
    Callers can only revoke their own tokens unless they are admins.
    """
    try:
        target_payload = decode_token(body.token, expected_type=body.token_type)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot parse token to revoke: {e}",
        )

    # Authorization: only allow self-revocation or admin revocation
    is_self_revoke = caller.sub == target_payload.sub
    is_admin = caller.sub_type == "admin"
    if not (is_self_revoke or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only revoke your own tokens",
        )

    # 1. Redis blacklist (fast-path)
    await blacklist_token(target_payload.jti, target_payload.exp)

    # 2. PostgreSQL durable backup
    db_record = TokenBlacklist(
        jti=target_payload.jti,
        token_type=body.token_type,
        revoked_by=caller.sub,
        expires_at=target_payload.exp,
    )
    db.add(db_record)

    logger.info(
        f"Token revoked: JTI={target_payload.jti} "
        f"target={target_payload.sub} by={caller.sub}"
    )

    from app.events import emit_event
    emit_event("TokenRevoked", {
        "jti": target_payload.jti,
        "token_type": body.token_type,
        "revoked_by": caller.sub,
        "target_sub": target_payload.sub
    })

    return MessageResponse(message="Token revoked successfully")


# ── GET /auth/token/jwks ──────────────────────────────────────────────────────

@router.get("/jwks")
async def get_jwks():
    """
    Expose the RS256 public key as a JWKS (JSON Web Key Set).
    Other microservices can use this endpoint to fetch the public key
    for independent JWT verification without calling Auth Service on every request.
    """
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
    from cryptography.hazmat.primitives import serialization
    import base64, json
    from app.jwt_handler import _load_public_key
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    pem = _load_public_key().encode()
    public_key = load_pem_public_key(pem)

    # Export as DER and build a minimal JWKS manually
    public_numbers = public_key.public_key().public_numbers() if hasattr(public_key, 'public_key') else public_key.public_numbers()

    def _int_to_base64url(n: int) -> str:
        byte_length = (n.bit_length() + 7) // 8
        return base64.urlsafe_b64encode(n.to_bytes(byte_length, "big")).rstrip(b"=").decode()

    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": "nhai-rs256-1",
                "n": _int_to_base64url(public_numbers.n),
                "e": _int_to_base64url(public_numbers.e),
            }
        ]
    }
    return jwks
