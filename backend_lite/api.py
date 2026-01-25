"""
Contradiction Service API
=========================

FastAPI endpoints for contradiction detection, cross-examination, and document management.

Core Endpoints:
- POST /analyze        - Analyze free text
- POST /analyze_claims - Analyze pre-extracted claims
- GET  /health         - Health check

Upload System Endpoints (requires DATABASE_URL):
- POST   /api/v1/cases/{case_id}/folders     - Create folder
- GET    /api/v1/cases/{case_id}/folders/tree - Get folder tree
- POST   /api/v1/cases/{case_id}/documents   - Upload document
- POST   /api/v1/cases/{case_id}/documents/zip - Upload ZIP archive
- GET    /api/v1/documents/{doc_id}          - Get document
- GET    /api/v1/documents/{doc_id}/snippet  - Get document snippet
- POST   /api/v1/cases/{case_id}/analyze     - Start analysis job
- GET    /api/v1/jobs/{job_id}               - Get job status

Run with:
    uvicorn backend_lite.api:app --host 0.0.0.0 --port 8000
"""

import logging
import os
import uuid
import asyncio
import hashlib
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Header, Depends, Body, APIRouter, UploadFile, File, Form, Query, WebSocket, WebSocketDisconnect, Response, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.responses import StreamingResponse
import json
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .config import get_settings, get_llm_mode
from .schemas import (
    AnalyzeTextRequest,
    AnalyzeClaimsRequest,
    AnalysisResponse,
    AnalysisMetadata,
    RuleStats,
    VerifierStats,
    ContradictionOutput,
    ContradictionStatus,
    ContradictionType,
    ContradictionSubtype,
    ClaimEvidence,
    CrossExamQuestionsOutput,
    CrossExamQuestion,
    HealthResponse,
    ErrorResponse,
    SnippetResponse,
    LLMMode,
    Severity,
    TextSpan,
    Locator,
    EvidenceAnchor,
    # Case management request models
    CreateCaseRequest,
    AddDocumentRequest,
    AnalyzeCaseRequest,
    # Claims table support
    ClaimOutput,
    ClaimResult,
    ClaimStatus,
    ClaimFeatures,
    # Cross-Exam Tracks (Litigator Dashboard)
    CrossExamTrack,
    CrossExamTracksResponse,
    TrackStep,
    TrackEvidence,
    StyleVariants,
    # Attribution Layer
    ContradictionBucket,
    ContradictionRelation,
    DisputeIssue,
    AttributionSummary,
)
from .extractor import extract_claims, ClaimExtractor
from .detector import detect_contradictions, DetectedContradiction
from .cross_exam import generate_cross_exam_questions, CrossExamSet
from .llm_client import detect_with_llm, get_llm_client  # Legacy, kept for compatibility
from .llm import get_analyzer, get_verifier  # New architecture
from .dedup import deduplicate_contradictions

# SQLAlchemy models (unified database layer)
from .db.session import get_db, init_db, get_db_session
from .db.models import (
    Firm, User, Team, TeamMember, CaseTeam, CaseParticipant,
    Case, Document, Folder, Job, Event, Claim,
    SystemRole, TeamRole, CaseStatus, DocumentParty, DocumentRole,
    JobType, JobStatus
)

# Legacy imports for Paragraph dataclass (used in text chunking)
from .models import Paragraph

# Auth (now SQLAlchemy-based)
from .auth import (
    AuthService, AuthContext, Permission,
    get_auth_service,
    create_access_token, create_refresh_token, decode_token,
    get_password_hash, verify_password,
    PASSWORD_HASHING_AVAILABLE, is_jwt_available,
    is_password_too_long, MAX_PASSWORD_BYTES,
)

from sqlalchemy.orm import Session

# Database dependency for FastAPI (defined early to avoid NameError)
def get_db_dependency():
    """Get database session for FastAPI dependency injection"""
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()

# Upload system (folders, documents, jobs)
try:
    from .api_upload import router as upload_router
    from .api_upload import get_auth_context, AnalyzeCaseRequest
    UPLOAD_ENABLED = True
except ImportError as e:
    UPLOAD_ENABLED = False
    upload_router = None
    get_auth_context = None  # type: ignore[assignment]
    AnalyzeCaseRequest = None  # type: ignore[assignment]
    logging.warning(f"Upload system not available: {e}")

# Ensure optional upload imports don't break app startup
if get_auth_context is None:
    def get_auth_context():  # type: ignore[no-redef]
        raise HTTPException(status_code=503, detail="Upload/analysis system is not enabled")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_database():
    """
    Legacy DB accessor (deprecated).

    This codebase migrated to SQLAlchemy + `/api/v1/*` upload/analysis endpoints.
    Older endpoints still present in this file may reference `get_database()`.
    To avoid hard 500/NameError in production, we fail fast with a clear message.
    """
    raise HTTPException(
        status_code=410,
        detail="Legacy endpoints are deprecated. Use /api/v1/* endpoints instead.",
    )


# =============================================================================
# FastAPI App
# =============================================================================

app = FastAPI(
    title="Contradiction Service",
    description="Legal contradiction detection and cross-examination questions for Hebrew text",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS - get allowed origins from environment, default to localhost for development
def _parse_cors_origins(raw: str) -> List[str]:
    origins: List[str] = []
    for item in raw.split(","):
        origin = item.strip().strip('"').strip("'").rstrip("/")
        if origin:
            origins.append(origin)
    return origins

_cors_raw = os.environ.get(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
)
CORS_ALLOW_ORIGINS = _parse_cors_origins(_cors_raw)
logger.info(f"CORS allow origins: {CORS_ALLOW_ORIGINS}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

# Security Headers Middleware
try:
    from .middleware.security import SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("Security headers middleware enabled")
except ImportError:
    logger.warning("Security headers middleware not available")

# Rate Limiting Middleware
try:
    from .middleware.rate_limit import RateLimitMiddleware
    RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "false").lower() == "true"
    if RATE_LIMIT_ENABLED:
        app.add_middleware(RateLimitMiddleware)
        logger.info("Rate limiting middleware enabled")
except ImportError:
    logger.warning("Rate limiting middleware not available")

# Static files
# - Legacy/static UI lives under backend_lite/static
# - React (CRA) build, if present, is copied into backend_lite/frontend_build
LEGACY_STATIC_DIR = Path(__file__).parent / "static"
REACT_BUILD_DIR = Path(os.environ.get("REACT_BUILD_DIR", str(Path(__file__).parent / "frontend_build")))
REACT_STATIC_DIR = REACT_BUILD_DIR / "static"
REACT_ENABLED = (REACT_BUILD_DIR / "index.html").exists() and REACT_STATIC_DIR.exists()

if REACT_ENABLED:
    logger.info(f"React frontend build available at {REACT_BUILD_DIR}")
    # CRA expects assets at /static/*
    app.mount("/static", StaticFiles(directory=str(REACT_STATIC_DIR)), name="static")
    # Keep legacy assets accessible for debugging
    if LEGACY_STATIC_DIR.exists():
        app.mount("/legacy-static", StaticFiles(directory=str(LEGACY_STATIC_DIR)), name="legacy-static")
else:
    # Legacy mode
    STATIC_DIR = LEGACY_STATIC_DIR
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# React Frontend Build (if available)
# The React frontend build directory takes precedence over the basic UI
# First check inside backend_lite (for Docker/Railway deployment)
# Then fallback to parent frontend directory (for local development)
FRONTEND_BUILD_DIR = Path(__file__).parent / "frontend_build"
if not FRONTEND_BUILD_DIR.exists():
    FRONTEND_BUILD_DIR = Path(__file__).parent.parent / "frontend" / "build"
FRONTEND_BUILD_AVAILABLE = FRONTEND_BUILD_DIR.exists() and (FRONTEND_BUILD_DIR / "index.html").exists()
FRONTEND_STATIC_DIR = FRONTEND_BUILD_DIR / "static"
if FRONTEND_BUILD_AVAILABLE and FRONTEND_STATIC_DIR.exists():
    # Mount React static assets (JS, CSS, etc.)
    app.mount("/react-static", StaticFiles(directory=str(FRONTEND_STATIC_DIR)), name="react-static")
    logger.info(f"React frontend build available at {FRONTEND_BUILD_DIR}")
elif FRONTEND_BUILD_AVAILABLE:
    logger.info(f"React frontend build available at {FRONTEND_BUILD_DIR} (no /static dir)")

# Include upload router if available
if UPLOAD_ENABLED and upload_router:
    app.include_router(upload_router, prefix="/api/v1")
    logger.info("Upload system enabled at /api/v1")


# =============================================================================
# Frontend Compatibility Layer (/api/*)
# =============================================================================
#
# The React UI (frontend/) is built against a legacy/full-backend contract under `/api/*`.
# backend_lite historically exposed:
# - root endpoints (e.g. /cases, /teams, /users/by-email)
# - upload/analysis endpoints under /api/v1/*
#
# To avoid a "blank UI" in production, we expose a minimal, stable `/api/*` surface
# that maps to backend_lite's real capabilities (cases/files/analysis).

frontend_router = APIRouter(prefix="/api", tags=["frontend"])


def _party_to_source(party: Optional[DocumentParty]) -> str:
    if not party:
        return "self"
    v = party.value if hasattr(party, "value") else str(party)
    return {
        "ours": "self",
        "theirs": "opponent",
        "court": "court",
        "third_party": "third_party",
        "unknown": "self",
    }.get(v, "self")


def _source_to_party(source: Optional[str]) -> DocumentParty:
    v = (source or "self").strip().lower()
    return {
        "self": DocumentParty.OURS,
        "opponent": DocumentParty.THEIRS,
        "court": DocumentParty.COURT,
        "third_party": DocumentParty.THIRD_PARTY,
        "third-party": DocumentParty.THIRD_PARTY,
    }.get(v, DocumentParty.UNKNOWN)


def _doc_type_to_role(doc_type: Optional[str]) -> DocumentRole:
    v = (doc_type or "other").strip().lower()
    return {
        "claim": DocumentRole.STATEMENT_OF_CLAIM,
        "defense": DocumentRole.DEFENSE,
        "reply": DocumentRole.REPLY,
        "summaries": DocumentRole.SUMMATIONS,
        "summations": DocumentRole.SUMMATIONS,
        "protocol": DocumentRole.PROTOCOL,
        "affidavit": DocumentRole.AFFIDAVIT,
        "expert_opinion": DocumentRole.EXPERT_OPINION,
        "contract": DocumentRole.CONTRACT,
        "correspondence": DocumentRole.LETTER,
        "court_decision": DocumentRole.JUDGMENT,
        "motion": DocumentRole.MOTION,
        "evidence": DocumentRole.EXHIBIT,
        "other": DocumentRole.UNKNOWN,
    }.get(v, DocumentRole.UNKNOWN)


def _case_status_for_ui(db: Session, case_id: str) -> str:
    """Derive a UX-friendly case status for React UI."""
    from .db.models import AnalysisRun, DocumentStatus

    latest_run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.case_id == case_id)
        .order_by(AnalysisRun.created_at.desc())
        .first()
    )
    if latest_run:
        st = (latest_run.status or "").lower()
        if st in ("running", "queued"):
            return "analyzing"
        if st in ("done", "completed"):
            return "completed"
        if st in ("failed", "error"):
            return "failed"

    docs = db.query(Document).filter(Document.case_id == case_id).all()
    if any(d.status == DocumentStatus.PROCESSING for d in docs):
        return "processing"
    if any(d.status == DocumentStatus.UPLOADED for d in docs):
        return "processing"
    if any(d.status == DocumentStatus.FAILED for d in docs):
        return "failed"
    if any(d.status == DocumentStatus.READY for d in docs):
        return "ready"
    return "active"


def _accessible_org_ids(db: Session, auth: Optional[AuthContext]) -> Optional[List[str]]:
    if not auth:
        return []
    if auth.system_role in (SystemRole.SUPER_ADMIN, SystemRole.ADMIN):
        return None

    from .orgs import ensure_default_org, list_user_org_ids

    org_ids = list_user_org_ids(db, auth.firm_id, auth.user_id)
    if not org_ids:
        org = ensure_default_org(db, auth.firm_id, auth.user_id)
        db.flush()
        org_ids = [org.id]
    return org_ids


def _require_case_access(db: Session, auth: AuthContext, case_id: str) -> Case:
    case = db.query(Case).filter(
        Case.id == case_id,
        Case.firm_id == auth.firm_id
    ).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    org_ids = _accessible_org_ids(db, auth)
    if case.organization_id is None:
        from .orgs import ensure_default_org
        org = ensure_default_org(db, auth.firm_id, auth.user_id)
        case.organization_id = org.id
        db.flush()
        if org_ids is not None and org.id not in org_ids:
            org_ids.append(org.id)

    if org_ids is not None and case.organization_id not in org_ids:
        raise HTTPException(status_code=403, detail="Case not accessible")

    return case


@frontend_router.get("/healthz")
async def api_healthz():
    return {"status": "ok", "service": "backend_lite"}


@frontend_router.get("/health")
async def api_health():
    return await api_healthz()


@frontend_router.get("/auth/me")
async def api_auth_me():
    """
    React UI expects `/api/auth/me`. We keep it best-effort:
    - If JWT auth present: return user info
    - Else: return a minimal anonymous user (prevents UI hard-fail)
    """
    return {"user": {"id": None, "email": None, "name": "Guest", "role": "user", "is_admin": False}}


@frontend_router.get("/cases/recent")
async def api_cases_recent(
    limit: int = Query(default=5, ge=1, le=50),
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    q = db.query(Case).filter(Case.firm_id == auth.firm_id)
    org_ids = _accessible_org_ids(db, auth)
    if org_ids is not None:
        q = q.filter(Case.organization_id.in_(org_ids))
    cases = q.order_by(Case.updated_at.desc()).limit(limit).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "status": _case_status_for_ui(db, c.id),
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in cases
    ]


