"""
tests/unit/test_encryption.py
"""
import pytest
from app.encryption import encrypt_embedding, decrypt_embedding, _load_aes_key
from cryptography.exceptions import InvalidTag
import os
from unittest.mock import patch

@pytest.fixture(autouse=True)
def mock_aes_key():
    with patch("app.encryption.settings") as mock_settings:
        mock_settings.USE_AWS_SECRETS = False
        # Use a dummy 32-byte hex key
        mock_settings.AES_EMBEDDING_KEY_HEX = os.urandom(32).hex()
        # Clear cached key to force reload
        import app.encryption as enc
        enc._aes_key = None
        yield mock_settings

def test_encrypt_decrypt_roundtrip():
    # 128-D vector
    plaintext = [0.5] * 128
    
    ct, nonce, tag = encrypt_embedding(plaintext)
    
    assert len(nonce) == 12
    assert len(tag) == 16
    assert len(ct) > 0
    
    decrypted = decrypt_embedding(ct, nonce, tag)
    assert decrypted == plaintext

def test_tampered_ciphertext_fails():
    plaintext = [0.5] * 128
    ct, nonce, tag = encrypt_embedding(plaintext)
    
    # Tamper with ciphertext
    tampered_ct = bytearray(ct)
    tampered_ct[0] ^= 0xFF
    
    with pytest.raises(InvalidTag):
        decrypt_embedding(bytes(tampered_ct), nonce, tag)

def test_tampered_tag_fails():
    plaintext = [0.5] * 128
    ct, nonce, tag = encrypt_embedding(plaintext)
    
    tampered_tag = bytearray(tag)
    tampered_tag[0] ^= 0xFF
    
    with pytest.raises(InvalidTag):
        decrypt_embedding(ct, nonce, bytes(tampered_tag))
