"""
schemas.py — Pydantic v2 DTOs for Enrollment Service.
"""
import re
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


WORKER_ID_PATTERN = re.compile(r"^NHAI-[A-Z]{2,4}-\d{4}$")


# ── Worker (Personnel) Schemas ────────────────────────────────────────────────

class WorkerCreateRequest(BaseModel):
    """POST /enroll/worker"""
    worker_id:   str = Field(..., description="Format: NHAI-XXX-NNNN (e.g. NHAI-DEL-0419)")
    name:        str = Field(..., min_length=2, max_length=256)
    department:  Optional[str] = Field(None, max_length=128)
    site_code:   str = Field(..., min_length=2, max_length=32)

    @field_validator("worker_id")
    @classmethod
    def validate_worker_id(cls, v: str) -> str:
        if not WORKER_ID_PATTERN.match(v):
            raise ValueError(
                "worker_id must match pattern NHAI-XX-NNNN "
                "(e.g. NHAI-DEL-0419, NHAI-MUM-0012)"
            )
        return v


class WorkerResponse(BaseModel):
    worker_id:   str
    name:        str
    department:  Optional[str]
    site_code:   str
    enrolled_at: Optional[datetime]
    model_version: Optional[str]
    is_active:   bool
    has_embedding: bool = False   # True if a face template exists


class WorkerListResponse(BaseModel):
    workers: List[WorkerResponse]
    total:   int


# ── Face Enrollment Schemas ───────────────────────────────────────────────────

class FaceEnrollResponse(BaseModel):
    """Response after successfully uploading + processing a face photo."""
    worker_id:       str
    embedding_id:    UUID
    face_confidence: float = Field(..., description="YuNet detection confidence [0,1]")
    face_bbox:       dict  = Field(..., description="{x, y, w, h} in original image pixels")
    model_version:   str
    message:         str = "Face embedding enrolled successfully"


class FaceEnrollErrorResponse(BaseModel):
    """Returned when the enrollment pipeline rejects the image."""
    worker_id: str
    error:     str
    hint:      str = "Re-upload a clearer, well-lit photo showing one face"


# ── Device Sync Schemas ───────────────────────────────────────────────────────

class EmbeddingPayload(BaseModel):
    """
    Single encrypted embedding payload delivered to a field device during sync.
    The device stores this in its local SQLCipher DB.
    The device_key is NOT the raw AES key — it's the embedding re-encrypted
    with a device-specific key derived from the Auth Service device record.
    """
    worker_id:      str
    embedding_id:   str
    # Encrypted blob fields (base64-encoded for JSON transport)
    encrypted_blob: str   # base64
    nonce:          str   # base64 (12 bytes)
    tag:            str   # base64 (16 bytes)
    model_version:  Optional[str]
    worker_name:    str   # human-readable for device UI


class DeviceSyncResponse(BaseModel):
    device_id:    str
    site_code:    str
    embeddings:   List[EmbeddingPayload]
    sync_version: str     # new cursor for next delta pull
    total:        int


# ── Generic ───────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str
    success: bool = True
