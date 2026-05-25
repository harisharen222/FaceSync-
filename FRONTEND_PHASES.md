# Frontend Implementation Roadmap (React Native)

To align with the backend's architecture and the NHAI Hackathon 7.0 constraints, the frontend development should be executed in the following structured phases.

---

## Phase 1: Security Foundation & Registration
**Goal:** Establish the zero-trust cryptographic foundation and connect the device to the backend.

- [ ] **Setup React Native:** Initialize a bare React Native project (to avoid Expo constraints with heavy native AI modules later).
- [ ] **Cryptographic Key Generation:** Implement `react-native-biometrics` or `react-native-crypto` to generate an ECDSA P-256 keypair on the device.
- [ ] **Secure Storage:** Ensure the private key never leaves the device's Secure Enclave/Keystore.
- [ ] **Registration UI:** Build a simple screen for the Supervisor to enter the Site Code and trigger `POST /auth/device/register` with the generated public key.
- [ ] **Authentication Flow:** Implement the Challenge-Response cycle (`GET /auth/device/challenge` -> Sign -> `POST /auth/device/token`) to retrieve and store the `DEVICE_JWT`.

---

## Phase 2: AI Model Integration (OTA)
**Goal:** Satisfy the < 20MB app size constraint by pulling AI models from the cloud dynamically.

- [ ] **Manifest Fetching:** Call `GET /models/manifest` to retrieve CloudFront URLs for `yunet.tflite` and `mobilefacenet.tflite`.
- [ ] **File Download Manager:** Use `react-native-fs` (RNFS) to download these files to the local document directory, tracking download progress.
- [ ] **TFLite Initialization:** Integrate `react-native-fast-tflite` (or similar C++ JSI based library for high performance) and load the downloaded `.tflite` files into memory.
- [ ] **Status Reporting:** Ping `POST /models/status` to notify the backend that the device is ready for inference.

---

## Phase 3: Supervisor Admin Capabilities
**Goal:** Allow authorized supervisors to enroll new field workers from the mobile app.

- [ ] **Supervisor Login:** UI for the supervisor to login (`POST /auth/admin/login`) and retrieve an `ADMIN_JWT`.
- [ ] **Worker Enrollment Form:** UI to input a worker's details (Name, Department, Site Code) hitting `POST /enroll/worker`.
- [ ] **Face Capture for Enrollment:** Access the camera, capture a clear face photo, and upload it as `multipart/form-data` to `POST /enroll/worker/{id}/face`.
- [ ] **Syncing Roster:** Call `GET /enroll/sync/{device_id}` to pull down the list of enrolled workers and their AES-encrypted 128D embeddings for offline matching.
- [ ] **Local DB Setup:** Initialize `react-native-sqlite-storage`. Create a table to store the decrypted worker profiles and embeddings.

---

## Phase 4: The Offline Camera & AI Pipeline
**Goal:** Build the core zero-network biometric attendance scanner (Sub-1 second response).

- [ ] **Camera Integration:** Integrate `react-native-vision-camera` for real-time frame processing via frame processors.
- [ ] **Face Detection (YuNet):** Run the YuNet model on the camera frames to draw bounding boxes around faces.
- [ ] **Liveness Detection:** Implement UI prompts (e.g., "Blink your eyes", "Turn head left") and verify them using simple frame comparisons or a secondary liveness model to prevent spoofing.
- [ ] **Face Recognition (MobileFaceNet):** Crop the detected face, pass it to MobileFaceNet, and extract the 128D array.
- [ ] **Cosine Similarity Matching:** Write a fast JavaScript (or JSI C++) function to compare the real-time 128D array against the SQLite database of embeddings. Threshold > 0.65 = Match.

---

## Phase 5: Offline Storage & Async Syncing
**Goal:** Securely record attendance offline and flush to the backend when internet is restored.

- [ ] **Record Construction:** Upon a successful match, generate the JSON payload containing the timestamp, liveness score, and worker ID.
- [ ] **Payload Signing:** Implement the canonical serialization `JSON.stringify(payload, Object.keys(payload).sort())` and sign it using the ECDSA private key.
- [ ] **Offline Queue:** Save the JSON payload and the `signature_hex` to a `pending_sync` SQLite table.
- [ ] **Network Listener:** Use `@react-native-community/netinfo` to listen for network restoration.
- [ ] **Batch Syncing:** When online, read the `pending_sync` table and `POST /attendance/sync`.
- [ ] **Purge Mechanism:** Upon a `200 OK` response from the backend, `DELETE` the successfully synced records from SQLite.
