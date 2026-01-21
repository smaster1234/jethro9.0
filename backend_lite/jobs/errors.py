"""
Shared job error types.

Placed in a separate module so tests (and other modules) can safely import the
same exception class even if `backend_lite.jobs.tasks` is reloaded.
"""


class ZipSecurityError(Exception):
    """Raised when ZIP file fails security checks."""

