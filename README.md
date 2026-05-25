# NHAI Biometric Attendance — Backend Microservices

Offline-first, zero-trust, sub-400ms biometric attendance platform for NHAI field operations.

---

## Phase 1, 2, & 3 — Core Architecture

Phase 1 built the zero-trust Auth Service. 
Phase 2 added the Enrollment Service (face AI pipeline) and Attendance Sync Service (offline ECDSA verification + SQS queuing).
Phase 3 added the Model Delivery Service (OTA TFLite updates via CloudFront presigned URLs).

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
│   ├── auth-service/           # Phase 1: JWT + ECDSA device auth
│   │   └── ...                 # (see phase 1 structure)
│   │
│   ├── enrollment-service/     # Phase 2: Face photo → ONNX AI → AES-256-GCM
│   │   ├── app/
│   │   │   ├── pipeline.py     # YuNet + alignment + CLAHE + MobileFaceNet
│   │   │   ├── onnx_runner.py  # CPU inference wrappers
│   │   │   ├── encryption.py   # AES-256-GCM embedding encryption
│   │   │   └── routes/         # POST /enroll/worker/{id}/face, GET /enroll/sync
│   │   └── Dockerfile
│   │
│   └── attendance-service/     # Phase 2: Offline sync ingress
│       ├── app/
│       │   ├── validator.py    # ECDSA signature verification + Deduplication
│       │   ├── sqs_producer.py # Async enqueuing to SQS
│       │   ├── sqs_consumer.py # Background worker (SQS → Postgres + EventBridge)
│       │   └── routes/         # POST /attendance/sync
│       └── Dockerfile
│
│   └── model-service/          # Phase 3: OTA Model Delivery
│       ├── app/
│       │   ├── s3_client.py    # Boto3 client for uploads & Presigned URLs
│       │   └── routes/         # Admin upload + Device manifest
│       └── Dockerfile
│
├── infrastructure/
│   ├── docker-compose.yml      # All services + Postgres + Redis + LocalStack
│   ├── init-db/
│   │   └── 01_create_schemas.sql
│   ├── init-localstack/
│   │   └── setup.sh            # Auto-creates SQS queue, EventBridge bus, S3 bucket
│   └── cdk/
│       ├── app.py
│       ├── network_stack.py
│       ├── secrets_stack.py
│       ├── rds_stack.py
│       ├── elasticache_stack.py
│       ├── s3_stack.py         # Model bucket + CloudFront OAC
│       ├── sqs_stack.py        # Standard Queue + DLQ
│       ├── eventbridge_stack.py# Custom Event Bus
│       ├── ecs_stack.py        # Fargate tasks (Auth, Enroll, Att, Model)
│       └── apigw_stack.py      # HTTP API → ALB
└── README.md
```

---

## Auth Service API Reference

Base URL (local): `http://localhost:8001`  
Base URL (cloud): `https://<api-id>.execute-api.ap-south-1.amazonaws.com`

### Admin Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/admin/login` | None | Login → RS256 JWT |
| `POST` | `/auth/admin` | Superadmin JWT | Create admin account |
| `GET` | `/auth/admin/me` | Admin JWT | Own profile |

### Device Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/device/register` | Admin JWT | Register device + ECDSA public key |
| `GET` | `/auth/device/challenge/{id}` | None | Get ECDSA challenge nonce |
| `POST` | `/auth/device/token` | ECDSA signed challenge | Issue device JWT |
| `GET` | `/auth/device/{id}/pubkey` | Internal API key | Fetch device public key |

### Token Endpoints (Auth Service)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/token/refresh` | Refresh token | Rotate access token |
| `POST` | `/auth/token/revoke` | Access token | Blacklist a token |
| `GET` | `/auth/token/jwks` | None | RS256 public key (JWKS format) |

### Enrollment Service

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/enroll/worker` | Admin JWT | Create worker record |
| `POST` | `/enroll/worker/{id}/face` | Admin JWT | Upload photo → AI pipeline → AES encrypt |
| `GET` | `/enroll/sync/{device_id}` | Device JWT | Delta pull encrypted embeddings for site |

### Attendance Sync Service

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/attendance/sync` | Device JWT | Ingest batch of offline ECDSA-signed records |
| `GET` | `/attendance/worker/{id}` | Admin JWT | Query attendance history for a worker |
| `GET` | `/attendance/site/{code}` | Admin JWT | Query attendance history for a site |

### Model Delivery Service (OTA)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/models/admin/upload` | Admin JWT | Upload new .tflite to S3 |
| `PATCH` | `/models/admin/rollout/{id}` | Admin JWT | Mark a release as ACTIVE |
| `GET` | `/models/manifest` | Device JWT | Get presigned URLs for active models |
| `POST` | `/models/status` | Device JWT | Report successfully loaded models |

---

## AWS Deployment

```bash
# Install CDK dependencies
cd infrastructure/cdk
pip install aws-cdk-lib constructs

# Bootstrap CDK (once per account/region)
cdk bootstrap aws://YOUR_ACCOUNT_ID/ap-south-1

# Synthesize CloudFormation templates
cdk synth --context env=staging

# Deploy Phase 1 stacks
cdk deploy --all --context env=staging --require-approval never

# After deploy: populate RS256 keys in Secrets Manager
aws secretsmanager put-secret-value \
  --secret-id nhai/staging/rs256-keypair \
  --secret-string "{\"private_key\": \"$(cat private.pem)\", \"public_key\": \"$(cat public.pem)\"}"
```

---

## Security Architecture

```
Internet
   │ HTTPS
   ▼
API Gateway (TLS termination)
   │ VPC Link (private)
   ▼
Internal ALB (private subnet)
   │ HTTP
   ▼
ECS Fargate Task (private subnet)
  ├── RS256 private key  → AWS Secrets Manager
  ├── Token blacklist    → ElastiCache Redis (isolated subnet, TLS)
  └── Auth DB            → RDS PostgreSQL (isolated subnet, encrypted)
```

**Zero-trust principles applied:**
- Device authentication via ECDSA P-256 challenge-response (private key never leaves TEE)
- RS256 JWTs — Auth Service holds private key; all others verify with public key only
- Token blacklisting with dual-write (Redis fast-path + PostgreSQL durability)
- Least-privilege IAM task roles (each service reads only its own secrets)
- All DB/Redis in isolated subnets with no internet access

---

## Upcoming Phases

| Phase | Services |
|---|---|
| **Phase 4** | Audit & Security Service + Notification Service |
| **Phase 5** | Reporting Service |
| **Phase 6** | CI/CD pipelines + full CDK deploy |
