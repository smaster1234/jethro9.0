# JETHRO 9.0 - Contradiction Detection Service
# =============================================
# Production-ready Docker image for legal contradiction detection
#
# Build:
#   docker build -t jethro9 .
#
# Run:
#   docker run -p 8000:8000 -e DATABASE_URL=... -e REDIS_URL=... jethro9

# Frontend build stage
FROM node:20-alpine AS frontend_builder

WORKDIR /frontend

# Copy package files
COPY frontend/package*.json ./

# Install ALL dependencies (including devDependencies for build)
RUN npm ci --legacy-peer-deps 2>/dev/null || npm install --legacy-peer-deps

# Copy source files
COPY frontend/ .

# Build the app
RUN npm run build

# Backend stage
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

# Replace bundled frontend with fresh Vite build artifacts
RUN rm -rf ./backend_lite/frontend_build && mkdir -p ./backend_lite/frontend_build
COPY --from=frontend_builder /frontend/dist ./backend_lite/frontend_build

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
