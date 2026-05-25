from pydantic import BaseModel
from typing import List, Optional
import datetime

class DailySiteReportResponse(BaseModel):
    site_code: str
    date: datetime.date
    total_enrolled: int
    total_present: int
    attendance_percentage: float

class WorkerAttendanceSummaryResponse(BaseModel):
    worker_id: str
    month_start: datetime.date
    month_end: datetime.date
    days_present: int
    attendance_dates: List[datetime.date]

class MessageResponse(BaseModel):
    message: str
