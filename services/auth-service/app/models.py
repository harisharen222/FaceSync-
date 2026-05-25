"""
models.py — SQLAlchemy ORM models for the Auth Service (auth_schema).

Tables:
  - devices         : registered field devices + their ECDSA public keys
  - admins          : admin/supervisor accounts
  - token_blacklist : revoked JWTs (checked on every protected request)
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, String, Text, func
)
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Device(Base):
    """
    Represents a registered NHAI field Android/iOS terminal.
    Each device carries a unique ECDSA P-256 keypair generated on first boot.
    The PUBLIC key is registered here; the private key never leaves the device.
    """
    __tablename__ = "devices"
    __table_args__ = {"schema": "auth_schema"}

    device_id       = Column(String(64), primary_key=True, index=True)
    public_key_pem  = Column(Text, nullable=False)          # ECDSA P-256 PEM
    site_code       = Column(String(32), nullable=False)    # e.g. NH-44-KM120
    device_model    = Column(String(128), nullable=True)    # e.g. "Samsung Galaxy A52"
    android_version = Column(String(16), nullable=True)
    registered_by   = Column(String(64), nullable=True)     # admin_id who registered
    registered_at   = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at    = Column(DateTime(timezone=True), nullable=True)
    is_active       = Column(Boolean, default=True, nullable=False)


class Admin(Base):
    """
    Admin or site supervisor account.
    Passwords are hashed with bcrypt (cost factor 12).
    """
    __tablename__ = "admins"
    __table_args__ = {"schema": "auth_schema"}

    admin_id        = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email           = Column(String(256), unique=True, nullable=False, index=True)
    password_hash   = Column(String(256), nullable=False)
    full_name       = Column(String(256), nullable=True)
    role            = Column(String(32), default="supervisor", nullable=False)
    # Roles: "superadmin" | "supervisor" | "readonly"
    site_code       = Column(String(32), nullable=True)     # null → access to all sites
    is_active       = Column(Boolean, default=True, nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at   = Column(DateTime(timezone=True), nullable=True)


class TokenBlacklist(Base):
    """
    Revoked JWT IDs. Checked on every authenticated request.
    Expired tokens are purged nightly by a background cleanup job.
    Redis is the primary blacklist store (fast); this table acts as the
    durable backup in case Redis is flushed or cold-started.
    """
    __tablename__ = "token_blacklist"
    __table_args__ = {"schema": "auth_schema"}

    jti             = Column(String(64), primary_key=True)  # JWT ID claim
    token_type      = Column(String(16), default="access")  # access | refresh
    revoked_by      = Column(String(64), nullable=True)     # admin_id or "device"
    revoked_at      = Column(DateTime(timezone=True), server_default=func.now())
    expires_at      = Column(DateTime(timezone=True), nullable=False)
