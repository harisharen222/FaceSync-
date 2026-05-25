"""
routes/sync.py — Attendance offline-sync ingress endpoint.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import SyncBatchRequest, SyncBatchResponse
from app.auth_client import get_device_public_key, AuthClientError
from app.validator import process_record, compute_dedup_hash, is_duplicate
from app.sqs_producer import enqueue_verified_records
from app.dependencies import require_device_jwt, TokenPayload
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/attendance/sync", tags=["Device Sync"])


@router.post("", response_model=SyncBatchResponse)
async def sync_offline_attendance(
    body: SyncBatchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Annotated[TokenPayload, Depends(require_device_jwt)],
):
    """
    Ingest a batch of signed offline attendance records from a field device.
    
    Flow:
    1. Verify JWT belongs to the requesting device.
    2. Fetch device's ECDSA public key from Auth Service (cached).
    3. Loop through records:
       a. Verify ECDSA signature of payload.
       b. Check deduplication hash (PostgreSQL).
    4. Enqueue valid records to SQS for background DB insert.
    """
    if caller.sub != body.device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="JWT device_id does not match request body device_id",
        )
        
    site_code = caller.site_code
    if not site_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device JWT missing site_code claim",
        )
        
    if not body.records:
        return SyncBatchResponse(accepted=0, rejected=0, message="Empty batch")
        
    if len(body.records) > settings.MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Max batch size is {settings.MAX_BATCH_SIZE}",
        )

    # Fetch public key from Auth Service
    try:
        public_key_pem = await get_device_public_key(body.device_id)
        if not public_key_pem:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Device is inactive or not found in Auth Service",
            )
    except AuthClientError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    valid_records_to_enqueue = []
    errors = []
    accepted = 0
    rejected = 0

    for record in body.records:
        is_valid, record_status, err_msg = await process_record(
            db=db,
            record=record,
            device_id=body.device_id,
            public_key_pem=public_key_pem
        )
        
        if is_valid:
            # Prepare payload for SQS (add site_code from JWT)
            record_dict = record.model_dump()
            record_dict["site_code"] = site_code
            record_dict["device_id"] = body.device_id
            
            # Reformat datetime to ISO for JSON serialization
            record_dict["timestamp_utc"] = record_dict["timestamp_utc"].isoformat()
            
            valid_records_to_enqueue.append(record_dict)
            accepted += 1
        else:
            rejected += 1
            if record_status != "DUPLICATE":
                errors.append({
                    "record_id": str(record.id),
                    "error": err_msg,
                    "status": record_status
                })

    # Push valid records to SQS
    if valid_records_to_enqueue:
        await enqueue_verified_records(valid_records_to_enqueue)

    return SyncBatchResponse(
        accepted=accepted,
        rejected=rejected,
        errors=errors,
        message=f"Batch processed. Enqueued {accepted} records for writing."
    )
