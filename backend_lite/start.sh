#!/bin/sh
# Unified start script for Railway deployment
# SERVICE_TYPE=worker -> starts RQ worker
# Otherwise -> starts web server (uvicorn)

ROLE="${BACKEND_LITE_ROLE:-web}"
if [ "$ROLE" = "worker" ]; then
  echo "Starting in WORKER mode (BACKEND_LITE_ROLE=worker)"
  exec /app/backend_lite/start_worker.sh
fi

PORT="${PORT:-8000}"
echo "Starting Contradiction Service on port $PORT"
exec python3 -m uvicorn backend_lite.api:app --host 0.0.0.0 --port "$PORT"
