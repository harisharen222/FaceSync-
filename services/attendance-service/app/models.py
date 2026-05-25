"""
models.py — SQLAlchemy ORM for Attendance Sync Service (attendance_schema).
"""
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, String, Numeric, func
)
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class AttendanceRecord(Base):
    """
    Verified attendance records synced from field devices.
    """
    __tablename__ = "records"
    __table_args__ = {"schema": "attendance_schema"}

    id              = Column(UUID(as_uuid=True), primary_key=True)
    worker_id       = Column(String(32), nullable=False, index=True)
    device_id       = Column(String(64), nullable=False, index=True)
    timestamp_utc   = Column(DateTime(timezone=True), nullable=False, index=True)
    confidence      = Column(Numeric(4, 3), nullable=True)
    liveness_score  = Column(Numeric(4, 3), nullable=True)
    liveness_passed = Column(Boolean, nullable=False)
    site_code       = Column(String(32), nullable=False, index=True)
    ecdsa_signature = Column(String(256), nullable=False)
    sync_received   = Column(DateTime(timezone=True), server_default=func.now())
    status          = Column(String(32), default="VERIFIED", nullable=False)
    # Statuses: VERIFIED | FLAGGED | INVALID_SIGNATURE


class DeduplicationIndex(Base):
    """
    SHA-256 hash index to prevent replay attacks and duplicate syncs.
    Hash = SHA256(worker_id + timestamp_utc_iso + device_id)
    """
    __tablename__ = "dedup_index"
    __table_args__ = {"schema": "attendance_schema"}

    dedup_hash      = Column(String(64), primary_key=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
