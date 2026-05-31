import requests
import json
import logging
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Constants
AWS_BASE_IP = "13.48.24.253"
AUTH_SERVICE_URL = f"http://{AWS_BASE_IP}:8001"
ADMIN_EMAIL = "admin@nhai.gov.in"
ADMIN_PASSWORD = "ChangeMe@2026!"
DEVICE_ID = "saraw-iphone-16"
SITE_CODE = "SITE_123"

# Keypair generated for the device
PRIVATE_KEY_HEX = "ce2630516688e8d76ff661685ce458ff84028278a67f39e3608ecd81b85c57f5"
PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEEEYOhX0a+UbEJ7CcYoj/z9JiiWPB
TGuUUglTR+THtq5zgbFtHy0R6zTBo0Tqwh8s7R27TEYGvERs9DMrlK6e9g==
-----END PUBLIC KEY-----"""

def run_registration_pipeline():
    logger.info("Starting AWS Device Registration and Challenge-Response flow...")
    
    # ── Step 1: Login as Admin to get Admin JWT ───────────────────────────────
    logger.info(f"Step 1: Logging in as Admin ({ADMIN_EMAIL}) to get Admin JWT...")
    login_url = f"{AUTH_SERVICE_URL}/auth/admin/login"
    try:
        resp = requests.post(login_url, json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if resp.status_code != 200:
            logger.error(f"Admin login failed: HTTP {resp.status_code} - {resp.text}")
            return
        
        login_data = resp.json()
        admin_jwt = login_data["access_token"]
        logger.info("Admin login successful. Admin JWT obtained ✓")
    except Exception as e:
        logger.error(f"Error during Admin login: {e}")
        return

    # ── Step 2: Register Device ──────────────────────────────────────────────
    logger.info(f"Step 2: Registering device '{DEVICE_ID}' with the public key on AWS...")
    register_url = f"{AUTH_SERVICE_URL}/auth/device/register"
    headers = {
        "Authorization": f"Bearer {admin_jwt}",
        "Content-Type": "application/json"
    }
    register_payload = {
        "device_id": DEVICE_ID,
        "public_key_pem": PUBLIC_KEY_PEM,
        "site_code": SITE_CODE
    }
    try:
        resp = requests.post(register_url, json=register_payload, headers=headers)
        if resp.status_code == 409:
            logger.warning("Device already registered on the server. Proceeding to challenge flow...")
        elif resp.status_code not in (200, 201):
            logger.error(f"Device registration failed: HTTP {resp.status_code} - {resp.text}")
            return
        else:
            logger.info(f"Device '{DEVICE_ID}' successfully registered ✓")
    except Exception as e:
        logger.error(f"Error during Device registration: {e}")
        return

    # ── Step 3: Get ECDSA Challenge Nonce ─────────────────────────────────────
    logger.info("Step 3: Fetching cryptographic challenge nonce from AWS...")
    challenge_url = f"{AUTH_SERVICE_URL}/auth/device/challenge/{DEVICE_ID}"
    try:
        resp = requests.get(challenge_url)
        if resp.status_code != 200:
            logger.error(f"Challenge request failed: HTTP {resp.status_code} - {resp.text}")
            return
        
        challenge_data = resp.json()
        challenge_nonce = challenge_data["challenge"]
        logger.info(f"Obtained challenge nonce: {challenge_nonce} ✓")
    except Exception as e:
        logger.error(f"Error fetching challenge: {e}")
        return

    # ── Step 4: Sign the Challenge locally with ECDSA Private Key ──────────────
    logger.info("Step 4: Signing the challenge nonce locally using the ECDSA Private Key...")
    try:
        # Load local private key
        private_value = int(PRIVATE_KEY_HEX, 16)
        private_key = ec.derive_private_key(private_value, ec.SECP256R1())
        
        # Sign the raw challenge string (UTF-8 encoded) using ECDSA + SHA-256
        message_bytes = challenge_nonce.encode("utf-8")
        signature_bytes = private_key.sign(message_bytes, ec.ECDSA(hashes.SHA256()))
        signature_hex = signature_bytes.hex()
        logger.info(f"Challenge signed successfully. Signature Hex: {signature_hex} ✓")
    except Exception as e:
        logger.error(f"Error signing challenge: {e}")
        return

    # ── Step 5: Get Device JWT ────────────────────────────────────────────────
    logger.info("Step 5: Exchanging signed challenge for Device JWT on AWS...")
    token_url = f"{AUTH_SERVICE_URL}/auth/device/token"
    token_payload = {
        "device_id": DEVICE_ID,
        "challenge": challenge_nonce,
        "signature_hex": signature_hex
    }
    try:
        resp = requests.post(token_url, json=token_payload)
        if resp.status_code != 200:
            logger.error(f"Failed to obtain Device JWT: HTTP {resp.status_code} - {resp.text}")
            return
        
        token_data = resp.json()
        device_jwt = token_data["access_token"]
        logger.info("Device JWT successfully issued by AWS Auth Service ✓")
        
        print("\n" + "="*80)
        print("🎉 DEVICE REGISTRATION COMPLETED SUCCESSFULLY! 🎉")
        print(f"Device ID:  {DEVICE_ID}")
        print(f"Device JWT: {device_jwt}")
        print("="*80 + "\n")
        
        return device_jwt
    except Exception as e:
        logger.error(f"Error fetching Device JWT: {e}")
        return None

if __name__ == "__main__":
    run_registration_pipeline()
