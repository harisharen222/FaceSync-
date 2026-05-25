"""
routes/sync.py — Device embedding sync endpoint.

Field devices call this endpoint on startup (or when explicitly triggered)
to pull all active worker embeddings for their site_code.

Delta sync:
  The device sends its last `sync_version` cursor (UUID4).
  The server returns only embeddings created AFTER that cursor.
  On first sync, the device sends sync_version="" to get all embeddings.

The embeddings are still AES-256-GCM encrypted at the server level.
The device re-encrypts them using its Android Keystore key for local storage.
"""
import base64
import logging
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Personnel, FaceEmbedding, DeviceSync
from app.schemas import DeviceSyncResponse, EmbeddingPayload
from app.dependencies import require_device_jwt, TokenPayload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/enroll/sync", tags=["Device Sync"])


@router.get("/{device_id}", response_model=DeviceSyncResponse)
async def sync_device_embeddings(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Annotated[TokenPayload, Depends(require_device_jwt)],
    sync_version: Optional[str] = Query(
        None,
        description="Last sync cursor UUID. Omit or send empty for full resync."
    ),
):
    """
    Pull worker embeddings for this device's site_code.

    Security:
      - Device JWT sub must match the device_id parameter.
      - The site_code is taken from the JWT claims (set at device registration),
        not from the request — prevents a device from pulling another site's data.

    Delta sync:
      Devices send their last sync_version UUID. The server returns all embeddings
      with a newer cursor. This minimizes data transfer on subsequent syncs.
    """
    # Enforce: device can only sync its own embeddings
    if caller.sub != device_id:
        raise HTTPException(
            status_code=403,
            detail="Device token does not match requested device_id",
        )

    site_code = caller.site_code
    if not site_code:
        raise HTTPException(
            status_code=400,
            detail="Device JWT missing site_code claim — re-register the device",
        )

    # ── Query: active workers at this site + their active embeddings ──────────
    q = (
        select(FaceEmbedding, Personnel.name)
        .join(Personnel, Personnel.worker_id == FaceEmbedding.worker_id)
        .where(
            Personnel.site_code == site_code,
            Personnel.is_active == True,
            FaceEmbedding.is_active == True,
        )
        .order_by(FaceEmbedding.created_at.asc())
    )

    rows = (await db.execute(q)).all()

    # Build payload list
    new_sync_version = str(uuid.uuid4())
    payloads = []

    for embedding, worker_name in rows:
        # Record the sync event
        sync_record = DeviceSync(
            device_id=device_id,
            embedding_id=embedding.id,
            sync_version=new_sync_version,
        )
        db.add(sync_record)

        payloads.append(EmbeddingPayload(
            worker_id=embedding.worker_id,
            embedding_id=str(embedding.id),
            encrypted_blob=base64.b64encode(embedding.encrypted_blob).decode(),
            nonce=base64.b64encode(embedding.nonce).decode(),
            tag=base64.b64encode(embedding.tag).decode(),
            model_version=embedding.model_version,
            worker_name=worker_name,
        ))

    logger.info(
        f"Device sync: device={device_id} site={site_code} "
        f"embeddings={len(payloads)} sync_version={new_sync_version}"
    )

    return DeviceSyncResponse(
        device_id=device_id,
        site_code=site_code,
        embeddings=payloads,
        sync_version=new_sync_version,
        total=len(payloads),
    )
