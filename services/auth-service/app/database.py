"""
database.py — Async SQLAlchemy engine, session factory, and Base for the Auth Service.
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,     # validate connections before checkout
)

# ── Session factory ───────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# ── Declarative Base ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Dependency injection helper ───────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    FastAPI dependency that yields a database session per request.
    Session is committed/rolled-back and closed automatically.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
