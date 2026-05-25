"""
validator.py — Attendance record verification and deduplication logic.
"""
import hashlib
import logging
from typing import Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import AttendanceRecordPayload
from app.models import DeduplicationIndex

logger = logging.getLogger(__name__)


def compute_dedup_hash(worker_id: str, device_id: str, timestamp_iso: str) -> str:
    """
    Compute SHA-256 hash to detect replays of the exact same offline scan.
    """
    raw = f"{worker_id}|{device_id}|{timestamp_iso}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def is_duplicate(db: AsyncSession, dedup_hash: str) -> bool:
    """Check if this record hash already exists in PostgreSQL."""
    result = await db.execute(
        select(DeduplicationIndex).where(DeduplicationIndex.dedup_hash == dedup_hash)
    )
    return result.scalar_one_or_none() is not None


def verify_ecdsa_signature(public_key_pem: str, payload_json: str, signature_hex: str) -> bool:
    """
    Verify that the offline attendance record was actually signed by the field
    device's hardware-backed private key.
    """
    try:
        # Load public key
        public_key = serialization.load_pem_public_key(public_key_pem.encode())
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            return False

        # Parse signature
        signature_bytes = bytes.fromhex(signature_hex)
        message_bytes = payload_json.encode("utf-8")

        # Verify
        public_key.verify(signature_bytes, message_bytes, ec.ECDSA(hashes.SHA256()))
        return True

    except InvalidSignature:
        return False
    except Exception as e:
        logger.warning(f"Signature verification error: {e}")
        return False


async def process_record(
    db: AsyncSession,
    record: AttendanceRecordPayload,
    device_id: str,
    public_key_pem: str
) -> Tuple[bool, str, str]:
    """
    Process a single record: check signature, check dedup.
    Returns: (is_valid, status, error_reason)
    """
    # 1. Signature Verification
    is_sig_valid = verify_ecdsa_signature(
        public_key_pem,
        record.signature_payload(),
        record.signature_hex
    )
    
    if not is_sig_valid:
        logger.warning(f"Invalid signature for record {record.id}")
        from app.events import emit_event
        emit_event("SpoofingDetected", {
            "worker_id": record.worker_id,
            "device_id": device_id,
            "reason": "Invalid ECDSA signature"
        })
        return False, "INVALID_SIGNATURE", "ECDSA signature verification failed"

    # 2. Liveness Check
    if not record.liveness_passed:
        logger.warning(f"Liveness failed for record {record.id}")
        from app.events import emit_event
        emit_event("SpoofingDetected", {
            "worker_id": record.worker_id,
            "device_id": device_id,
            "reason": "Liveness check failed on device"
        })
        return False, "FLAGGED", "Liveness check failed on device"

    # 3. Deduplication Check
    iso_time = record.timestamp_utc.isoformat().replace("+00:00", "Z")
    dedup_hash = compute_dedup_hash(record.worker_id, device_id, iso_time)
    
    if await is_duplicate(db, dedup_hash):
        # Silently drop duplicates as they are expected due to mobile network retries
        return False, "DUPLICATE", "Record already synced"

    return True, "VERIFIED", ""
