"""
main.py — Model Delivery Service FastAPI application.
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
from app.routes import admin, device

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
                __import__("sqlalchemy").text("CREATE SCHEMA IF NOT EXISTS models_schema")
            )
            await conn.run_sync(Base.metadata.create_all)

    yield

    await engine.dispose()
    logger.info("Model Delivery Service shutdown complete")


app = FastAPI(
    title="NHAI Model Delivery Service (OTA)",
    version=settings.APP_VERSION,
    description="Distributes ONNX/TFLite models to edge devices via presigned URLs.",
    docs_url="/docs" if settings.ENV != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENV == "development" else [],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception in Model Service: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(admin.router)
app.include_router(device.router)


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