@frontend_router.get("/cases")
async def api_list_cases(
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    q = db.query(Case).filter(Case.firm_id == auth.firm_id)
    org_ids = _accessible_org_ids(db, auth)
    if org_ids is not None:
        q = q.filter(Case.organization_id.in_(org_ids))
    cases = q.order_by(Case.updated_at.desc()).all()
    out = []
    for c in cases:
        doc_count = db.query(Document).filter(Document.case_id == c.id).count()
        out.append(
            {
                "id": c.id,
                "name": c.name,
                "status": _case_status_for_ui(db, c.id),
                "case_number": c.case_number,
                "document_count": doc_count,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
        )
    return out


@frontend_router.get("/cases/{case_id}")
async def api_get_case(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    c = _require_case_access(db, auth, case_id)

    docs = (
        db.query(Document)
        .filter(Document.case_id == case_id)
        .order_by(Document.created_at.desc())
        .all()
    )

    files = []
    for d in docs:
        files.append(
            {
                "id": d.id,
                "filename": d.doc_name,
                "original_filename": d.original_filename,
                "name": d.doc_name,
                "pages": d.page_count,
                "size": d.size_bytes,
                "uploaded_at": d.created_at.isoformat() if d.created_at else None,
                "status": "ready" if str(d.status.value) == "ready" else ("processing" if str(d.status.value) in ("uploaded", "processing") else "missing"),
                "source": _party_to_source(d.party),
                "document_type": (d.role.value if d.role else None),
                "claims_count": db.query(Claim).filter(Claim.document_id == d.id).count(),
                "entities_count": 0,
                "analysis_status": (
                    "completed" if str(d.status.value) == "ready" else
                    "analyzing" if str(d.status.value) == "processing" else
                    "pending" if str(d.status.value) == "uploaded" else
                    "error" if str(d.status.value) == "failed" else
                    "pending"
                ),
                "analysis_error": (d.extra_data or {}).get("error") if isinstance(d.extra_data, dict) else None,
                "analyzed_at": None,
                "opponent_lawyer_name": d.author if _party_to_source(d.party) == "opponent" else None,
            }
        )

    return {
        "id": c.id,
        "name": c.name,
        "status": _case_status_for_ui(db, c.id),
        "case_type": "case",
        "description": c.description,
        "case_number": c.case_number,
        "organization_id": c.organization_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "files": files,
    }


@frontend_router.get("/cases/{case_id}/files")
async def api_list_case_files(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    _require_case_access(db, auth, case_id)
    return {"files": (await api_get_case(case_id=case_id, db=db, auth=auth)).get("files", [])}


@frontend_router.post("/cases/{case_id}/files")
async def api_upload_case_files(
    case_id: str,
    reanalyze_mode: str = Form(default="skip"),
    document_types: str = Form(default="[]"),
    file_sources: str = Form(default="[]"),
    opponent_lawyer_names: str = Form(default="[]"),
    files: List[UploadFile] = File(...),
    auth: AuthContext = Depends(get_auth_context),  # reuse upload auth (X-User-Email / Authorization)
    db: Session = Depends(get_db_dependency),
):
    """
    React FileManager upload contract.
    We translate it into `/api/v1/cases/{case_id}/documents` (upload router).
    """
    # Parse arrays
    try:
        doc_types = json.loads(document_types) if document_types else []
    except Exception:
        doc_types = []
    try:
        sources = json.loads(file_sources) if file_sources else []
    except Exception:
        sources = []
    try:
        opp_names = json.loads(opponent_lawyer_names) if opponent_lawyer_names else []
    except Exception:
        opp_names = []

    meta = []
    for i, f in enumerate(files):
        src = sources[i] if i < len(sources) else "self"
        dt = doc_types[i] if i < len(doc_types) else "other"
        opp = opp_names[i] if i < len(opp_names) else ""
        meta.append(
            {
                "party": _source_to_party(src).value,
                "role": _doc_type_to_role(dt).value,
                "author": opp or None,
            }
        )

    _require_case_access(db, auth, case_id)

    # Call upload router function directly (keeps DB/storage logic centralized)
    from .api_upload import upload_documents as _upload_documents

    # Build form fields expected by upload_documents
    # (it accepts 'files' and 'metadata_json' as Form)
    resp = await _upload_documents(
        case_id=case_id,
        files=files,
        file=None,
        metadata_json=json.dumps(meta),
        folder_id=None,
        party=None,
        role=None,
        author=None,
        version_label=None,
        auth=auth,
    )

    # Return in React-friendly shape
    uploaded_files = []
    # resp.document_ids aligns with created docs
    for idx, doc_id in enumerate(resp.document_ids):
        filename = None
        try:
            filename = files[idx].filename
        except Exception:
            filename = None
        uploaded_files.append(
            {
                "id": doc_id,
                "filename": filename or doc_id,
                "status": "processing",
                "uploaded_at": datetime.utcnow().isoformat(),
            }
        )
    # React FileManager triggers analysis right after upload; mark as reanalyzing for UX
    return {"status": "success", "uploaded_files": uploaded_files, "reanalyzing": True}


@frontend_router.patch("/cases/{case_id}/files/{file_id}")
async def api_update_file_source(
    case_id: str,
    file_id: str,
    source: str = Query(...),
    opponent_lawyer_name: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db_dependency),
):
    _require_case_access(db, auth, case_id)
    doc = db.query(Document).filter(Document.id == file_id, Document.case_id == case_id, Document.firm_id == auth.firm_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    doc.party = _source_to_party(source)
    if opponent_lawyer_name:
        doc.author = opponent_lawyer_name
    db.commit()
    return {"ok": True}


@frontend_router.delete("/cases/{case_id}/files/{file_id}")
async def api_delete_file(
    case_id: str,
    file_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db_dependency),
):
    _require_case_access(db, auth, case_id)
    doc = db.query(Document).filter(Document.id == file_id, Document.case_id == case_id, Document.firm_id == auth.firm_id).first()
    if not doc:
        return {"ok": True}
    db.delete(doc)
    db.commit()
    return {"ok": True}


@frontend_router.get("/cases/{case_id}/files/{file_id}/download")
async def api_download_file(
    case_id: str,
    file_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db_dependency),
):
    from .storage import get_storage

    _require_case_access(db, auth, case_id)
    doc = db.query(Document).filter(Document.id == file_id, Document.case_id == case_id, Document.firm_id == auth.firm_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    storage = get_storage()
    data = storage.get(doc.storage_key)
    filename = doc.original_filename or doc.doc_name
    media_type = doc.mime_type or "application/octet-stream"
    return StreamingResponse(
        iter([data]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@frontend_router.post("/cases/{case_id}/reanalyze")
async def api_reanalyze_case(
    case_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db_dependency),
):
    """
    React calls this after uploads. Map to the real analysis job under `/api/v1`.
    """
    from .api_upload import analyze_case as _analyze_case

    mode = payload.get("mode") or "full"
    if AnalyzeCaseRequest is None:
        raise HTTPException(status_code=503, detail="Upload/analysis system is not enabled")
    _require_case_access(db, auth, case_id)
    req = AnalyzeCaseRequest(document_ids=None, mode=mode)
    return await _analyze_case(case_id=case_id, request=req, auth=auth)


@frontend_router.get("/cases/{case_id}/analysis-status")
async def api_case_analysis_status(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    from .db.models import AnalysisRun
    _require_case_access(db, auth, case_id)
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.case_id == case_id)
        .order_by(AnalysisRun.created_at.desc())
        .first()
    )
    if not run:
        return {"status": "ready"}
    st = (run.status or "").lower()
    if st in ("done", "completed"):
        st = "completed"
    elif st in ("running", "queued"):
        st = "analyzing"
    elif st in ("failed", "error"):
        st = "failed"
    return {"status": st or "completed"}


@frontend_router.get("/cases/{case_id}/analysis")
async def api_case_analysis(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    """
    Minimal analysis payload for React UI.
    - `status`: completed/analyzing/ready/failed
    - `contradictions`: array with {id, description, type, severity, source1, source2}
    - `claims`: optional, for small header badges
    """
    from .db.models import AnalysisRun, Contradiction

    _require_case_access(db, auth, case_id)
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.case_id == case_id)
        .order_by(AnalysisRun.created_at.desc())
        .first()
    )
    if not run:
        return {"status": "ready", "contradictions": [], "claims": [], "entities": [], "metadata": {"claims_total": 0}}

    contradictions = (
        db.query(Contradiction)
        .filter(Contradiction.run_id == run.id)
        .order_by(Contradiction.created_at.asc())
        .all()
    )
    claims = db.query(Claim).filter(Claim.run_id == run.id).all()

    def _sev(v: Optional[str]) -> str:
        s = (v or "medium").lower()
        if s in ("critical",):
            return "high"
        if s in ("high", "medium", "low"):
            return s
        return "medium"

    out_contrs = []
    for c in contradictions:
        out_contrs.append(
            {
                "id": c.id,
                "type": c.contradiction_type,
                "severity": _sev(c.severity),
                "calculated_severity": _sev(c.severity),
                "description": c.explanation or "סתירה זוהתה",
                "source1": c.quote1,
                "source2": c.quote2,
            }
        )

    return {
        "status": (lambda s: "completed" if s in ("done", "completed") else "analyzing" if s in ("running", "queued") else "failed" if s in ("failed", "error") else (s or "completed"))((run.status or "").lower()),
        "contradictions": out_contrs,
        "claims": [{"id": cl.id, "text": cl.text} for cl in claims[:50]],
        "entities": [],
        "metadata": {"claims_total": len(claims), "contradictions_total": len(out_contrs)},
    }


@frontend_router.get("/cases/{case_id}/claims")
async def api_case_claims(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    """
    Legacy claims endpoint used by LegalNotebookPanel.
    Returns: { claims: [...] }
    """
    from .db.models import AnalysisRun
    _require_case_access(db, auth, case_id)
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.case_id == case_id)
        .order_by(AnalysisRun.created_at.desc())
        .first()
    )
    if not run:
        return {"claims": []}
    claims = db.query(Claim).filter(Claim.run_id == run.id).order_by(Claim.created_at.asc()).all()
    return {
        "claims": [
            {
                "id": c.id,
                "claim_text": c.text,
                "claim_type": "factual",
                "confidence": None,
                "party_from": c.party,
                "party_against": None,
                "evidence_refs": [
                    {
                        "doc_id": (c.locator_json or {}).get("doc_id"),
                        "page": None,
                        "quote": c.text[:220],
                    }
                ],
            }
            for c in claims
        ]
    }


legal_nb_router = APIRouter(prefix="/api/legal-notebook", tags=["legal-notebook"])


@legal_nb_router.get("/cases/{case_id}/contradictions")
async def api_legal_notebook_contradictions(case_id: str, db: Session = Depends(get_db_dependency)):
    """
    Minimal endpoint to unblock the LegalNotebookPanel.
    Returns: { contradictions: [...] }
    """
    from .db.models import AnalysisRun, Contradiction

    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.case_id == case_id)
        .order_by(AnalysisRun.created_at.desc())
        .first()
    )
    if not run:
        return {"contradictions": []}

    contradictions = (
        db.query(Contradiction)
        .filter(Contradiction.run_id == run.id)
        .order_by(Contradiction.created_at.asc())
        .all()
    )

    sev_map = {"critical": "CRITICAL", "high": "HIGH", "medium": "MED", "low": "LOW"}

    out = []
    for c in contradictions:
        out.append(
            {
                "id": c.id,
                "description": c.explanation or "סתירה זוהתה",
                "severity": sev_map.get((c.severity or "medium").lower(), "MED"),
                "statement_a": {
                    "claim_id": c.claim1_id,
                    "doc_id": (c.locator1_json or {}).get("doc_id"),
                    "page": None,
                    "quote": c.quote1,
                },
                "statement_b": {
                    "claim_id": c.claim2_id,
                    "doc_id": (c.locator2_json or {}).get("doc_id"),
                    "page": None,
                    "quote": c.quote2,
                },
            }
        )

    return {"contradictions": out}


# -----------------------------------------------------------------------------
# Additional /api/* stubs required by React UI contract tests
# -----------------------------------------------------------------------------

@frontend_router.get("/capabilities")
async def api_capabilities_root():
    # Global capability catalog (minimal)
    return {
        "capabilities": [
            {"id": "claims", "name": "Claims", "name_he": "טענות", "status": "ready"},
            {"id": "contradictions", "name": "Contradictions", "name_he": "סתירות", "status": "ready"},
        ]
    }


@frontend_router.get("/ui/microcopy")
async def api_ui_microcopy():
    # Minimal microcopy map; UI can safely fall back to defaults.
    return {}


