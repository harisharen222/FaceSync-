"""
config.py — Environment-driven settings for the Auth Service.
All secrets are loaded from environment variables injected by ECS task definitions
or from a local .env file during development.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "NHAI Auth Service"
    APP_VERSION: str = "1.0.0"
    ENV: str = "development"              # development | staging | production
    DEBUG: bool = False

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://nhai:nhai_dev@localhost:5432/nhai_auth"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT ───────────────────────────────────────────────────────────────────
    # In production these are fetched from AWS Secrets Manager at startup.
    # In development, set them directly in your .env file.
    JWT_RS256_PRIVATE_KEY: str = ""      # PEM string of RS256 private key
    JWT_RS256_PUBLIC_KEY: str = ""       # PEM string of RS256 public key
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    JWT_ALGORITHM: str = "RS256"
    JWT_ISSUER: str = "nhai-auth-service"

    # ── AWS (for Secrets Manager in production) ───────────────────────────────
    AWS_REGION: str = "ap-south-1"
    AWS_SECRET_NAME_RS256: str = "nhai/rs256-keypair"  # key in Secrets Manager
    USE_AWS_SECRETS: bool = False        # Set True in staging/production

    # ── Admin bootstrap ──────────────────────────────────────────────────────
    # First admin account seeded on startup if no admins exist.
    BOOTSTRAP_ADMIN_EMAIL: str = "admin@nhai.gov.in"
    BOOTSTRAP_ADMIN_PASSWORD: str = "ChangeMe@2026!"  # override via env in production

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — call get_settings() anywhere in the app."""
    return Settings()
