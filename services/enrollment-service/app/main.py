"""
main.py — Enrollment Service FastAPI application entry point.
"""
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import engine, Base
from app.encryption import init_encryption_key
from app.onnx_runner import load_models
from app.routes import workers, face, sync

logger = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout, level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENV}]")

    # 1. Validate + cache AES-256 key
    init_encryption_key()

    # 2. Load ONNX models into memory
    try:
        load_models()
    except FileNotFoundError as e:
        logger.warning(
            f"ONNX model files not found: {e}. "
            "Enrollment pipeline will fail until model files are placed at configured paths."
        )

    # 3. Dev: auto-create tables
    if settings.ENV == "development":
        async with engine.begin() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("CREATE SCHEMA IF NOT EXISTS enrollment_schema")
            )
            await conn.run_sync(Base.metadata.create_all)

    logger.info("Enrollment Service startup complete ✓")
    yield

    await engine.dispose()
    logger.info("Enrollment Service shutdown complete")


app = FastAPI(
    title="NHAI Enrollment Service",
    version=settings.APP_VERSION,
    description=(
        "Manages NHAI worker enrollment: face photo upload → "
        "YuNet detection → alignment → CLAHE → MobileFaceNet → AES-256-GCM encrypted embedding storage. "
        "Distributes encrypted embeddings to field devices via delta sync."
    ),
    docs_url="/docs" if settings.ENV != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENV == "development" else [],
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception in Enrollment Service: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(workers.router)
app.include_router(face.router)
app.include_router(sync.router)


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
