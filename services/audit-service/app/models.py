import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String, index=True)
    source = Column(String, index=True)
    detail_type = Column(String, index=True)
    timestamp_utc = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    detail = Column(JSONB)
