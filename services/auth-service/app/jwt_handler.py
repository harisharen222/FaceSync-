"""
jwt_handler.py — RS256 JWT issuance and verification for the NHAI Auth Service.

Design decisions:
  - RS256 (asymmetric): private key stays in Auth Service / Secrets Manager.
    All other microservices can verify tokens using only the PUBLIC key (read-only).
  - Every token carries a unique JTI (JWT ID) enabling individual token revocation.
  - Access tokens are short-lived (30 min). Refresh tokens are long-lived (30 days)
    but stored server-side in Redis so they can be immediately invalidated on logout.
"""
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Key loading ───────────────────────────────────────────────────────────────

def _load_private_key() -> str:
    """
    Returns the RS256 private key PEM string.
    In production, this is fetched from AWS Secrets Manager at startup and
    cached in settings. In development, it is read from the .env file.
    """
    if not settings.JWT_RS256_PRIVATE_KEY:
        raise RuntimeError(
            "JWT_RS256_PRIVATE_KEY is not configured. "
            "Set it in .env for development or ensure AWS Secrets Manager is accessible."
        )
    return settings.JWT_RS256_PRIVATE_KEY


def _load_public_key() -> str:
    if not settings.JWT_RS256_PUBLIC_KEY:
        raise RuntimeError("JWT_RS256_PUBLIC_KEY is not configured.")
    return settings.JWT_RS256_PUBLIC_KEY


# ── Token creation ────────────────────────────────────────────────────────────

def create_access_token(
    subject: str,
    subject_type: Literal["device", "admin"],
    extra_claims: Optional[dict] = None,
) -> tuple[str, str]:
    """
    Issue a short-lived RS256 JWT access token.

    Args:
        subject: device_id or admin_id (str)
        subject_type: "device" | "admin"
        extra_claims: additional payload fields (e.g. {"site_code": "NH-44"})

    Returns:
        (encoded_token, jti) — the JTI is stored in Redis for blacklist checking.
    """
    jti = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "iss": settings.JWT_ISSUER,
        "sub": subject,
        "sub_type": subject_type,
        "jti": jti,
        "iat": now,
        "exp": expire,
        "token_type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, _load_private_key(), algorithm=settings.JWT_ALGORITHM)
    return token, jti


def create_refresh_token(
    subject: str,
    subject_type: Literal["device", "admin"],
) -> tuple[str, str]:
    """
    Issue a long-lived refresh token.
    Refresh tokens contain minimal claims — just enough to issue a new access token.
    """
    jti = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "iss": settings.JWT_ISSUER,
        "sub": subject,
        "sub_type": subject_type,
        "jti": jti,
        "iat": now,
        "exp": expire,
        "token_type": "refresh",
    }

    token = jwt.encode(payload, _load_private_key(), algorithm=settings.JWT_ALGORITHM)
    return token, jti


# ── Token verification ────────────────────────────────────────────────────────

class TokenPayload:
    """Parsed and validated JWT payload."""
    def __init__(self, raw: dict):
        self.sub:        str = raw["sub"]
        self.sub_type:   str = raw.get("sub_type", "unknown")
        self.jti:        str = raw["jti"]
        self.exp:        datetime = datetime.fromtimestamp(raw["exp"], tz=timezone.utc)
        self.token_type: str = raw.get("token_type", "access")
        self.site_code:  Optional[str] = raw.get("site_code")
        self.role:       Optional[str] = raw.get("role")
        self.raw:        dict = raw


def decode_token(token: str, expected_type: Literal["access", "refresh"] = "access") -> TokenPayload:
    """
    Decode and validate a JWT.

    Raises:
        jwt.ExpiredSignatureError: if token is past its expiry
        jwt.InvalidTokenError:     if signature or claims are invalid
        ValueError:                if token_type doesn't match expected_type
    """
    try:
        payload = jwt.decode(
            token,
            _load_public_key(),
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "jti", "exp", "iss"]},
            issuer=settings.JWT_ISSUER,
        )
    except ExpiredSignatureError:
        logger.warning("JWT decode failed: token expired")
        raise
    except InvalidTokenError as e:
        logger.warning(f"JWT decode failed: {e}")
        raise

    parsed = TokenPayload(payload)

    if parsed.token_type != expected_type:
        raise ValueError(
            f"Expected token_type='{expected_type}', got '{parsed.token_type}'"
        )

    return parsed
