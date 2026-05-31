import argparse
import os
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Constants
AWS_BASE_IP = "13.48.24.253"
AUTH_SERVICE_URL = f"http://{AWS_BASE_IP}:8001"
ENROLLMENT_SERVICE_URL = f"http://{AWS_BASE_IP}:8002"
ADMIN_EMAIL = "admin@nhai.gov.in"
ADMIN_PASSWORD = "ChangeMe@2026!"

def login_as_admin():
    """Step 1: Authenticate and get Admin JWT"""
    logger.info(f"Logging in as Admin ({ADMIN_EMAIL}) to get Admin JWT...")
    login_url = f"{AUTH_SERVICE_URL}/auth/admin/login"
    try:
        resp = requests.post(login_url, json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if resp.status_code != 200:
            logger.error(f"Admin login failed: HTTP {resp.status_code} - {resp.text}")
            return None
        
        login_data = resp.json()
        admin_jwt = login_data["access_token"]
        logger.info("Admin login successful. Admin JWT obtained ✓")
        return admin_jwt
    except Exception as e:
        logger.error(f"Error during Admin login: {e}")
        return None

def create_worker_profile(admin_jwt, worker_id, name, department, site_code):
    """Step 2: Create worker metadata profile"""
    logger.info(f"Registering worker profile for ID: {worker_id}...")
    headers = {
        "Authorization": f"Bearer {admin_jwt}",
        "Content-Type": "application/json"
    }
    payload = {
        "worker_id": worker_id,
        "name": name,
        "department": department,
        "site_code": site_code
    }
    url = f"{ENROLLMENT_SERVICE_URL}/enroll/worker"
    try:
        resp = requests.post(url, headers=headers, json=payload)
        if resp.status_code == 201:
            logger.info(f"Successfully created worker profile for {name} ({worker_id})! ✓")
            return True
        elif resp.status_code == 409:
            logger.warning(f"Worker '{worker_id}' already exists in database. Proceeding to face upload.")
            return True
        else:
            logger.error(f"Failed to create worker: HTTP {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Error during worker profile creation: {e}")
        return False

def enroll_face_photo(admin_jwt, worker_id, image_path):
    """Step 3: Upload face photo to extract & encrypt biometric embeddings"""
    logger.info(f"Uploading face image '{image_path}' to extract biometrics for {worker_id}...")
    
    if not os.path.exists(image_path):
        logger.error(f"Image file not found: {image_path}")
        return False
        
    headers = {
        "Authorization": f"Bearer {admin_jwt}",
    }
    url = f"{ENROLLMENT_SERVICE_URL}/enroll/worker/{worker_id}/face"
    
    # Determine correct MIME type
    ext = os.path.splitext(image_path)[1].lower()
    mime_type = "image/jpeg"
    if ext == ".png":
        mime_type = "image/png"
    elif ext == ".webp":
        mime_type = "image/webp"

    try:
        with open(image_path, "rb") as f:
            files = {
                "photo": (os.path.basename(image_path), f, mime_type)
            }
            resp = requests.post(url, headers=headers, files=files)
            
        if resp.status_code == 200:
            result = resp.json()
            logger.info("Biometric enrollment successful! ✓")
            logger.info(f"  • Embedding ID: {result.get('embedding_id')}")
            logger.info(f"  • Face Confidence: {result.get('face_confidence'):.4f}")
            logger.info(f"  • Bounding Box: {result.get('face_bbox')}")
            return True
        else:
            logger.error(f"Biometric extraction failed: HTTP {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Error during face photo enrollment: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="NHAI Biometric Worker Enrollment Tool")
    parser.add_argument("--id", type=str, default="NHAI-DEL-1234", help="Worker ID (Format: NHAI-DEL-XXXX)")
    parser.add_argument("--name", type=str, default="Jane Doe", help="Worker's full name")
    parser.add_argument("--dept", type=str, default="Operations", help="Worker's department")
    parser.add_argument("--site", type=str, default="SITE_123", help="Site Code")
    parser.add_argument("--image", type=str, help="Path to worker's face photo (JPEG/PNG)")
    
    args = parser.parse_args()
    
    admin_jwt = login_as_admin()
    if not admin_jwt:
        logger.error("Authentication failed. Cannot proceed.")
        return
        
    profile_ok = create_worker_profile(
        admin_jwt=admin_jwt,
        worker_id=args.id,
        name=args.name,
        department=args.dept,
        site_code=args.site
    )
    
    if profile_ok and args.image:
        enroll_face_photo(
            admin_jwt=admin_jwt,
            worker_id=args.id,
            image_path=args.image
        )
    elif profile_ok:
        logger.info("\n" + "="*80)
        logger.info("Worker profile is registered but no face photo was provided.")
        logger.info("To upload a face photo and complete biometric enrollment, run:")
        logger.info(f"  python3 enroll_worker.py --id {args.id} --image /path/to/your/face_image.jpg")
        logger.info("="*80 + "\n")

if __name__ == "__main__":
    main()
