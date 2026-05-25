"""
encryption.py — AES-256-GCM encryption for 128-D face embeddings.

Design:
  - AES-256-GCM provides authenticated encryption (confidentiality + integrity).
  - Each encrypt() call generates a fresh random 12-byte nonce — NEVER reuse a nonce.
  - The GCM auth tag (16 bytes) detects any tampering with the ciphertext.
  - The raw 32-byte AES key is stored in AWS Secrets Manager; never in code or env vars in prod.

Storage layout in face_embeddings table:
  encrypted_blob = AES-GCM ciphertext (same length as plaintext)
  nonce          = 12 random bytes  (generated fresh per encryption)
  tag            = 16 bytes GCM authentication tag
"""
import os
import json
import logging
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Key loading ───────────────────────────────────────────────────────────────
_aes_key: Optional[bytes] = None


def _load_aes_key() -> bytes:
    """
    Returns the 32-byte AES-256 key.
    Production: fetched from AWS Secrets Manager at startup.
    Development: parsed from AES_EMBEDDING_KEY_HEX env var.

    Key format: 64-character lowercase hex string → 32 bytes.
    Generate with: python -c "import os,binascii; print(binascii.hexlify(os.urandom(32)).decode())"
    """
    global _aes_key
    if _aes_key is not None:
        return _aes_key

    if settings.USE_AWS_SECRETS:
        _aes_key = _fetch_key_from_secrets_manager()
    else:
        hex_key = settings.AES_EMBEDDING_KEY_HEX
        if not hex_key or len(hex_key) != 64:
            raise RuntimeError(
                "AES_EMBEDDING_KEY_HEX must be a 64-char hex string (32 bytes). "
                "Generate with: python -c \"import os,binascii; print(binascii.hexlify(os.urandom(32)).decode())\""
            )
        _aes_key = bytes.fromhex(hex_key)

    return _aes_key


def _fetch_key_from_secrets_manager() -> bytes:
    import boto3
    client = boto3.client("secretsmanager", region_name=settings.AWS_REGION)
    response = client.get_secret_value(SecretId=settings.AWS_SECRET_NAME_AES)
    secret = json.loads(response["SecretString"])
    return bytes.fromhex(secret["key_hex"])


def init_encryption_key() -> None:
    """Call at app startup to eagerly validate the AES key configuration."""
    _load_aes_key()
    logger.info("AES-256-GCM embedding encryption key loaded ✓")


# ── Encrypt / Decrypt ─────────────────────────────────────────────────────────

def encrypt_embedding(embedding: list[float]) -> tuple[bytes, bytes, bytes]:
    """
    Encrypt a 128-D float embedding list with AES-256-GCM.

    Args:
        embedding: list of 128 floats (L2-normalized, from MobileFaceNet)

    Returns:
        (ciphertext, nonce, tag)
        - ciphertext: encrypted bytes (same length as plaintext)
        - nonce: 12-byte random IV (store alongside ciphertext)
        - tag: 16-byte GCM authentication tag (appended by AESGCM, split here for storage)

    Storage note:
        AESGCM.encrypt() returns ciphertext + tag concatenated.
        We split the last 16 bytes as the tag for clean column storage.
    """
    plaintext = json.dumps(embedding, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)   # GCM nonce — must be unique per encryption

    aesgcm = AESGCM(_load_aes_key())
    ct_with_tag = aesgcm.encrypt(nonce, plaintext, associated_data=None)

    # Split ciphertext and 16-byte auth tag
    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]

    logger.debug(f"Embedding encrypted: {len(plaintext)}B plaintext → {len(ciphertext)}B ciphertext")
    return ciphertext, nonce, tag


def decrypt_embedding(ciphertext: bytes, nonce: bytes, tag: bytes) -> list[float]:
    """
    Decrypt and authenticate an AES-256-GCM encrypted embedding.

    Raises:
        cryptography.exceptions.InvalidTag: if ciphertext has been tampered with.
        json.JSONDecodeError: if decrypted data is not valid JSON (should never happen).
    """
    aesgcm = AESGCM(_load_aes_key())
    # Reassemble ciphertext + tag for decryption
    ct_with_tag = ciphertext + tag
    plaintext = aesgcm.decrypt(nonce, ct_with_tag, associated_data=None)
    return json.loads(plaintext.decode("utf-8"))
