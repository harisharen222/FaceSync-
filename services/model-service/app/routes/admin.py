"""
admin.py — Admin endpoints for uploading and rolling out models.
"""
import hashlib
import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ModelRelease, ModelType, ReleaseStatus
from app.schemas import ModelReleaseResponse
from app.dependencies import require_admin_jwt, TokenPayload
from app.s3_client import upload_model_file

router = APIRouter(prefix="/models/admin", tags=["Admin Model Management"])


@router.post("/upload", response_model=ModelReleaseResponse)
async def upload_new_model(
    model_type: Annotated[ModelType, Form(...)],
    version: Annotated[str, Form(...)],
    file: Annotated[UploadFile, File(...)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[TokenPayload, Depends(require_admin_jwt)]
):
    """
    Upload a new model binary (TFLite/ONNX).
    Stores it in S3 and creates an UPLOADED database record.
    """
    # 1. Check if version already exists
    stmt = select(ModelRelease).where(
        ModelRelease.model_type == model_type,
        ModelRelease.version == version
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Model version already exists")

    # 2. Read file and compute SHA256
    file_bytes = await file.read()
    file_size = len(file_bytes)
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

    # 3. Upload to S3
    s3_key = f"{model_type.value.lower()}/{version}/model.tflite"
    success = await upload_model_file(s3_key, file_bytes)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to upload model to S3")

    # 4. Create DB record
    release = ModelRelease(
        model_type=model_type,
        version=version,
        s3_key=s3_key,
        file_size=file_size,
        sha256_hash=sha256_hash,
        status=ReleaseStatus.UPLOADED
    )
    db.add(release)
    
    return release


@router.patch("/rollout/{release_id}", response_model=ModelReleaseResponse)
async def activate_model_release(
    release_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[TokenPayload, Depends(require_admin_jwt)]
):
    """
    Mark a specific model release as ACTIVE.
    Automatically marks other ACTIVE releases of the same type as DEPRECATED.
    """
    release = await db.get(ModelRelease, release_id)
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")

    if release.status == ReleaseStatus.ACTIVE:
        return release

    # Mark others as deprecated
    stmt = select(ModelRelease).where(
        ModelRelease.model_type == release.model_type,
        ModelRelease.status == ReleaseStatus.ACTIVE
    )
    active_releases = (await db.execute(stmt)).scalars().all()
    for active in active_releases:
        active.status = ReleaseStatus.DEPRECATED

    # Activate this one
    release.status = ReleaseStatus.ACTIVE
    from datetime import datetime, timezone
    release.activated_at = datetime.now(tz=timezone.utc)
    
    return release


@router.get("/releases", response_model=List[ModelReleaseResponse])
async def list_releases(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[TokenPayload, Depends(require_admin_jwt)]
):
    """List all model releases."""
    result = await db.execute(select(ModelRelease).order_by(ModelRelease.created_at.desc()))
    return result.scalars().all()
