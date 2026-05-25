"""
models.py — SQLAlchemy ORM for Model Service (models_schema).
"""
from datetime import datetime
from sqlalchemy import (
    Column, DateTime, String, Integer, Enum, func, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
import enum
import uuid

class ModelType(str, enum.Enum):
    MOBILEFACENET = "MOBILEFACENET"
    YUNET = "YUNET"
    MINIFASNET = "MINIFASNET"

class ReleaseStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"     # Just uploaded, not serving
    ACTIVE = "ACTIVE"         # Currently serving to devices
    DEPRECATED = "DEPRECATED" # Serving to stragglers, but newer version exists
    DISABLED = "DISABLED"     # Prevent devices from using/downloading this

class ModelRelease(Base):
    """
    Tracks metadata for a specific TFLite/ONNX model version.
    """
    __tablename__ = "releases"
    __table_args__ = {"schema": "models_schema"}

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_type    = Column(Enum(ModelType), nullable=False)
    version       = Column(String(32), nullable=False)  # e.g. "v1.2.0"
    s3_key        = Column(String(256), nullable=False) # e.g. "mobilefacenet/v1.2.0/model.tflite"
    file_size     = Column(Integer, nullable=False)
    sha256_hash   = Column(String(64), nullable=False)  # For device-side integrity verification
    status        = Column(Enum(ReleaseStatus), default=ReleaseStatus.UPLOADED, nullable=False)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    activated_at  = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        UniqueConstraint('model_type', 'version', name='uq_model_version'),
        {"schema": "models_schema"}
    )

class DeviceModelStatus(Base):
    """
    Tracks which devices are currently running which model versions.
    Updated when a device hits the manifest or sync endpoint.
    """
    __tablename__ = "device_status"
    __table_args__ = {"schema": "models_schema"}

    device_id     = Column(String(64), primary_key=True)
    model_type    = Column(Enum(ModelType), primary_key=True)
    version       = Column(String(32), nullable=False)
    last_reported = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
