"""
sqs_consumer.py — Synchronous background worker polling SQS.

This runs as a background task (or separate ECS process).
It pulls verified records from SQS, inserts them into PostgreSQL,
and emits an `AttendanceVerified` event to EventBridge.
"""
import json
import logging
import time
from typing import Any, Dict

import boto3
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

from app.config import get_settings
from app.database import SyncSessionLocal
from app.models import AttendanceRecord, DeduplicationIndex
from app.validator import compute_dedup_hash

logger = logging.getLogger(__name__)
settings = get_settings()

sqs_client = boto3.client('sqs', region_name=settings.AWS_REGION)
events_client = boto3.client('events', region_name=settings.AWS_REGION)


def process_message(msg_body: str) -> None:
    """Process a single SQS message payload."""
    data = json.loads(msg_body)
    
    # 1. Prepare DB objects
    iso_time = data["timestamp_utc"]
    dedup_hash = compute_dedup_hash(data["worker_id"], data["device_id"], iso_time)
    
    db_record = AttendanceRecord(
        id=data["id"],
        worker_id=data["worker_id"],
        device_id=data["device_id"],
        timestamp_utc=iso_time,
        confidence=data.get("confidence"),
        liveness_score=data.get("liveness_score"),
        liveness_passed=data["liveness_passed"],
        site_code=data["site_code"],
        ecdsa_signature=data["signature_hex"],
        status="VERIFIED"
    )
    
    db_dedup = DeduplicationIndex(dedup_hash=dedup_hash)
    
    # 2. Database Insert (transactional)
    with SyncSessionLocal() as session:
        try:
            session.add(db_dedup)
            session.add(db_record)
            session.commit()
            logger.info(f"Database write successful: record {db_record.id}")
            
        except IntegrityError:
            session.rollback()
            logger.warning(f"Duplicate constraint hit for {db_record.id} in consumer worker")
            # If it's a duplicate, we consider it "processed" so SQS deletes it
            return
        except Exception as e:
            session.rollback()
            logger.error(f"Database write failed for {db_record.id}: {e}")
            raise  # Let SQS visibility timeout handle retry

    # 3. Emit EventBridge Event (fire-and-forget for downstream services)
    try:
        event_detail = {
            "worker_id": data["worker_id"],
            "site_code": data["site_code"],
            "timestamp_utc": iso_time,
            "liveness_score": data.get("liveness_score"),
            "confidence": data.get("confidence")
        }
        
        events_client.put_events(
            Entries=[
                {
                    'Source': 'nhai.attendance',
                    'DetailType': 'AttendanceVerified',
                    'Detail': json.dumps(event_detail),
                    'EventBusName': settings.EVENT_BUS_NAME
                }
            ]
        )
        logger.debug(f"Emitted AttendanceVerified event for {db_record.id}")
    except Exception as e:
        logger.error(f"Failed to emit EventBridge event for {db_record.id}: {e}")
        # We don't fail the message if EventBridge fails; DB write was successful.
        # In a perfectly resilient system, we might use the Outbox Pattern instead.


def run_worker_loop():
    """Long-polling SQS consumer loop."""
    logger.info(f"Starting SQS consumer worker on {settings.SQS_QUEUE_URL}")
    
    while True:
        try:
            response = sqs_client.receive_message(
                QueueUrl=settings.SQS_QUEUE_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20  # Long polling
            )
            
            messages = response.get('Messages', [])
            if not messages:
                continue
                
            for msg in messages:
                try:
                    process_message(msg['Body'])
                    
                    # Delete message on success
                    sqs_client.delete_message(
                        QueueUrl=settings.SQS_QUEUE_URL,
                        ReceiptHandle=msg['ReceiptHandle']
                    )
                except Exception as e:
                    logger.error(f"Failed to process message {msg['MessageId']}: {e}")
                    # Don't delete — SQS visibility timeout will return it to queue
                    
        except Exception as e:
            logger.error(f"SQS polling error: {e}")
            time.sleep(5)  # Backoff on AWS errors


if __name__ == "__main__":
    # Can run this file directly to start the worker
    run_worker_loop()
