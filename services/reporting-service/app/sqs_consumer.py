import json
import logging
import time
import datetime
import boto3
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.database import SyncSessionLocal
from app.models import WorkerRoster, DailyAttendance

logger = logging.getLogger(__name__)
settings = get_settings()

sqs_client = boto3.client('sqs', region_name=settings.AWS_REGION)

def process_message(msg_body: str) -> None:
    data = json.loads(msg_body)
    detail_type = data.get("detail-type")
    detail = data.get("detail", {})
    
    if detail_type == "WorkerEnrolled":
        with SyncSessionLocal() as session:
            try:
                # Upsert into WorkerRoster
                stmt = insert(WorkerRoster).values(
                    worker_id=detail["worker_id"],
                    site_code=detail["site_code"],
                    name=detail["name"],
                    is_active=True
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=['worker_id'],
                    set_={"is_active": True, "site_code": detail["site_code"], "name": detail["name"]}
                )
                session.execute(stmt)
                session.commit()
                logger.info(f"Updated roster for worker {detail['worker_id']}")
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to update roster: {e}")
                raise

    elif detail_type == "AttendanceVerified":
        # Extract date from timestamp_utc string
        iso_time = detail["timestamp_utc"]
        # Parse ISO8601 (e.g. 2026-05-25T10:00:00Z)
        try:
            dt = datetime.datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
            date_val = dt.date()
        except Exception:
            date_val = datetime.date.today() # fallback
            
        with SyncSessionLocal() as session:
            try:
                # Try to insert first_scan. If conflict, ignore (we only care about first scan)
                stmt = insert(DailyAttendance).values(
                    worker_id=detail["worker_id"],
                    site_code=detail["site_code"],
                    date=date_val,
                    first_scan_utc=iso_time
                )
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=['worker_id', 'date']
                )
                session.execute(stmt)
                session.commit()
                logger.info(f"Recorded attendance for worker {detail['worker_id']} on {date_val}")
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to record attendance: {e}")
                raise


def run_worker_loop():
    logger.info(f"Starting SQS consumer worker on {settings.SQS_QUEUE_URL}")
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
                    logger.error(f"Failed to process message {msg.get('MessageId')}: {e}")
        except Exception as e:
            logger.error(f"SQS polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_worker_loop()
