"""
Middleware Package
==================

FastAPI middleware for rate limiting, logging, etc.
"""

from .rate_limit import (
    RateLimitMiddleware,
    RateLimiter,
    get_rate_limiter,
    check_document_quota,
    check_ocr_quota,
    increment_document_quota,
    increment_ocr_quota
)

__all__ = [
    "RateLimitMiddleware",
    "RateLimiter",
    "get_rate_limiter",
    "check_document_quota",
    "check_ocr_quota",
    "increment_document_quota",
    "increment_ocr_quota",
]
