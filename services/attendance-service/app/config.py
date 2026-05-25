"""
config.py — Attendance Sync Service settings.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "NHAI Attendance Sync Service"
    APP_VERSION: str = "1.0.0"
    ENV: str = "development"
    DEBUG: bool = False

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://nhai:nhai_dev_password@localhost:5432/nhai_auth"
    # Used by the synchronous background worker
    SYNC_DATABASE_URL: str = "postgresql://nhai:nhai_dev_password@localhost:5432/nhai_auth"

    # ── Auth Service Integration ─────────────────────────────────────────────
    AUTH_JWKS_URL: str = "http://localhost:8001/auth/token/jwks"
    AUTH_SERVICE_URL: str = "http://localhost:8001"
    INTERNAL_API_KEY: str = "dev-internal-key-change-in-prod"
    JWT_ALGORITHM: str = "RS256"
    JWT_ISSUER: str = "nhai-auth-service"

    # ── AWS SQS & EventBridge ────────────────────────────────────────────────
    AWS_REGION: str = "ap-south-1"
    SQS_QUEUE_URL: str = "http://localhost:4566/000000000000/nhai-attendance-queue"
    EVENT_BUS_NAME: str = "nhai-event-bus"
    
    # ── Sync batch limits ────────────────────────────────────────────────────
    MAX_BATCH_SIZE: int = 500

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
