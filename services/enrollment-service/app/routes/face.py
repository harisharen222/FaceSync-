"""
routes/face.py — Face photo upload and embedding extraction endpoint.
"""
import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Personnel, FaceEmbedding
from app.schemas import FaceEnrollResponse
from app.pipeline import run_enrollment_pipeline, EnrollmentError
from app.encryption import encrypt_embedding
from app.dependencies import require_admin_jwt, TokenPayload
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/enroll/worker", tags=["Face Enrollment"])

# Supported MIME types for face photo uploads
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MODEL_VERSION = "1.0.0"   # Bump when new MobileFaceNet weights are deployed


@router.post("/{worker_id}/face", response_model=FaceEnrollResponse)
async def enroll_face(
    worker_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Annotated[TokenPayload, Depends(require_admin_jwt)],
    photo: UploadFile = File(..., description="JPEG/PNG face photo of the worker"),
):
    """
    Upload a face photo for a registered worker.
    Runs the full enrollment pipeline:
      YuNet detection → alignment → CLAHE → MobileFaceNet → AES-256-GCM encrypt → store

    Re-enrollment:
      If the worker already has an active embedding, it is deactivated and replaced.
      The old embedding is NOT deleted — it is kept for audit purposes.

    Rejects:
      - Images with 0 or >1 detected faces
      - Faces smaller than MIN_FACE_SIZE_PX
      - Files > MAX_IMAGE_SIZE_MB
      - Non-image content types
    """
    # ── Validation: worker must exist and be active ────────────────────────────
    result = await db.execute(
        select(Personnel).where(Personnel.worker_id == worker_id, Personnel.is_active == True)
    )
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Worker '{worker_id}' not found or inactive. Register the worker first.",
        )

    # ── Validation: file type ─────────────────────────────────────────────────
    if photo.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{photo.content_type}'. Upload JPEG, PNG, or WebP.",
        )

    # ── Validation: file size ──────────────────────────────────────────────────
    image_bytes = await photo.read()
    max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
    if len(image_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image too large ({len(image_bytes)//1024} KB). Maximum: {settings.MAX_IMAGE_SIZE_MB} MB.",
        )

    # ── Run enrollment pipeline ───────────────────────────────────────────────
    try:
        pipeline_result = run_enrollment_pipeline(image_bytes)
    except EnrollmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # ── AES-256-GCM encrypt the embedding ──────────────────────────────────────
    ciphertext, nonce, tag = encrypt_embedding(pipeline_result.embedding)

    # ── Deactivate any previous active embedding (re-enrollment) ──────────────
    await db.execute(
        update(FaceEmbedding)
        .where(FaceEmbedding.worker_id == worker_id, FaceEmbedding.is_active == True)
        .values(is_active=False)
    )

    # ── Store new embedding ────────────────────────────────────────────────────
    embedding_id = uuid4()
    new_embedding = FaceEmbedding(
        id=embedding_id,
        worker_id=worker_id,
        encrypted_blob=ciphertext,
        nonce=nonce,
        tag=tag,
        model_version=MODEL_VERSION,
        is_active=True,
    )
    db.add(new_embedding)

    # Update worker model_version
    worker.model_version = MODEL_VERSION

    logger.info(
        f"Face enrolled: worker={worker_id} "
        f"confidence={pipeline_result.face_confidence:.3f} "
        f"embedding_id={embedding_id} by admin={caller.sub}"
    )

    return FaceEnrollResponse(
        worker_id=worker_id,
        embedding_id=embedding_id,
        face_confidence=pipeline_result.face_confidence,
        face_bbox=pipeline_result.face_bbox,
        model_version=MODEL_VERSION,
    )
