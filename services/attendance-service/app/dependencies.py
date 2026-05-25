"""
dependencies.py — JWT verification for Attendance Sync Service.
"""
import logging
from typing import Optional, Annotated

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_bearer = HTTPBearer(auto_error=True)

# ── JWKS public key cache ─────────────────────────────────────────────────────
_cached_public_key: Optional[str] = None


async def _get_public_key() -> str:
    global _cached_public_key
    if _cached_public_key:
        return _cached_public_key

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(settings.AUTH_JWKS_URL)
            resp.raise_for_status()
            jwks = resp.json()

        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
        from cryptography.hazmat.primitives import serialization
        import base64

        key_data = jwks["keys"][0]
        def _b64url_decode(s):
            padding = 4 - len(s) % 4
            return base64.urlsafe_b64decode(s + "=" * padding)

        n = int.from_bytes(_b64url_decode(key_data["n"]), "big")
        e = int.from_bytes(_b64url_decode(key_data["e"]), "big")
        pub_key = RSAPublicNumbers(e, n).public_key()
        pem = pub_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        _cached_public_key = pem
        return pem

    except Exception as exc:
        logger.error(f"Failed to fetch JWKS from {settings.AUTH_JWKS_URL}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth Service unavailable — cannot verify tokens",
        )


class TokenPayload:
    def __init__(self, raw: dict):
        self.sub:      str = raw["sub"]
        self.sub_type: str = raw.get("sub_type", "unknown")
        self.role:     Optional[str] = raw.get("role")
        self.site_code: Optional[str] = raw.get("site_code")
        self.jti:      str = raw["jti"]


async def _verify_token(credentials: HTTPAuthorizationCredentials) -> TokenPayload:
    public_key = await _get_public_key()
    try:
        payload = jwt.decode(
            credentials.credentials,
            public_key,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "jti", "exp"]},
            issuer=settings.JWT_ISSUER,
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    return TokenPayload(payload)


async def require_admin_jwt(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)]
) -> TokenPayload:
    payload = await _verify_token(credentials)
    if payload.sub_type != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return payload


async def require_device_jwt(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)]
) -> TokenPayload:
    payload = await _verify_token(credentials)
    if payload.sub_type != "device":
        raise HTTPException(status_code=403, detail="Device token required")
    return payload
