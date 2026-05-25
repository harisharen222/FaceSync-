"""
tests/unit/test_jwt_handler.py — Unit tests for RS256 JWT issuance and verification.
"""
import pytest
import time
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# ── Generate a test RSA keypair in-memory ─────────────────────────────────────

def _generate_test_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


_PRIVATE_KEY, _PUBLIC_KEY = _generate_test_keypair()


@pytest.fixture(autouse=True)
def patch_settings():
    """Patch settings to inject test RSA keys for all tests."""
    with patch("app.jwt_handler.settings") as mock_settings:
        mock_settings.JWT_RS256_PRIVATE_KEY = _PRIVATE_KEY
        mock_settings.JWT_RS256_PUBLIC_KEY = _PUBLIC_KEY
        mock_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
        mock_settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS = 30
        mock_settings.JWT_ALGORITHM = "RS256"
        mock_settings.JWT_ISSUER = "nhai-auth-service"
        yield mock_settings


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestAccessTokenCreation:
    def test_create_access_token_returns_token_and_jti(self):
        from app.jwt_handler import create_access_token
        token, jti = create_access_token("ANDROID123", "device")
        assert isinstance(token, str) and len(token) > 20
        assert isinstance(jti, str) and len(jti) == 36  # UUID4

    def test_access_token_is_decodable(self):
        from app.jwt_handler import create_access_token, decode_token
        token, _ = create_access_token("ANDROID123", "device", {"site_code": "NH-44"})
        payload = decode_token(token, "access")
        assert payload.sub == "ANDROID123"
        assert payload.sub_type == "device"
        assert payload.site_code == "NH-44"
        assert payload.token_type == "access"

    def test_admin_access_token_claims(self):
        from app.jwt_handler import create_access_token, decode_token
        token, _ = create_access_token(
            "admin-uuid-123", "admin", {"role": "supervisor", "site_code": "NH-48"}
        )
        payload = decode_token(token, "access")
        assert payload.sub_type == "admin"
        assert payload.role == "supervisor"

    def test_unique_jtis_per_token(self):
        from app.jwt_handler import create_access_token
        _, jti1 = create_access_token("DEV1", "device")
        _, jti2 = create_access_token("DEV1", "device")
        assert jti1 != jti2  # Every token must have a unique JTI


class TestRefreshTokenCreation:
    def test_refresh_token_type_claim(self):
        from app.jwt_handler import create_refresh_token, decode_token
        token, _ = create_refresh_token("admin-uuid", "admin")
        payload = decode_token(token, "refresh")
        assert payload.token_type == "refresh"

    def test_refresh_token_rejected_as_access(self):
        from app.jwt_handler import create_refresh_token, decode_token
        token, _ = create_refresh_token("ANDROID123", "device")
        with pytest.raises(ValueError, match="Expected token_type='access'"):
            decode_token(token, "access")


class TestTokenVerification:
    def test_tampered_token_raises_invalid(self):
        import jwt as pyjwt
        from app.jwt_handler import create_access_token, decode_token
        token, _ = create_access_token("ANDROID123", "device")
        # Tamper with payload
        parts = token.split(".")
        tampered = parts[0] + "." + "dGFtcGVyZWQ" + "." + parts[2]
        with pytest.raises(pyjwt.exceptions.InvalidTokenError):
            decode_token(tampered, "access")

    def test_wrong_key_rejected(self):
        import jwt as pyjwt
        from cryptography.hazmat.primitives.asymmetric import rsa as _rsa
        from cryptography.hazmat.primitives import serialization as _ser
        from app.jwt_handler import decode_token

        # Sign with a completely different private key
        other_private = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_private_pem = other_private.private_bytes(
            _ser.Encoding.PEM, _ser.PrivateFormat.TraditionalOpenSSL, _ser.NoEncryption()
        ).decode()

        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone
        token = pyjwt.encode(
            {"sub": "EVIL", "jti": "x", "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1),
             "iss": "nhai-auth-service", "token_type": "access", "sub_type": "device"},
            other_private_pem, algorithm="RS256"
        )
        with pytest.raises(pyjwt.exceptions.InvalidTokenError):
            decode_token(token, "access")
