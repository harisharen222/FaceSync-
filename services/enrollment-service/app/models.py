"""
models.py — SQLAlchemy ORM for Enrollment Service (enrollment_schema).

Tables:
  - personnel      : worker master data
  - face_embeddings: AES-256-GCM encrypted 128-D embedding blobs
  - device_sync    : tracks which workers have been pushed to which device
"""
import uuid
from sqlalchemy import (
    Boolean, Column, DateTime, String, Text,
    LargeBinary, ForeignKey, UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Personnel(Base):
    """
    NHAI worker master record.
    The enrollment_schema owns this table — only the Enrollment Service writes it.
    """
    __tablename__ = "personnel"
    __table_args__ = {"schema": "enrollment_schema"}

    worker_id       = Column(String(32), primary_key=True, index=True)
    # e.g. "NHAI-DEL-0419" — validated by regex at API layer
    name            = Column(String(256), nullable=False)
    department      = Column(String(128), nullable=True)
    site_code       = Column(String(32),  nullable=False, index=True)
    enrolled_at     = Column(DateTime(timezone=True), server_default=func.now())
    model_version   = Column(String(16), nullable=True)   # e.g. "1.2.0"
    is_active       = Column(Boolean, default=True, nullable=False)
    enrolled_by     = Column(String(64), nullable=True)   # admin_id


class FaceEmbedding(Base):
    """
    AES-256-GCM encrypted 128-D float embedding for a worker.
    Stored as three byte columns: ciphertext, GCM nonce (12 B), GCM auth tag (16 B).
    Re-enrollment is handled by inserting a new row and marking the old one inactive.
    """
    __tablename__ = "face_embeddings"
    __table_args__ = {"schema": "enrollment_schema"}

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_id       = Column(
        String(32),
        ForeignKey("enrollment_schema.personnel.worker_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    encrypted_blob  = Column(LargeBinary, nullable=False)   # AES-256-GCM ciphertext
    nonce           = Column(LargeBinary(12), nullable=False)  # GCM nonce
    tag             = Column(LargeBinary(16), nullable=False)  # GCM auth tag
    model_version   = Column(String(16), nullable=True)
    is_active       = Column(Boolean, default=True, nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class DeviceSync(Base):
    """
    Tracks which worker embeddings have been synced to which field device.
    When a device calls GET /enroll/sync/{device_id}, it receives all
    active embeddings for its site_code that it hasn't yet received.
    The sync_version acts as a cursor — the device sends its last seen version
    and receives only newer entries.
    """
    __tablename__ = "device_sync"
    __table_args__ = (
        UniqueConstraint("device_id", "embedding_id", name="uq_device_embedding"),
        {"schema": "enrollment_schema"},
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id       = Column(String(64), nullable=False, index=True)
    embedding_id    = Column(
        UUID(as_uuid=True),
        ForeignKey("enrollment_schema.face_embeddings.id", ondelete="CASCADE"),
        nullable=False,
    )
    synced_at       = Column(DateTime(timezone=True), server_default=func.now())
    sync_version    = Column(String(36), nullable=False)  # UUID4 monotonic cursor
