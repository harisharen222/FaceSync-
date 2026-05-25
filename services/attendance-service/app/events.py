import json
import logging
import boto3
from typing import Dict, Any

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

events_client = boto3.client('events', region_name=settings.AWS_REGION) if hasattr(settings, 'AWS_REGION') else None

def emit_event(detail_type: str, detail: Dict[str, Any]):
    if not events_client:
        return
        
    try:
        events_client.put_events(
            Entries=[
                {
                    'Source': 'nhai.attendance',
                    'DetailType': detail_type,
                    'Detail': json.dumps(detail),
                    'EventBusName': getattr(settings, 'EVENT_BUS_NAME', 'nhai-event-bus')
                }
            ]
        )
    except Exception as e:
        logger.error(f"Failed to emit event {detail_type}: {e}")
