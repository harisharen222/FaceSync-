import json
import logging
import time

import boto3
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()

sqs_client = boto3.client('sqs', region_name=settings.AWS_REGION)

def process_message(msg_body: str) -> None:
    data = json.loads(msg_body)
    
    event_id = data.get("id")
    detail_type = data.get("detail-type")
    detail = data.get("detail", {})
    
    # Mock sending notification
    logger.info("=========================================")
    logger.info("🔔  NEW NOTIFICATION  🔔")
    logger.info(f"Event ID: {event_id}")
    logger.info(f"Type: {detail_type}")
    
    if detail_type == "SpoofingDetected":
        logger.warning(f"🚨 ALERT: Spoofing attempt detected!")
        logger.warning(f"Worker: {detail.get('worker_id')} at Site: {detail.get('site_code')}")
        
    elif detail_type == "AdminLoginFailed":
        logger.warning(f"🚨 ALERT: Admin login failed!")
        logger.warning(f"Email: {detail.get('email')}")
        
    elif detail_type == "WorkerEnrolled":
        logger.info(f"✅ Worker enrolled successfully!")
        logger.info(f"Worker: {detail.get('worker_id')} Name: {detail.get('name')}")
        
    logger.info("=========================================")

def run_worker_loop():
    logger.info(f"Starting Notification SQS consumer on {settings.SQS_QUEUE_URL}")
    
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
