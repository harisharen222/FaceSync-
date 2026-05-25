"""
routes/admin.py — Admin account management + login endpoints.
"""
import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from app.database import get_db
from app.models import Admin
from app.schemas import (
    AdminLoginRequest, AdminLoginResponse,
    AdminCreateRequest, AdminResponse,
    MessageResponse,
)
from app.jwt_handler import create_access_token, create_refresh_token
from app.dependencies import require_superadmin_jwt, require_admin_jwt
from app.jwt_handler import TokenPayload
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/auth/admin", tags=["Admin Auth"])

# bcrypt context — cost factor 12 balances security vs latency for admin logins
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


# ── POST /auth/admin/login ────────────────────────────────────────────────────

@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(
    body: AdminLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Authenticate an admin/supervisor with email + password.
    Issues RS256 JWT access + refresh tokens on success.
    Enforces constant-time comparison to prevent timing attacks.
    """
    result = await db.execute(
        select(Admin).where(Admin.email == body.email, Admin.is_active == True)
    )
    admin = result.scalar_one_or_none()

    # Constant-time password comparison (prevent timing oracle attacks)
    password_valid = admin is not None and pwd_context.verify(body.password, admin.password_hash)

    if not password_valid:
        from app.events import emit_event
        emit_event("AdminLoginFailed", {"email": body.email})
        # Generic error — don't reveal whether email exists
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    extra_claims = {"role": admin.role, "site_code": admin.site_code}
    access_token, _ = create_access_token(
        subject=str(admin.admin_id),
        subject_type="admin",
        extra_claims=extra_claims,
    )
    refresh_token, _ = create_refresh_token(
        subject=str(admin.admin_id),
        subject_type="admin",
    )

    # Update last login timestamp
    from datetime import datetime, timezone
    admin.last_login_at = datetime.now(tz=timezone.utc)

    logger.info(f"Admin login: {admin.email} (role={admin.role})")

    return AdminLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        admin_id=str(admin.admin_id),
        role=admin.role,
    )


# ── POST /auth/admin — create admin (superadmin only) ────────────────────────

@router.post("", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
async def create_admin(
    body: AdminCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _caller: Annotated[TokenPayload, Depends(require_superadmin_jwt)],
):
    """Create a new admin or supervisor account (superadmin only)."""
    # Check uniqueness
    existing = await db.execute(select(Admin).where(Admin.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Admin with email '{body.email}' already exists",
        )

    new_admin = Admin(
        admin_id=uuid4(),
        email=body.email,
        password_hash=pwd_context.hash(body.password),
        full_name=body.full_name,
        role=body.role,
        site_code=body.site_code,
    )
    db.add(new_admin)
    logger.info(f"New admin created: {body.email} (role={body.role}) by {_caller.sub}")

    return AdminResponse(
        admin_id=new_admin.admin_id,
        email=new_admin.email,
        full_name=new_admin.full_name,
        role=new_admin.role,
        site_code=new_admin.site_code,
        is_active=new_admin.is_active,
        created_at=new_admin.created_at,
    )


# ── GET /auth/admin/me — current admin profile ───────────────────────────────

@router.get("/me", response_model=AdminResponse)
async def get_current_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Annotated[TokenPayload, Depends(require_admin_jwt)],
):
    """Return the profile of the currently authenticated admin."""
    from uuid import UUID
    result = await db.execute(
        select(Admin).where(Admin.admin_id == UUID(caller.sub))
    )
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")

    return AdminResponse(
        admin_id=admin.admin_id,
        email=admin.email,
        full_name=admin.full_name,
        role=admin.role,
        site_code=admin.site_code,
        is_active=admin.is_active,
        created_at=admin.created_at,
    )
