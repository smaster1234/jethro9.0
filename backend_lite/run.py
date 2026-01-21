#!/usr/bin/env python3
"""
Quick runner for Contradiction Service
======================================

Usage:
    python -m backend_lite.run
    # or
    python backend_lite/run.py
"""

import uvicorn

if __name__ == "__main__":
    print("Starting Contradiction Service...")
    print("API docs: http://localhost:8000/docs")
    print("Health:   http://localhost:8000/health")
    print()

    uvicorn.run(
        "backend_lite.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
