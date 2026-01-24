"""
Security Middleware
====================

Adds security headers and HTTPS enforcement.
"""

import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, RedirectResponse

# Security configuration
ENFORCE_HTTPS = os.environ.get("ENFORCE_HTTPS", "false").lower() in ("true", "1", "yes")
HSTS_MAX_AGE = int(os.environ.get("HSTS_MAX_AGE", "31536000"))  # 1 year default


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.

    Headers added:
    - Strict-Transport-Security (HSTS)
    - X-Content-Type-Options
    - X-Frame-Options
    - X-XSS-Protection
    - Referrer-Policy
    - Content-Security-Policy (basic)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # HTTPS enforcement (skip in development)
        if ENFORCE_HTTPS and request.url.scheme != "https":
            # Check for proxy headers
            forwarded_proto = request.headers.get("x-forwarded-proto", "")
            if forwarded_proto != "https":
                # Redirect to HTTPS
                url = str(request.url).replace("http://", "https://", 1)
                return RedirectResponse(url, status_code=301)

        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # HSTS header (only on HTTPS or if proxied)
        is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        if is_https:
            response.headers["Strict-Transport-Security"] = f"max-age={HSTS_MAX_AGE}; includeSubDomains"

        # Basic CSP - adjust based on your frontend needs
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "  # Required for React dev
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp

        return response
