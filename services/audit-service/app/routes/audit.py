from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional

from app.database import get_db
from app.models import AuditLog
from app.schemas import AuditLogResponse
from app.dependencies import verify_admin_jwt

router = APIRouter(prefix="/audit", tags=["Audit"])

@router.get("/logs", response_model=List[AuditLogResponse])
async def get_audit_logs(
    source: Optional[str] = None,
    detail_type: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(verify_admin_jwt)
):
    stmt = select(AuditLog)
    
    if source:
        stmt = stmt.where(AuditLog.source == source)
    if detail_type:
        stmt = stmt.where(AuditLog.detail_type == detail_type)
        
    stmt = stmt.order_by(desc(AuditLog.timestamp_utc)).limit(limit).offset(offset)
    
    result = await db.execute(stmt)
    logs = result.scalars().all()
    
    return logs
