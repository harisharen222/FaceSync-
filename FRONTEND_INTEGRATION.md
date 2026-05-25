# Frontend Integration Guide (React Native)

Welcome, Frontend Developers! This document outlines how the React Native "Datalake 3.0" mobile application should integrate with the NHAI Biometric Attendance backend. 

Because the system operates in **zero-network zones**, the mobile app carries a lot of responsibility. It must securely verify faces offline, cryptographically sign attendance records to prove authenticity, and sync data when the internet returns.

---

## 1. Security & Device Registration

The backend employs a **Zero-Trust architecture**. The backend does not blindly trust attendance records; the mobile app must cryptographically sign them using a hardware-backed private key.

### Step 1.1: Key Generation
On the first app launch, use a React Native security library (like `react-native-keychain` or `react-native-biometrics`) to generate an **ECDSA P-256 keypair** entirely within the device's Trusted Execution Environment (TEE) / Secure Enclave.
- Keep the **private key** securely on the device (never transmit it).
- Extract the **public key** in PEM format.

### Step 1.2: Device Registration
Register the device with the backend (requires an Admin JWT):
- **POST** `/auth/device/register`
- **Body:** `{ "device_id": "<UUID>", "public_key_pem": "<PEM string>", "site_code": "SITE_123" }`

### Step 1.3: Fetching the Device JWT
To interact with device endpoints (like syncing attendance), the device needs a JWT. Because the backend doesn't know the device's private key, it issues a challenge:
1. **GET** `/auth/device/challenge/{device_id}` -> Returns a random `nonce` string.
2. App signs the `nonce` using the local ECDSA private key.
3. **POST** `/auth/device/token`
   - **Body:** `{ "device_id": "<UUID>", "nonce": "<nonce>", "signature_hex": "<signed_nonce_hex>" }`
4. Backend verifies the signature against the public key and returns the JWT.

---

## 2. OTA Model Updates (Keeping the App < 20MB)

Do not bundle the AI models (YuNet and MobileFaceNet) in the `.apk` or `.ipa` to keep the app size small. Instead, fetch them dynamically.

1. **GET** `/models/manifest` (Requires Device JWT)
   - Returns a list of active models and CloudFront pre-signed download URLs.
2. Download the `.tflite` files to the app's local document directory.
3. Use a React Native TFLite library (like `react-native-fast-tflite`) to load the models into memory.
4. **POST** `/models/status` to report back to the backend that the device has successfully downloaded and loaded the models.

---

## 3. Worker Enrollment & Syncing

### Enrolling a New Worker (Admin Only)
Supervisors with internet connectivity can enroll new workers.
1. **POST** `/enroll/worker` -> Creates the worker profile.
2. **POST** `/enroll/worker/{id}/face` -> Upload a clear, cropped image (multipart/form-data) of the worker's face. The backend runs the heavy AI pipeline, extracts the 128D embedding, and encrypts it using AES-256-GCM.

### Syncing Embeddings Down to the Device
Before going offline into the field, the device must pull down the latest face embeddings for its specific site.
1. **GET** `/enroll/sync/{device_id}` (Requires Device JWT)
   - Returns an array of workers and their AES-encrypted face embeddings.
2. The device decrypts these embeddings using a symmetric key (handled via AWS Secrets Manager or secure local vault) and stores them in the local SQLite database.

---

## 4. The Offline Attendance Flow (Zero-Network)

When the field supervisor is out in a remote location with no internet, the app functions entirely offline.

1. **Camera Feed:** Pass the camera frames to the downloaded YuNet `.tflite` model to detect the face bounding box.
2. **Liveness Detection:** Implement basic UI challenges (e.g., "Please smile" or "Turn head left").
3. **Face Recognition:** Pass the cropped face to the MobileFaceNet `.tflite` model to extract the 128D embedding.
4. **Matching:** Compare this embedding (using Cosine Similarity) against the decrypted SQLite database of enrolled workers. If similarity > 0.65, it's a match.
5. **Construct the Record:**
   ```json
   {
     "id": "uuid-for-record",
     "worker_id": "W123",
     "timestamp_utc": "2026-05-25T10:00:00Z",
     "confidence": 0.92,
     "liveness_score": 0.88,
     "liveness_passed": true
   }
   ```
6. **Cryptographic Signing:** Serialize that JSON to a string, and sign it using the device's ECDSA private key.
7. **Store in SQLite:** Save the JSON payload and the `signature_hex` in a local SQLite `pending_sync` table.

---

## 5. Sync & Purge Mechanism

When the device detects a stable internet connection (WiFi or Cellular), it must flush the `pending_sync` SQLite table to the backend.

1. **Query** the local SQLite table for all pending records.
2. **POST** `/attendance/sync` (Requires Device JWT)
   - **Body:**
     ```json
     {
       "device_id": "D-123",
       "records": [
         {
           "id": "uuid-for-record",
           "worker_id": "W123",
           ...
           "signature_hex": "abcd1234efgh5678..."
         }
       ]
     }
     ```
3. The backend returns a response indicating which records were successfully ingested.
4. **Purge:** Delete the successfully ingested records from the local SQLite database to free up space.

---

## Backend Services Overview
If you are running the backend locally via Docker Compose (`docker compose up`), here are the relevant API swagger docs:

- **Auth & Device Registration:** `http://localhost:8001/docs`
- **Worker Enrollment:** `http://localhost:8002/docs`
- **Attendance Sync:** `http://localhost:8003/docs`
- **OTA Models:** `http://localhost:8004/docs`
