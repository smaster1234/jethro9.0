"""
Worker Health Server
====================

Railway (and similar platforms) may enforce an HTTP healthcheck even for worker
services. This tiny FastAPI app exists to satisfy `/health` while an RQ worker
process runs in parallel.
"""

from datetime import datetime

from fastapi import FastAPI

app = FastAPI(title="backend_lite worker health", docs_url=None, redoc_url=None)


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

