# JETHRO 9.0 - Makefile
# ======================
# Common commands for development and deployment

.PHONY: help install dev test build up down logs clean

# Default target
help:
	@echo "JETHRO 9.0 - Available commands:"
	@echo ""
	@echo "  make install    - Install Python dependencies"
	@echo "  make dev        - Run development server"
	@echo "  make test       - Run tests"
	@echo "  make build      - Build Docker image"
	@echo "  make up         - Start all services (docker-compose)"
	@echo "  make down       - Stop all services"
	@echo "  make logs       - View service logs"
	@echo "  make clean      - Clean up generated files"
	@echo ""

# Install dependencies
install:
	pip install -r backend_lite/requirements.txt

# Run development server
dev:
	uvicorn backend_lite.api:app --reload --port 8000

# Run worker (development)
worker:
	python -m backend_lite.jobs.worker --log-level INFO

# Run tests
test:
	pytest backend_lite/tests/ -v

# Run tests with coverage
test-cov:
	pytest backend_lite/tests/ --cov=backend_lite --cov-report=html

# Build Docker image
build:
	docker build -t jethro9 .

# Start all services with docker-compose
up:
	docker-compose up -d

# Start only web service
up-web:
	docker-compose up -d postgres redis web

# Stop all services
down:
	docker-compose down

# View logs
logs:
	docker-compose logs -f

# View web logs only
logs-web:
	docker-compose logs -f web

# View worker logs only
logs-worker:
	docker-compose logs -f worker

# Restart services
restart:
	docker-compose restart

# Clean up
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov 2>/dev/null || true
	rm -f dev.db 2>/dev/null || true

# Database migrations (if using alembic in future)
# migrate:
# 	alembic upgrade head

# Shell into running container
shell:
	docker-compose exec web /bin/sh

# Check service health
health:
	@curl -s http://localhost:8000/health | python -m json.tool

# Format code (if using black/ruff)
# format:
# 	black backend_lite/
# 	ruff check backend_lite/ --fix
