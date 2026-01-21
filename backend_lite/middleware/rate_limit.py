"""
Rate Limiting Middleware
========================

Redis-based rate limiting for API endpoints.
"""

import os
import time
import logging
from typing import Optional, Callable
from datetime import datetime

from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Configuration from environment
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Rate limits
RATE_LIMIT_PER_USER = int(os.environ.get("RATE_LIMIT_PER_USER", "30"))  # requests per minute
RATE_LIMIT_PER_FIRM = int(os.environ.get("RATE_LIMIT_PER_FIRM", "200"))  # requests per minute
RATE_LIMIT_ANALYZE = int(os.environ.get("RATE_LIMIT_ANALYZE", "5"))  # analyze requests per minute

# Daily quotas
MAX_DOCS_PER_DAY = int(os.environ.get("MAX_DOCS_PER_DAY_PER_FIRM", "1000"))
MAX_OCR_PAGES_PER_DAY = int(os.environ.get("MAX_OCR_PAGES_PER_DAY_PER_FIRM", "5000"))

# Try to import Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available. Rate limiting disabled.")


class RateLimiter:
    """
    Redis-based rate limiter using sliding window algorithm.
    """

    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self._client = None

    @property
    def client(self):
        """Lazy-load Redis client"""
        if not REDIS_AVAILABLE:
            return None

        if self._client is None:
            try:
                self._client = redis.from_url(
                    self.redis_url,
                    decode_responses=True
                )
                self._client.ping()  # Test connection
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self._client = None

        return self._client

    def is_allowed(
        self,
        key: str,
        limit: int,
        window_seconds: int = 60
    ) -> tuple:
        """
        Check if request is allowed under rate limit.

        Args:
            key: Rate limit key (e.g., "user:123")
            limit: Maximum requests allowed
            window_seconds: Time window in seconds

        Returns:
            (is_allowed, remaining, reset_time)
        """
        if not self.client:
            # No Redis - allow all
            return (True, limit, 0)

        now = time.time()
        window_start = now - window_seconds

        try:
            pipe = self.client.pipeline()

            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start)

            # Count current requests
            pipe.zcard(key)

            # Add current request
            pipe.zadd(key, {str(now): now})

            # Set expiry
            pipe.expire(key, window_seconds)

            results = pipe.execute()
            current_count = results[1]

            remaining = max(0, limit - current_count - 1)
            reset_time = int(now + window_seconds)

            if current_count >= limit:
                return (False, 0, reset_time)

            return (True, remaining, reset_time)

        except Exception as e:
            logger.warning(f"Rate limit check failed: {e}")
            return (True, limit, 0)

    def check_daily_quota(
        self,
        key: str,
        limit: int
    ) -> tuple:
        """
        Check daily quota.

        Args:
            key: Quota key
            limit: Daily limit

        Returns:
            (is_allowed, remaining)
        """
        if not self.client:
            return (True, limit)

        today = datetime.utcnow().strftime("%Y-%m-%d")
        quota_key = f"quota:{today}:{key}"

        try:
            current = self.client.get(quota_key)
            current = int(current) if current else 0

            if current >= limit:
                return (False, 0)

            return (True, limit - current)

        except Exception as e:
            logger.warning(f"Quota check failed: {e}")
            return (True, limit)

    def increment_quota(self, key: str, amount: int = 1):
        """Increment daily quota counter"""
        if not self.client:
            return

        today = datetime.utcnow().strftime("%Y-%m-%d")
        quota_key = f"quota:{today}:{key}"

        try:
            pipe = self.client.pipeline()
            pipe.incrby(quota_key, amount)
            pipe.expire(quota_key, 86400 * 2)  # 2 days TTL
            pipe.execute()
        except Exception as e:
            logger.warning(f"Quota increment failed: {e}")


# Singleton rate limiter
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get singleton rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.
    """

    def __init__(self, app):
        super().__init__(app)
        self.limiter = get_rate_limiter()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/", "/docs", "/openapi.json"]:
            return await call_next(request)

        # Get user and firm IDs from headers
        user_id = request.headers.get("X-User-Id")
        firm_id = request.headers.get("X-Firm-Id")

        # Check user rate limit
        if user_id:
            user_key = f"ratelimit:user:{user_id}"

            # Use stricter limit for analyze endpoints
            limit = RATE_LIMIT_ANALYZE if "/analyze" in request.url.path else RATE_LIMIT_PER_USER

            allowed, remaining, reset = self.limiter.is_allowed(
                user_key, limit, window_seconds=60
            )

            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "detail": f"User limit: {limit} requests per minute",
                        "retry_after": reset - int(time.time())
                    },
                    headers={
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset),
                        "Retry-After": str(reset - int(time.time()))
                    }
                )

        # Check firm rate limit
        if firm_id:
            firm_key = f"ratelimit:firm:{firm_id}"

            allowed, remaining, reset = self.limiter.is_allowed(
                firm_key, RATE_LIMIT_PER_FIRM, window_seconds=60
            )

            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "detail": f"Firm limit: {RATE_LIMIT_PER_FIRM} requests per minute",
                        "retry_after": reset - int(time.time())
                    },
                    headers={
                        "X-RateLimit-Limit": str(RATE_LIMIT_PER_FIRM),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset),
                        "Retry-After": str(reset - int(time.time()))
                    }
                )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        if user_id:
            response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_PER_USER)
            response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response


def check_document_quota(firm_id: str, count: int = 1) -> bool:
    """
    Check if firm has document upload quota remaining.

    Args:
        firm_id: Firm ID
        count: Number of documents to upload

    Returns:
        True if allowed
    """
    limiter = get_rate_limiter()
    allowed, remaining = limiter.check_daily_quota(
        f"docs:{firm_id}",
        MAX_DOCS_PER_DAY
    )
    return allowed and remaining >= count


def check_ocr_quota(firm_id: str, pages: int = 1) -> bool:
    """
    Check if firm has OCR page quota remaining.

    Args:
        firm_id: Firm ID
        pages: Number of pages to OCR

    Returns:
        True if allowed
    """
    limiter = get_rate_limiter()
    allowed, remaining = limiter.check_daily_quota(
        f"ocr:{firm_id}",
        MAX_OCR_PAGES_PER_DAY
    )
    return allowed and remaining >= pages


def increment_document_quota(firm_id: str, count: int = 1):
    """Increment document upload counter"""
    limiter = get_rate_limiter()
    limiter.increment_quota(f"docs:{firm_id}", count)


def increment_ocr_quota(firm_id: str, pages: int = 1):
    """Increment OCR page counter"""
    limiter = get_rate_limiter()
    limiter.increment_quota(f"ocr:{firm_id}", pages)
