import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import engine, Base
from app.routes import audit

logger = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout, level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENV}]")
    
    if settings.ENV == "development":
        async with engine.begin() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("CREATE SCHEMA IF NOT EXISTS audit_schema")
            )
            await conn.run_sync(Base.metadata.create_all)
            
    yield
    await engine.dispose()
    logger.info("Audit Service shutdown complete")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.ENV != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENV == "development" else [],
    allow_methods=["GET"],
    allow_headers=["Authorization"],
)

app.include_router(audit.router)

@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
