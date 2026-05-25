"""
device_auth.py — ECDSA P-256 public key registration and challenge-response verification.

Flow:
  1. Device generates an ECDSA P-256 keypair on first boot (inside Android Keystore / iOS Keychain).
  2. Admin registers the device by posting the PUBLIC key PEM to /auth/device/register.
  3. When the device wants a JWT, it calls GET /auth/device/challenge to get a random nonce.
  4. Device signs the nonce with its PRIVATE key and POSTs the signature to /auth/device/token.
  5. Auth Service verifies the signature using the stored PUBLIC key and issues JWT if valid.

This scheme proves device private-key ownership without the private key ever leaving hardware.
"""
import os
import hashlib
import logging
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.exceptions import InvalidSignature

logger = logging.getLogger(__name__)


# ── Challenge store (in-memory for single-instance dev; use Redis in prod) ────
# In production, replace with Redis SET with 60-second TTL.
_challenge_store: dict[str, str] = {}  # device_id → challenge_hex


def generate_challenge(device_id: str) -> str:
    """
    Generate a cryptographically random 32-byte hex challenge for the device.
    Stored server-side for 60 seconds before the device must use it.
    """
    challenge = os.urandom(32).hex()
    _challenge_store[device_id] = challenge
    logger.debug(f"Generated challenge for device {device_id}")
    return challenge


def consume_challenge(device_id: str) -> Optional[str]:
    """
    Pop and return the pending challenge for a device.
    Returns None if no challenge exists (expired or never requested).
    """
    return _challenge_store.pop(device_id, None)


# ── Public key parsing ────────────────────────────────────────────────────────

def load_ec_public_key(pem: str) -> ec.EllipticCurvePublicKey:
    """
    Parse a PEM-encoded ECDSA P-256 public key.
    Raises ValueError if the key is malformed or uses an unsupported curve.
    """
    try:
        key = serialization.load_pem_public_key(pem.encode())
    except Exception as e:
        raise ValueError(f"Failed to parse public key PEM: {e}")

    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise ValueError("Provided key is not an EC public key")

    if not isinstance(key.curve, ec.SECP256R1):
        raise ValueError(
            f"Expected SECP256R1 (P-256) curve, got {key.curve.name}"
        )

    return key


# ── Signature verification ────────────────────────────────────────────────────

def verify_ecdsa_signature(
    public_key_pem: str,
    message: str,
    signature_hex: str,
) -> bool:
    """
    Verify that `signature_hex` is a valid ECDSA P-256 signature over `message`
    using the public key in `public_key_pem`.

    The device signs the raw challenge string (UTF-8 encoded) using SHA-256.
    The signature is DER-encoded and transmitted as a hex string.

    Returns True if valid, False otherwise. Never raises on invalid signatures.
    """
    try:
        public_key = load_ec_public_key(public_key_pem)
        signature_bytes = bytes.fromhex(signature_hex)
        message_bytes = message.encode("utf-8")

        # SHA-256 is used as the digest; ECDSA provides the signature scheme
        public_key.verify(signature_bytes, message_bytes, ec.ECDSA(hashes.SHA256()))
        logger.debug("ECDSA signature verification: PASSED")
        return True

    except InvalidSignature:
        logger.warning("ECDSA signature verification: FAILED (invalid signature)")
        return False
    except (ValueError, Exception) as e:
        logger.warning(f"ECDSA signature verification: ERROR — {e}")
        return False


def verify_attendance_record_signature(
    public_key_pem: str,
    payload_json: str,
    signature_hex: str,
) -> bool:
    """
    Verify an attendance record ECDSA signature.
    Called by the Attendance Sync Service via the internal /auth/device/{id}/pubkey
    endpoint — it fetches the public key and then calls this to validate each record.

    The device signs SHA-256( JSON.stringify(payload, sorted_keys) ).
    """
    return verify_ecdsa_signature(public_key_pem, payload_json, signature_hex)
