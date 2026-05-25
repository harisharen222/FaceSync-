"""
main.py — FastAPI application entry point for the NHAI Auth Service.

Startup sequence:
  1. Load settings (env / Secrets Manager)
  2. Fetch RS256 keypair from AWS Secrets Manager (prod) or env (dev)
  3. Initialize Redis connection
  4. Run Alembic migrations (auto, dev only)
  5. Seed bootstrap admin if no admins exist
  6. Mount all routers
"""
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import engine, Base, AsyncSessionLocal
from app.redis_client import init_redis, close_redis
from app.routes import admin as admin_router
from app.routes import device as device_router
from app.routes import token as token_router

logger = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

settings = get_settings()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup + shutdown lifecycle handler."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENV}]")

    # 1. Fetch RS256 keys from AWS Secrets Manager in production
    if settings.USE_AWS_SECRETS:
        _load_keys_from_secrets_manager()

    # 2. Initialize Redis
    await init_redis()

    # 3. Create DB tables (dev convenience — use Alembic migrations in prod)
    if settings.ENV == "development":
        async with engine.begin() as conn:
            # Ensure the auth_schema exists
            await conn.execute(
                __import__("sqlalchemy").text("CREATE SCHEMA IF NOT EXISTS auth_schema")
            )
            await conn.run_sync(Base.metadata.create_all)
        logger.info("DB tables created/verified (dev mode)")

    # 4. Seed bootstrap admin if not present
    await _seed_bootstrap_admin()

    logger.info("Auth Service startup complete ✓")
    yield

    # Shutdown
    await close_redis()
    await engine.dispose()
    logger.info("Auth Service shutdown complete")


def _load_keys_from_secrets_manager():
    """Fetch RS256 keypair from AWS Secrets Manager and inject into settings."""
    import boto3
    import json

    client = boto3.client("secretsmanager", region_name=settings.AWS_REGION)
    try:
        response = client.get_secret_value(SecretId=settings.AWS_SECRET_NAME_RS256)
        secret = json.loads(response["SecretString"])
        # Mutate settings (safe since Settings is loaded once)
        settings.JWT_RS256_PRIVATE_KEY = secret["private_key"]
        settings.JWT_RS256_PUBLIC_KEY = secret["public_key"]
        logger.info("RS256 keypair loaded from AWS Secrets Manager")
    except Exception as e:
        logger.critical(f"Failed to load RS256 keys from Secrets Manager: {e}")
        raise


async def _seed_bootstrap_admin():
    """Create the first superadmin account if no admins exist."""
    from sqlalchemy import select, func
    from app.models import Admin
    from passlib.context import CryptContext
    from uuid import uuid4

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

    async with AsyncSessionLocal() as session:
        count = await session.execute(select(func.count()).select_from(Admin))
        if count.scalar() == 0:
            bootstrap = Admin(
                admin_id=uuid4(),
                email=settings.BOOTSTRAP_ADMIN_EMAIL,
                password_hash=pwd_ctx.hash(settings.BOOTSTRAP_ADMIN_PASSWORD),
                full_name="NHAI Super Admin",
                role="superadmin",
                is_active=True,
            )
            session.add(bootstrap)
            await session.commit()
            logger.warning(
                f"Bootstrap admin created: {settings.BOOTSTRAP_ADMIN_EMAIL} "
                f"— CHANGE THE PASSWORD IMMEDIATELY"
            )


# ── App Factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="NHAI Auth Service",
    version=settings.APP_VERSION,
    description=(
        "Identity and access management service for the NHAI Biometric Attendance Platform. "
        "Issues RS256 JWTs for field devices and admin users. "
        "Manages ECDSA P-256 device public key registry."
    ),
    docs_url="/docs" if settings.ENV != "production" else None,
    redoc_url="/redoc" if settings.ENV != "production" else None,
    lifespan=lifespan,
)


# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENV == "development" else [],
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Internal-Api-Key"],
)


# ── Global exception handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_code": "INTERNAL_ERROR"},
    )


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(admin_router.router)
app.include_router(device_router.router)
app.include_router(token_router.router)


# ── Health + metadata endpoints ───────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe for ECS / ALB health checks."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.ENV,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@app.get("/", tags=["Meta"], include_in_schema=False)
async def root():
    return {"service": settings.APP_NAME, "docs": "/docs"}
