FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all code to backend_lite/
COPY . ./backend_lite/

# Create __init__.py if missing
RUN touch ./backend_lite/__init__.py

# Make start scripts executable
RUN chmod +x ./backend_lite/start.sh ./backend_lite/start_worker.sh

# Environment
ENV LLM_MODE=none
ENV PORT=8000
ENV PYTHONPATH=/app

EXPOSE 8000

# Run with shell wrapper to expand $PORT variable
CMD ["sh", "-c", "uvicorn backend_lite.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
