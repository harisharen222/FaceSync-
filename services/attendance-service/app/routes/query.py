"""
routes/query.py — Admin read endpoints for attendance records.
"""
from datetime import date
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AttendanceRecord
from app.schemas import AttendanceQueryResponse
from app.dependencies import require_admin_jwt, TokenPayload

router = APIRouter(prefix="/attendance", tags=["Query"])


@router.get("/worker/{worker_id}", response_model=List[AttendanceQueryResponse])
async def get_worker_attendance(
    worker_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[TokenPayload, Depends(require_admin_jwt)],
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(100, le=500),
):
    """Get attendance history for a specific worker."""
    q = select(AttendanceRecord).where(AttendanceRecord.worker_id == worker_id)
    
    if date_from:
        q = q.where(AttendanceRecord.timestamp_utc >= date_from)
    if date_to:
        q = q.where(AttendanceRecord.timestamp_utc <= date_to)
        
    q = q.order_by(AttendanceRecord.timestamp_utc.desc()).limit(limit)
    
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/site/{site_code}", response_model=List[AttendanceQueryResponse])
async def get_site_attendance(
    site_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Annotated[TokenPayload, Depends(require_admin_jwt)],
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(100, le=500),
):
    """Get attendance history for a specific site."""
    # Enforce site access limits if the admin is just a supervisor
    if caller.role != "superadmin" and caller.site_code != site_code:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=403,
            detail="Supervisors can only query their assigned site."
        )

    q = select(AttendanceRecord).where(AttendanceRecord.site_code == site_code)
    
    if date_from:
        q = q.where(AttendanceRecord.timestamp_utc >= date_from)
    if date_to:
        q = q.where(AttendanceRecord.timestamp_utc <= date_to)
        
    q = q.order_by(AttendanceRecord.timestamp_utc.desc()).limit(limit)
    
    result = await db.execute(q)
    return result.scalars().all()
