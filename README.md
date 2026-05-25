# NHAI Biometric Attendance — Backend Microservices (Hackathon 7.0 Submission)

Offline-first, zero-trust, sub-400ms biometric attendance platform for NHAI field operations.
**Built specifically for NHAI Hackathon 7.0.**

---

## Architecture Phases Completed

- **Phase 1: Zero-Trust Auth Service:** ECDSA P-256 hardware-backed device authentication and RS256 JWTs.
- **Phase 2: Enrollment & Attendance Sync:** Face AI pipeline (YuNet + MobileFaceNet) and Offline ECDSA signature verification with SQS enqueuing for high-throughput sync.
- **Phase 3: OTA Model Delivery:** Delivering lightweight (~2MB) `.tflite` models to edge devices via CloudFront presigned URLs.
- **Phase 4: Audit & Notification (Event-Driven):** EventBridge decoupled architecture logging all actions and alerting on `SpoofingDetected`.
- **Phase 5: Reporting Service (CQRS):** Read-optimized materialized views for fast analytical dashboarding of attendance metrics.

### Quick Start (Local Development)

**Prerequisites:** Docker Desktop, Python 3.11+

#### 1. Generate RS256 keypair for local development

```bash
# Run from services/auth-service/
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem

# Convert to single-line escaped PEM strings and paste into .env
cat private.pem | awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' 
cat public.pem  | awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}'
```

#### 2. Configure environment

```bash
cd services/auth-service
cp .env.example .env
# Edit .env — paste the keypair strings from step 1
```

#### 3. Start all services

```bash
cd infrastructure
docker compose up --build
```

Services will be available at:
- **Auth Service:**  `http://localhost:8001/docs`
- **Enrollment Service:** `http://localhost:8002/docs`
- **Attendance Sync Service:** `http://localhost:8003/docs`
- **Model Delivery Service:** `http://localhost:8004/docs`
- **Audit Service:** `http://localhost:8005/docs`
- **Reporting Service:** `http://localhost:8006/docs`
- **pgAdmin:**      `http://localhost:5050` *(start with `--profile tools`)*
- **LocalStack (SQS/EventBridge/S3):** `http://localhost:4566`

#### 4. Run unit tests

```bash
cd services/auth-service
pip install -r requirements.txt
pytest tests/unit/ -v
```

---

## Project Structure

```
nhai-backend/
├── services/
│   ├── auth-service/           # JWT + ECDSA device auth
│   ├── enrollment-service/     # Face photo → ONNX AI → AES-256-GCM
│   ├── attendance-service/     # Offline sync ingress + Deduplication
│   ├── model-service/          # OTA Model Delivery via S3 Presigned URLs
│   ├── audit-service/          # EventBridge consumer for compliance logging
│   ├── notification-service/   # SQS worker for spoofing alerts
│   └── reporting-service/      # CQRS read-optimized analytics views
│
├── infrastructure/
│   ├── docker-compose.yml      # All services + Postgres + Redis + LocalStack
│   ├── init-db/
│   │   └── 01_create_schemas.sql
│   ├── init-localstack/
│   │   └── setup.sh            # Auto-creates SQS queues, EventBus, S3 bucket
│   └── cdk/                    # Complete AWS CDK IaC (Fargate, ALB, APIGW)
└── README.md
```

---

## API Reference

Base URL (local): `http://localhost:<PORT>`  
Base URL (cloud): `https://<api-id>.execute-api.ap-south-1.amazonaws.com`

### Auth Service (Port 8001)
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/admin/login` | None | Login → RS256 JWT |
| `POST` | `/auth/device/register` | Admin JWT | Register device + ECDSA public key |
| `GET` | `/auth/device/challenge/{id}` | None | Get ECDSA challenge nonce |
| `POST` | `/auth/device/token` | Signed challenge | Issue device JWT |

### Enrollment Service (Port 8002)
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/enroll/worker` | Admin JWT | Create worker record |
| `POST` | `/enroll/worker/{id}/face` | Admin JWT | Upload photo → AI pipeline → AES encrypt |
| `GET` | `/enroll/sync/{device_id}` | Device JWT | Delta pull encrypted embeddings for site |

### Attendance Sync Service (Port 8003)
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/attendance/sync` | Device JWT | Ingest batch of offline ECDSA-signed records |

### Model Delivery Service (Port 8004)
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/models/admin/upload` | Admin JWT | Upload new .tflite to S3 |
| `PATCH`| `/models/admin/rollout/{id}` | Admin JWT | Mark a release as ACTIVE |
| `GET`  | `/models/manifest` | Device JWT | Get presigned URLs for active models |

### Audit Service (Port 8005)
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/audit/logs` | Admin JWT | Search compliance logs (event-sourced) |

### Reporting Service (Port 8006)
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/reports/site/{site_code}/daily` | Admin JWT | Daily aggregated attendance metrics |
| `GET` | `/reports/worker/{worker_id}/monthly` | Admin JWT | Monthly attendance days for a worker |

---

## Security & Hackathon 7.0 Alignment

**Zero-Trust Offline Authentication:**
- Devices generate an ECDSA P-256 keypair locally in the TEE.
- Attendance records (including liveness score) are **signed cryptographically** by the device while offline.
- When internet is restored, the `Attendance Sync Service` verifies this signature against the public key registered on the server. If spoofing is detected, it emits a `SpoofingDetected` event via EventBridge.

**Edge AI Lightweight Integration:**
- The `Model Delivery Service` supports OTA updates of highly compressed `.tflite` models (<5MB total for YuNet + MobileFaceNet).
- Keeping models out of the React Native bundle satisfies the Hackathon's strict <20MB footprint requirement.

**Scalable Sync & Purge Mechanism:**
- The `/attendance/sync` ingress uses an **SQS buffer**. When a site restores network connectivity, thousands of pending records might hit the server simultaneously. The ALB + API Gateway route traffic to Fargate, which pushes directly to SQS, allowing background workers to deduplicate and batch-insert into PostgreSQL gracefully without overwhelming the DB.
