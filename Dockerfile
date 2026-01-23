# JETHRO 9.0 - Contradiction Detection Service
# =============================================
# Production-ready Docker image for legal contradiction detection
#
# Build:
#   docker build -t jethro9 .
#
# Run:
#   docker run -p 8000:8000 -e DATABASE_URL=... -e REDIS_URL=... jethro9

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend_lite/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend_lite/ ./backend_lite/

# Ensure __init__.py exists
RUN touch ./backend_lite/__init__.py

# Make start scripts executable
RUN chmod +x ./backend_lite/start.sh ./backend_lite/start_worker.sh 2>/dev/null || true

# Environment defaults
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV LLM_MODE=none
ENV PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8080}/health')" || exit 1

EXPOSE 8080

# Default command - Web server
# For worker: override with BACKEND_LITE_ROLE=worker
CMD ["sh", "-c", "/app/backend_lite/start.sh"]
