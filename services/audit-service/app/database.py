from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    server_settings={"search_path": "audit_schema"}
)

AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False
)

sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    connect_args={"options": "-csearch_path=audit_schema"}
)

SyncSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=sync_engine
)

Base = declarative_base()
