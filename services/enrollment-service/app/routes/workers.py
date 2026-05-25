"""
routes/workers.py — Worker (Personnel) CRUD endpoints.
"""
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Personnel, FaceEmbedding
from app.schemas import WorkerCreateRequest, WorkerResponse, WorkerListResponse, MessageResponse
from app.dependencies import require_admin_jwt, TokenPayload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/enroll/worker", tags=["Workers"])


@router.post("", response_model=WorkerResponse, status_code=status.HTTP_201_CREATED)
async def create_worker(
    body: WorkerCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Annotated[TokenPayload, Depends(require_admin_jwt)],
):
    """
    Register a new worker in the personnel master table.
    No face template yet — follow with POST /enroll/worker/{id}/face.
    """
    existing = await db.execute(
        select(Personnel).where(Personnel.worker_id == body.worker_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Worker '{body.worker_id}' already exists.",
        )

    worker = Personnel(
        worker_id=body.worker_id,
        name=body.name,
        department=body.department,
        site_code=body.site_code,
        enrolled_by=caller.sub,
    )
    db.add(worker)
    logger.info(f"Worker created: {body.worker_id} by admin {caller.sub}")

    from app.events import emit_event
    emit_event("WorkerEnrolled", {
        "worker_id": body.worker_id,
        "name": body.name,
        "site_code": body.site_code,
        "enrolled_by": caller.sub
    })

    return WorkerResponse(
        worker_id=worker.worker_id,
        name=worker.name,
        department=worker.department,
        site_code=worker.site_code,
        enrolled_at=None,
        model_version=None,
        is_active=worker.is_active,
        has_embedding=False,
    )


@router.get("", response_model=WorkerListResponse)
async def list_workers(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[TokenPayload, Depends(require_admin_jwt)],
    site_code: Optional[str] = Query(None, description="Filter by site code"),
    active_only: bool = Query(True),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    """List all enrolled workers with optional site filter."""
    q = select(Personnel)
    if site_code:
        q = q.where(Personnel.site_code == site_code)
    if active_only:
        q = q.where(Personnel.is_active == True)

    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar()

    result = await db.execute(q.offset(offset).limit(limit))
    workers = result.scalars().all()

    # Bulk check which workers have embeddings
    worker_ids = [w.worker_id for w in workers]
    embed_q = select(FaceEmbedding.worker_id).where(
        FaceEmbedding.worker_id.in_(worker_ids),
        FaceEmbedding.is_active == True,
    )
    embedded_ids = set((await db.execute(embed_q)).scalars().all())

    return WorkerListResponse(
        total=total,
        workers=[
            WorkerResponse(
                worker_id=w.worker_id,
                name=w.name,
                department=w.department,
                site_code=w.site_code,
                enrolled_at=w.enrolled_at,
                model_version=w.model_version,
                is_active=w.is_active,
                has_embedding=w.worker_id in embedded_ids,
            )
            for w in workers
        ],
    )


@router.get("/{worker_id}", response_model=WorkerResponse)
async def get_worker(
    worker_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[TokenPayload, Depends(require_admin_jwt)],
):
    result = await db.execute(select(Personnel).where(Personnel.worker_id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status_code=404, detail=f"Worker '{worker_id}' not found")

    has_emb = (await db.execute(
        select(exists().where(FaceEmbedding.worker_id == worker_id, FaceEmbedding.is_active == True))
    )).scalar()

    return WorkerResponse(
        worker_id=worker.worker_id, name=worker.name,
        department=worker.department, site_code=worker.site_code,
        enrolled_at=worker.enrolled_at, model_version=worker.model_version,
        is_active=worker.is_active, has_embedding=bool(has_emb),
    )


@router.delete("/{worker_id}", response_model=MessageResponse)
async def deactivate_worker(
    worker_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[TokenPayload, Depends(require_admin_jwt)],
):
    """
    Soft-delete a worker. Marks personnel + all embeddings as inactive.
    The device sync mechanism will propagate this deactivation on next sync.
    """
    result = await db.execute(select(Personnel).where(Personnel.worker_id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status_code=404, detail=f"Worker '{worker_id}' not found")

    worker.is_active = False

    # Deactivate all embeddings
    embed_result = await db.execute(
        select(FaceEmbedding).where(FaceEmbedding.worker_id == worker_id)
    )
    for emb in embed_result.scalars().all():
        emb.is_active = False

    logger.info(f"Worker deactivated: {worker_id}")
    return MessageResponse(message=f"Worker '{worker_id}' deactivated successfully")
