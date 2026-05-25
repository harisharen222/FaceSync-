"""
routes/device.py — Field device registration, challenge issuance, and JWT issuance.
"""
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Device
from app.schemas import (
    DeviceRegisterRequest, DeviceRegisterResponse,
    DeviceChallengeResponse, DeviceTokenRequest, DeviceTokenResponse,
    DevicePublicKeyResponse,
)
from app.device_auth import load_ec_public_key, verify_ecdsa_signature
from app.redis_client import store_challenge, consume_challenge
from app.jwt_handler import create_access_token, create_refresh_token
from app.dependencies import require_admin_jwt, require_internal_service_key
from app.jwt_handler import TokenPayload
from app.config import get_settings
import os

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/auth/device", tags=["Device Auth"])


# ── POST /auth/device/register ────────────────────────────────────────────────

@router.post("/register", response_model=DeviceRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_device(
    body: DeviceRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _caller: Annotated[TokenPayload, Depends(require_admin_jwt)],
):
    """
    Register a new NHAI field device with its ECDSA P-256 public key.
    Only admins can register devices. The public key is validated (curve check)
    before storage. Private key never leaves the device hardware.
    """
    # Validate the submitted PEM is a real P-256 EC key
    try:
        load_ec_public_key(body.public_key_pem)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    # Check for duplicate registration
    existing = await db.execute(select(Device).where(Device.device_id == body.device_id))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Device '{body.device_id}' is already registered. Use PATCH to rotate key.",
        )

    device = Device(
        device_id=body.device_id,
        public_key_pem=body.public_key_pem,
        site_code=body.site_code,
        device_model=body.device_model,
        android_version=body.android_version,
        registered_by=_caller.sub,
    )
    db.add(device)
    logger.info(f"Device registered: {body.device_id} @ site {body.site_code} by admin {_caller.sub}")

    from app.events import emit_event
    emit_event("DeviceRegistered", {
        "device_id": body.device_id,
        "site_code": body.site_code,
        "device_model": body.device_model,
        "registered_by": _caller.sub
    })

    return DeviceRegisterResponse(
        device_id=device.device_id,
        site_code=device.site_code,
        registered_at=datetime.now(tz=timezone.utc),
    )


# ── GET /auth/device/challenge/{device_id} ────────────────────────────────────

@router.get("/challenge/{device_id}", response_model=DeviceChallengeResponse)
async def get_device_challenge(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Issue a random 32-byte hex challenge for the device to sign.
    Challenge is stored in Redis with 60-second TTL.
    Device must call /auth/device/token within 60 seconds.
    """
    result = await db.execute(
        select(Device).where(Device.device_id == device_id, Device.is_active == True)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Device not found or inactive")

    challenge = os.urandom(32).hex()
    await store_challenge(device_id, challenge, ttl_seconds=60)

    logger.debug(f"Challenge issued for device: {device_id}")
    return DeviceChallengeResponse(challenge=challenge)


# ── POST /auth/device/token ───────────────────────────────────────────────────

@router.post("/token", response_model=DeviceTokenResponse)
async def get_device_token(
    body: DeviceTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Issue a JWT for a registered device after verifying ECDSA challenge signature.

    Full flow:
      1. Device calls GET /auth/device/challenge/{device_id} → receives challenge hex
      2. Device signs challenge bytes with ECDSA P-256 private key (in Android Keystore)
      3. Device posts challenge + signature_hex here
      4. Server verifies signature against stored public key
      5. On success: issues RS256 access + refresh tokens
    """
    # 1. Load device record
    result = await db.execute(
        select(Device).where(Device.device_id == body.device_id, Device.is_active == True)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found or inactive")

    # 2. Retrieve and consume the pending challenge (atomic: deleted from Redis on read)
    stored_challenge = await consume_challenge(body.device_id)
    if not stored_challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending challenge found. Call GET /auth/device/challenge/{device_id} first.",
        )

    # 3. The challenge in the request must match the stored one
    if body.challenge != stored_challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Challenge mismatch. Request a new challenge.",
        )

    # 4. Verify ECDSA signature of the challenge using the registered public key
    is_valid = verify_ecdsa_signature(
        public_key_pem=device.public_key_pem,
        message=body.challenge,
        signature_hex=body.signature_hex,
    )
    if not is_valid:
        logger.warning(f"ECDSA verification FAILED for device {body.device_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ECDSA signature verification failed. Device authentication rejected.",
        )

    # 5. Issue tokens
    extra_claims = {"site_code": device.site_code}
    access_token, _ = create_access_token(
        subject=device.device_id,
        subject_type="device",
        extra_claims=extra_claims,
    )
    refresh_token, _ = create_refresh_token(
        subject=device.device_id,
        subject_type="device",
    )

    # Update last seen
    device.last_seen_at = datetime.now(tz=timezone.utc)

    logger.info(f"Device JWT issued: {body.device_id} @ site {device.site_code}")

    return DeviceTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── GET /auth/device/{device_id}/pubkey ──────────────────────────────────────
# Internal endpoint — called by Attendance Service to verify record signatures.

@router.get("/{device_id}/pubkey", response_model=DevicePublicKeyResponse)
async def get_device_pubkey(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_internal_service_key)],
):
    """
    Internal endpoint for other microservices to fetch a device's registered public key.
    Protected by X-Internal-Api-Key header (not JWT, to avoid circular auth dependencies).
    """
    result = await db.execute(select(Device).where(Device.device_id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return DevicePublicKeyResponse(
        device_id=device.device_id,
        public_key_pem=device.public_key_pem,
        site_code=device.site_code,
        is_active=device.is_active,
    )
