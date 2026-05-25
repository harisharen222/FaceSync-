"""
device.py — Device endpoints for fetching OTA model updates.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ModelRelease, ReleaseStatus, DeviceModelStatus, ModelType
from app.schemas import DeviceManifestResponse, ManifestItem, DeviceStatusReport
from app.dependencies import require_device_jwt, TokenPayload
from app.s3_client import generate_presigned_url
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/models", tags=["Device OTA"])


@router.get("/manifest", response_model=DeviceManifestResponse)
async def get_device_manifest(
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Annotated[TokenPayload, Depends(require_device_jwt)]
):
    """
    Get the active model manifest.
    Returns S3/CloudFront pre-signed URLs for any ACTIVE model versions.
    Devices should call this on startup.
    """
    stmt = select(ModelRelease).where(ModelRelease.status == ReleaseStatus.ACTIVE)
    active_releases = (await db.execute(stmt)).scalars().all()
    
    manifest_items = []
    
    for release in active_releases:
        # Generate short-lived presigned URL
        url = await generate_presigned_url(release.s3_key)
        if not url:
            logger.error(f"Failed to generate presigned URL for {release.id}")
            continue
            
        manifest_items.append(
            ManifestItem(
                model_type=release.model_type,
                version=release.version,
                download_url=url,
                expires_in_seconds=settings.PRESIGNED_URL_EXPIRY_SECONDS,
                file_size=release.file_size,
                sha256_hash=release.sha256_hash
            )
        )
        
    return DeviceManifestResponse(
        models=manifest_items,
        # In a real app, you might check the device's currently reported version
        # to determine if an update is strictly required before allowing attendance.
        # For now, we assume if the manifest contains models, the device should check them.
        requires_update=len(manifest_items) > 0
    )


@router.post("/status")
async def report_device_status(
    report: DeviceStatusReport,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Annotated[TokenPayload, Depends(require_device_jwt)]
):
    """
    Device reports which model versions it has successfully loaded.
    Used by admins to monitor the rollout progress across the fleet.
    """
    if caller.sub != report.device_id:
        raise HTTPException(status_code=403, detail="device_id mismatch")
        
    for m_type, version in report.models.items():
        # Upsert status
        stmt = select(DeviceModelStatus).where(
            DeviceModelStatus.device_id == report.device_id,
            DeviceModelStatus.model_type == m_type
        )
        status_record = (await db.execute(stmt)).scalar_one_or_none()
        
        if status_record:
            status_record.version = version
        else:
            db.add(DeviceModelStatus(
                device_id=report.device_id,
                model_type=m_type,
                version=version
            ))
            
    return {"status": "recorded"}
