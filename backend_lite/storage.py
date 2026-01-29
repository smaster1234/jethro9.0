"""
Storage Backend
===============

Pluggable storage for document files.

Supports:
- LocalStorage: filesystem-based (default, suitable for single-node / Railway)
- S3Storage: S3-compatible object storage (AWS S3, Cloudflare R2, MinIO, etc.)

Configuration via environment variables:
- STORAGE_BACKEND: "local" (default) or "s3"
- STORAGE_PATH: base directory for local storage (default: ./storage)
- S3_BUCKET, S3_ENDPOINT, S3_REGION, S3_ACCESS_KEY / AWS_ACCESS_KEY_ID,
  S3_SECRET_KEY / AWS_SECRET_ACCESS_KEY
"""

import hashlib
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Storage metadata returned by put()
# ---------------------------------------------------------------------------

@dataclass
class StorageMeta:
    """Metadata returned after storing a file."""
    size_bytes: int
    sha256: str
    key: str


# ---------------------------------------------------------------------------
# Local filesystem storage
# ---------------------------------------------------------------------------

class LocalStorage:
    """Store files on the local filesystem."""

    def __init__(self, base_path: Optional[str] = None):
        self._base = Path(base_path or os.environ.get("STORAGE_PATH", "./storage"))
        self._base.mkdir(parents=True, exist_ok=True)

    # -- core operations ---------------------------------------------------

    def put(self, key: str, data: bytes, mime_type: str = "") -> StorageMeta:
        """Write *data* to *key*. Parent directories are created automatically."""
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        return StorageMeta(size_bytes=len(data), sha256=sha, key=key)

    def get(self, key: str) -> bytes:
        """Return the raw bytes stored under *key*."""
        target = self._resolve(key)
        if not target.exists():
            raise FileNotFoundError(f"Storage key not found: {key}")
        return target.read_bytes()

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def delete(self, key: str) -> bool:
        target = self._resolve(key)
        if target.exists():
            target.unlink()
            return True
        return False

    # -- key generation ----------------------------------------------------

    @staticmethod
    def generate_key(
        firm_id: str,
        case_id: str,
        filename: str,
        prefix: str = "uploads",
    ) -> str:
        """Generate a unique, collision-free storage key."""
        unique = uuid.uuid4().hex[:12]
        safe_name = os.path.basename(filename)
        return f"{prefix}/{firm_id}/{case_id}/{unique}_{safe_name}"

    # -- internal ----------------------------------------------------------

    def _resolve(self, key: str) -> Path:
        """Resolve *key* to an absolute path under the base directory."""
        resolved = (self._base / key).resolve()
        # Guard against path traversal
        if not str(resolved).startswith(str(self._base.resolve())):
            raise ValueError(f"Path traversal blocked: {key}")
        return resolved


# ---------------------------------------------------------------------------
# S3-compatible storage
# ---------------------------------------------------------------------------

class S3Storage:
    """Store files on an S3-compatible backend (AWS, R2, MinIO, etc.)."""

    def __init__(self):
        import boto3

        # Support multiple env-var naming conventions used in the codebase
        access_candidates = [
            "AWS_ACCESS_KEY_ID",
            "S3_ACCESS_KEY",
            "S3_ACCESS_KEY_ID",
            "S3_KEY_ID",
            "R2_ACCESS_KEY_ID",
        ]
        secret_candidates = [
            "AWS_SECRET_ACCESS_KEY",
            "S3_SECRET_KEY",
            "S3_SECRET_ACCESS_KEY",
            "S3_SECRET_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
        ]

        access_key = next(
            (os.environ[k] for k in access_candidates if os.environ.get(k)),
            None,
        )
        secret_key = next(
            (os.environ[k] for k in secret_candidates if os.environ.get(k)),
            None,
        )

        self._bucket = os.environ.get("S3_BUCKET", "jethro-documents")
        endpoint = os.environ.get("S3_ENDPOINT") or None
        region = os.environ.get("S3_REGION", "us-east-1")

        session_kwargs = {}
        if access_key:
            session_kwargs["aws_access_key_id"] = access_key
        if secret_key:
            session_kwargs["aws_secret_access_key"] = secret_key

        client_kwargs = {"region_name": region}
        if endpoint:
            client_kwargs["endpoint_url"] = endpoint

        self._client = boto3.client("s3", **client_kwargs, **session_kwargs)

    # -- core operations ---------------------------------------------------

    def put(self, key: str, data: bytes, mime_type: str = "") -> StorageMeta:
        extra = {}
        if mime_type:
            extra["ContentType"] = mime_type
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            **extra,
        )
        sha = hashlib.sha256(data).hexdigest()
        return StorageMeta(size_bytes=len(data), sha256=sha, key=key)

    def get(self, key: str) -> bytes:
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except self._client.exceptions.NoSuchKey:
            return False
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    # -- key generation ----------------------------------------------------

    @staticmethod
    def generate_key(
        firm_id: str,
        case_id: str,
        filename: str,
        prefix: str = "uploads",
    ) -> str:
        unique = uuid.uuid4().hex[:12]
        safe_name = os.path.basename(filename)
        return f"{prefix}/{firm_id}/{case_id}/{unique}_{safe_name}"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_instance = None


def get_storage():
    """Return a storage backend instance (cached singleton).

    Reads STORAGE_BACKEND (or legacy STORAGE_TYPE) from the environment.
    Defaults to LocalStorage when the variable is missing or set to "local".
    """
    global _instance
    if _instance is not None:
        return _instance

    backend = (
        os.environ.get("STORAGE_BACKEND")
        or os.environ.get("STORAGE_TYPE")
        or "local"
    ).strip().lower() or "local"

    if backend == "s3":
        logger.info("Initializing S3 storage (bucket=%s)", os.environ.get("S3_BUCKET", "jethro-documents"))
        _instance = S3Storage()
    else:
        storage_path = os.environ.get("STORAGE_PATH", "./storage")
        logger.info("Initializing local storage (path=%s)", storage_path)
        _instance = LocalStorage(base_path=storage_path)

    return _instance
