from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=10,
    max_overflow=20
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autoflush=False,
    expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with SessionLocal() as session:
        yield session
