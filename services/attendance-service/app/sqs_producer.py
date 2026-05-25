"""
sqs_producer.py — Async SQS publisher for verified attendance records.
"""
import json
import logging
from typing import List, Dict, Any

import aioboto3
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_session = aioboto3.Session()


async def enqueue_verified_records(records: List[Dict[str, Any]]):
    """
    Send a batch of verified records to SQS for background database insertion.
    SQS allows up to 10 messages per batch request.
    """
    if not records:
        return

    # SQS batch limit is 10
    chunks = [records[i:i + 10] for i in range(0, len(records), 10)]

    async with _session.client('sqs', region_name=settings.AWS_REGION) as sqs:
        for chunk in chunks:
            entries = []
            for record in chunk:
                entries.append({
                    'Id': str(record['id']),  # SQS batch entry ID
                    'MessageBody': json.dumps(record),
                    # Grouping by device ensures FIFO per device if using a FIFO queue
                    # (Standard queue doesn't need this, but good practice)
                    'MessageGroupId': record['device_id'] 
                })
            
            try:
                # In standard queue, MessageGroupId is ignored unless explicitly configured,
                # but we'll send it as a standard SendMessageBatch
                clean_entries = [{'Id': e['Id'], 'MessageBody': e['MessageBody']} for e in entries]
                
                resp = await sqs.send_message_batch(
                    QueueUrl=settings.SQS_QUEUE_URL,
                    Entries=clean_entries
                )
                
                if 'Failed' in resp and resp['Failed']:
                    logger.error(f"Failed to enqueue {len(resp['Failed'])} records: {resp['Failed']}")
                else:
                    logger.debug(f"Successfully enqueued {len(resp.get('Successful', []))} records")
                    
            except Exception as e:
                logger.error(f"SQS batch send failed: {e}")
                # Depending on reliability requirements, we might raise here to fail the sync request,
                # or log and rely on the device retrying later.
                raise
