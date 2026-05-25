"""
tests/unit/test_device_auth.py — Unit tests for ECDSA P-256 device authentication.
"""
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_ec_keypair():
    """Generate a fresh P-256 keypair for testing."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_key, private_pem, public_pem


def _sign_message(private_key: ec.EllipticCurvePrivateKey, message: str) -> str:
    """Sign a message string with an ECDSA P-256 private key. Returns hex DER."""
    signature = private_key.sign(message.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    return signature.hex()


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestLoadEcPublicKey:
    def test_valid_p256_key_accepted(self):
        from app.device_auth import load_ec_public_key
        _, _, public_pem = _generate_ec_keypair()
        key = load_ec_public_key(public_pem)
        assert isinstance(key, ec.EllipticCurvePublicKey)
        assert isinstance(key.curve, ec.SECP256R1)

    def test_invalid_pem_raises_value_error(self):
        from app.device_auth import load_ec_public_key
        with pytest.raises(ValueError, match="Failed to parse public key PEM"):
            load_ec_public_key("not-a-pem")

    def test_rsa_key_rejected(self):
        from app.device_auth import load_ec_public_key
        from cryptography.hazmat.primitives.asymmetric import rsa
        rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        rsa_pem = rsa_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
        with pytest.raises(ValueError, match="not an EC public key"):
            load_ec_public_key(rsa_pem)


class TestVerifyEcdsaSignature:
    def test_valid_signature_returns_true(self):
        from app.device_auth import verify_ecdsa_signature
        private_key, _, public_pem = _generate_ec_keypair()
        challenge = "abc123deadbeef"
        sig_hex = _sign_message(private_key, challenge)
        assert verify_ecdsa_signature(public_pem, challenge, sig_hex) is True

    def test_wrong_message_returns_false(self):
        from app.device_auth import verify_ecdsa_signature
        private_key, _, public_pem = _generate_ec_keypair()
        sig_hex = _sign_message(private_key, "original_message")
        assert verify_ecdsa_signature(public_pem, "different_message", sig_hex) is False

    def test_wrong_key_returns_false(self):
        from app.device_auth import verify_ecdsa_signature
        private_key1, _, _ = _generate_ec_keypair()
        _, _, public_pem2 = _generate_ec_keypair()  # Different keypair
        challenge = "some_challenge"
        sig_hex = _sign_message(private_key1, challenge)
        # Signature made with key1 must NOT verify against key2
        assert verify_ecdsa_signature(public_pem2, challenge, sig_hex) is False

    def test_malformed_signature_returns_false(self):
        from app.device_auth import verify_ecdsa_signature
        _, _, public_pem = _generate_ec_keypair()
        assert verify_ecdsa_signature(public_pem, "challenge", "deadbeef00") is False

    def test_empty_signature_returns_false(self):
        from app.device_auth import verify_ecdsa_signature
        _, _, public_pem = _generate_ec_keypair()
        assert verify_ecdsa_signature(public_pem, "challenge", "") is False
