"""
config.py — Enrollment Service settings.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "NHAI Enrollment Service"
    APP_VERSION: str = "1.0.0"
    ENV: str = "development"
    DEBUG: bool = False

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://nhai:nhai_dev_password@localhost:5432/nhai_auth"

    # ── JWT verification ──────────────────────────────────────────────────────
    # URL of Auth Service JWKS endpoint — used to verify admin/device JWTs
    AUTH_JWKS_URL: str = "http://localhost:8001/auth/token/jwks"
    JWT_ALGORITHM: str = "RS256"
    JWT_ISSUER: str = "nhai-auth-service"

    # ── Internal API key (for calling Auth Service /pubkey) ───────────────────
    INTERNAL_API_KEY: str = "dev-internal-key-change-in-prod"
    AUTH_SERVICE_URL: str = "http://localhost:8001"

    # ── AES-256-GCM Embedding encryption ──────────────────────────────────────
    # 32-byte hex key — in production fetched from AWS Secrets Manager
    AES_EMBEDDING_KEY_HEX: str = ""
    USE_AWS_SECRETS: bool = False
    AWS_REGION: str = "ap-south-1"
    AWS_SECRET_NAME_AES: str = "nhai/staging/aes256-embedding-key"

    # ── ONNX model paths ──────────────────────────────────────────────────────
    YUNET_MODEL_PATH: str = "models/yunet.onnx"
    MOBILEFACENET_MODEL_PATH: str = "models/mobilefacenet.onnx"

    # ── Image validation ──────────────────────────────────────────────────────
    MAX_IMAGE_SIZE_MB: int = 5
    MIN_FACE_SIZE_PX: int = 80   # reject tiny/distant faces at enrollment

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
