import datetime
import calendar
from typing import Annotated, List

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import WorkerRoster, DailyAttendance
from app.schemas import DailySiteReportResponse, WorkerAttendanceSummaryResponse
from app.dependencies import require_admin_jwt, TokenPayload

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/site/{site_code}/daily", response_model=List[DailySiteReportResponse])
async def get_daily_site_reports(
    site_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[TokenPayload, Depends(require_admin_jwt)],
    start_date: datetime.date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: datetime.date = Query(..., description="End date (YYYY-MM-DD)"),
):
    """
    Get daily aggregated attendance metrics for a site within a date range.
    """
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
        
    # Get total enrolled active workers for the site
    # Note: In a perfectly event-sourced system, we'd query historical roster size per day.
    # For now, we use the current roster size for all historical reports.
    enrolled_query = select(func.count(WorkerRoster.worker_id)).where(
        WorkerRoster.site_code == site_code,
        WorkerRoster.is_active == True
    )
    total_enrolled = (await db.execute(enrolled_query)).scalar() or 0
    
    # Get daily attendance counts
    attendance_query = select(
        DailyAttendance.date,
        func.count(DailyAttendance.worker_id).label("total_present")
    ).where(
        DailyAttendance.site_code == site_code,
        DailyAttendance.date >= start_date,
        DailyAttendance.date <= end_date
    ).group_by(DailyAttendance.date)
    
    attendance_results = (await db.execute(attendance_query)).all()
    
    # Create a map for fast lookup
    attendance_map = {row.date: row.total_present for row in attendance_results}
    
    # Generate full date range
    reports = []
    current_date = start_date
    while current_date <= end_date:
        total_present = attendance_map.get(current_date, 0)
        percentage = (total_present / total_enrolled * 100) if total_enrolled > 0 else 0.0
        
        reports.append(DailySiteReportResponse(
            site_code=site_code,
            date=current_date,
            total_enrolled=total_enrolled,
            total_present=total_present,
            attendance_percentage=round(percentage, 2)
        ))
        current_date += datetime.timedelta(days=1)
        
    return reports

@router.get("/worker/{worker_id}/monthly", response_model=WorkerAttendanceSummaryResponse)
async def get_worker_monthly_summary(
    worker_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[TokenPayload, Depends(require_admin_jwt)],
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
):
    """
    Get the attendance summary for a specific worker for a given month.
    """
    # Calculate month date range
    _, last_day = calendar.monthrange(year, month)
    start_date = datetime.date(year, month, 1)
    end_date = datetime.date(year, month, last_day)
    
    # Query attendance records
    query = select(DailyAttendance.date).where(
        DailyAttendance.worker_id == worker_id,
        DailyAttendance.date >= start_date,
        DailyAttendance.date <= end_date
    ).order_by(DailyAttendance.date)
    
    results = (await db.execute(query)).scalars().all()
    
    return WorkerAttendanceSummaryResponse(
        worker_id=worker_id,
        month_start=start_date,
        month_end=end_date,
        days_present=len(results),
        attendance_dates=list(results)
    )
