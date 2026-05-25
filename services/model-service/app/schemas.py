"""
schemas.py — Pydantic DTOs for Model Service.
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field

from app.models import ModelType, ReleaseStatus

class ModelReleaseResponse(BaseModel):
    id: UUID
    model_type: ModelType
    version: str
    file_size: int
    sha256_hash: str
    status: ReleaseStatus
    created_at: datetime
    activated_at: Optional[datetime]

class ManifestItem(BaseModel):
    """A single model defined in the manifest for the device."""
    model_type: ModelType
    version: str
    download_url: str = Field(description="CloudFront pre-signed URL")
    expires_in_seconds: int
    file_size: int
    sha256_hash: str

class DeviceManifestResponse(BaseModel):
    """Response payload for GET /models/manifest"""
    models: List[ManifestItem]
    requires_update: bool = Field(description="True if the device must download new models before syncing attendance")

class DeviceStatusReport(BaseModel):
    """Payload sent by device to report its current loaded models"""
    device_id: str
    models: dict[ModelType, str] = Field(description="Mapping of ModelType to version string currently active on device")
