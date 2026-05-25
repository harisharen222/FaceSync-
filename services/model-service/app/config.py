"""
config.py — Model Delivery Service settings.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "NHAI Model Delivery Service"
    APP_VERSION: str = "1.0.0"
    ENV: str = "development"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str

    # Auth Service Integration
    AUTH_JWKS_URL: str
    JWT_ALGORITHM: str = "RS256"
    JWT_ISSUER: str = "nhai.auth.service"

    # AWS configuration
    AWS_REGION: str = "ap-south-1"
    
    # S3 / CloudFront configuration
    MODEL_BUCKET_NAME: str
    CLOUDFRONT_DOMAIN: Optional[str] = None
    
    # In local dev (LocalStack), we talk directly to S3 without CloudFront
    # and we need to configure custom endpoint URLs
    S3_ENDPOINT_URL: Optional[str] = None
    
    # Max presigned URL lifespan (15 minutes)
    PRESIGNED_URL_EXPIRY_SECONDS: int = 900

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
