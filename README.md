# JETHRO 9.0

**מערכת גילוי סתירות משפטית מבוססת AI**

Legal Contradiction Detection System powered by AI

---

## Overview

JETHRO 9.0 is a standalone contradiction detection service designed for legal document analysis. It identifies contradictions, inconsistencies, and discrepancies across multiple documents, and generates cross-examination questions.

Current release version is stored in `VERSION`.

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

---

## Golden Path (E2E, <10 דקות)

הסקריפט מריץ נתיב זהב מקצה לקצה (כולל העלאת מסמכים לדוגמה):

```bash
./scripts/golden_path.sh
```

ברירת מחדל משתמשת ב־`backend_lite/fixtures/*.txt` ובכתובת `http://localhost:8000`.
ניתן להגדיר:

```bash
BASE_URL=http://localhost:8000 \
DOC1=backend_lite/fixtures/temporal_01.txt \
DOC2=backend_lite/fixtures/temporal_02.txt \
./scripts/golden_path.sh
```

הסקריפט מבצע:
1. `docker-compose up -d`
2. הרשמה והפקת טוקן
3. יצירת תיק
4. העלאת מסמכים
5. הרצת ניתוח + המתנה לסיום
6. יצירת עד/גרסאות והפקת diff
7. יצירת תכנית חקירה וייצוא DOCX

טיפ: ניתן להצביע על מסמכי DOCX/PDF קיימים ע"י שינוי `DOC1`/`DOC2`.

---

## Org Setup (B1) — משרדים, חברים ותפקידים

המערכת תומכת במשרדים (Organizations) עם תפקידים:
`viewer` (קריאה בלבד), `intern` (הכנה ללא ייצוא), `lawyer`/`owner` (כולל ייצוא).

### יצירת משרד וחברים
```bash
# יצירת משרד
POST /api/v1/orgs

# רשימת משרדים למשתמש הנוכחי
GET /api/v1/orgs

# הוספת משתמש קיים
POST /api/v1/orgs/{org_id}/members  (body: { user_id, role })

# הזמנה במייל
POST /api/v1/orgs/{org_id}/invites  (body: { email, role, expires_in_days })

# קבלת הזמנה
POST /api/v1/invites/{token}/accept
```

### שיוך תיק למשרד
בשדה `organization_id` ביצירת תיק (`POST /cases`) או באמצעות ברירת מחדל אוטומטית.

---

## Training Mode 2.0 (C1)

```bash
# התחלת אימון
POST /api/v1/cases/{case_id}/training/start
{ "plan_id": "...", "witness_id": "...", "persona": "cooperative" }

# תור אימון
POST /api/v1/training/{session_id}/turn
{ "step_id": "step-1", "chosen_branch": "לא זוכר" }

# חזרה צעד (מוגבל ל-2)
POST /api/v1/training/{session_id}/back

# סיום וסיכום
POST /api/v1/training/{session_id}/finish
```

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
| `/auth/register` | POST | Register new firm |
| `/auth/login` | POST | Login |
| `/auth/me` | GET | Get current user |

### Organizations & Training

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/orgs` | GET/POST | List/create organizations |
| `/api/v1/orgs/{id}/members` | GET/POST | List/add org members |
| `/api/v1/orgs/{id}/invites` | POST | Invite by email |
| `/api/v1/invites/{token}/accept` | POST | Accept invite |
| `/api/v1/cases/{case_id}/training/start` | POST | Start training session |
| `/api/v1/training/{session_id}/turn` | POST | Record training turn |
| `/api/v1/training/{session_id}/back` | POST | Undo last turn |
| `/api/v1/training/{session_id}/finish` | POST | Finish + summary |

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
