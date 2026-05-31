import json
import logging
import requests
from datetime import datetime
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

AWS_BASE_IP = "13.48.24.253"
ATTENDANCE_SERVICE_URL = f"http://{AWS_BASE_IP}:8003"
DEVICE_ID = "saraw-iphone-16"
PRIVATE_KEY_HEX = "ce2630516688e8d76ff661685ce458ff84028278a67f39e3608ecd81b85c57f5"
DEVICE_JWT = "eyJhbGciOiJSUzI1NiIsImtpZCI6Im5oYWktcnMyNTYtMSIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJuaGFpLWF1dGgtc2VydmljZSIsInN1YiI6InNhcmF3LWlwaG9uZS0xNiIsInN1Yl90eXBlIjoiZGV2aWNlIiwianRpIjoiMjQ4NWNjOTQtOWYwMi00YTQzLTk1ZTMtN2JlODI0NzRhNWQ1IiwiaWF0IjoxNzgwMjMyODc0LCJleHAiOjE3ODAyMzQ2NzQsInRva2VuX3R5cGUiOiJhY2Nlc3MiLCJzaXRlX2NvZGUiOiJTSVRFXzEyMyJ9.cQdONYIiLri_6UoGw7kr3N_woZt_mB7PvDixBq2z_4yTQvIfSxKT-PRxlPlrBL47SPNPWAaWqelkDXQZ4OCElLNF2VEdE-kYzJG_OJIWds2TTbqyQI3ONEBITG5PR3J6KfFMHXcF0KC2QNCrqK2N8EFKCJSfOJQCmRXtZwM9-hcSPsL51XBu9F5YbAP0BIyg1yhxu6un_NJ7uZ4UUIskvfAYbdqj_EI3X-pH7HrARSHQriQIB6S8pgduarMbi92Gsbwb5dmLGMnEuN_ubMSvoDADxUFQYS2UY8zo_fBq2_OzpkQ6_R2swOLa5vs922xNJlStWfu2zq7mzUROS1F-Sw"

def canonical_stringify(payload):
    # Sort keys alphabetically and remove spaces
    sorted_items = sorted(payload.items())
    parts = []
    for k, v in sorted_items:
        key_str = json.dumps(k)
        if isinstance(v, bool):
            val_str = "true" if v else "false"
        elif isinstance(v, (int, float)):
            val_str = str(v)
        else:
            val_str = json.dumps(v)
        parts.append(f"{key_str}:{val_str}")
    return "{" + ",".join(parts) + "}"

def run_test_sync():
    logger.info("Starting test sync payload preparation...")
    
    # 1. Construct the payload
    record_id = str(uuid4())
    payload = {
        "confidence": 0.92,
        "id": record_id,
        "liveness_passed": True,
        "liveness_score": 0.88,
        "timestamp_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "worker_id": "NHAI-DEL-1234"
    }
    
    # 2. Canonical serialization
    canonical_str = canonical_stringify(payload)
    logger.info(f"Canonical Payload: {canonical_str}")
    
    # 3. Cryptographic signing with private key
    logger.info("Signing the canonical payload with P-256 private key...")
    try:
        private_value = int(PRIVATE_KEY_HEX, 16)
        private_key = ec.derive_private_key(private_value, ec.SECP256R1())
        
        signature_bytes = private_key.sign(
            canonical_str.encode("utf-8"),
            ec.ECDSA(hashes.SHA256())
        )
        signature_hex = signature_bytes.hex()
        logger.info(f"Generated Signature Hex: {signature_hex}")
    except Exception as e:
        logger.error(f"Failed to sign: {e}")
        return
        
    # 4. Construct complete sync body
    sync_body = {
        "device_id": DEVICE_ID,
        "records": [
            {
                "confidence": payload["confidence"],
                "id": payload["id"],
                "liveness_passed": payload["liveness_passed"],
                "liveness_score": payload["liveness_score"],
                "timestamp_utc": payload["timestamp_utc"],
                "worker_id": payload["worker_id"],
                "signature_hex": signature_hex
            }
        ]
    }
    
    # 5. Send POST to AWS attendance-service
    logger.info(f"Sending POST to {ATTENDANCE_SERVICE_URL}/attendance/sync...")
    headers = {
        "Authorization": f"Bearer {DEVICE_JWT}",
        "Content-Type": "application/json"
    }
    try:
        resp = requests.post(
            f"{ATTENDANCE_SERVICE_URL}/attendance/sync",
            json=sync_body,
            headers=headers
        )
        logger.info(f"HTTP Status: {resp.status_code}")
        logger.info(f"Response Body: {resp.text}")
    except Exception as e:
        logger.error(f"Error during post: {e}")

if __name__ == "__main__":
    run_test_sync()
