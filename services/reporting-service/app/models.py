import datetime
from sqlalchemy import Column, String, Date, Integer, Boolean, MetaData, UniqueConstraint

from app.database import Base

metadata = MetaData(schema="reporting_schema")

class WorkerRoster(Base):
    """Event-sourced roster reflecting the current state of workers."""
    __tablename__ = "worker_roster"
    __table_args__ = {"schema": "reporting_schema"}

    worker_id = Column(String, primary_key=True, index=True)
    site_code = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)


class DailyAttendance(Base):
    """One row per worker per day to track attendance quickly."""
    __tablename__ = "daily_attendance"
    __table_args__ = (
        UniqueConstraint('worker_id', 'date', name='uq_worker_date'),
        {"schema": "reporting_schema"}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    worker_id = Column(String, index=True, nullable=False)
    site_code = Column(String, index=True, nullable=False)
    date = Column(Date, index=True, nullable=False)
    first_scan_utc = Column(String, nullable=False)
