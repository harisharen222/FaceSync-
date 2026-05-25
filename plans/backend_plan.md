# NHAI Biometric Attendance — BACKEND PLAN
### AWS Cloud Infrastructure + REST API

---

## Overview

The backend is a **serverless AWS architecture** that receives, validates, stores, and reports verified biometric attendance records pushed from the mobile app when connectivity is restored. It also hosts and version-controls the quantized TFLite model weights for OTA (Over-The-Air) updates.

```
┌───────────────────────────────────────────────────────┐
│               MOBILE APP (Offline Queue)              │
│           Signed + AES-256 Encrypted Payload          │
└───────────────────────┬───────────────────────────────┘
                        │ HTTPS POST (on network restore)
                        ▼
┌───────────────────────────────────────────────────────┐
│             AWS API GATEWAY (REST)                    │
│         /attendance  /enroll  /model  /report         │
└──────┬─────────────────────┬─────────────────────────┘
       │                     │
       ▼                     ▼
┌──────────────┐     ┌────────────────────┐
│  AWS Lambda  │     │   AWS Lambda       │
│  (Sync &     │     │   (Admin/Report    │
│  Validate)   │     │    Generator)      │
└──────┬───────┘     └────────┬───────────┘
       │                      │
       ▼                      ▼
┌──────────────┐     ┌────────────────────┐
│  DynamoDB    │     │   S3 Bucket        │
│  Attendance  │     │   Model Weights +  │
│  Records     │     │   Reports Storage  │
└──────────────┘     └────────────────────┘
       │
       ▼
┌──────────────────┐
│  CloudWatch      │
│  Monitoring +    │
│  SNS Alerts      │
└──────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Cloud Provider | AWS |
| API Layer | AWS API Gateway (REST) |
| Compute | AWS Lambda (Python 3.11) |
| Database | AWS DynamoDB (NoSQL, on-demand billing) |
| File Storage | AWS S3 |
| Auth | AWS Cognito (admin) + HMAC token validation (device) |
| Monitoring | AWS CloudWatch + SNS Email Alerts |
| IaC | AWS CDK (Python) — deployable in one command |
| Local Dev | LocalStack (offline AWS emulator for testing) |

---

## Phase 1: Core Infrastructure Setup (AWS CDK)

**Goal:** Define and deploy all cloud resources as code.

### 1.1 Initialize CDK Project
```bash
mkdir nhai-backend && cd nhai-backend
pip install aws-cdk-lib constructs
cdk init app --language=python
```

### 1.2 DynamoDB Tables

#### Table 1: `nhai_attendance_records`
Stores verified attendance records pushed from devices.

| Attribute | Type | Role |
|---|---|---|
| `worker_id` | String | **Partition Key (PK)** |
| `timestamp` | String (ISO-8601) | **Sort Key (SK)** |
| `device_id` | String | Which field terminal submitted |
| `match_score` | Number | Cosine similarity score at auth |
| `liveness_passed` | Boolean | Active + Passive FAS result |
| `signature` | String | SHA-256 HMAC from device Keystore |
| `site_code` | String | Highway site location code |
| `sync_received_at` | String | Server-side timestamp on receipt |
| `status` | String | `VERIFIED` / `FLAGGED` |

**GSI (Global Secondary Index):**
- `site_code-timestamp-index` → fetch all workers at a site between two timestamps.

#### Table 2: `nhai_worker_profiles`
Stores enrolled worker metadata (NOT the embedding — that stays on device).

| Attribute | Type | Role |
|---|---|---|
| `worker_id` | String | **Partition Key** |
| `name` | String | Full name |
| `department` | String | |
| `site_code` | String | Current site assignment |
| `enrolled_at` | String | |
| `model_version` | String | TFLite version at enrollment time |
| `active` | Boolean | Admin can deactivate remotely |

#### Table 3: `nhai_model_registry`
Tracks published TFLite model versions for OTA updates.

| Attribute | Type | Role |
|---|---|---|
| `model_name` | String | **PK** e.g. `mobilefacenet_int8` |
| `version` | String | **SK** e.g. `v2.1.0` |
| `s3_key` | String | Path to `.tflite` file in S3 |
| `checksum_sha256` | String | Integrity verification hash |
| `release_notes` | String | |
| `is_latest` | Boolean | |

---

## Phase 2: Lambda Functions

**Goal:** Implement all business logic as serverless Python Lambda functions.

### 2.1 `POST /attendance/sync` — Attendance Sync Handler
**Trigger:** Mobile app sends a batch of encrypted + signed logs when online.

```python
# lambda/sync_attendance.py

