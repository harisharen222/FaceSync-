import json
import logging
import time
from datetime import datetime

import boto3
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import SyncSessionLocal
from app.models import AuditLog

logger = logging.getLogger(__name__)
settings = get_settings()

sqs_client = boto3.client('sqs', region_name=settings.AWS_REGION)

def process_message(msg_body: str) -> None:
    data = json.loads(msg_body)
    
    # EventBridge payload
    event_id = data.get("id")
    source = data.get("source")
    detail_type = data.get("detail-type")
    time_str = data.get("time") # ISO8601
    detail = data.get("detail", {})

    if time_str:
        timestamp_utc = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
    else:
        timestamp_utc = datetime.utcnow()

    db_log = AuditLog(
        event_id=event_id,
        source=source,
        detail_type=detail_type,
        timestamp_utc=timestamp_utc,
        detail=detail
    )
    
    with SyncSessionLocal() as session:
        try:
            session.add(db_log)
            session.commit()
            logger.info(f"Audit log saved: {detail_type} from {source}")
        except Exception as e:
            session.rollback()
            logger.error(f"Database write failed for audit event {event_id}: {e}")
            raise

def run_worker_loop():
    logger.info(f"Starting Audit SQS consumer on {settings.SQS_QUEUE_URL}")
    
    while True:
        try:
            response = sqs_client.receive_message(
                QueueUrl=settings.SQS_QUEUE_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20
            )
            
            messages = response.get('Messages', [])
            if not messages:
                continue
                
            for msg in messages:
                try:
                    process_message(msg['Body'])
                    sqs_client.delete_message(
                        QueueUrl=settings.SQS_QUEUE_URL,
                        ReceiptHandle=msg['ReceiptHandle']
                    )
                except Exception as e:
                    logger.error(f"Failed to process message {msg['MessageId']}: {e}")
                    
        except Exception as e:
            logger.error(f"SQS polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_worker_loop()
