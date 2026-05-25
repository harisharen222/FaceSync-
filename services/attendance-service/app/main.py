"""
main.py — Attendance Sync Service FastAPI application.
"""
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import async_engine, sync_engine, Base
from app.routes import sync, query
import asyncio

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
        async with async_engine.begin() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("CREATE SCHEMA IF NOT EXISTS attendance_schema")
            )
            await conn.run_sync(Base.metadata.create_all)
            
        # In dev, we can run the SQS consumer as a background asyncio task
        # In production, this should be a separate ECS Fargate task!
        from app.sqs_consumer import run_worker_loop
        loop = asyncio.get_running_loop()
        app.state.consumer_task = loop.run_in_executor(None, run_worker_loop)

    yield

    await async_engine.dispose()
    sync_engine.dispose()
    logger.info("Attendance Sync Service shutdown complete")


app = FastAPI(
    title="NHAI Attendance Sync Service",
    version=settings.APP_VERSION,
    description=(
        "Handles offline attendance sync from field devices. "
        "Verifies ECDSA signatures, performs deduplication, and queues "
        "verified records to SQS for background insertion."
    ),
    docs_url="/docs" if settings.ENV != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENV == "development" else [],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception in Attendance Service: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(sync.router)
app.include_router(query.router)


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
