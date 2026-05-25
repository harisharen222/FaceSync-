"""
schemas.py — Pydantic v2 DTOs for Attendance Sync Service.
"""
import re
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


WORKER_ID_PATTERN = re.compile(r"^NHAI-[A-Z]{2,4}-\d{4}$")


class AttendanceRecordPayload(BaseModel):
    """
    A single offline attendance record sent by a field device.
    The device signs the JSON representation of this object (excluding signature).
    """
    id:              UUID = Field(..., description="Device-generated UUID for the record")
    worker_id:       str  = Field(..., description="Format: NHAI-XXX-NNNN")
    timestamp_utc:   datetime
    confidence:      float = Field(..., ge=0.0, le=1.0)
    liveness_score:  float = Field(..., ge=0.0, le=1.0)
    liveness_passed: bool
    signature_hex:   str  = Field(..., description="ECDSA P-256 signature over the record data")

    @field_validator("worker_id")
    @classmethod
    def validate_worker_id(cls, v: str) -> str:
        if not WORKER_ID_PATTERN.match(v):
            raise ValueError("worker_id must match pattern NHAI-XX-NNNN")
        return v

    def signature_payload(self) -> str:
        """
        Reconstructs the exact canonical JSON string that the device signed.
        Must match the device's serialization format exactly.
        """
        import json
        payload = {
            "id": str(self.id),
            "worker_id": self.worker_id,
            # Force ISO 8601 with Z timezone indicator (standard for JS/mobile)
            "timestamp_utc": self.timestamp_utc.isoformat().replace("+00:00", "Z"),
            "confidence": self.confidence,
            "liveness_score": self.liveness_score,
            "liveness_passed": self.liveness_passed,
        }
        return json.dumps(payload, separators=(',', ':'), sort_keys=True)


class SyncBatchRequest(BaseModel):
    """POST /attendance/sync"""
    device_id: str
    records:   List[AttendanceRecordPayload] = Field(..., max_length=500)


class SyncBatchResponse(BaseModel):
    accepted: int
    rejected: int
    errors:   List[dict] = Field(default_factory=list)
    message:  str


class AttendanceQueryResponse(BaseModel):
    """GET /attendance/worker/{id} or /attendance/site/{code}"""
    id:              UUID
    worker_id:       str
    device_id:       str
    timestamp_utc:   datetime
    confidence:      float
    liveness_passed: bool
    status:          str
