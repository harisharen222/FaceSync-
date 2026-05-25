"""
auth_client.py — HTTP client for internal Auth Service endpoints.

Used by Attendance Service to fetch device public keys for signature verification.
Uses the X-Internal-Api-Key to bypass JWT authentication.
"""
import logging
from typing import Optional
import httpx
from async_lru import alru_cache

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthClientError(Exception):
    pass


@alru_cache(maxsize=1000, ttl=300)
async def get_device_public_key(device_id: str) -> Optional[str]:
    """
    Fetch a device's ECDSA public key from the Auth Service.
    Results are cached in memory for 5 minutes (ttl=300) to avoid slamming
    the Auth Service during large batch syncs.
    
    Returns:
        PEM string of the public key, or None if device not found.
    """
    url = f"{settings.AUTH_SERVICE_URL}/auth/device/{device_id}/pubkey"
    headers = {"X-Internal-Api-Key": settings.INTERNAL_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url, headers=headers)
            
            if resp.status_code == 404:
                logger.warning(f"Device public key not found for {device_id}")
                return None
                
            resp.raise_for_status()
            data = resp.json()
            
            if not data.get("is_active"):
                logger.warning(f"Device {device_id} is marked inactive in Auth Service")
                return None
                
            return data["public_key_pem"]
            
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch public key for {device_id}: {e}")
        raise AuthClientError("Internal Auth Service unavailable")
