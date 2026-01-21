# Contradiction Service - Legal Text Analysis MVP

A minimal, standalone service for:
1. **Detecting contradictions** in Hebrew legal text
2. **Generating cross-examination questions** based on detected contradictions

No database, no Celery, no authentication required.

## Quick Start

### Installation

```bash
cd backend_lite
pip install -r requirements.txt
```

### Run the Server

```bash
# From project root
uvicorn backend_lite.api:app --host 0.0.0.0 --port 8000

# Or with auto-reload for development
uvicorn backend_lite.api:app --reload --port 8000
```

### Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "llm_mode": "none",
  "timestamp": "2024-01-15T10:30:00"
}
```

## API Endpoints

### POST /analyze

Analyze free Hebrew text for contradictions.

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "text": "החוזה נחתם ב-15.3.2020 במשרדי החברה. לאחר חתימת החוזה ב-20.5.2021 החלו העבודות.",
    "source_name": "כתב תביעה"
  }'
```

### POST /analyze_claims

Analyze pre-extracted claims with IDs.

```bash
curl -X POST http://localhost:8000/analyze_claims \
  -H "Content-Type: application/json" \
  -d '{
    "claims": [
      {"id": "1", "text": "החוזה נחתם ב-15.3.2020", "source": "תצהיר"},
      {"id": "2", "text": "החוזה נחתם ב-20.5.2021", "source": "עדות"}
    ]
  }'
```

### Response Format

All endpoints return a stable JSON structure:

```json
{
  "contradictions": [
    {
      "id": "contr_abc123",
      "claim1_id": "1",
      "claim2_id": "2",
      "type": "temporal_conflict",
      "severity": "high",
      "confidence": 0.85,
      "explanation": "סתירה בתאריכים: 15.3.2020 לעומת 20.5.2021",
      "quote1": "נחתם ב-15.3.2020",
      "quote2": "נחתם ב-20.5.2021"
    }
  ],
  "cross_exam_questions": [
    {
      "contradiction_id": "contr_abc123",
      "target_party": null,
      "questions": [
        {
          "id": "q_xyz789",
          "question": "אתה מאשר שהחוזה נחתם ב-15.3.2020?",
          "purpose": "קיבוע מועד מוקדם",
          "severity": "high",
          "follow_up": "אם מאשר - המשך לשאלה הבאה"
        }
      ]
    }
  ],
  "metadata": {
    "mode": "none",
    "rule_based_time_ms": 45.2,
    "llm_time_ms": null,
    "total_time_ms": 45.2,
    "model_used": null,
    "claims_count": 2,
    "validation_flags": []
  }
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MODE` | `none` | `none`, `openrouter`, or `gemini` |
| `OPENROUTER_API_KEY` | - | API key for OpenRouter |
| `OPENROUTER_MODEL` | `anthropic/claude-3-haiku` | Model to use |
| `GEMINI_API_KEY` | - | API key for Google Gemini |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Model to use |

### Example .env file

```bash
# Rule-based only (default, fastest)
LLM_MODE=none

# Or with OpenRouter
LLM_MODE=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=anthropic/claude-3-haiku

# Or with Gemini
LLM_MODE=gemini
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-1.5-flash
```

## Contradiction Types

| Type | Hebrew | Description |
|------|--------|-------------|
| `temporal_conflict` | סתירה כרונולוגית | Different dates for same event |
| `quantitative_conflict` | סתירה כמותית | Different amounts/numbers |
| `attribution_conflict` | סתירה בייחוס | Different actors for same action |
| `factual_conflict` | סתירה עובדתית | General factual contradiction |
| `version_conflict` | שינוי גרסה | Story changed over time |
| `witness_conflict` | סתירה בין עדים | Witness contradicts self |

## Severity Levels

| Level | Hebrew | Description |
|-------|--------|-------------|
| `critical` | קריטי | Undermines core credibility |
| `high` | גבוה | Significant inconsistency |
| `medium` | בינוני | Notable contradiction |
| `low` | נמוך | Minor discrepancy |

## Running Tests

```bash
# From project root
pytest backend_lite/tests/ -v

# Run specific test file
pytest backend_lite/tests/test_detector_rule_based.py -v

# Run API contract tests
pytest backend_lite/tests/test_api_contract.py -v
```

## Performance

- **Rule-based only** (`LLM_MODE=none`): < 1 second for 50 claims
- **With LLM** (`LLM_MODE=openrouter`): 2-5 seconds depending on model

Target: < 10 seconds for 2-5 page document in rule-based mode.

## Architecture

```
backend_lite/
├── __init__.py
├── api.py           # FastAPI endpoints
├── config.py        # Environment configuration
├── schemas.py       # Pydantic input/output models
├── extractor.py     # Claim extraction from text
├── detector.py      # Rule-based contradiction detection
├── cross_exam.py    # Cross-examination question generation
├── llm_client.py    # Optional LLM enhancement
├── requirements.txt
├── README.md
└── tests/
    ├── fixtures/
    │   ├── sample_claims_temporal.json
    │   └── sample_claims_quantitative.json
    ├── test_detector_rule_based.py
    └── test_api_contract.py
```

## Validation Flags

The `metadata.validation_flags` field may contain:

| Flag | Meaning |
|------|---------|
| `LLM_FAILED_FALLBACK` | LLM failed, used rule-based only |
| `LLM_RETURNED_EMPTY` | LLM returned no contradictions |
| `NO_CLAIMS_EXTRACTED` | No claims found in text |
| `ANALYSIS_ERROR` | Analysis failed (still returns valid JSON) |

## JSON Stability Guarantee

The API **always** returns valid JSON, even on errors. The response structure is fixed and won't change between versions without a major version bump.

## Differences from Full JETHRO4

This MVP does **NOT** include:
- Database (SQLAlchemy)
- Background jobs (Celery)
- Caching (Redis)
- Authentication
- Admin panel
- Billing
- RAG/Vector search
- Chat interface
- Multi-agent orchestration

It **ONLY** includes:
- Contradiction detection (rule-based + optional LLM)
- Cross-examination question generation
- Simple REST API