@frontend_router.get("/cases/{case_id}/capabilities")
async def api_case_capabilities(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    _require_case_access(db, auth, case_id)
    return (await api_capabilities_root()).get("capabilities", [])


@frontend_router.get("/cases/{case_id}/state")
async def api_case_state(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    _require_case_access(db, auth, case_id)
    return {"case_id": case_id, "status": _case_status_for_ui(db, case_id)}


@frontend_router.get("/cases/{case_id}/jobs")
async def api_case_jobs(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    _require_case_access(db, auth, case_id)
    jobs = db.query(Job).filter(Job.case_id == case_id).order_by(Job.created_at.desc()).all()
    return {
        "jobs": [
            {
                "job_id": j.id,
                "status": (j.status.value if hasattr(j.status, "value") else str(j.status)),
                "type": (j.job_type.value if hasattr(j.job_type, "value") else str(j.job_type)),
                "progress": j.progress,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "error": j.error_message,
            }
            for j in jobs
        ]
    }


@frontend_router.get("/cases/{case_id}/snapshot")
async def api_case_snapshot(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    # Notebook snapshot is a composite; provide minimal structure.
    _require_case_access(db, auth, case_id)
    case = await api_get_case(case_id=case_id, db=db, auth=auth)
    analysis = await api_case_analysis(case_id=case_id, db=db, auth=auth)
    return {
        "case": case,
        "analysis": analysis,
        "generated_at": datetime.utcnow().isoformat(),
    }


@frontend_router.get("/cases/{case_id}/memory")
async def api_case_memory_get(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    c = _require_case_access(db, auth, case_id)
    mem = (c.extra_data or {}).get("memory", [])
    return {"memory": mem}


@frontend_router.post("/cases/{case_id}/memory")
async def api_case_memory_post(
    case_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    c = _require_case_access(db, auth, case_id)
    ed = c.extra_data or {}
    items = payload.get("memory") or payload.get("items") or payload
    ed["memory"] = items
    c.extra_data = ed
    db.commit()
    return {"ok": True}


@frontend_router.get("/files/{file_id}/info")
async def api_file_info(
    file_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    doc = db.query(Document).filter(Document.id == file_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    _require_case_access(db, auth, doc.case_id)
    return {
        "id": doc.id,
        "filename": doc.doc_name,
        "mime_type": doc.mime_type,
        "pages": doc.page_count,
        "uploaded_at": doc.created_at.isoformat() if doc.created_at else None,
    }


@frontend_router.get("/files/{file_id}/content")
async def api_file_content(
    file_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    doc = db.query(Document).filter(Document.id == file_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    _require_case_access(db, auth, doc.case_id)
    return {"text": doc.full_text or "", "id": doc.id}


@frontend_router.get("/files/{file_id}/page/{page}")
async def api_file_page(file_id: str, page: int):
    # Minimal placeholder image. The UI uses this for previews; real rendering can be wired later.
    # 1x1 transparent PNG
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return Response(content=png, media_type="image/png")


@frontend_router.get("/subscription/me")
async def api_subscription_me():
    # backend_lite does not enforce billing; return a conservative default.
    return {"tier": "free", "subscription_tier": "free", "role": "user"}


@frontend_router.get("/cases/{case_id}/ai-summary")
async def api_case_ai_summary(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    # Optional enhancement endpoint; UI can fall back to deterministic summaries.
    _require_case_access(db, auth, case_id)
    return {"exists": False, "summary": None}


@frontend_router.get("/cases/{case_id}/capabilities-manifest")
async def api_case_capabilities_manifest(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    # Placeholder manifest for notebook UX
    _require_case_access(db, auth, case_id)
    return {"case_id": case_id, "capabilities": (await api_case_capabilities(case_id, db=db, auth=auth)).copy()}


@frontend_router.get("/cases/{case_id}/context")
async def api_case_context_get(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    _require_case_access(db, auth, case_id)
    return {"has_context": False, "context": None}


@frontend_router.post("/cases/{case_id}/context")
async def api_case_context_post(
    case_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    _require_case_access(db, auth, case_id)
    return {"ok": True, "has_context": True, "context": payload}


@frontend_router.patch("/cases/{case_id}/context")
async def api_case_context_patch(
    case_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    _require_case_access(db, auth, case_id)
    return {"ok": True, "has_context": True, "context": payload}


@frontend_router.get("/cases/{case_id}/progress")
async def api_case_progress(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    _require_case_access(db, auth, case_id)
    st = _case_status_for_ui(db, case_id)
    return {"case_id": case_id, "status": st, "progress": 0 if st in ("ready", "completed") else 50, "current_stage": st}


@frontend_router.get("/cases/{case_id}/progress/refresh")
async def api_case_progress_refresh(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    return await api_case_progress(case_id=case_id, db=db, auth=auth)


@frontend_router.get("/cases/{case_id}/intelligence-status")
async def api_case_intelligence_status(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    _require_case_access(db, auth, case_id)
    return {"has_intelligence": False, "is_running": False, "can_run_intelligence": False, "progress": None}


@frontend_router.post("/cases/{case_id}/run-intelligence")
async def api_case_run_intelligence(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    # Not supported in backend_lite; keep contract stable.
    _require_case_access(db, auth, case_id)
    return {"status": "not_supported"}


@frontend_router.get("/cases/{case_id}/intelligence")
async def api_case_intelligence(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(get_auth_context),
):
    _require_case_access(db, auth, case_id)
    return {"intelligence": None}


@frontend_router.post("/cases/{case_id}/analyze-on-demand")
async def api_case_analyze_on_demand(
    case_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db_dependency),
):
    # Alias for reanalyze/full analysis
    mode = payload.get("mode") or "full"
    _require_case_access(db, auth, case_id)
    return await api_reanalyze_case(case_id=case_id, payload={"mode": mode}, auth=auth, db=db)


# Register routers
app.include_router(frontend_router)
app.include_router(legal_nb_router)


@app.websocket("/ws/progress/{case_id}")
async def ws_progress(websocket: WebSocket, case_id: str):
    """
    Minimal WebSocket endpoint for the React UI progress monitor.
    This implementation is intentionally lightweight: it accepts the connection and
    sends a single "connected" message, then waits for client disconnect.
    """
    await websocket.accept()
    try:
        await websocket.send_json({"case_id": case_id, "status": "connected"})
        while True:
            # Keep the socket open; client may ignore messages and just rely on connection.
            await websocket.receive_text()
    except WebSocketDisconnect:
        return


# =============================================================================
# Helper Functions
# =============================================================================

def convert_contradiction_to_output(
    contr: DetectedContradiction
) -> ContradictionOutput:
    """Convert internal contradiction to API output format with full evidence"""
    # Build locators for each claim
    locator1 = None
    locator2 = None

    # Get locator info from claims
    if hasattr(contr.claim1, 'doc_id') and contr.claim1.doc_id:
        locator1 = Locator(
            doc_id=contr.claim1.doc_id,
            page=getattr(contr.claim1, 'page', None),
            block_index=getattr(contr.claim1, 'block_index', None),
            paragraph=getattr(contr.claim1, 'paragraph_index', None),
            char_start=getattr(contr.claim1, 'char_start', None),
            char_end=getattr(contr.claim1, 'char_end', None)
        )

    if hasattr(contr.claim2, 'doc_id') and contr.claim2.doc_id:
        locator2 = Locator(
            doc_id=contr.claim2.doc_id,
            page=getattr(contr.claim2, 'page', None),
            block_index=getattr(contr.claim2, 'block_index', None),
            paragraph=getattr(contr.claim2, 'paragraph_index', None),
            char_start=getattr(contr.claim2, 'char_start', None),
            char_end=getattr(contr.claim2, 'char_end', None)
        )

    # Build ClaimEvidence for each side
    claim1_evidence = ClaimEvidence(
        claim_id=contr.claim1.id,
        doc_id=getattr(contr.claim1, 'doc_id', None),
        locator=locator1,
        anchor=EvidenceAnchor(
            doc_id=getattr(contr.claim1, 'doc_id', None) or "",
            page_no=getattr(contr.claim1, 'page', None),
            block_index=getattr(contr.claim1, 'block_index', None),
            paragraph_index=getattr(contr.claim1, 'paragraph_index', None),
            char_start=getattr(contr.claim1, 'char_start', None),
            char_end=getattr(contr.claim1, 'char_end', None),
            snippet=contr.quote1,
            bbox=getattr(contr.claim1, 'bbox', None),
        ) if getattr(contr.claim1, 'doc_id', None) else None,
        quote=contr.quote1,
        normalized=getattr(contr, 'normalized1', None)
    )

    claim2_evidence = ClaimEvidence(
        claim_id=contr.claim2.id,
        doc_id=getattr(contr.claim2, 'doc_id', None),
        locator=locator2,
        anchor=EvidenceAnchor(
            doc_id=getattr(contr.claim2, 'doc_id', None) or "",
            page_no=getattr(contr.claim2, 'page', None),
            block_index=getattr(contr.claim2, 'block_index', None),
            paragraph_index=getattr(contr.claim2, 'paragraph_index', None),
            char_start=getattr(contr.claim2, 'char_start', None),
            char_end=getattr(contr.claim2, 'char_end', None),
            snippet=contr.quote2,
            bbox=getattr(contr.claim2, 'bbox', None),
        ) if getattr(contr.claim2, 'doc_id', None) else None,
        quote=contr.quote2,
        normalized=getattr(contr, 'normalized2', None)
    )

    # Get status
    status = getattr(contr, 'status', ContradictionStatus.SUSPICIOUS)

    # Compute "usable" flag: Only What I Can Use
    # A contradiction is usable when:
    # 1. Status is verified or likely (not just suspicious)
    # 2. Has evidence locators (can show source)
    # 3. Has non-empty quotes
    has_good_status = status in (ContradictionStatus.VERIFIED, ContradictionStatus.LIKELY)
    has_locators = (locator1 is not None) or (locator2 is not None)
    has_quotes = bool(contr.quote1) and bool(contr.quote2)
    usable = has_good_status and has_locators and has_quotes

    return ContradictionOutput(
        id=contr.id,
        type=contr.type,
        subtype=getattr(contr, 'subtype', None),
        status=status,
        severity=contr.severity,
        confidence=contr.confidence,
        same_event_confidence=getattr(contr, 'same_event_confidence', None),
        claim1=claim1_evidence,
        claim2=claim2_evidence,
        # Legacy fields for backwards compatibility
        claim1_id=contr.claim1.id,
        claim2_id=contr.claim2.id,
        quote1=contr.quote1,
        quote2=contr.quote2,
        span1=None,
        span2=None,
        explanation=contr.explanation,
        usable=usable,
        # Category fields (hard contradiction vs narrative ambiguity)
        category=getattr(contr, 'category', None),
        ambiguity_explanation=getattr(contr, 'ambiguity_explanation', None),
        category_badge=getattr(contr, 'category_badge', None),
        category_label_short=getattr(contr, 'category_label_short', None),
    )


def convert_cross_exam_to_output(
    cross_exam: CrossExamSet
) -> CrossExamQuestionsOutput:
    """Convert internal cross-exam to API output format"""
    questions = [
        CrossExamQuestion(
            id=q.id,
            question=q.question,
            purpose=q.purpose,
            severity=q.severity,
            follow_up=q.follow_up,
        )
        for q in cross_exam.questions
    ]

    return CrossExamQuestionsOutput(
        contradiction_id=cross_exam.contradiction_id,
        target_party=cross_exam.target_party,
        questions=questions,
    )


def chunk_text_to_paragraphs(
    text: str,
    doc_id: str,
    case_id: str,
    min_chars: int = 50
) -> List[Paragraph]:
    """
    Split document text into paragraphs with stable IDs.

    Uses double newlines as primary delimiter, then numbered sections.
    Each paragraph gets a stable ID based on hash(doc_id + index + text[:100]).
    """
    import re

    paragraphs = []

    # Split on double newlines first
    raw_chunks = re.split(r'\n\s*\n', text)

    # Also handle numbered sections like "1." "2." etc.
    refined_chunks = []
    for chunk in raw_chunks:
        # Check if chunk has numbered items
        if re.search(r'^\s*\d+\.', chunk, re.MULTILINE):
            # Split by numbered items, keeping the numbers
            sub_chunks = re.split(r'(?=^\s*\d+\.)', chunk, flags=re.MULTILINE)
            refined_chunks.extend([c for c in sub_chunks if c.strip()])
        else:
            refined_chunks.append(chunk)

    # Create Paragraph objects
    char_offset = 0
    for idx, chunk_text in enumerate(refined_chunks):
        chunk_text = chunk_text.strip()

        # Skip very short chunks
        if len(chunk_text) < min_chars:
            char_offset = text.find(chunk_text, char_offset) + len(chunk_text)
            continue

        # Find character position in original text
        char_start = text.find(chunk_text, char_offset)
        if char_start == -1:
            char_start = char_offset
        char_end = char_start + len(chunk_text)

        # Compute stable ID
        para_id = Paragraph.compute_id(doc_id, idx, chunk_text)

        paragraphs.append(Paragraph(
            id=para_id,
            doc_id=doc_id,
            case_id=case_id,
            paragraph_index=idx,
            text=chunk_text,
            char_start=char_start,
            char_end=char_end
        ))

        char_offset = char_end

    return paragraphs


def build_claim_outputs(
    claims: List,
    claims_data: List[dict],
    doc_lookup: Optional[Dict[str, Any]] = None
) -> List[ClaimOutput]:
    """
    Build ClaimOutput list from extracted claims.

    Args:
        claims: List of Claim objects from extractor
        claims_data: Original claim data with doc info
        doc_lookup: Optional dict mapping doc_id to Document for party/role/author

    Returns:
        List of ClaimOutput for the response
    """
    claim_outputs = []

    # Build lookup from claims_data
    data_lookup = {d.get("id", f"claim_{i}"): d for i, d in enumerate(claims_data)}

    for claim in claims:
        # Get original data if available
        data = data_lookup.get(claim.id, {})

        # Build locator
        locator = None
        if claim.doc_id or claim.paragraph_index is not None or claim.char_start is not None:
            locator = Locator(
                doc_id=claim.doc_id,
                page=getattr(claim, "page", None),
                block_index=getattr(claim, "block_index", None),
                paragraph=claim.paragraph_index,
                char_start=claim.char_start,
                char_end=claim.char_end
            )
        anchor = None
        if claim.doc_id:
            anchor = EvidenceAnchor(
                doc_id=claim.doc_id,
                page_no=getattr(claim, "page", None),
                block_index=getattr(claim, "block_index", None),
                paragraph_index=claim.paragraph_index,
                char_start=claim.char_start,
                char_end=claim.char_end,
                snippet=claim.text,
                bbox=getattr(claim, "bbox", None),
            )

        # Extract features (dates, amounts) from metadata if available
        features = None
        if claim.metadata:
            dates = claim.metadata.get("dates", [])
            amounts = claim.metadata.get("amounts", [])
            entities = claim.metadata.get("entities", [])
            if dates or amounts or entities:
                features = ClaimFeatures(dates=dates, amounts=amounts, entities=entities)

        # Get party/role/author from document lookup if available
        party = data.get("party")
        role = data.get("role")
        author = data.get("author")

        if doc_lookup and claim.doc_id and claim.doc_id in doc_lookup:
            doc = doc_lookup[claim.doc_id]
            party = party or (doc.party.value if hasattr(doc, 'party') and doc.party else None)
            role = role or getattr(doc, 'role', None)
            author = author or getattr(doc, 'author', None)

        claim_outputs.append(ClaimOutput(
            id=claim.id,
            text=claim.text,
            doc_id=claim.doc_id or data.get("doc_id"),
            doc_name=claim.source or data.get("source"),
            party=party,
            role=role,
            author=author,
            witness_version_id=getattr(claim, "witness_version_id", None),
            locator=locator,
            anchor=anchor,
            features=features
        ))

    return claim_outputs


# =============================================================================
# Attribution Layer - Contradiction Bucketing
# =============================================================================

def apply_attribution_bucketing(
    contradictions: List[ContradictionOutput],
    claims_lookup: Dict[str, ClaimOutput]
) -> List[ContradictionOutput]:
    """
    Apply attribution layer bucketing to contradictions.

    Determines bucket (internal_contradiction/dispute/needs_classification)
    and relation (internal/cross_party/cross_doc) based on party of each claim.
    """
    for contr in contradictions:
        # Get parties from claims
        claim1_id = contr.claim1_id or (contr.claim1.claim_id if contr.claim1 else None)
        claim2_id = contr.claim2_id or (contr.claim2.claim_id if contr.claim2 else None)

        party1 = None
        party2 = None

        if claim1_id and claim1_id in claims_lookup:
            party1 = claims_lookup[claim1_id].party
        if claim2_id and claim2_id in claims_lookup:
            party2 = claims_lookup[claim2_id].party

        # Store parties on contradiction
        contr.claim1_party = party1
        contr.claim2_party = party2

        # Determine bucket and relation
        if not party1 or not party2 or party1 == "unknown" or party2 == "unknown":
            contr.bucket = ContradictionBucket.NEEDS_CLASSIFICATION
            contr.relation = None
        elif party1 == party2:
            # Same party = internal contradiction
            contr.bucket = ContradictionBucket.INTERNAL_CONTRADICTION
            # Check if same doc or different docs
            doc1 = contr.claim1.doc_id if contr.claim1 else None
            doc2 = contr.claim2.doc_id if contr.claim2 else None
            if doc1 and doc2 and doc1 != doc2:
                contr.relation = ContradictionRelation.CROSS_DOC
            else:
                contr.relation = ContradictionRelation.INTERNAL
        else:
            # Different parties = dispute
            contr.bucket = ContradictionBucket.DISPUTE
            contr.relation = ContradictionRelation.CROSS_PARTY

    return contradictions


def group_disputes_by_issue(
    contradictions: List[ContradictionOutput],
    claims_lookup: Dict[str, ClaimOutput]
) -> List[DisputeIssue]:
    """
    Group disputes into issues based on type and entities.

    Creates issue_id for each group and collects claims/evidence.
    """
    import hashlib

    # Filter to disputes only
    disputes = [c for c in contradictions if c.bucket == ContradictionBucket.DISPUTE]

    if not disputes:
        return []

    # Group by type + key entities/topic
    issue_groups: Dict[str, List[ContradictionOutput]] = {}

    for dispute in disputes:
        # Create issue key based on type and normalized content
        type_str = dispute.type.value if hasattr(dispute.type, 'value') else str(dispute.type)

        # Extract key terms from quotes for grouping
        quote1 = (dispute.quote1 or "")[:50]
        quote2 = (dispute.quote2 or "")[:50]

        # Simple key: type + first significant word from quotes
        key_words = []
        for word in (quote1 + " " + quote2).split():
            # Skip short/common words
            if len(word) > 3 and word not in ['היה', 'היא', 'הוא', 'את', 'של', 'על', 'עם']:
                key_words.append(word[:10])
                if len(key_words) >= 2:
                    break

        issue_key = f"{type_str}|{'_'.join(key_words)}"
        issue_id = f"issue_{hashlib.sha256(issue_key.encode()).hexdigest()[:8]}"

        # Assign issue_id to contradiction
        dispute.issue_id = issue_id

        if issue_id not in issue_groups:
            issue_groups[issue_id] = []
        issue_groups[issue_id].append(dispute)

    # Build DisputeIssue objects
    issues = []
    for issue_id, group in issue_groups.items():
        ours_claims = set()
        theirs_claims = set()
        contradiction_ids = []
        evidence_refs = []
        max_severity = None
        primary_type = None

        for contr in group:
            contradiction_ids.append(contr.id)

            # Collect claims by party
            claim1_id = contr.claim1_id or (contr.claim1.claim_id if contr.claim1 else None)
            claim2_id = contr.claim2_id or (contr.claim2.claim_id if contr.claim2 else None)

            if contr.claim1_party == "ours" and claim1_id:
                ours_claims.add(claim1_id)
            elif contr.claim1_party == "theirs" and claim1_id:
                theirs_claims.add(claim1_id)

            if contr.claim2_party == "ours" and claim2_id:
                ours_claims.add(claim2_id)
            elif contr.claim2_party == "theirs" and claim2_id:
                theirs_claims.add(claim2_id)

            # Collect evidence refs
            if contr.claim1:
                evidence_refs.append({
                    "doc_id": contr.claim1.doc_id,
                    "paragraph": contr.claim1.locator.paragraph if contr.claim1.locator else None,
                    "quote": contr.quote1 or contr.claim1.quote
                })
            if contr.claim2:
                evidence_refs.append({
                    "doc_id": contr.claim2.doc_id,
                    "paragraph": contr.claim2.locator.paragraph if contr.claim2.locator else None,
                    "quote": contr.quote2 or contr.claim2.quote
                })

            # Track max severity and type
            if not primary_type:
                primary_type = contr.type
            if contr.severity:
                severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
                current_order = severity_order.get(
                    contr.severity.value if hasattr(contr.severity, 'value') else str(contr.severity), 0
                )
                max_order = severity_order.get(
                    max_severity.value if max_severity and hasattr(max_severity, 'value') else str(max_severity) if max_severity else "", 0
                )
                if current_order > max_order:
                    max_severity = contr.severity

        # Generate title based on type
        type_titles = {
            "temporal_date_conflict": "מחלוקת על תאריך",
            "quant_amount_conflict": "מחלוקת על סכום",
            "actor_attribution_conflict": "מחלוקת על ייחוס פעולה",
            "presence_participation_conflict": "מחלוקת על נוכחות/השתתפות",
            "document_existence_conflict": "מחלוקת על קיום מסמך",
            "identity_basic_conflict": "מחלוקת על זהות",
            "factual_conflict": "מחלוקת עובדתית"
        }
        type_str = primary_type.value if primary_type and hasattr(primary_type, 'value') else str(primary_type)
        title = type_titles.get(type_str, "פלוגתא")

        issues.append(DisputeIssue(
            issue_id=issue_id,
            title=title,
            ours_claims=list(ours_claims),
            theirs_claims=list(theirs_claims),
            contradiction_ids=contradiction_ids,
            evidence_refs=evidence_refs[:6],  # Limit to 6 evidence refs
            type=primary_type,
            severity=max_severity
        ))

    return issues


def compute_attribution_summary(
    contradictions: List[ContradictionOutput],
    claims: List[ClaimOutput]
) -> AttributionSummary:
    """
    Compute summary statistics for attribution layer.
    """
    internal_theirs = 0
    internal_ours = 0
    disputes = 0
    needs_classification = 0

    for contr in contradictions:
        if contr.bucket == ContradictionBucket.INTERNAL_CONTRADICTION:
            if contr.claim1_party == "theirs":
                internal_theirs += 1
            elif contr.claim1_party == "ours":
                internal_ours += 1
        elif contr.bucket == ContradictionBucket.DISPUTE:
            disputes += 1
        elif contr.bucket == ContradictionBucket.NEEDS_CLASSIFICATION:
            needs_classification += 1

    # Check if any claims have party attribution
    has_party = any(c.party and c.party != "unknown" for c in claims)

    return AttributionSummary(
        internal_theirs=internal_theirs,
        internal_ours=internal_ours,
        disputes=disputes,
        needs_classification=needs_classification,
        has_party_attribution=has_party
    )


def compute_claim_results(
    claims: List,
    contradictions: List[ContradictionOutput]
) -> List[ClaimResult]:
    """
    Compute ClaimResult for each claim based on contradictions.

    Algorithm:
    1. Build map: claim_id -> list of contradictions
    2. For each claim:
       - If no contradictions: status = no_issues
       - If has verified contradiction: status = verified_contradiction
       - Else if has likely: status = potential_contradiction
       - Else: status = needs_review
    3. Compute count, max_severity, types, top_contradiction_ids

    Args:
        claims: List of Claim objects
        contradictions: List of ContradictionOutput

    Returns:
        List of ClaimResult in same order as claims
    """
    # Build adjacency: claim_id -> contradictions
    claim_contradictions: dict = {}
    for claim in claims:
        claim_contradictions[claim.id] = []

    for contr in contradictions:
        # Get claim IDs from contradiction (try multiple locations)
        claim1_id = contr.claim1_id or (contr.claim1.claim_id if contr.claim1 else None)
        claim2_id = contr.claim2_id or (contr.claim2.claim_id if contr.claim2 else None)

        if claim1_id and claim1_id in claim_contradictions:
            claim_contradictions[claim1_id].append(contr)
        if claim2_id and claim2_id in claim_contradictions:
            claim_contradictions[claim2_id].append(contr)

    # Severity ordering for comparison
    severity_order = {
        Severity.CRITICAL: 4,
        Severity.HIGH: 3,
        Severity.MEDIUM: 2,
        Severity.LOW: 1,
        None: 0
    }

    # Compute results
    results = []
    for claim in claims:
        contrs = claim_contradictions.get(claim.id, [])

        if not contrs:
            # No contradictions
            results.append(ClaimResult(
                claim_id=claim.id,
                status=ClaimStatus.NO_ISSUES,
                contradiction_count=0,
                max_severity=None,
                types=[],
                top_contradiction_ids=[]
            ))
            continue

        # Determine status based on contradiction statuses
        has_verified = any(c.status == ContradictionStatus.VERIFIED for c in contrs)
        has_likely = any(c.status == ContradictionStatus.LIKELY for c in contrs)

        if has_verified:
            status = ClaimStatus.VERIFIED_CONTRADICTION
        elif has_likely:
            status = ClaimStatus.POTENTIAL_CONTRADICTION
        else:
            status = ClaimStatus.NEEDS_REVIEW

        # Compute max severity
        max_sev = max(contrs, key=lambda c: severity_order.get(c.severity, 0)).severity

        # Get unique types
        types = list(set(c.type for c in contrs))

        # Top 3 by severity
        sorted_contrs = sorted(contrs, key=lambda c: severity_order.get(c.severity, 0), reverse=True)
        top_ids = [c.id for c in sorted_contrs[:3]]

        results.append(ClaimResult(
            claim_id=claim.id,
            status=status,
            contradiction_count=len(contrs),
            max_severity=max_sev,
            types=types,
            top_contradiction_ids=top_ids
        ))

    return results


def build_metadata(
    duration_ms: float,
    claims_total: int,
    llm_mode: LLMMode,
    rule_based_time_ms: float = 0.0,
    llm_time_ms: Optional[float] = None,
    model_used: Optional[str] = None,
    validation_flags: List[str] = None,
    llm_parse_ok: bool = True,
    llm_empty: bool = False,
    rule_stats: Optional[RuleStats] = None,
    verifier_stats: Optional[VerifierStats] = None,
    claim_results: List[ClaimResult] = None
) -> AnalysisMetadata:
    """
    Build AnalysisMetadata with the unified output contract fields.

    Args:
        duration_ms: Total processing time
        claims_total: Total claims analyzed
        llm_mode: LLM mode used
        rule_based_time_ms: Rule-based detection time
        llm_time_ms: LLM detection time if used
        model_used: LLM model name if used
        validation_flags: List of validation warnings
        llm_parse_ok: Whether LLM response was parsed successfully
        llm_empty: Whether LLM returned empty response
        rule_stats: Rule-based detection statistics
        verifier_stats: Verifier layer statistics
        claim_results: Computed claim results for counting

    Returns:
        AnalysisMetadata with all required fields
    """
    if validation_flags is None:
        validation_flags = []

    # Count claims by status
    claims_ok = 0
    claims_with_issues = 0
    if claim_results:
        for cr in claim_results:
            if cr.status == ClaimStatus.NO_ISSUES:
                claims_ok += 1
            else:
                claims_with_issues += 1

    return AnalysisMetadata(
        # Required fields
        duration_ms=duration_ms,
        claims_total=claims_total,
        llm_mode=llm_mode,
        # Timing
        rule_based_time_ms=rule_based_time_ms,
        llm_time_ms=llm_time_ms,
        total_time_ms=duration_ms,  # Legacy field
        # Counts
        claims_ok=claims_ok,
        claims_with_issues=claims_with_issues,
        contradictions_total=sum(1 for cr in (claim_results or []) if cr.contradiction_count > 0),
        # LLM status
        mode=llm_mode,  # Legacy field
        model_used=model_used,
        llm_parse_ok=llm_parse_ok,
        llm_empty=llm_empty,
        # Validation
        validation_flags=validation_flags,
        # Legacy
        claims_count=claims_total,
        # Detailed stats
        rule_stats=rule_stats,
        verifier_stats=verifier_stats,
    )


async def analyze_claims_internal(
    claims_data: List[dict],
    source_name: str = "document"
) -> AnalysisResponse:
    """
    Internal analysis function used by both endpoints.

    Always returns valid JSON, even on errors.
    Uses fallback to rule-based if LLM fails.
    """
    settings = get_settings()
    validation_flags = []

    # Validate config
    config_warnings = settings.validate_llm_config()
    validation_flags.extend(config_warnings)

    start_time = datetime.now()
    rule_based_time_ms = 0.0
    llm_time_ms = None

    # 1. Convert to Claim objects
    extractor = ClaimExtractor()
    claims = extractor.extract_from_claims_input(claims_data)

    if not claims:
        return AnalysisResponse(
            claims=[],
            claim_results=[],
            contradictions=[],
            cross_exam_questions=[],
            metadata=build_metadata(
                duration_ms=0.0,
                claims_total=0,
                llm_mode=get_llm_mode(),
                validation_flags=["NO_CLAIMS_EXTRACTED"]
            )
        )

    # 2. Rule-based detection (always runs)
    rule_start = datetime.now()
    rule_result = detect_contradictions(claims)
    rule_based_time_ms = (datetime.now() - rule_start).total_seconds() * 1000

    all_contradictions = list(rule_result.contradictions)

    # 3. LLM detection using new Analyzer/Verifier architecture (optional)
    llm_mode = get_llm_mode()
    model_used = None
    verifier_stats_data = None

    if llm_mode != LLMMode.NONE:
        try:
            llm_start = datetime.now()

            # Get analyzer (DeepSeek via OpenRouter)
            analyzer = get_analyzer()

            if analyzer.enabled:
                # Prepare claims for analyzer
                claims_for_llm = [
                    {"id": c.id, "text": c.text, "source": c.source}
                    for c in claims
                ]

                logger.info(f"Sending {len(claims_for_llm)} claims to analyzer")

                # Run analyzer
                analyzer_result = await analyzer.analyze(claims_for_llm)
                llm_time_ms = (datetime.now() - llm_start).total_seconds() * 1000

                logger.info(f"Analyzer result: success={analyzer_result.success}, contradictions={len(analyzer_result.contradictions)}")

                if analyzer_result.success and analyzer_result.contradictions:
                    model_used = analyzer.model

                    # Merge analyzer results with rule-based
                    existing_pairs = {
                        (c.claim1.id, c.claim2.id)
                        for c in all_contradictions
                    }

                    for llm_contr in analyzer_result.contradictions:
                        pair = (llm_contr.get("claim1_id"), llm_contr.get("claim2_id"))
                        if pair not in existing_pairs and pair[::-1] not in existing_pairs:
                            # Find the actual claim objects
                            claim1 = next((c for c in claims if c.id == pair[0]), None)
                            claim2 = next((c for c in claims if c.id == pair[1]), None)

                            if claim1 and claim2:
                                contr_type = llm_contr.get("type", "factual_conflict")
                                try:
                                    contr_type_enum = ContradictionType(contr_type)
                                except ValueError:
                                    contr_type_enum = ContradictionType.FACTUAL

                                severity_str = llm_contr.get("severity", "medium")
                                severity_map = {
                                    "critical": Severity.CRITICAL,
                                    "high": Severity.HIGH,
                                    "medium": Severity.MEDIUM,
                                    "low": Severity.LOW,
                                }
                                severity = severity_map.get(severity_str, Severity.MEDIUM)

                                all_contradictions.append(DetectedContradiction(
                                    id=f"contr_llm_{uuid.uuid4().hex[:6]}",
                                    claim1=claim1,
                                    claim2=claim2,
                                    type=contr_type_enum,
                                    subtype=None,  # Analyzer doesn't provide subtype
                                    status=ContradictionStatus.LIKELY,  # Analyzer = likely
                                    severity=severity,
                                    confidence=llm_contr.get("confidence", 0.7),
                                    same_event_confidence=llm_contr.get("confidence", 0.7),
                                    explanation=llm_contr.get("explanation", ""),
                                    quote1=llm_contr.get("quote1", claim1.text[:100]),
                                    quote2=llm_contr.get("quote2", claim2.text[:100]),
                                    metadata={"source": "analyzer", "model": model_used}
                                ))

                elif not analyzer_result.success:
                    validation_flags.append("ANALYZER_FAILED")
                    logger.error(f"Analyzer failed: {analyzer_result.error}")
                else:
                    validation_flags.append("ANALYZER_RETURNED_EMPTY")

            else:
                validation_flags.append("ANALYZER_NOT_ENABLED")

            # 3b. Run verifier on ambiguous/suspicious candidates (Qwen via OpenRouter)
            verifier = get_verifier()
            if verifier.enabled and all_contradictions:
                verifier.reset_stats()  # Reset for this analysis

                # Verify suspicious and likely candidates
                for contr in all_contradictions:
                    status = getattr(contr, 'status', ContradictionStatus.SUSPICIOUS)
                    confidence = getattr(contr, 'confidence', 0.5)

                    # Skip verified (rule-based) and very low confidence
                    if status == ContradictionStatus.VERIFIED:
                        continue
                    if confidence < 0.3:
                        continue
                    if not verifier.can_verify():
                        break  # Hit max calls

                    # Get claim texts
                    claim1_text = contr.claim1.text if hasattr(contr.claim1, 'text') else str(contr.claim1)
                    claim2_text = contr.claim2.text if hasattr(contr.claim2, 'text') else str(contr.claim2)
                    suggested_type = contr.type.value if hasattr(contr.type, 'value') else str(contr.type)

                    # Run verification
                    verdict = await verifier.verify(claim1_text, claim2_text, suggested_type)

                    if verdict and verdict.success:
                        # Update status based on verifier decision
                        if verdict.contradiction == "yes" and verdict.confidence >= 0.7:
                            contr.status = ContradictionStatus.LIKELY
                            contr.confidence = max(contr.confidence, verdict.confidence)
                        elif verdict.contradiction == "no":
                            contr.status = ContradictionStatus.SUSPICIOUS
                            contr.confidence = min(contr.confidence, 0.4)

                # Collect verifier stats
                v_stats = verifier.get_stats()
                verifier_stats_data = VerifierStats(
                    calls=v_stats.get("calls", 0),
                    promoted=v_stats.get("promoted", 0),
                    rejected=v_stats.get("rejected", 0),
                    unclear=v_stats.get("unclear", 0)
                )

        except Exception as e:
            logger.error(f"LLM detection failed: {e}")
            validation_flags.append("LLM_FAILED_FALLBACK")
            llm_time_ms = 0.0

    # 4. Deduplicate contradictions
    deduped_contradictions = []
    for c in all_contradictions:
        deduped_contradictions.append({
            "explanation": c.explanation,
            "claim1_id": c.claim1.id,
            "claim2_id": c.claim2.id,
            "type": c.type.value,
            "_obj": c
        })
    deduped = deduplicate_contradictions(deduped_contradictions)
    all_contradictions = [d["_obj"] for d in deduped]

    # 5. Generate cross-examination questions
    cross_exam_sets = generate_cross_exam_questions(all_contradictions)

    # 6. Convert to output format
    contradictions_output = [
        convert_contradiction_to_output(c) for c in all_contradictions
    ]

    cross_exam_output = [
        convert_cross_exam_to_output(ce) for ce in cross_exam_sets
    ]

    # 7. Build claims table data
    claim_outputs = build_claim_outputs(claims, claims_data)
    claim_results = compute_claim_results(claims, contradictions_output)

    # 8. Apply Attribution Layer bucketing
    claims_lookup = {c.id: c for c in claim_outputs}
    contradictions_output = apply_attribution_bucketing(contradictions_output, claims_lookup)

    # 9. Group disputes by issue
    disputes = group_disputes_by_issue(contradictions_output, claims_lookup)

    # 10. Compute attribution summary
    attribution_summary = compute_attribution_summary(contradictions_output, claim_outputs)

    total_time_ms = (datetime.now() - start_time).total_seconds() * 1000

    return AnalysisResponse(
        claims=claim_outputs,
        claim_results=claim_results,
        contradictions=contradictions_output,
        cross_exam_questions=cross_exam_output,
        disputes=disputes,
        attribution_summary=attribution_summary,
        metadata=build_metadata(
            duration_ms=total_time_ms,
            claims_total=len(claims),
            llm_mode=llm_mode,
            rule_based_time_ms=rule_based_time_ms,
            llm_time_ms=llm_time_ms,
            model_used=model_used,
            validation_flags=validation_flags,
            verifier_stats=verifier_stats_data,
            claim_results=claim_results
        )
    )


# =============================================================================
# Endpoints
# =============================================================================

@app.get("/", tags=["UI"])
async def root():
    """Serve the main web UI"""
    # Prefer React build if available (CRA expects /static/* assets)
    if REACT_ENABLED:
        return FileResponse(str(REACT_BUILD_DIR / "index.html"))

    # Fallback to legacy static UI
    app_file = LEGACY_STATIC_DIR / "app.html"
    if app_file.exists():
        return FileResponse(str(app_file))
    index_file = LEGACY_STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Contradiction Service API", "docs": "/docs"}


@app.get("/simple", tags=["UI"])
async def simple_ui():
    """Serve the simple text analysis UI (original version)"""
    index_file = LEGACY_STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Simple UI not available"}


@app.get("/litigator", tags=["UI"])
async def litigator_dashboard():
    """Serve the Litigator Dashboard UI"""
    litigator_file = LEGACY_STATIC_DIR / "litigator.html"
    if litigator_file.exists():
        return FileResponse(str(litigator_file))
    # Fallback to basic UI
    return FileResponse(str(LEGACY_STATIC_DIR / "index.html"))


@app.post("/debug/init-demo", tags=["System"], include_in_schema=False)
async def init_demo_users(db: Session = Depends(get_db)):
    """Initialize demo users (for debugging)"""
    try:
        # Check if demo users exist
        existing = db.query(User).filter(User.email == "david@demo.com").first()
        if existing:
            users = db.query(User).all()
            return {
                "status": "exists",
                "message": "Demo users already exist",
                "users": [{"id": u.id, "email": u.email} for u in users]
            }

        # Create demo firm
        firm = Firm(name="משרד דמו לבדיקות", domain="demo.jethro.ai")
        db.add(firm)
        db.commit()
        db.refresh(firm)

        # Create demo users
        demo_users = [
            ("david@demo.com", "דוד כהן (Super Admin)", SystemRole.SUPER_ADMIN, "שותף בכיר"),
            ("sarah@demo.com", "שרה לוי (Admin)", SystemRole.ADMIN, "עו״ד בכיר"),
            ("moshe@demo.com", "משה ישראלי (Member)", SystemRole.MEMBER, "עו״ד"),
            ("rachel@demo.com", "רחל אברהם (Viewer)", SystemRole.VIEWER, "מתמחה"),
        ]

        created = []
        for email, name, role, prof_role in demo_users:
            user = User(
                firm_id=firm.id,
                email=email,
                name=name,
                system_role=role,
                professional_role=prof_role
            )
            db.add(user)
            db.flush()
            created.append({"id": user.id, "email": email})

        db.commit()
        return {"status": "created", "users": created, "firm_id": firm.id}
    except Exception as e:
        logger.error(f"Failed to create demo users: {e}")
        db.rollback()
        return {"status": "error", "message": str(e)}


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        version=settings.service_version,
        llm_mode=get_llm_mode(),
        timestamp=datetime.now()
    )


@app.post(
    "/analyze",
    response_model=AnalysisResponse,
    tags=["Analysis"],
    summary="Analyze free text for contradictions",
    responses={
        200: {"description": "Successful analysis"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    }
)
async def analyze_text(request: AnalyzeTextRequest):
    """
    Analyze free Hebrew text for contradictions.

    The text will be split into claims automatically.
    Returns contradictions and cross-examination questions.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        # Extract claims from text
        claims = extract_claims(
            text=request.text,
            source_name=request.source_name or "document"
        )

        # Convert to dict format
        claims_data = [c.to_dict() for c in claims]

        # Run analysis
        return await analyze_claims_internal(
            claims_data=claims_data,
            source_name=request.source_name or "document"
        )

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        # Return valid JSON even on error
        return AnalysisResponse(
            claims=[],
            claim_results=[],
            contradictions=[],
            cross_exam_questions=[],
            metadata=build_metadata(
                duration_ms=0.0,
                claims_total=0,
                llm_mode=get_llm_mode(),
                validation_flags=["ANALYSIS_ERROR", str(e)[:100]]
            )
        )


@app.post(
    "/analyze_claims",
    response_model=AnalysisResponse,
    tags=["Analysis"],
    summary="Analyze pre-extracted claims for contradictions",
    responses={
        200: {"description": "Successful analysis"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    }
)
async def analyze_claims(request: AnalyzeClaimsRequest):
    """
    Analyze pre-extracted claims for contradictions.

    Use this when you already have claims with IDs and metadata.
    Returns contradictions and cross-examination questions.
    """
    if not request.claims:
        raise HTTPException(status_code=400, detail="Claims list cannot be empty")

    try:
        # Convert to dict format
        claims_data = [c.model_dump() for c in request.claims]

        # Run analysis
        return await analyze_claims_internal(claims_data=claims_data)

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        # Return valid JSON even on error
        return AnalysisResponse(
            claims=[],
            claim_results=[],
            contradictions=[],
            cross_exam_questions=[],
            metadata=build_metadata(
                duration_ms=0.0,
                claims_total=0,
                llm_mode=get_llm_mode(),
                validation_flags=["ANALYSIS_ERROR", str(e)[:100]]
            )
        )


# =============================================================================
# Cross-Exam Track Generation
# =============================================================================

def generate_cross_exam_track(contr: ContradictionOutput) -> CrossExamTrack:
    """
    Generate a cross-examination track for a contradiction.

    Creates 4-step track: pin_fact_a, pin_fact_b, confront, close_gap
    With 3 style variants: calm, aggressive, judicial
    """
    def truncate(text: str, max_len: int) -> str:
        """Truncate text and remove system markers"""
        if not text:
            return ""
        # Remove system markers
        import re
        text = re.sub(r'תוצאות הניתוח|מטא-דאטה|טבלת טענות|LLM_|claim_|contr_', '', text)
        text = text.strip()
        return text[:max_len] + '...' if len(text) > max_len else text

    def get_type_key(t: str) -> str:
        """Map contradiction type to simple key"""
        t_lower = (t or "").lower()
        if "temporal" in t_lower or "date" in t_lower:
            return "temporal"
        if "quant" in t_lower or "amount" in t_lower:
            return "quant"
        if "presence" in t_lower or "particip" in t_lower:
            return "presence"
        if "actor" in t_lower or "attrib" in t_lower:
            return "actor"
        if "document" in t_lower or "doc" in t_lower:
            return "document"
        if "identity" in t_lower:
            return "identity"
        return "factual"

    def generate_goal(type_key: str) -> str:
        """Generate goal based on contradiction type"""
        goals = {
            "temporal": "להראות שינוי גרסה בנוגע לתאריכים",
            "quant": "להראות פער בין הסכומים שנטענו",
            "presence": "להוכיח סתירה בנוגע לנוכחות",
            "actor": "להראות אי-התאמה בייחוס הפעולה",
            "document": "להציג סתירה בנוגע לקיום המסמך",
            "identity": "להוכיח אי-התאמה בזיהוי",
            "factual": "להראות סתירה בין הטענות"
        }
        return goals.get(type_key, goals["factual"])

    def make_steps(quote1: str, quote2: str, style: str) -> List[TrackStep]:
        """Generate steps for a given style"""
        style_config = {
            "calm": {"prefix": "האם נכון ש", "suffix": "?"},
            "aggressive": {"prefix": "איך תסביר ש", "suffix": "?"},
            "judicial": {"prefix": "לצורך התיק, אשר ש", "suffix": ""}
        }
        cfg = style_config.get(style, style_config["calm"])

        confront_questions = {
            "calm": "אתה מסכים שיש סתירה בין שתי הטענות?",
            "aggressive": "אז איזו טענה נכונה - הראשונה או השנייה?",
            "judicial": "לתיק: האם הטענות עולות בקנה אחד?"
        }
        close_questions = {
            "calm": "איך מיישבים את הפער בין הגרסאות?",
            "aggressive": "למה שינית את הגרסה?",
            "judicial": "מבקש להבהיר את הסתירה לפרוטוקול"
        }

        return [
            TrackStep(
                step="pin_fact_a",
                question=truncate(f"{cfg['prefix']}{quote1}{cfg['suffix']}", 160),
                expected_answer="כן"
            ),
            TrackStep(
                step="pin_fact_b",
                question=truncate(f"{cfg['prefix']}{quote2}{cfg['suffix']}", 160),
                expected_answer="כן"
            ),
            TrackStep(
                step="confront",
                question=truncate(confront_questions[style], 160),
                expected_answer="הימנעות/התחמקות"
            ),
            TrackStep(
                step="close_gap",
                question=truncate(close_questions[style], 160),
                expected_answer="הסבר/שתיקה"
            )
        ]

    # Extract quotes
    quote1 = truncate(contr.quote1 or (contr.claim1.quote if contr.claim1 else "") or "", 100)
    quote2 = truncate(contr.quote2 or (contr.claim2.quote if contr.claim2 else "") or "", 100)

    type_key = get_type_key(contr.type.value if hasattr(contr.type, 'value') else str(contr.type))
    status_str = contr.status.value if hasattr(contr.status, 'value') else str(contr.status)
    severity_str = contr.severity.value if hasattr(contr.severity, 'value') else str(contr.severity)

    return CrossExamTrack(
        track_id=f"track_{contr.id}",
        contradiction_id=contr.id,
        type=type_key,
        status=status_str,
        severity=severity_str,
        confidence=contr.confidence or 0.0,
        goal=generate_goal(type_key),
        style_variants=StyleVariants(
            calm=make_steps(quote1, quote2, "calm"),
            aggressive=make_steps(quote1, quote2, "aggressive"),
            judicial=make_steps(quote1, quote2, "judicial")
        ),
        evidence={
            "claim1": TrackEvidence(
                claim_id=contr.claim1_id or (contr.claim1.claim_id if contr.claim1 else None),
                doc_name=contr.claim1.doc_id if contr.claim1 else None,
                locator=contr.claim1.locator if contr.claim1 else None,
                quote=truncate(contr.quote1 or (contr.claim1.quote if contr.claim1 else "") or "", 200)
            ),
            "claim2": TrackEvidence(
                claim_id=contr.claim2_id or (contr.claim2.claim_id if contr.claim2 else None),
                doc_name=contr.claim2.doc_id if contr.claim2 else None,
                locator=contr.claim2.locator if contr.claim2 else None,
                quote=truncate(contr.quote2 or (contr.claim2.quote if contr.claim2 else "") or "", 200)
            )
        }
    )


@app.post(
    "/generate_tracks",
    response_model=CrossExamTracksResponse,
    tags=["Analysis"],
    summary="Generate cross-examination tracks from analysis results"
)
async def generate_tracks_endpoint(analysis: AnalysisResponse):
    """
    Generate cross-examination tracks from analysis results.

    Takes an AnalysisResponse and generates CrossExamTrack for each
    verified or likely contradiction.
    """
    tracks = []

    for contr in analysis.contradictions:
        # Only generate tracks for verified/likely contradictions
        status_str = contr.status.value if hasattr(contr.status, 'value') else str(contr.status)
        if status_str not in ("verified", "likely"):
            continue

        track = generate_cross_exam_track(contr)
        tracks.append(track)

    return CrossExamTracksResponse(
        cross_exam_tracks=tracks,
        total_tracks=len(tracks),
        metadata={
            "source_contradictions": len(analysis.contradictions),
            "filtered_contradictions": len(tracks)
        }
    )


@app.post(
    "/analyze_with_tracks",
    tags=["Analysis"],
    summary="Analyze text and generate cross-exam tracks in one call"
)
async def analyze_with_tracks(request: AnalyzeTextRequest):
    """
    Analyze text for contradictions AND generate cross-examination tracks.

    Combines /analyze and /generate_tracks into a single call.
    Returns both the analysis response and cross-exam tracks.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        # Extract claims from text
        claims = extract_claims(
            text=request.text,
            source_name=request.source_name or "document"
        )

        # Convert to dict format
        claims_data = [c.to_dict() for c in claims]

        # Run analysis
        analysis = await analyze_claims_internal(
            claims_data=claims_data,
            source_name=request.source_name or "document"
        )

        # Generate tracks
        tracks = []
        for contr in analysis.contradictions:
            status_str = contr.status.value if hasattr(contr.status, 'value') else str(contr.status)
            if status_str in ("verified", "likely"):
                track = generate_cross_exam_track(contr)
                tracks.append(track)

        return {
            "analysis": analysis.model_dump(),
            "cross_exam_tracks": [t.model_dump() for t in tracks],
            "total_tracks": len(tracks)
        }

    except Exception as e:
        logger.error(f"Analysis with tracks failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def get_current_user(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db_dependency)
) -> Optional[AuthContext]:
    """
    Get current user from either:
    - `Authorization: Bearer <jwt>` (preferred when present)
    - `X-User-Id` header (legacy/backwards compatibility)
    - `X-User-Email` header (fallback for demo tooling)

    For MVP, this is a simple header-based auth.
    Returns None if no header provided (anonymous access for backwards compat).
    """
    token_user_id: Optional[str] = None
    token_email: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = decode_token(token)
        if payload:
            token_user_id = payload.get("sub")
            token_email = payload.get("email") or payload.get("preferred_username")

    effective_user_id = token_user_id or x_user_id
    effective_email = token_email or x_user_email

    if not effective_user_id and not effective_email:
        return None

    auth_service = get_auth_service(db)
    # Flexible auth: allow email fallback + optional dev/demo auto-provisioning
    auth = auth_service.get_auth_context_flexible(effective_user_id, email=effective_email)

    if not auth:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return auth


async def require_auth(
    auth: Optional[AuthContext] = Depends(get_current_user)
) -> AuthContext:
    """Require authenticated user"""
    if not auth:
        raise HTTPException(status_code=401, detail="Authentication required")
    return auth


# =============================================================================
# Auth Endpoints (JWT)
# =============================================================================

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    firm_id: Optional[str] = None  # If not provided, creates new firm


@app.post("/auth/login", tags=["Auth"], response_model=TokenResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db_dependency)):
    """
    Login with email and password.
    Returns JWT access token.
    """
    if not is_jwt_available() or not PASSWORD_HASHING_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="JWT authentication not available. Install PyJWT and passlib."
        )
    if is_password_too_long(request.password):
        raise HTTPException(
            status_code=400,
            detail=f"Password too long (max {MAX_PASSWORD_BYTES} bytes)"
        )

    auth_service = get_auth_service(db)
    auth = auth_service.authenticate_user(request.email, request.password)

    if not auth:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Create tokens
    token_data = {"sub": auth.user_id, "firm_id": auth.firm_id}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@app.post("/auth/register", tags=["Auth"], response_model=TokenResponse)
async def register(request: RegisterRequest, db: Session = Depends(get_db_dependency)):
    """
    Register a new user with email and password.
    If firm_id is not provided, creates a new firm for the user.
    """
    if not is_jwt_available() or not PASSWORD_HASHING_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="JWT authentication not available. Install PyJWT and passlib."
        )
    if is_password_too_long(request.password):
        raise HTTPException(
            status_code=400,
            detail=f"Password too long (max {MAX_PASSWORD_BYTES} bytes)"
        )

    # Check if email already exists
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create or get firm
    if request.firm_id:
        firm = db.query(Firm).filter(Firm.id == request.firm_id).first()
        if not firm:
            raise HTTPException(status_code=404, detail="Firm not found")
    else:
        # Create new firm
        firm = Firm(name=f"Firm for {request.email}")
        db.add(firm)
        db.commit()
        db.refresh(firm)

    # Create user with hashed password
    user = User(
        firm_id=firm.id,
        email=request.email,
        name=request.name,
        password_hash=get_password_hash(request.password),
        system_role=SystemRole.SUPER_ADMIN if not request.firm_id else SystemRole.MEMBER
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create tokens
    token_data = {"sub": user.id, "firm_id": firm.id}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@app.get("/auth/me", tags=["Auth"])
async def auth_me(
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """Get current authenticated user info from token"""
    firm = db.query(Firm).filter(Firm.id == auth.firm_id).first()

    return {
        "user_id": auth.user_id,
        "email": auth.email,
        "name": auth.name,
        "firm_id": auth.firm_id,
        "firm_name": firm.name if firm else None,
        "system_role": auth.system_role.value,
        "is_admin": auth.is_admin,
        "is_super_admin": auth.is_super_admin,
        "teams": auth.team_ids,
        "team_leader_of": auth.team_leader_of
    }


# Password Reset Request
class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


@app.post("/auth/forgot-password", tags=["Auth"])
async def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db_dependency)):
    """
    Request a password reset token.
    In production, this would send an email with the reset link.
    For now, returns the token directly (development mode).
    """
    import secrets
    import hashlib
    from .db.models import PasswordResetToken

    # Find user by email
    user = db.query(User).filter(User.email == request.email, User.is_active == True).first()

    # Always return success (don't reveal if email exists)
    if not user:
        return {"message": "If this email is registered, a reset link will be sent."}

    # Generate reset token
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # Delete any existing tokens for this user
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id).delete()

    # Create new token (expires in 1 hour)
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    db.add(reset_token)
    db.commit()

    # Send password reset email
    from .email_utils import send_password_reset_email, is_email_configured

    email_sent = send_password_reset_email(
        to_email=user.email,
        reset_token=token,
        user_name=user.name
    )

    # In development mode (no SMTP), include token in response
    is_dev = os.environ.get("ENVIRONMENT", "development") == "development"

    response = {"message": "If this email is registered, a reset link will be sent."}
    if is_dev and not is_email_configured():
        response["_dev_token"] = token  # Only in dev mode without SMTP!
        response["_dev_note"] = "SMTP not configured. Configure SMTP_HOST, SMTP_USER, SMTP_PASSWORD to send real emails."

    return response


@app.post("/auth/reset-password", tags=["Auth"])
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db_dependency)):
    """
    Reset password using a reset token.
    """
    import hashlib
    from .db.models import PasswordResetToken

    if not PASSWORD_HASHING_AVAILABLE:
        raise HTTPException(status_code=501, detail="Password hashing not available")

    if is_password_too_long(request.new_password):
        raise HTTPException(
            status_code=400,
            detail=f"Password too long (max {MAX_PASSWORD_BYTES} bytes)"
        )

    # Validate password strength
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Find token
    token_hash = hashlib.sha256(request.token.encode()).hexdigest()
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.used_at == None,
        PasswordResetToken.expires_at > datetime.utcnow()
    ).first()

    if not reset_token:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Get user
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    # Update password
    user.password_hash = get_password_hash(request.new_password)

    # Mark token as used
    reset_token.used_at = datetime.utcnow()

    db.commit()

    return {"message": "Password reset successfully"}


@app.post("/auth/refresh", tags=["Auth"], response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db_dependency)):
    """
    Refresh an access token using a refresh token.
    """
    from .db.models import TokenBlacklist
    from .token_blacklist import is_blacklisted as redis_blacklist_check

    if not is_jwt_available():
        raise HTTPException(status_code=501, detail="JWT not available")

    # Decode refresh token
    payload = decode_token(request.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Check token type
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # Check if token is blacklisted (Redis first, then database fallback)
    jti = payload.get("jti") or hashlib.sha256(request.refresh_token.encode()).hexdigest()[:32]

    # Fast Redis check
    redis_result = redis_blacklist_check(jti)
    if redis_result is True:
        raise HTTPException(status_code=401, detail="Token has been revoked")

    # Fallback to database if Redis returned None (not definitive)
    if redis_result is None:
        blacklisted = db.query(TokenBlacklist).filter(TokenBlacklist.jti == jti).first()
        if blacklisted:
            raise HTTPException(status_code=401, detail="Token has been revoked")

    # Get user
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Create new tokens
    token_data = {"sub": user.id, "firm_id": user.firm_id}
    new_access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token
    )


@app.post("/auth/logout", tags=["Auth"])
async def logout(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db_dependency)
):
    """
    Logout and invalidate the current access token.
    Also invalidates the refresh token if provided.
    """
    import hashlib
    from .db.models import TokenBlacklist
    from .token_blacklist import add_to_blacklist as redis_blacklist_add

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="No token provided")

    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token)

    if not payload:
        # Token already invalid, that's fine for logout
        return {"message": "Logged out"}

    # Add token to blacklist
    jti = payload.get("jti") or hashlib.sha256(token.encode()).hexdigest()[:32]
    user_id = payload.get("sub")
    exp = payload.get("exp")
    token_type = payload.get("type", "access")
    expires_at = datetime.utcfromtimestamp(exp) if exp else datetime.utcnow() + timedelta(hours=1)

    # Add to Redis blacklist (fast) for future checks
    redis_blacklist_add(jti, expires_at, token_type)

    # Also persist to database (for durability and Redis restart recovery)
    existing = db.query(TokenBlacklist).filter(TokenBlacklist.jti == jti).first()
    if not existing:
        blacklist_entry = TokenBlacklist(
            jti=jti,
            token_type=token_type,
            user_id=user_id,
            expires_at=expires_at
        )
        db.add(blacklist_entry)
        db.commit()

    return {"message": "Logged out successfully"}


# =============================================================================
# Case Management Endpoints
# =============================================================================

@app.post("/cases", tags=["Cases"], summary="Create a new case")
async def create_case(
    request: CreateCaseRequest,
    auth: Optional[AuthContext] = Depends(get_current_user),
    db: Session = Depends(get_db_dependency)
):
    """Create a new legal case"""
    try:
        # Require authentication
        if not auth or not auth.firm_id:
            raise HTTPException(status_code=401, detail="Authentication required to create cases")

        from .orgs import ensure_default_org, get_org_member

        org_id = request.organization_id
        if org_id:
            if auth.system_role not in (SystemRole.SUPER_ADMIN, SystemRole.ADMIN):
                member = get_org_member(db, org_id, auth.user_id)
                if not member:
                    raise HTTPException(status_code=403, detail="No access to organization")
        else:
            org = ensure_default_org(db, auth.firm_id, auth.user_id)
            org_id = org.id

        case = Case(
            name=request.name,
            description=request.description,
            client_name=request.client_name,
            our_side=request.our_side or "unknown",
            opponent_name=request.opponent_name,
            court=request.court,
            case_number=request.case_number,
            firm_id=auth.firm_id,
            created_by_user_id=auth.user_id,
            organization_id=org_id,
            status=CaseStatus.ACTIVE
        )
        db.add(case)
        db.commit()
        db.refresh(case)

        return {
            "id": case.id,
            "name": case.name,
            "client_name": case.client_name,
            "our_side": case.our_side or "unknown",
            "opponent_name": case.opponent_name,
            "court": case.court,
            "case_number": case.case_number,
            "description": case.description,
            "firm_id": case.firm_id,
            "organization_id": case.organization_id,
            "created_at": case.created_at.isoformat() if case.created_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create case failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/cases", tags=["Cases"], summary="List all cases")
async def list_cases(
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """List all legal cases (filtered by firm if authenticated)"""
    try:
        query = db.query(Case).filter(Case.firm_id == auth.firm_id)
        org_ids = _accessible_org_ids(db, auth)
        if org_ids is not None:
            query = query.filter(Case.organization_id.in_(org_ids))
        cases = query.all()

        result = []
        for c in cases:
            doc_count = db.query(Document).filter(Document.case_id == c.id).count()
            result.append({
                "id": c.id,
                "name": c.name,
                "client_name": c.client_name,
                "our_side": c.our_side or "unknown",
                "case_number": c.case_number,
                "status": c.status.value if c.status else "active",
                "description": c.description,
                "document_count": doc_count,
                "firm_id": c.firm_id,
                "organization_id": c.organization_id,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None
            })
        return result
    except Exception as e:
        logger.error(f"List cases failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/cases/{case_id}", tags=["Cases"], summary="Get case details")
async def get_case(
    case_id: str,
    db: Session = Depends(get_db_dependency),
    auth: AuthContext = Depends(require_auth),
):
    """Get case by ID"""
    try:
        case = _require_case_access(db, auth, case_id)

        return {
            "id": case.id,
            "name": case.name,
            "client_name": case.client_name,
            "our_side": case.our_side or "unknown",
            "opponent_name": case.opponent_name,
            "court": case.court,
            "case_number": case.case_number,
            "description": case.description,
            "tags": case.tags or [],
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "updated_at": case.updated_at.isoformat() if case.updated_at else None,
            "extra_data": case.extra_data or {},
            "organization_id": case.organization_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get case failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.post("/cases/{case_id}/documents", tags=["Documents"], summary="Add document to case")
async def add_document(case_id: str, request: AddDocumentRequest):
    """
    Add a document to a case.

    The document text is automatically chunked into paragraphs with stable IDs.
    Each paragraph can be referenced by doc_id + paragraph_id for evidence locators.
    """
    db = get_database()

    # Verify case exists
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    try:
        dtype = DocumentType(request.doc_type)
    except ValueError:
        dtype = DocumentType.OTHER

    # Parse party enum
    from .models import DocumentParty
    try:
        party = DocumentParty(request.party) if request.party else DocumentParty.UNKNOWN
    except ValueError:
        party = DocumentParty.UNKNOWN

    # 1. Add the document
    doc = db.add_document(
        case_id=case_id,
        name=request.name,
        text=request.extracted_text,
        doc_type=dtype,
        party=party,
        role=request.role,
        version=request.version,
        author=request.author
    )

    # 2. Chunk into paragraphs
    paragraphs = chunk_text_to_paragraphs(
        text=request.extracted_text,
        doc_id=doc.id,
        case_id=case_id
    )

    # 3. Store paragraphs
    if paragraphs:
        db.add_paragraphs(doc.id, case_id, paragraphs)

    return {
        "id": doc.id,
        "case_id": doc.case_id,
        "name": doc.name,
        "doc_type": doc.doc_type.value,
        "party": doc.party.value,
        "role": doc.role,
        "text_hash": doc.text_hash,
        "paragraph_count": len(paragraphs),
        "created_at": doc.created_at.isoformat()
    }


@app.get("/cases/{case_id}/documents", tags=["Documents"], summary="List case documents")
async def list_documents(case_id: str):
    """List all documents in a case"""
    db = get_database()

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    docs = db.get_case_documents(case_id)
    return [
        {
            "id": d.id,
            "name": d.name,
            "doc_type": d.doc_type.value,
            "party": d.party.value if d.party else "unknown",
            "role": d.role,
            "author": d.author,
            "text_hash": d.text_hash,
            "page_count": d.page_count,
            "created_at": d.created_at.isoformat()
        }
        for d in docs if d
    ]


@app.get("/documents/{doc_id}", tags=["Documents"], summary="Get document with text")
async def get_document(doc_id: str):
    """Get document by ID including full text"""
    db = get_database()
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "case_id": doc.case_id,
        "name": doc.name,
        "doc_type": doc.doc_type.value,
        "party": doc.party.value if doc.party else "unknown",
        "role": doc.role,
        "author": doc.author,
        "extracted_text": doc.extracted_text,
        "text_hash": doc.text_hash,
        "page_count": doc.page_count,
        "created_at": doc.created_at.isoformat(),
        "metadata": doc.metadata
    }


@app.get(
    "/documents/{doc_id}/snippet",
    response_model=SnippetResponse,
    tags=["Documents"],
    summary="Get paragraph snippet with context"
)
async def get_document_snippet(
    doc_id: str,
    paragraph_index: int = 0,
    highlight: Optional[str] = None
):
    """
    Get a specific paragraph with context (before/after paragraphs).

    Use this for "Show me the source" functionality in the UI.
    The optional `highlight` parameter specifies text to highlight within the paragraph.

    Args:
        doc_id: Document ID
        paragraph_index: Target paragraph index (0-based)
        highlight: Optional quote to highlight within the text

    Returns:
        SnippetResponse with main text and optional context
    """
    db = get_database()

    # Get the document
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get all paragraphs for the document
    paragraphs = db.get_document_paragraphs(doc_id)
    if not paragraphs:
        # Fall back to full text if no paragraphs
        return SnippetResponse(
            doc_id=doc_id,
            doc_name=doc.name,
            paragraph_index=0,
            text=doc.extracted_text or "",
            context_before=None,
            context_after=None,
            highlight_quote=highlight
        )

    # Find the target paragraph
    target_para = None
    for para in paragraphs:
        if para.paragraph_index == paragraph_index:
            target_para = para
            break

    if not target_para:
        # Try to find closest paragraph
        if paragraph_index < 0:
            target_para = paragraphs[0] if paragraphs else None
        elif paragraph_index >= len(paragraphs):
            target_para = paragraphs[-1] if paragraphs else None
        else:
            # Find by index position
            target_para = paragraphs[paragraph_index] if paragraph_index < len(paragraphs) else None

    if not target_para:
        raise HTTPException(status_code=404, detail="Paragraph not found")

    # Get context paragraphs
    context_before = None
    context_after = None

    # Find paragraphs by index
    para_by_index = {p.paragraph_index: p for p in paragraphs}

    if paragraph_index > 0 and (paragraph_index - 1) in para_by_index:
        context_before = para_by_index[paragraph_index - 1].text

    if (paragraph_index + 1) in para_by_index:
        context_after = para_by_index[paragraph_index + 1].text

    return SnippetResponse(
        doc_id=doc_id,
        doc_name=doc.name,
        paragraph_index=target_para.paragraph_index,
        text=target_para.text,
        context_before=context_before,
        context_after=context_after,
        highlight_quote=highlight,
        char_start=target_para.char_start,
        char_end=target_para.char_end
    )


@app.post("/cases/{case_id}/analyze", tags=["Analysis"], summary="Analyze case documents")
async def analyze_case(case_id: str, request: Optional[AnalyzeCaseRequest] = None):
    """
    Analyze documents in a case for contradictions.

    If document_ids is provided, only those documents are analyzed.
    Otherwise, all documents in the case are analyzed.

    Results are cached by document fingerprint unless force=True.
    """
    db = get_database()
    settings = get_settings()

    # Handle optional request body
    document_ids = request.document_ids if request else None
    force = request.force if request else False
    rag_top_k = request.rag_top_k if request else settings.rag_top_k

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Get documents
    all_docs = db.get_case_documents(case_id)
    if document_ids:
        docs = [d for d in all_docs if d and d.id in document_ids]
    else:
        docs = [d for d in all_docs if d]

    if not docs:
        raise HTTPException(status_code=400, detail="No documents found")

    # Check cache (unless force=True)
    fingerprint = DBAnalysisRun.compute_fingerprint(docs)

    if not force:
        cached_run = db.get_run_by_fingerprint(case_id, fingerprint)
        if cached_run:
            return {
                "cached": True,
                "run_id": cached_run.id,
                "contradictions": cached_run.contradictions,
                "cross_exam_questions": cached_run.cross_exam_questions,
                "validation_flags": cached_run.validation_flags,
                "duration_ms": cached_run.duration_ms,
                "created_at": cached_run.created_at.isoformat()
            }

    # Run analysis
    start_time = datetime.now()

    # Get paragraphs for all documents
    all_paragraphs = []
    for doc in docs:
        doc_paras = db.get_document_paragraphs(doc.id)
        if doc_paras:
            all_paragraphs.extend(doc_paras)
        else:
            # Fallback: if no paragraphs stored, chunk now
            new_paras = chunk_text_to_paragraphs(
                text=doc.extracted_text,
                doc_id=doc.id,
                case_id=case_id
            )
            if new_paras:
                db.add_paragraphs(doc.id, case_id, new_paras)
                all_paragraphs.extend(new_paras)

    # Extract claims from paragraphs with locators
    claims = []
    for para in all_paragraphs:
        # Get document name for source
        doc = next((d for d in docs if d.id == para.doc_id), None)
        doc_name = doc.name if doc else "unknown"

        para_claims = extract_claims(
            text=para.text,
            source_name=f"{doc_name}§{para.paragraph_index}",
            doc_id=para.doc_id,
            paragraph_id=para.id,
            paragraph_index=para.paragraph_index,
            char_offset=para.char_start or 0
        )
        claims.extend(para_claims)

    # Convert to dict format with locator info
    claims_data = []
    for c in claims:
        claim_dict = c.to_dict()
        claim_dict['doc_id'] = getattr(c, 'doc_id', None)
        claim_dict['paragraph_id'] = getattr(c, 'paragraph_id', None)
        claim_dict['paragraph_index'] = getattr(c, 'paragraph_index', None)
        claims_data.append(claim_dict)

    # Analyze
    result = await analyze_claims_internal(claims_data, source_name=case.name)

    duration_ms = (datetime.now() - start_time).total_seconds() * 1000

    # Save run
    run = DBAnalysisRun(
        id=str(uuid.uuid4()),
        case_id=case_id,
        document_ids=[d.id for d in docs],
        input_fingerprint=fingerprint,
        contradictions=[c.model_dump() for c in result.contradictions],
        cross_exam_questions=[q.model_dump() for q in result.cross_exam_questions],
        metadata={
            "paragraph_count": len(all_paragraphs),
            "claims_count": len(claims),
            "rag_top_k": rag_top_k
        },
        validation_flags=result.metadata.validation_flags,
        duration_ms=duration_ms
    )
    db.save_analysis_run(run)

    return {
        "cached": False,
        "run_id": run.id,
        "contradictions": run.contradictions,
        "cross_exam_questions": run.cross_exam_questions,
        "validation_flags": run.validation_flags,
        "duration_ms": run.duration_ms,
        "paragraph_count": len(all_paragraphs),
        "claims_count": len(claims),
        "created_at": run.created_at.isoformat()
    }


@app.get("/cases/{case_id}/runs", tags=["Analysis"], summary="List analysis runs")
async def list_runs(case_id: str):
    """List all analysis runs for a case"""
    db = get_database()

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    runs = db.get_case_runs(case_id)
    return [
        {
            "id": r.id,
            "document_ids": r.document_ids,
            "input_fingerprint": r.input_fingerprint,
            "contradictions_count": len(r.contradictions),
            "questions_count": len(r.cross_exam_questions),
            "duration_ms": r.duration_ms,
            "created_at": r.created_at.isoformat()
        }
        for r in runs
    ]


# =============================================================================
# Startup/Shutdown
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    settings = get_settings()
    logger.info(f"Starting Contradiction Service v{settings.service_version}")
    logger.info(f"LLM Mode: {settings.llm_mode}")
    # Storage config visibility (critical when using S3 across web+worker)
    # Support legacy alias STORAGE_TYPE as well.
    storage_backend = (os.environ.get("STORAGE_BACKEND") or os.environ.get("STORAGE_TYPE") or "local").strip().lower()
    if storage_backend == "s3":
        # Don't log secrets; only log whether creds appear to be present and which ENV keys were used.
        access_candidates = [
            "AWS_ACCESS_KEY_ID",
            "S3_ACCESS_KEY",
            "S3_ACCESS_KEY_ID",
            "S3_KEY_ID",
            "R2_ACCESS_KEY_ID",
        ]
        secret_candidates = [
            "AWS_SECRET_ACCESS_KEY",
            "S3_SECRET_KEY",
            "S3_SECRET_ACCESS_KEY",
            "S3_SECRET_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
        ]
        access_key_env = next((k for k in access_candidates if (os.environ.get(k) or "").strip()), None)
        secret_key_env = next((k for k in secret_candidates if (os.environ.get(k) or "").strip()), None)

        logger.info(
            "Storage backend: s3 (bucket=%s, endpoint=%s)",
            os.environ.get("S3_BUCKET") or "jethro-documents",
            os.environ.get("S3_ENDPOINT") or "(aws default)",
        )
        logger.info(
            "S3 credentials detected: access_key=%s secret_key=%s",
            access_key_env or "(missing)",
            secret_key_env or "(missing)",
        )
    else:
        logger.info("Storage backend: %s", storage_backend or "local")
    # Help confirm Railway deployments (if env vars are provided by platform)
    for key in ("RAILWAY_GIT_COMMIT_SHA", "RAILWAY_GIT_COMMIT", "GIT_COMMIT", "COMMIT_SHA"):
        val = os.environ.get(key)
        if val:
            logger.info(f"Build commit: {key}={val}")
            break

    warnings = settings.validate_llm_config()
    for warning in warnings:
        logger.warning(warning)

    # Initialize database + seed users.
    # In production (PostgreSQL/Railway) we do this in the background so /health can come up fast.
    # In SQLite (dev/tests) we do it synchronously so the first request doesn't race bootstrap.
    db_url_now = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")
    is_test_env = bool(os.environ.get("PYTEST_CURRENT_TEST")) or os.environ.get("BACKEND_LITE_SYNC_STARTUP", "").strip().lower() in ("1", "true", "yes", "y", "on")
    should_sync_bootstrap = is_test_env or db_url_now.startswith("sqlite")

    async def _bootstrap_db_background():
        try:
            await asyncio.to_thread(init_db)  # Creates tables if they don't exist
            db_url = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")
            db_type = "PostgreSQL" if db_url.startswith("postgresql") else "SQLite"
            logger.info(f"Database initialized ({db_type})")
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}")

        # Create demo users for testing (best-effort)
        try:
            await asyncio.to_thread(_create_demo_users)
        except Exception as e:
            logger.warning(f"Demo bootstrap failed: {e}")

    if should_sync_bootstrap:
        try:
            init_db()
            _create_demo_users()
        except Exception as e:
            logger.warning(f"Test bootstrap failed: {e}")
    else:
        asyncio.create_task(_bootstrap_db_background())


def _create_demo_users():
    """Create demo firm and users for testing"""
    try:
        with get_db_session() as db:
            # Get or create demo firm (idempotent across restarts)
            firm = db.query(Firm).filter(Firm.domain == "demo.jethro.ai").first()
            if not firm:
                firm = Firm(name="משרד דמו לבדיקות", domain="demo.jethro.ai")
                db.add(firm)
                db.commit()
                db.refresh(firm)
                logger.info(f"Demo firm created (id={firm.id})")
            else:
                logger.info(f"Demo firm already exists (id={firm.id})")

            demo_firm_id = firm.id

            # Ensure demo users exist (idempotent)
            demo_users = [
                ("david@demo.com", "דוד כהן (Super Admin)", SystemRole.SUPER_ADMIN, "שותף בכיר"),
                ("sarah@demo.com", "שרה לוי (Admin)", SystemRole.ADMIN, "עו״ד בכיר"),
                ("moshe@demo.com", "משה ישראלי (Member)", SystemRole.MEMBER, "עו״ד"),
                ("rachel@demo.com", "רחל אברהם (Viewer)", SystemRole.VIEWER, "מתמחה"),
                # Service account used by some internal/demo tooling
                ("system@demo.com", "System", SystemRole.SUPER_ADMIN, None),
            ]

            created_users = 0
            for email, name, role, prof_role in demo_users:
                existing = db.query(User).filter(User.firm_id == demo_firm_id, User.email == email).first()
                if existing:
                    continue
                user = User(
                    firm_id=demo_firm_id,
                    email=email,
                    name=name,
                    system_role=role,
                    professional_role=prof_role,
                    is_active=True,
                )
                db.add(user)
                created_users += 1

            # Ensure at least one demo team exists
            team = db.query(Team).filter(Team.firm_id == demo_firm_id, Team.name == "צוות ליטיגציה").first()
            if not team:
                team = Team(
                    firm_id=demo_firm_id,
                    name="צוות ליטיגציה",
                    description="צוות התדיינות ראשי",
                )
                db.add(team)

            db.commit()
            if created_users:
                logger.info(f"Demo users ensured (created={created_users})")

    except Exception as e:
        logger.warning(f"Could not create demo users: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    # Close legacy LLM client
    client = get_llm_client()
    await client.close()

    # Close new architecture clients
    analyzer = get_analyzer()
    await analyzer.close()

    verifier = get_verifier()
    await verifier.close()

    logger.info("Contradiction Service stopped")


# =============================================================================
# Firm Management Endpoints
# =============================================================================

class CreateFirmBody(BaseModel):
    name: str
    domain: Optional[str] = None


@app.post("/firms", tags=["Firms"], summary="Create a new firm")
async def create_firm_endpoint(
    payload: Optional[CreateFirmBody] = Body(default=None),
    name: Optional[str] = None,
    domain: Optional[str] = None,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """Create a new firm (super_admin only)"""
    # Support both JSON body (preferred) and legacy query params
    if payload is not None:
        name = payload.name
        domain = payload.domain
    if not name:
        raise HTTPException(status_code=400, detail="Firm name is required")

    if auth.system_role != SystemRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super_admin can create firms")

    firm = Firm(name=name, domain=domain)
    db.add(firm)
    db.commit()
    db.refresh(firm)

    return {
        "id": firm.id,
        "name": firm.name,
        "domain": firm.domain,
        "created_at": firm.created_at.isoformat() if firm.created_at else None
    }


@app.get("/firms", tags=["Firms"], summary="List firms")
async def list_firms(
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """List all firms (super_admin sees all, others see their own)"""
    if auth.system_role == SystemRole.SUPER_ADMIN:
        firms = db.query(Firm).all()
    else:
        firm = db.query(Firm).filter(Firm.id == auth.firm_id).first()
        firms = [firm] if firm else []

    return [
        {
            "id": f.id,
            "name": f.name,
            "domain": f.domain,
            "created_at": f.created_at.isoformat() if f.created_at else None
        }
        for f in firms if f
    ]


@app.get("/firms/{firm_id}", tags=["Firms"], summary="Get firm details")
async def get_firm_endpoint(
    firm_id: str,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """Get firm by ID"""
    # Users can only view their own firm unless super_admin
    if firm_id != auth.firm_id and auth.system_role != SystemRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Cannot view other firms")

    firm = db.query(Firm).filter(Firm.id == firm_id).first()

    if not firm:
        raise HTTPException(status_code=404, detail="Firm not found")

    return {
        "id": firm.id,
        "name": firm.name,
        "domain": firm.domain,
        "settings": firm.settings,
        "created_at": firm.created_at.isoformat() if firm.created_at else None,
        "extra_data": firm.extra_data
    }


# =============================================================================
# User Management Endpoints
# =============================================================================

class CreateUserBody(BaseModel):
    email: str
    name: str
    system_role: str = "member"
    professional_role: Optional[str] = None


@app.post("/users", tags=["Users"], summary="Create a new user")
async def create_user_endpoint(
    payload: Optional[CreateUserBody] = Body(default=None),
    email: Optional[str] = None,
    name: Optional[str] = None,
    system_role: str = "member",
    professional_role: Optional[str] = None,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """Create a new user in the firm"""
    # Support both JSON body (preferred) and legacy query params
    if payload is not None:
        email = payload.email
        name = payload.name
        system_role = payload.system_role or system_role
        professional_role = payload.professional_role
    if not email or not name:
        raise HTTPException(status_code=400, detail="email and name are required")

    # Check permissions
    if not auth.has_permission(Permission.USER_CREATE):
        raise HTTPException(status_code=403, detail="Cannot create users")

    # Validate role
    try:
        role_enum = SystemRole(system_role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid system_role: {system_role}")

    # Admin cannot create super_admin
    if role_enum == SystemRole.SUPER_ADMIN and auth.system_role != SystemRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super_admin can create super_admin users")

    # Check if email already exists
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        firm_id=auth.firm_id,
        email=email,
        name=name,
        system_role=role_enum,
        professional_role=professional_role
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "firm_id": user.firm_id,
        "email": user.email,
        "name": user.name,
        "system_role": user.system_role.value,
        "professional_role": user.professional_role,
        "created_at": user.created_at.isoformat() if user.created_at else None
    }


@app.get("/users", tags=["Users"], summary="List users in firm")
async def list_users(
    active_only: bool = True,
    email: Optional[str] = None,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """List all users in the firm"""
    if not auth.has_permission(Permission.USER_READ):
        raise HTTPException(status_code=403, detail="Cannot view users")

    query = db.query(User).filter(User.firm_id == auth.firm_id)
    if active_only:
        query = query.filter(User.is_active == True)
    if email:
        query = query.filter(User.email == email)
    users = query.all()

    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "system_role": u.system_role.value,
            "professional_role": u.professional_role,
            "is_active": u.is_active,
            "last_login": u.last_login.isoformat() if u.last_login else None
        }
        for u in users if u
    ]


@app.get("/users/me", tags=["Users"], summary="Get current user")
async def get_current_user_info(
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """Get current authenticated user info"""
    firm = db.query(Firm).filter(Firm.id == auth.firm_id).first()
    teams = db.query(Team).filter(Team.id.in_(auth.team_ids)).all() if auth.team_ids else []

    return {
        "id": auth.user_id,
        "email": auth.email,
        "name": auth.name,
        "system_role": auth.system_role.value,
        "professional_role": auth.professional_role,
        "firm": {
            "id": auth.firm_id,
            "name": firm.name if firm else None
        },
        "teams": [{"id": t.id, "name": t.name} for t in teams],
        "team_leader_of": auth.team_leader_of,
        "is_admin": auth.is_admin,
        "is_super_admin": auth.is_super_admin
    }


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    professional_role: Optional[str] = None


@app.patch("/users/me", tags=["Users"], summary="Update current user profile")
async def update_current_user_profile(
    request: UpdateProfileRequest,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """Update the current authenticated user's profile"""
    user = db.query(User).filter(User.id == auth.user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if request.name is not None:
        user.name = request.name.strip()

    if request.professional_role is not None:
        user.professional_role = request.professional_role.strip() if request.professional_role else None

    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "professional_role": user.professional_role,
        "message": "Profile updated successfully"
    }


@app.get("/users/by-email", tags=["Users"], summary="Get user by email (for demo login)")
async def get_user_by_email(email: str, db: Session = Depends(get_db_dependency)):
    """
    Get user by email address.
    Used for demo login - no authentication required.
    Only returns basic user info needed for login.
    """
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "system_role": user.system_role.value,
        "firm_id": user.firm_id,
        "professional_role": user.professional_role
    }


@app.get("/users/{user_id}", tags=["Users"], summary="Get user details")
async def get_user(
    user_id: str,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """Get user by ID"""
    if not auth.has_permission(Permission.USER_READ):
        raise HTTPException(status_code=403, detail="Cannot view users")

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Can only view users in same firm (unless super_admin)
    if user.firm_id != auth.firm_id and auth.system_role != SystemRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Cannot view users in other firms")

    return {
        "id": user.id,
        "firm_id": user.firm_id,
        "email": user.email,
        "name": user.name,
        "system_role": user.system_role.value,
        "professional_role": user.professional_role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None
    }


# =============================================================================
# Team Management Endpoints
# =============================================================================

class CreateTeamBody(BaseModel):
    name: str
    description: Optional[str] = None


@app.post("/teams", tags=["Teams"], summary="Create a new team")
async def create_team(
    payload: Optional[CreateTeamBody] = Body(default=None),
    name: Optional[str] = None,
    description: Optional[str] = None,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency),
):
    """Create a new team in the firm"""
    # Support both JSON body (preferred) and legacy query params
    if payload is not None:
        name = payload.name
        description = payload.description
    if not name:
        raise HTTPException(status_code=400, detail="Team name is required")

    if not auth.has_permission(Permission.TEAM_CREATE):
        raise HTTPException(status_code=403, detail="Cannot create teams")

    team = Team(
        firm_id=auth.firm_id,
        name=name,
        description=description,
        created_by_user_id=auth.user_id,
    )
    db.add(team)
    db.commit()
    db.refresh(team)

    return {
        "id": team.id,
        "firm_id": team.firm_id,
        "name": team.name,
        "description": team.description,
        "created_at": team.created_at.isoformat() if team.created_at else None
    }


@app.get("/teams", tags=["Teams"], summary="List teams in firm")
async def list_teams(
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency),
):
    """List all teams in the firm"""
    if not auth.has_permission(Permission.TEAM_READ):
        raise HTTPException(status_code=403, detail="Cannot view teams")
    teams = db.query(Team).filter(Team.firm_id == auth.firm_id).order_by(Team.created_at.desc()).all()

    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "created_at": t.created_at.isoformat() if t.created_at else None
        }
        for t in teams if t
    ]


@app.get("/teams/{team_id}", tags=["Teams"], summary="Get team details")
async def get_team_details(
    team_id: str,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency),
):
    """Get team by ID with members"""
    if not auth.has_permission(Permission.TEAM_READ):
        raise HTTPException(status_code=403, detail="Cannot view teams")

    team = db.query(Team).filter(Team.id == team_id).first()

    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if team.firm_id != auth.firm_id:
        raise HTTPException(status_code=403, detail="Cannot view teams in other firms")

    # Get team members
    members = db.query(TeamMember).filter(TeamMember.team_id == team_id).all()
    users_by_id = {
        u.id: u
        for u in db.query(User).filter(User.id.in_([m.user_id for m in members])).all()
    } if members else {}

    member_details = []
    for m in members:
        user = users_by_id.get(m.user_id)
        if not user:
            continue
        member_details.append({
            "id": m.user_id,  # UI expects `id`
            "user_id": m.user_id,
            "name": user.name,
            "email": user.email,
            "team_role": m.team_role.value if hasattr(m.team_role, "value") else str(m.team_role),
            "added_at": m.added_at.isoformat() if m.added_at else None
        })

    return {
        "id": team.id,
        "name": team.name,
        "description": team.description,
        "created_at": team.created_at.isoformat() if team.created_at else None,
        "members": member_details
    }


class AddTeamMemberRequest(BaseModel):
    user_id: str
    team_role: str = "team_member"


@app.post("/teams/{team_id}/members", tags=["Teams"], summary="Add member to team")
async def add_team_member(
    team_id: str,
    request: AddTeamMemberRequest,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency),
):
    """Add a user to a team"""
    if not auth.has_permission(Permission.TEAM_MANAGE_MEMBERS):
        raise HTTPException(status_code=403, detail="Cannot manage team members")

    if not auth.can_manage_team(team_id):
        raise HTTPException(status_code=403, detail="Cannot manage this team")

    # Validate role
    try:
        role_enum = TeamRole(request.team_role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid team_role: {request.team_role}")

    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.firm_id != auth.firm_id:
        raise HTTPException(status_code=403, detail="Cannot manage teams in other firms")

    target_user = db.query(User).filter(User.id == request.user_id).first()
    if not target_user or target_user.firm_id != auth.firm_id:
        raise HTTPException(status_code=403, detail="Cannot add user from different firm")

    existing = db.query(TeamMember).filter(
        TeamMember.team_id == team_id,
        TeamMember.user_id == request.user_id,
    ).first()
    if existing:
        existing.team_role = role_enum
        db.commit()
        return {
            "team_id": existing.team_id,
            "user_id": existing.user_id,
            "team_role": existing.team_role.value if hasattr(existing.team_role, "value") else str(existing.team_role),
            "added_at": existing.added_at.isoformat() if existing.added_at else None,
            "updated": True,
        }

    member = TeamMember(
        team_id=team_id,
        user_id=request.user_id,
        team_role=role_enum,
        added_by_user_id=auth.user_id,
    )
    db.add(member)
    db.commit()

    return {
        "team_id": member.team_id,
        "user_id": member.user_id,
        "team_role": member.team_role.value if hasattr(member.team_role, "value") else str(member.team_role),
        "added_at": member.added_at.isoformat() if member.added_at else None
    }


@app.delete("/teams/{team_id}/members/{user_id}", tags=["Teams"], summary="Remove member from team")
async def remove_team_member(
    team_id: str,
    user_id: str,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency),
):
    """Remove a user from a team"""
    if not auth.has_permission(Permission.TEAM_MANAGE_MEMBERS):
        raise HTTPException(status_code=403, detail="Cannot manage team members")

    if not auth.can_manage_team(team_id):
        raise HTTPException(status_code=403, detail="Cannot manage this team")

    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.firm_id != auth.firm_id:
        raise HTTPException(status_code=403, detail="Cannot manage teams in other firms")

    tm = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()
    if not tm:
        return {"message": "Member not found"}
    db.delete(tm)
    db.commit()

    return {"message": "Member removed"}


# =============================================================================
# Case Access Control Endpoints
# =============================================================================

@app.post("/cases/{case_id}/teams", tags=["Cases"], summary="Assign case to team")
async def assign_case_to_team(
    case_id: str,
    team_id: str = Query(...),
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """Assign a case to a team"""
    try:
        # Verify case exists and user has access
        case = _require_case_access(db, auth, case_id)

        # Verify team exists and is in same firm
        team = db.query(Team).filter(Team.id == team_id, Team.firm_id == auth.firm_id).first()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")

        # Only admin or team leader can assign
        if auth.system_role not in (SystemRole.SUPER_ADMIN, SystemRole.ADMIN):
            # Check if user is team leader
            tm = db.query(TeamMember).filter(
                TeamMember.team_id == team_id,
                TeamMember.user_id == auth.user_id,
                TeamMember.team_role == TeamRole.TEAM_LEADER
            ).first()
            if not tm:
                raise HTTPException(status_code=403, detail="Only admins or team leaders can assign cases to teams")

        # Check if already assigned
        existing = db.query(CaseTeam).filter(
            CaseTeam.case_id == case_id,
            CaseTeam.team_id == team_id
        ).first()
        if existing:
            return {
                "case_id": case_id,
                "team_id": team_id,
                "assigned_at": existing.assigned_at.isoformat()
            }

        # Create assignment
        ct = CaseTeam(
            case_id=case_id,
            team_id=team_id,
            assigned_by_user_id=auth.user_id
        )
        db.add(ct)
        db.commit()
        db.refresh(ct)

        return {
            "case_id": ct.case_id,
            "team_id": ct.team_id,
            "assigned_at": ct.assigned_at.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Assign case to team failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/cases/{case_id}/teams", tags=["Cases"], summary="List teams assigned to case")
async def list_case_teams(
    case_id: str,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """List all teams assigned to a case"""
    try:
        # Verify case exists and user has access
        case = _require_case_access(db, auth, case_id)

        # Get teams assigned to the case
        case_teams = db.query(CaseTeam).filter(CaseTeam.case_id == case_id).all()
        team_ids = [ct.team_id for ct in case_teams]

        if not team_ids:
            return []

        teams = db.query(Team).filter(Team.id.in_(team_ids)).all()

        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description
            }
            for t in teams
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List case teams failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.post("/cases/{case_id}/participants", tags=["Cases"], summary="Add participant to case")
async def add_case_participant(
    case_id: str,
    user_id: str = Query(...),
    role: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """Add a user as participant to a case"""
    try:
        # Verify case exists and is in user's firm
        case = _require_case_access(db, auth, case_id)

        # Only team leaders or admins can add participants
        if auth.system_role not in (SystemRole.SUPER_ADMIN, SystemRole.ADMIN):
            # Check if user is team leader for any team assigned to this case
            case_teams = db.query(CaseTeam).filter(CaseTeam.case_id == case_id).all()
            team_ids = [ct.team_id for ct in case_teams]
            if team_ids:
                is_team_leader = db.query(TeamMember).filter(
                    TeamMember.team_id.in_(team_ids),
                    TeamMember.user_id == auth.user_id,
                    TeamMember.team_role == TeamRole.TEAM_LEADER
                ).first() is not None
            else:
                # If no teams assigned, check if user created the case
                is_team_leader = case.created_by_user_id == auth.user_id

            if not is_team_leader:
                raise HTTPException(status_code=403, detail="Only team leaders can add participants")

        # Verify target user exists and is in same firm
        target_user = db.query(User).filter(User.id == user_id, User.firm_id == auth.firm_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found or not in same firm")

        # Check if already a participant
        existing = db.query(CaseParticipant).filter(
            CaseParticipant.case_id == case_id,
            CaseParticipant.user_id == user_id
        ).first()
        if existing:
            return {
                "case_id": case_id,
                "user_id": user_id,
                "name": target_user.name,
                "email": target_user.email,
                "role": existing.role,
                "added_at": existing.added_at.isoformat()
            }

        # Add participant
        cp = CaseParticipant(
            case_id=case_id,
            user_id=user_id,
            role=role,
            added_by_user_id=auth.user_id
        )
        db.add(cp)
        db.commit()
        db.refresh(cp)

        return {
            "case_id": cp.case_id,
            "user_id": cp.user_id,
            "name": target_user.name,
            "email": target_user.email,
            "role": cp.role,
            "added_at": cp.added_at.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add case participant failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/cases/{case_id}/participants", tags=["Cases"], summary="List case participants")
async def list_case_participants(
    case_id: str,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """List all participants in a case"""
    try:
        # Verify case exists and is in user's firm
        case = _require_case_access(db, auth, case_id)

        # Get participants with user info
        participants = db.query(CaseParticipant, User).join(
            User, CaseParticipant.user_id == User.id
        ).filter(CaseParticipant.case_id == case_id).all()

        result = []
        for cp, user in participants:
            result.append({
                "user_id": cp.user_id,
                "name": user.name,
                "email": user.email,
                "role": cp.role,
                "added_at": cp.added_at.isoformat()
            })

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List case participants failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# =============================================================================
# Authorized Case Listing
# =============================================================================

@app.get("/my/cases", tags=["Cases"], summary="List my accessible cases")
async def list_my_cases(
    status: Optional[str] = None,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_dependency)
):
    """List all cases the current user can access"""
    try:
        # Parse status filter
        status_enum = None
        if status:
            try:
                status_enum = CaseStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        # Build query for accessible cases
        # A user can access cases if they:
        # 1. Created the case
        # 2. Are a participant in the case
        # 3. Are a member of a team assigned to the case
        # 4. Are admin/super_admin of the firm

        from sqlalchemy import or_, distinct

        # Start with cases in the user's firm
        base_query = db.query(Case).filter(Case.firm_id == auth.firm_id)
        org_ids = _accessible_org_ids(db, auth)
        if org_ids is not None:
            base_query = base_query.filter(Case.organization_id.in_(org_ids))

        # Apply status filter if provided
        if status_enum:
            base_query = base_query.filter(Case.status == status_enum)

        # For super_admin or admin, show all firm cases
        if auth.system_role in (SystemRole.SUPER_ADMIN, SystemRole.ADMIN):
            cases = base_query.order_by(Case.updated_at.desc()).all()
        else:
            # For regular users, filter to accessible cases
            # Get team IDs for the user
            user_team_ids = db.query(TeamMember.team_id).filter(
                TeamMember.user_id == auth.user_id
            ).subquery()

            # Get case IDs assigned to those teams
            team_case_ids = db.query(CaseTeam.case_id).filter(
                CaseTeam.team_id.in_(user_team_ids)
            ).subquery()

            # Get case IDs where user is a participant
            participant_case_ids = db.query(CaseParticipant.case_id).filter(
                CaseParticipant.user_id == auth.user_id
            ).subquery()

            # Filter: user created it, is participant, or is in assigned team
            cases = base_query.filter(
                or_(
                    Case.created_by_user_id == auth.user_id,
                    Case.responsible_user_id == auth.user_id,
                    Case.id.in_(participant_case_ids),
                    Case.id.in_(team_case_ids)
                )
            ).order_by(Case.updated_at.desc()).all()

        # Build response with document counts
        result = []
        for case in cases:
            doc_count = db.query(Document).filter(Document.case_id == case.id).count()
            result.append({
                "id": case.id,
                "name": case.name,
                "client_name": case.client_name,
                "status": case.status.value if hasattr(case.status, 'value') else str(case.status),
                "our_side": case.our_side or "unknown",
                "case_number": case.case_number,
                "court": case.court,
                "description": case.description,
                "document_count": doc_count,
                "organization_id": case.organization_id,
                "created_at": case.created_at.isoformat() if case.created_at else None,
                "updated_at": case.updated_at.isoformat() if case.updated_at else None
            })

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List my cases failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# =============================================================================
# React Frontend Static Files & Catch-All Route
# =============================================================================

@app.get("/static/{path:path}", tags=["UI"], include_in_schema=False)
async def serve_react_static(path: str):
    """Serve React static assets (JS, CSS, images)"""
    if FRONTEND_BUILD_AVAILABLE:
        file_path = FRONTEND_BUILD_DIR / "static" / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
    # Fallback to backend_lite static
    fallback_path = STATIC_DIR / path
    if fallback_path.exists() and fallback_path.is_file():
        return FileResponse(str(fallback_path))
    raise HTTPException(status_code=404, detail="Static file not found")


@app.get("/manifest.json", tags=["UI"], include_in_schema=False)
async def serve_manifest():
    """Serve React manifest.json"""
    if FRONTEND_BUILD_AVAILABLE:
        return FileResponse(str(FRONTEND_BUILD_DIR / "manifest.json"))
    raise HTTPException(status_code=404, detail="Manifest not found")


@app.get("/favicon.ico", tags=["UI"], include_in_schema=False)
async def serve_favicon():
    """Serve favicon"""
    if FRONTEND_BUILD_AVAILABLE:
        favicon = FRONTEND_BUILD_DIR / "favicon.ico"
        if favicon.exists():
            return FileResponse(str(favicon))
    raise HTTPException(status_code=404, detail="Favicon not found")


@app.get("/{path:path}", tags=["UI"], include_in_schema=False)
async def catch_all(path: str):
    """Catch-all route for React client-side routing"""
    # Skip API routes and known static paths
    if path.startswith(("api/", "docs", "redoc", "openapi", "health", "analyze", "ws/")):
        raise HTTPException(status_code=404, detail="Not found")

    # Check for actual static files in frontend build
    if FRONTEND_BUILD_AVAILABLE:
        file_path = FRONTEND_BUILD_DIR / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        # Return index.html for client-side routing
        return FileResponse(str(FRONTEND_BUILD_DIR / "index.html"))

    # Fallback: check backend_lite static
    static_file = STATIC_DIR / path
    if static_file.exists() and static_file.is_file():
        return FileResponse(str(static_file))

    raise HTTPException(status_code=404, detail="Not found")


# =============================================================================
# Error Handlers
# =============================================================================

def _is_api_v1_request(request: Request) -> bool:
    return request.url.path.startswith("/api/v1")


def _sanitize_error_detail(detail: Any) -> Any:
    if detail is None:
        return None
    if isinstance(detail, str):
        compact = " ".join(detail.split())
        return compact[:300]
    return detail


def _error_code_for_status(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        413: "payload_too_large",
        422: "validation_error",
        500: "internal_error",
    }.get(status_code, "error")


def _build_error_payload(code: str, message: str, details: Any = None) -> Dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }


@app.exception_handler(HTTPException)
async def api_http_exception_handler(request: Request, exc: HTTPException):
    """Structured errors for /api/v1 endpoints."""
    if not _is_api_v1_request(request):
        return await http_exception_handler(request, exc)

    detail = _sanitize_error_detail(exc.detail)
    if isinstance(detail, dict):
        message = detail.get("message") or "שגיאה בבקשה"
        details = detail.get("details")
        code = detail.get("code") or _error_code_for_status(exc.status_code)
    elif isinstance(detail, str) and detail:
        message = detail
        details = None
        code = _error_code_for_status(exc.status_code)
    else:
        message = "שגיאה בבקשה"
        details = detail
        code = _error_code_for_status(exc.status_code)

    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_payload(code, message, details),
    )


@app.exception_handler(RequestValidationError)
async def api_validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return structured validation errors without leaking inputs."""
    if not _is_api_v1_request(request):
        return await request_validation_exception_handler(request, exc)

    sanitized_errors = [
        {"loc": err.get("loc"), "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_build_error_payload(
            "validation_error",
            "שגיאת אימות קלט",
            {"errors": sanitized_errors},
        ),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler - always return valid JSON"""
    logger.error("Unhandled exception on %s: %s", request.url.path, exc.__class__.__name__)
    if _is_api_v1_request(request):
        return JSONResponse(
            status_code=500,
            content=_build_error_payload("internal_error", "שגיאה פנימית", {"exception": exc.__class__.__name__}),
        )

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": _sanitize_error_detail(str(exc)),
            "validation_flags": ["UNHANDLED_ERROR"],
        },
    )


# =============================================================================
# Main (for direct execution)
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend_lite.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
