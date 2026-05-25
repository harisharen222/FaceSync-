"""
s3_client.py — AWS S3 / CloudFront integration.
"""
import logging
from typing import Optional
import aioboto3
from botocore.config import Config

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_session = aioboto3.Session()
_boto_config = Config(signature_version='s3v4')

# Handle LocalStack custom endpoint if provided
_client_kwargs = {
    "region_name": settings.AWS_REGION,
    "config": _boto_config,
}
if settings.S3_ENDPOINT_URL:
    _client_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL


async def upload_model_file(s3_key: str, file_bytes: bytes, content_type: str = "application/octet-stream") -> bool:
    """Upload a raw model binary to S3."""
    try:
        async with _session.client('s3', **_client_kwargs) as s3:
            await s3.put_object(
                Bucket=settings.MODEL_BUCKET_NAME,
                Key=s3_key,
                Body=file_bytes,
                ContentType=content_type
            )
            return True
    except Exception as e:
        logger.error(f"S3 Upload failed for {s3_key}: {e}")
        return False


async def generate_presigned_url(s3_key: str, expiration: int = None) -> Optional[str]:
    """
    Generate a pre-signed URL for secure, temporary download access.
    
    In production, this would ideally use CloudFront Signed URLs for edge caching.
    For simplicity in this architecture phase (and compatibility with LocalStack),
    we generate an S3 presigned URL. If a CloudFront domain is provided, we can
    rewrite the domain, assuming the S3 bucket allows CloudFront OAC.
    """
    if expiration is None:
        expiration = settings.PRESIGNED_URL_EXPIRY_SECONDS

    try:
        async with _session.client('s3', **_client_kwargs) as s3:
            url = await s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.MODEL_BUCKET_NAME, 'Key': s3_key},
                ExpiresIn=expiration
            )
            
            # If we have a CloudFront domain configured, rewrite the URL host.
            # Note: Pure S3 presigned URLs work through CloudFront *only if* CloudFront
            # forwards the exact query string and the Host header isn't tampered with, 
            # OR if we use CloudFront's native KeyPair signing (which is more complex).
            # For this MVP/LocalStack phase, if CLOUDFRONT_DOMAIN is missing, we just return the S3 URL.
            if settings.CLOUDFRONT_DOMAIN:
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(url)
                url = urlunparse(parsed._replace(netloc=settings.CLOUDFRONT_DOMAIN))
                
            return url
    except Exception as e:
        logger.error(f"Failed to generate presigned URL for {s3_key}: {e}")
        return None
