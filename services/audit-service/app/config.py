from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "NHAI Audit Service"
    APP_VERSION: str = "1.0.0"
    ENV: str = "development"
    DEBUG: bool = False
    
    # DB
    DATABASE_URL: str
    SYNC_DATABASE_URL: str
    
    # Auth Service integration
    AUTH_JWKS_URL: str
    
    # AWS
    AWS_REGION: str = "ap-south-1"
    SQS_QUEUE_URL: str
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

def get_settings() -> Settings:
    return Settings()
