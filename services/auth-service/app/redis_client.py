"""
redis_client.py — Redis-backed token blacklist for the Auth Service.

Two complementary stores:
  1. Redis (primary) — O(1) lookups, TTL-based auto-expiry, sub-millisecond
  2. PostgreSQL TokenBlacklist table (backup) — survives Redis flush/cold-start

On every authenticated request, the JWT bearer dependency checks Redis first.
If Redis is unreachable, it falls back to the DB check.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Singleton Redis client ────────────────────────────────────────────────────
# Created once at app startup in lifespan(). Reused across all requests.
_redis_client: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized. Call init_redis() at startup.")
    return _redis_client


async def init_redis() -> aioredis.Redis:
    """Call this in FastAPI lifespan startup."""
    global _redis_client
    _redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )
    await _redis_client.ping()
    logger.info("Redis connection established")
    return _redis_client


async def close_redis():
    """Call this in FastAPI lifespan shutdown."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed")


# ── Blacklist operations ──────────────────────────────────────────────────────

def _blacklist_key(jti: str) -> str:
    return f"nhai:auth:blacklist:{jti}"


async def blacklist_token(jti: str, expires_at: datetime) -> bool:
    """
    Add a JTI to the Redis blacklist.
    TTL is set to the token's remaining lifetime so Redis auto-purges expired entries.
    """
    try:
        redis = get_redis()
        now = datetime.now(tz=timezone.utc)
        ttl_seconds = max(1, int((expires_at - now).total_seconds()))
        await redis.setex(_blacklist_key(jti), ttl_seconds, "1")
        logger.info(f"Token {jti} blacklisted (TTL={ttl_seconds}s)")
        return True
    except Exception as e:
        logger.error(f"Redis blacklist write failed for JTI {jti}: {e}")
        return False


async def is_token_blacklisted(jti: str) -> bool:
    """
    Returns True if the JTI exists in the Redis blacklist.
    Falls back to False (allow) if Redis is unreachable — DB check should follow.
    """
    try:
        redis = get_redis()
        result = await redis.exists(_blacklist_key(jti))
        return result > 0
    except Exception as e:
        logger.error(f"Redis blacklist read failed for JTI {jti}: {e}. Allowing request.")
        return False


# ── Challenge cache (device auth handshake) ───────────────────────────────────

def _challenge_key(device_id: str) -> str:
    return f"nhai:auth:challenge:{device_id}"


async def store_challenge(device_id: str, challenge: str, ttl_seconds: int = 60) -> None:
    """Store a device authentication challenge in Redis with a 60-second TTL."""
    try:
        redis = get_redis()
        await redis.setex(_challenge_key(device_id), ttl_seconds, challenge)
    except Exception as e:
        logger.error(f"Failed to store challenge in Redis for device {device_id}: {e}")
        raise


async def consume_challenge(device_id: str) -> Optional[str]:
    """
    Atomically retrieve and delete the pending challenge for a device.
    Returns None if the challenge doesn't exist or has expired.
    """
    try:
        redis = get_redis()
        challenge = await redis.getdel(_challenge_key(device_id))
        return challenge
    except Exception as e:
        logger.error(f"Failed to consume challenge from Redis for device {device_id}: {e}")
        return None
