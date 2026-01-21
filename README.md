# JETHRO 9.0

**מערכת גילוי סתירות משפטית מבוססת AI**

Legal Contradiction Detection System powered by AI

---

## Overview

JETHRO 9.0 is a standalone contradiction detection service designed for legal document analysis. It identifies contradictions, inconsistencies, and discrepancies across multiple documents, and generates cross-examination questions.

### Key Features

- **Contradiction Detection** - Temporal, quantitative, factual, and version contradictions
- **Cross-Examination Generation** - AI-powered question generation based on Hebrew legal playbooks
- **Document Processing** - PDF, DOCX, TXT with OCR support
- **Multi-tenant Architecture** - Firm, team, and case management
- **Background Processing** - Redis Queue for async document analysis
- **LLM Integration** - Optional enhancement with OpenRouter, DeepSeek, or Gemini

---

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/smaster1234/jethro9.0.git
cd jethro9.0

# Copy environment file
cp .env.example .env

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f web
```

Access the application at: http://localhost:8000

### Option 2: Local Development

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r backend_lite/requirements.txt

# Set environment variables
export DATABASE_URL=sqlite:///./dev.db
export REDIS_URL=redis://localhost:6379/0
export LLM_MODE=none

# Run the server
uvicorn backend_lite.api:app --reload --port 8000
```

---

## Architecture

```
jethro9.0/
├── backend_lite/           # Main application package
│   ├── api.py              # FastAPI endpoints
│   ├── detector.py         # Rule-based contradiction detection
│   ├── extractor.py        # Claim extraction
│   ├── cross_exam.py       # Cross-examination generation
│   ├── db/                 # Database models (SQLAlchemy)
│   ├── jobs/               # Background tasks (RQ)
│   ├── storage/            # File storage (Local/S3)
│   ├── ingest/             # Document parsing
│   ├── llm/                # LLM integration
│   └── frontend_build/     # Pre-built React UI
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## API Endpoints

### Core Analysis

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/analyze` | POST | Analyze free text for contradictions |
| `/analyze_claims` | POST | Analyze pre-extracted claims |
| `/health` | GET | Health check |

### Document Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/cases/{case_id}/documents` | POST | Upload document |
| `/api/v1/cases/{case_id}/documents/zip` | POST | Upload ZIP archive |
| `/api/v1/documents/{doc_id}` | GET | Get document |
| `/api/v1/cases/{case_id}/analyze` | POST | Start analysis job |
| `/api/v1/jobs/{job_id}` | GET | Get job status |

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/register` | POST | Register new firm |
| `/api/v1/auth/login` | POST | Login |
| `/api/v1/auth/me` | GET | Get current user |

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `sqlite:///./dev.db` | PostgreSQL connection string |
| `REDIS_URL` | Yes | `redis://localhost:6379/0` | Redis connection string |
| `STORAGE_BACKEND` | No | `local` | `local` or `s3` |
| `LLM_MODE` | No | `none` | `none`, `openrouter`, `deepseek`, `gemini` |
| `PORT` | No | `8000` | Server port |
| `BACKEND_LITE_ROLE` | No | `web` | `web` or `worker` |

### LLM Configuration

For enhanced contradiction detection with AI:

```bash
# OpenRouter (recommended - access to multiple models)
LLM_MODE=openrouter
OPENROUTER_API_KEY=sk-or-v1-...

# Or DeepSeek
LLM_MODE=deepseek
DEEPSEEK_API_KEY=sk-...

# Or Gemini
LLM_MODE=gemini
GEMINI_API_KEY=...
```

---

## Deployment

### Railway

1. Connect your GitHub repository
2. Set Root Directory to `/` (or leave empty)
3. Add environment variables in Railway dashboard
4. Deploy!

For the worker service, create a second Railway service with:
- Same repository
- `BACKEND_LITE_ROLE=worker`

### Docker

```bash
# Build image
docker build -t jethro9 .

# Run web server
docker run -d \
  -p 8000:8000 \
  -e DATABASE_URL=postgresql://... \
  -e REDIS_URL=redis://... \
  jethro9

# Run worker
docker run -d \
  -e DATABASE_URL=postgresql://... \
  -e REDIS_URL=redis://... \
  -e BACKEND_LITE_ROLE=worker \
  jethro9
```

---

## Development

### Running Tests

```bash
# Run all tests
pytest backend_lite/tests/ -v

# Run specific test
pytest backend_lite/tests/test_detector_rule_based.py -v

# With coverage
pytest backend_lite/tests/ --cov=backend_lite
```

### Code Structure

- `detector.py` - Rule-based contradiction detection engine
- `extractor.py` - Claim extraction from Hebrew legal text
- `cross_exam.py` - Cross-examination question generation
- `playbooks.yaml` - Hebrew legal playbook templates
- `schemas.py` - Pydantic models for API

---

## License

Proprietary - All rights reserved

---

## Support

For issues and feature requests, please contact the development team.
