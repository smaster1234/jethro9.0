#!/bin/sh
# Worker start script for Railway deployment
# Starts the RQ worker to process background jobs

echo "Starting JETHRO4 Worker..."
echo "Redis URL: ${REDIS_URL:-not set}"

# Some platforms enforce an HTTP healthcheck even for workers.
# To guarantee healthcheck success, run the health server in the foreground,
# and run the RQ worker in the background with auto-restart.
PORT="${PORT:-8000}"

start_worker_loop() {
  while true; do
    echo "Starting RQ worker..."
    python3 -m backend_lite.jobs.worker --log-level INFO || true
    echo "RQ worker exited - restarting in 3s"
    sleep 3
  done
}

start_worker_loop &
WORKER_LOOP_PID="$!"

HEALTH_PID_8000=""
HEALTH_PID_8080=""

# Start fallback health servers on common ports to match platform UI settings.
if [ "$PORT" != "8000" ]; then
  echo "Starting worker health server on port 8000 (fallback)"
  python3 -m uvicorn backend_lite.worker_health:app --host 0.0.0.0 --port 8000 &
  HEALTH_PID_8000="$!"
fi

if [ "$PORT" != "8080" ]; then
  echo "Starting worker health server on port 8080 (fallback)"
  python3 -m uvicorn backend_lite.worker_health:app --host 0.0.0.0 --port 8080 &
  HEALTH_PID_8080="$!"
fi

cleanup() {
  if [ -n "$WORKER_LOOP_PID" ]; then
    kill "$WORKER_LOOP_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "$HEALTH_PID_8000" ]; then
    kill "$HEALTH_PID_8000" >/dev/null 2>&1 || true
  fi
  if [ -n "$HEALTH_PID_8080" ]; then
    kill "$HEALTH_PID_8080" >/dev/null 2>&1 || true
  fi
}

trap cleanup INT TERM EXIT

echo "Starting worker health server on port $PORT"
exec python3 -m uvicorn backend_lite.worker_health:app --host 0.0.0.0 --port "$PORT"
