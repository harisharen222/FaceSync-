"""
schemas.py — Pydantic v2 DTOs for all Auth Service request/response payloads.
"""
from datetime import datetime
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator, Field


# ── Device Schemas ────────────────────────────────────────────────────────────

class DeviceRegisterRequest(BaseModel):
    """POST /auth/device/register — register a new field device."""
    device_id:       str = Field(..., min_length=4, max_length=64,
                                  description="Unique hardware ID (e.g. ANDROID123)")
    public_key_pem:  str = Field(..., description="ECDSA P-256 public key in PEM format")
    site_code:       str = Field(..., min_length=2, max_length=32)
    device_model:    Optional[str] = None
    android_version: Optional[str] = None

    @field_validator("public_key_pem")
    @classmethod
    def validate_pem(cls, v: str) -> str:
        if "BEGIN PUBLIC KEY" not in v and "BEGIN EC PUBLIC KEY" not in v:
            raise ValueError("public_key_pem must be a valid PEM-encoded EC public key")
        return v.strip()


class DeviceRegisterResponse(BaseModel):
    device_id:    str
    site_code:    str
    registered_at: datetime
    message:      str = "Device registered successfully"


class DeviceTokenRequest(BaseModel):
    """
    POST /auth/device/token — request a JWT for a registered device.
    The device proves ownership of its private key by signing a server-issued
    challenge with its ECDSA P-256 private key.
    """
    device_id:       str
    challenge:       str  = Field(..., description="Server-issued random challenge nonce")
    signature_hex:   str  = Field(..., description="ECDSA signature of the challenge in hex")


class DeviceTokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int  # seconds


class DeviceChallengeResponse(BaseModel):
    """GET /auth/device/challenge — issued before token request."""
    challenge:   str
    expires_in:  int = 60  # challenge valid for 60 seconds


class DevicePublicKeyResponse(BaseModel):
    """GET /auth/device/{device_id}/pubkey — internal endpoint for other services."""
    device_id:       str
    public_key_pem:  str
    site_code:       str
    is_active:       bool


# ── Admin Schemas ─────────────────────────────────────────────────────────────

class AdminLoginRequest(BaseModel):
    """POST /auth/admin/login"""
    email:    EmailStr
    password: str = Field(..., min_length=8)


class AdminLoginResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int
    admin_id:      str
    role:          str


class AdminCreateRequest(BaseModel):
    """POST /auth/admin — create a new admin (superadmin only)."""
    email:     EmailStr
    password:  str = Field(..., min_length=12)
    full_name: Optional[str] = None
    role:      Literal["superadmin", "supervisor", "readonly"] = "supervisor"
    site_code: Optional[str] = None


class AdminResponse(BaseModel):
    admin_id:   UUID
    email:      str
    full_name:  Optional[str]
    role:       str
    site_code:  Optional[str]
    is_active:  bool
    created_at: datetime


# ── Token Schemas ─────────────────────────────────────────────────────────────

class TokenRefreshRequest(BaseModel):
    """POST /auth/token/refresh"""
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    expires_in:   int


class TokenRevokeRequest(BaseModel):
    """POST /auth/token/revoke"""
    token: str
    token_type: Literal["access", "refresh"] = "access"


# ── Generic Responses ─────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    detail:    str
    error_code: Optional[str] = None
