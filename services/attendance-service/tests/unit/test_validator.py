"""
tests/unit/test_validator.py
"""
import pytest
from uuid import uuid4
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization

from app.schemas import AttendanceRecordPayload
from app.validator import verify_ecdsa_signature, compute_dedup_hash

@pytest.fixture
def keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    
    pub_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    
    return private_key, pub_pem

@pytest.fixture
def valid_record():
    return AttendanceRecordPayload(
        id=uuid4(),
        worker_id="NHAI-DEL-0419",
        timestamp_utc=datetime.now(tz=timezone.utc),
        confidence=0.95,
        liveness_score=0.92,
        liveness_passed=True,
        signature_hex="dummy"  # replaced during test
    )

def test_verify_valid_signature(keypair, valid_record):
    private_key, pub_pem = keypair
    
    # 1. Device signs the payload
    payload_json = valid_record.signature_payload()
    signature = private_key.sign(
        payload_json.encode('utf-8'),
        ec.ECDSA(hashes.SHA256())
    )
    valid_record.signature_hex = signature.hex()
    
    # 2. Server verifies
    assert verify_ecdsa_signature(
        pub_pem,
        valid_record.signature_payload(),
        valid_record.signature_hex
    ) is True

def test_verify_tampered_payload(keypair, valid_record):
    private_key, pub_pem = keypair
    
    payload_json = valid_record.signature_payload()
    signature = private_key.sign(
        payload_json.encode('utf-8'),
        ec.ECDSA(hashes.SHA256())
    )
    valid_record.signature_hex = signature.hex()
    
    # Manually tamper with the record data
    valid_record.confidence = 0.99
    
    # Server verification should fail because the payload JSON changed
    assert verify_ecdsa_signature(
        pub_pem,
        valid_record.signature_payload(),
        valid_record.signature_hex
    ) is False

def test_dedup_hash_stability():
    hash1 = compute_dedup_hash("NHAI-01", "DEV-01", "2024-05-20T10:00:00Z")
    hash2 = compute_dedup_hash("NHAI-01", "DEV-01", "2024-05-20T10:00:00Z")
    hash3 = compute_dedup_hash("NHAI-01", "DEV-01", "2024-05-20T10:00:01Z")
    
    assert hash1 == hash2
    assert hash1 != hash3
