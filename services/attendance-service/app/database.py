"""
database.py — Async SQLAlchemy setup for FastAPI, plus sync setup for the SQS worker.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import get_settings

settings = get_settings()

# ── Async Engine (for FastAPI routes) ────────────────────────────────────────
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# ── Sync Engine (for background SQS worker) ──────────────────────────────────
# Background workers often benefit from simpler synchronous drivers (psycopg2/pg8000)
# since they process one message at a time sequentially per thread.
sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=5,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

class Base(DeclarativeBase):
    pass