import json
import hmac
import hashlib
import boto3
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('nhai_attendance_records')

SHARED_HMAC_KEY = get_secret('nhai/device_hmac_key')  # From AWS Secrets Manager

def handler(event, context):
    body = json.loads(event['body'])
    records = body.get('records', [])
    
    results = []
    for record in records:
        payload = record['payload']
        received_sig = record['signature']
        
        # Step 1: Verify HMAC-SHA256 Signature (non-repudiation check)
        expected_sig = hmac.new(
            SHARED_HMAC_KEY.encode(), 
            json.dumps(payload, sort_keys=True).encode(), 
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(expected_sig, received_sig):
            results.append({'worker_id': payload.get('worker_id'), 'status': 'SIGNATURE_INVALID'})
            continue
        
        # Step 2: Reject replayed logs (timestamp older than 24 hours)
        log_ts = datetime.fromisoformat(payload['timestamp'])
        if (datetime.utcnow() - log_ts).total_seconds() > 86400:
            results.append({'worker_id': payload['worker_id'], 'status': 'EXPIRED_LOG'})
            continue
        
        # Step 3: Write validated record to DynamoDB
        table.put_item(Item={
            'worker_id':        payload['worker_id'],
            'timestamp':        payload['timestamp'],
            'device_id':        payload['device_id'],
            'match_score':      str(payload['match_score']),
            'liveness_passed':  payload['liveness_passed'],
            'signature':        received_sig,
            'site_code':        payload.get('site_code', 'UNKNOWN'),
            'sync_received_at': datetime.utcnow().isoformat(),
            'status':           'VERIFIED'
        })
        results.append({'worker_id': payload['worker_id'], 'status': 'ACCEPTED'})
    
    return {'statusCode': 200, 'body': json.dumps({'results': results})}
```

---

### 2.2 `POST /worker/register` — Worker Profile Registration
**Trigger:** Admin registers a new worker from the web portal.

```
Input:  { worker_id, name, department, site_code }
Action: Write to nhai_worker_profiles DynamoDB table
Output: { success: true, worker_id }
```
- Validates that `worker_id` follows naming convention (`NHAI-XXX-NNNN`)
- Returns 409 Conflict if worker already exists

---

### 2.3 `GET /attendance/report` — Attendance Report Generator
**Trigger:** Supervisor or admin requests a daily/weekly attendance report.

```
Query Params:  site_code, date_from, date_to
Action:        Query DynamoDB GSI → generate CSV → upload to S3
Output:        { report_url: "s3_presigned_url", total_records: N }
```
- Presigned S3 URL is valid for 1 hour
- CSV columns: `worker_id, name, date, time, match_score, site_code, status`

---

### 2.4 `GET /model/latest` — OTA Model Version Check
**Trigger:** Mobile app checks on launch if a newer INT8 TFLite model exists.

```
Output: {
  model_name: "mobilefacenet_int8",
  version: "v2.1.0",
  download_url: "presigned_s3_url",
  checksum_sha256: "abc123..."
}
```
- App compares local model version with returned version
- Downloads and replaces local `.tflite` only if version differs and checksum validates

---

### 2.5 `POST /admin/flag` — Security Flag Handler
**Trigger:** Triggered automatically when `SIGNATURE_INVALID` or `SPOOF_DETECTED` occurs.

```
Action: Mark record as FLAGGED in DynamoDB
        Send SNS notification to site supervisor
        Log to CloudWatch with severity=HIGH
```

---

## Phase 3: Security Architecture

**Goal:** Ensure all data in transit and at rest is protected to the highest standard.

### 3.1 Device Authentication (HMAC Token)
- Each registered field device is issued a **unique HMAC device key** stored in **AWS Secrets Manager**.
- All attendance sync payloads must carry a valid `HMAC-SHA256` signature computed using this device key.
- Server recomputes the signature and compares using `hmac.compare_digest()` (timing-safe).

### 3.2 Admin Authentication (AWS Cognito)
- Admin panel and `GET /report` endpoints are protected by **AWS Cognito User Pool**.
- JWT Bearer token required in the `Authorization` header for all admin routes.
- MFA enforced for all admin accounts.

### 3.3 Replay Attack Prevention
- All log timestamps must be within **24 hours** of the server's current UTC time.
- Each record's `(worker_id + timestamp + device_id)` triplet is checked for **idempotency** using DynamoDB's conditional writes — duplicate submissions are silently discarded.

### 3.4 Data at Rest
- DynamoDB tables encrypted at rest using **AWS-managed keys (SSE-AES256)**.
- S3 buckets encrypted using **AES-256 with bucket-level policies** blocking all public access.

### 3.5 Data in Transit
- All API Gateway endpoints enforce **TLS 1.2+**.
- HTTP is rejected at the gateway level via policy.

---

## Phase 4: API Reference

### Base URL
```
https://<api-id>.execute-api.ap-south-1.amazonaws.com/prod
```

### Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/attendance/sync` | Device HMAC | Batch upload signed attendance logs |
| `POST` | `/worker/register` | Cognito JWT | Register new worker profile |
| `GET` | `/worker/{id}` | Cognito JWT | Fetch worker profile |
| `DELETE` | `/worker/{id}` | Cognito JWT | Deactivate worker |
| `GET` | `/attendance/report` | Cognito JWT | Generate + download attendance CSV |
| `GET` | `/model/latest` | Device HMAC | Check and download latest TFLite model |
| `POST` | `/admin/flag` | Internal Lambda | Flag suspicious device/record |
| `GET` | `/health` | None | Liveness check for monitoring |

---

## Phase 5: Monitoring & Alerting

**Goal:** Ensure visibility into system health, spoof attempts, and sync failures.

### 5.1 CloudWatch Dashboards
- **Sync Throughput:** Records per minute arriving at `/attendance/sync`
- **Signature Failure Rate:** Count of `SIGNATURE_INVALID` rejections over time
- **Lambda Latency P99:** Ensures API response under 500 ms
- **DynamoDB Read/Write Capacity:** Auto-scaling monitoring

### 5.2 SNS Alerts (Email / SMS to Site Supervisor)
| Alert Trigger | Severity |
|---|---|
| `SIGNATURE_INVALID` count > 3 in 5 minutes | HIGH |
| Device submitting logs with timestamp > 24h old | MEDIUM |
| Lambda error rate > 5% | HIGH |
| DynamoDB throttle events | MEDIUM |
| New model version pushed to S3 | INFO |

### 5.3 Deployment
```bash
# Deploy entire backend stack to AWS in one command
cd nhai-backend
cdk deploy --all --require-approval never
```

---

## Backend Deliverable Checklist

| # | Deliverable | Status |
|---|---|---|
| 1 | CDK stack with DynamoDB tables + GSI defined | ⬜ |
| 2 | `sync_attendance` Lambda with HMAC validation + replay protection | ⬜ |
| 3 | `worker_register` Lambda with ID format validation | ⬜ |
| 4 | `attendance_report` Lambda with CSV + S3 presigned URL | ⬜ |
| 5 | `model_latest` Lambda for OTA TFLite versioning | ⬜ |
| 6 | `admin_flag` Lambda + SNS alert wiring | ⬜ |
| 7 | API Gateway with Cognito + HMAC auth guards | ⬜ |
| 8 | S3 bucket for model weights + reports (private) | ⬜ |
| 9 | Secrets Manager entry for device HMAC keys | ⬜ |
| 10 | CloudWatch dashboard + 5 SNS alarm rules | ⬜ |
| 11 | LocalStack integration for offline local testing | ⬜ |
| 12 | CDK `cdk deploy` tested end-to-end | ⬜ |
