import requests
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Constants
AWS_BASE_IP = "13.48.24.253"
AUTH_SERVICE_URL = f"http://{AWS_BASE_IP}:8001"
AUDIT_SERVICE_URL = f"http://{AWS_BASE_IP}:8005"
ADMIN_EMAIL = "admin@nhai.gov.in"
ADMIN_PASSWORD = "ChangeMe@2026!"

def run_audit_fetch():
    logger.info("Starting audit compliance logs fetch from AWS...")
    
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

    # ── Step 2: Fetch Audit Logs ─────────────────────────────────────────────
    logger.info("Step 2: Requesting compliance logs from AWS Audit Service...")
    audit_url = f"{AUDIT_SERVICE_URL}/audit/logs"
    headers = {
        "Authorization": f"Bearer {admin_jwt}",
        "Content-Type": "application/json"
    }
    try:
        resp = requests.get(audit_url, headers=headers)
        if resp.status_code != 200:
            logger.error(f"Audit log fetch failed: HTTP {resp.status_code} - {resp.text}")
            return
        
        logs = resp.json()
        logger.info(f"Successfully retrieved {len(logs)} audit entries from AWS!")
        
        print("\n" + "="*80)
        print("📋 LIVE AWS AUDIT COMPLIANCE VAULT 📋")
        print("="*80)
        
        if not logs:
            print("No audit logs found (Pristine database).")
        else:
            for idx, entry in enumerate(logs, 1):
                print(f"\nEntry #{idx}:")
                print(f"  • Event ID:     {entry.get('event_id')}")
                print(f"  • Detail Type:  {entry.get('detail_type')}")
                print(f"  • Source:       {entry.get('source')}")
                print(f"  • Timestamp:    {entry.get('timestamp_utc')}")
                print(f"  • Payload Detail:")
                detail = entry.get("detail", {})
                print(json.dumps(detail, indent=4))
                print("-"*80)
        
        print("\n" + "="*80 + "\n")
        
    except Exception as e:
        logger.error(f"Error fetching audit logs: {e}")

if __name__ == "__main__":
    run_audit_fetch()
