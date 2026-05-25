from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class AuditLogResponse(BaseModel):
    id: UUID
    event_id: Optional[str] = None
    source: Optional[str] = None
    detail_type: Optional[str] = None
    timestamp_utc: datetime
    detail: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}
