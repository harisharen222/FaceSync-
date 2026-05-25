import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import reports

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="NHAI Biometric Attendance - Reporting Service",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENV != "production" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reports.router)

@app.get("/health", tags=["Health"])
def health_check():
    """Liveness probe"""
    return {"status": "ok", "service": "reporting"}
