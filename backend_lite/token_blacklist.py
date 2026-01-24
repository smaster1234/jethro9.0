"""
Token Blacklist Management
==========================

Redis-backed token blacklist for fast JWT revocation checks.
Falls back to database if Redis is unavailable.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
BLACKLIST_PREFIX = "token:blacklist:"

# Try to import Redis
try:
    from redis import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not installed. Token blacklist will use database only.")

_redis_client: Optional['Redis'] = None


def get_redis_client() -> Optional['Redis']:
    """Get Redis client (singleton)."""
    global _redis_client

    if not REDIS_AVAILABLE:
        return None

    if _redis_client is None:
        try:
            _redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
            # Test connection
            _redis_client.ping()
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Using database fallback.")
            return None

    return _redis_client


def add_to_blacklist(jti: str, expires_at: datetime, token_type: str = "access") -> bool:
    """
    Add a token JTI to the blacklist.

    Args:
        jti: JWT ID (unique identifier)
        expires_at: When the token would naturally expire
        token_type: "access" or "refresh"

    Returns:
        True if successfully added to Redis, False if using database fallback
    """
    redis = get_redis_client()

    if redis:
        try:
            # Calculate TTL (time until natural expiration + buffer)
            ttl_seconds = max(int((expires_at - datetime.utcnow()).total_seconds()), 60)

            # Store in Redis with auto-expiration
            key = f"{BLACKLIST_PREFIX}{jti}"
            redis.setex(key, ttl_seconds, token_type)
            return True
        except Exception as e:
            logger.warning(f"Redis blacklist add failed: {e}")

    return False


def is_blacklisted(jti: str) -> bool:
    """
    Check if a token JTI is blacklisted.

    Checks Redis first (fast), then falls back to database if needed.

    Args:
        jti: JWT ID to check

    Returns:
        True if blacklisted, False otherwise
    """
    redis = get_redis_client()

    if redis:
        try:
            key = f"{BLACKLIST_PREFIX}{jti}"
            if redis.exists(key):
                return True
            # Not in Redis - might need to check database as fallback
            # for tokens blacklisted before Redis was available
        except Exception as e:
            logger.warning(f"Redis blacklist check failed: {e}")

    # Fallback: check database
    # This is called by the API layer which has database access
    return None  # Signal to caller to check database


def remove_expired_blacklist_entries(db_session) -> int:
    """
    Clean up expired blacklist entries from database.

    Should be run periodically (e.g., daily cron job).

    Args:
        db_session: SQLAlchemy database session

    Returns:
        Number of entries removed
    """
    from .db.models import TokenBlacklist

    result = db_session.query(TokenBlacklist).filter(
        TokenBlacklist.expires_at < datetime.utcnow()
    ).delete()

    db_session.commit()
    return result


def sync_to_redis(db_session, max_entries: int = 10000) -> int:
    """
    Sync active blacklist entries from database to Redis.

    Useful when starting up or after Redis restart.

    Args:
        db_session: SQLAlchemy database session
        max_entries: Maximum number of entries to sync

    Returns:
        Number of entries synced
    """
    from .db.models import TokenBlacklist

    redis = get_redis_client()
    if not redis:
        return 0

    entries = db_session.query(TokenBlacklist).filter(
        TokenBlacklist.expires_at > datetime.utcnow()
    ).limit(max_entries).all()

    count = 0
    for entry in entries:
        if add_to_blacklist(entry.jti, entry.expires_at, entry.token_type):
            count += 1

    logger.info(f"Synced {count} blacklist entries to Redis")
    return count


def get_blacklist_stats() -> dict:
    """Get statistics about the token blacklist."""
    redis = get_redis_client()

    stats = {
        "redis_available": redis is not None,
        "redis_count": 0
    }

    if redis:
        try:
            # Count keys with our prefix
            keys = redis.keys(f"{BLACKLIST_PREFIX}*")
            stats["redis_count"] = len(keys)
        except Exception as e:
            stats["redis_error"] = str(e)

    return stats
