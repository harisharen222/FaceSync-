from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ENV: str = "development"
    AWS_REGION: str = "ap-south-1"
    SQS_QUEUE_URL: str
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

def get_settings() -> Settings:
    return Settings()
