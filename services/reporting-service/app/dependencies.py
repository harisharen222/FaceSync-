from typing import AsyncGenerator
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient

from app.database import AsyncSessionLocal
from app.config import get_settings

settings = get_settings()

security = HTTPBearer()

jwks_client = PyJWKClient(settings.AUTH_JWKS_URL)

async def get_db() -> AsyncGenerator:
    async with AsyncSessionLocal() as session:
        yield session

async def verify_admin_jwt(credentials: HTTPAuthorizationCredentials = Security(security)):
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(credentials.credentials)
        payload = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"]
        )
        if payload.get("role") not in ["ADMIN", "SUPERADMIN"]:
            raise HTTPException(status_code=403, detail="Admin access required")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
