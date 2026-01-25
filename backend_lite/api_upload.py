"""
Upload & Folder API Endpoints
=============================

FastAPI router for document upload and folder management.
"""

import os
import json
import logging
import secrets
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query, Header, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .schemas import (
    EvidenceAnchor,
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationMemberAddRequest,
    OrganizationMemberResponse,
    OrganizationInviteCreateRequest,
    OrganizationInviteResponse,
    OrganizationInviteAcceptResponse,
    UserSearchResponse,
    TrainingStartRequest,
    TrainingSessionResponse,
    TrainingTurnRequest,
    TrainingTurnResponse,
    TrainingBackResponse,
    TrainingFinishResponse,
    EntityUsageSummary,
    WitnessCreateRequest,
    WitnessVersionCreateRequest,
    WitnessResponse,
    WitnessVersionResponse,
    WitnessVersionDiffResponse,
    VersionShift,
    ContradictionInsightResponse,
    CrossExamPlanResponse,
    CrossExamPlanStage,
    CrossExamPlanStep,
    CrossExamPlanBranch,
    WitnessSimulationResponse,
    WitnessSimulationStep,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])

# Upload limits (shared with ZIP validation defaults)
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_FILE_BYTES", str(25 * 1024 * 1024)))


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class FolderCreate(BaseModel):
    """Create folder request"""
    name: str = Field(..., min_length=1, max_length=255)
    parent_id: Optional[str] = None


class FolderResponse(BaseModel):
    """Folder response"""
    id: str
    name: str
    parent_id: Optional[str]
    scope_type: str
    created_at: datetime


class FolderTreeItem(BaseModel):
    """Folder tree item"""
    id: str
    name: str
    parent_id: Optional[str]
    children: List['FolderTreeItem'] = []
    document_count: int = 0


FolderTreeItem.model_rebuild()

def _enum_value(v):
    return v.value if hasattr(v, "value") else v


class DocumentMetadata(BaseModel):
    """Document metadata for upload"""
    party: Optional[str] = None  # ours/theirs/court/unknown
    role: Optional[str] = None  # statement_of_claim/defense/etc
    author: Optional[str] = None
    version_label: Optional[str] = None
    occurred_at: Optional[datetime] = None


class UploadResponse(BaseModel):
    """Upload response"""
    document_ids: List[str]
    job_ids: List[str]
    message: str


class ZipUploadResponse(BaseModel):
    """ZIP upload response"""
    job_id: str
    message: str


class AnalyzeCaseRequest(BaseModel):
    """Analyze case request body (accepts empty JSON {})"""
    document_ids: Optional[List[str]] = None
    mode: str = "full"


class JobStatusResponse(BaseModel):
    """Job status response"""
    job_id: str
    status: str
    progress: int = 0
    result: Optional[dict] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class DocumentResponse(BaseModel):
    """Document response"""
    id: str
    doc_name: str
    mime_type: str
    party: Optional[str]
    role: Optional[str]
    status: str
    page_count: Optional[int]
    created_at: datetime
    # UI/legacy aliases (some UIs still expect these names)
    filename: Optional[str] = None
    name: Optional[str] = None
    content_type: Optional[str] = None
    uploaded_at: Optional[datetime] = None
    pages: Optional[int] = None


class SnippetResponse(BaseModel):
    """Snippet response for "Show source" """
    doc_id: str
    doc_name: str
    page_no: int
    block_index: int
    text: str
    context_before: Optional[str] = None
    context_after: Optional[str] = None


class AnchorResolveRequest(BaseModel):
    """Resolve an evidence anchor to a snippet"""
    anchor: EvidenceAnchor
    context: int = Field(default=1, ge=0, le=3, description="Context blocks before/after")


class AnchorResolveResponse(BaseModel):
    """Resolved anchor snippet with highlight offsets"""
    doc_id: str
    doc_name: str
    page_no: Optional[int]
    block_index: Optional[int]
    paragraph_index: Optional[int]
    char_start: Optional[int]
    char_end: Optional[int]
    text: str
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    highlight_start: Optional[int] = None
    highlight_end: Optional[int] = None
    highlight_text: Optional[str] = None
    bbox: Optional[dict] = None


class WitnessVersionDiffRequest(BaseModel):
    """Request to diff two witness versions"""
    version_a_id: str
    version_b_id: str


class CrossExamPlanRequest(BaseModel):
    """Request to generate a cross-exam plan"""
    contradiction_ids: Optional[List[str]] = None
    witness_id: Optional[str] = None


class WitnessSimulationRequest(BaseModel):
    """Request to simulate witness responses"""
    persona: str = Field("cooperative", description="cooperative/evasive/hostile")
    plan_id: Optional[str] = None


# =============================================================================
# DEPENDENCY - AUTH CONTEXT (Unified from auth.py)
# =============================================================================

from .auth import AuthContext, AuthService, Permission, get_auth_service, decode_token
from .db.session import get_db, get_db_session
from sqlalchemy.orm import Session

def _normalize_party(party: Optional[str]) -> Optional[str]:
    """
    Normalize UI/legacy party values into API enum strings.

    DB enum expects: ours/theirs/court/third_party/unknown.
    """
    if not party:
        return None
    p = party.strip().lower()
    mapping = {
        "ours": "ours",
        "our": "ours",
        "plaintiff": "ours",
        "theirs": "theirs",
        "defendant": "theirs",
        "court": "court",
        "third_party": "third_party",
        "third-party": "third_party",
        "unknown": "unknown",
    }
    return mapping.get(p, p)

def _storage_provider_name() -> str:
    return (os.environ.get("STORAGE_BACKEND") or os.environ.get("STORAGE_TYPE") or "local").strip().lower() or "local"


def _is_firm_admin(auth: AuthContext) -> bool:
    return auth.system_role in ("admin", "super_admin")


def _require_org_role(db: Session, auth: AuthContext, org_id: str, allowed_roles: Optional[List[str]] = None):
    from .orgs import get_org_member
    from .db.models import OrganizationRole

    if _is_firm_admin(auth):
        return None

    member = get_org_member(db, org_id, auth.user_id)
    if not member:
        raise HTTPException(status_code=403, detail={"code": "org_forbidden", "message": "אין הרשאה למשרד זה"})

    if allowed_roles:
        if member.role.value not in allowed_roles:
            raise HTTPException(status_code=403, detail={"code": "org_forbidden", "message": "אין הרשאה לפעולה זו"})

    return member


def _require_case_access(db: Session, auth: AuthContext, case_id: str):
    from .db.models import Case
    from .orgs import ensure_default_org, get_org_member

    case = db.query(Case).filter(
        Case.id == case_id,
        Case.firm_id == auth.firm_id
    ).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.organization_id:
        org = ensure_default_org(db, auth.firm_id, auth.user_id)
        case.organization_id = org.id
        db.flush()

    if _is_firm_admin(auth):
        return case, None

    member = get_org_member(db, case.organization_id, auth.user_id)
    if not member:
        raise HTTPException(status_code=403, detail={"code": "org_forbidden", "message": "אין הרשאה למשרד זה"})

    return case, member


def _flatten_plan_steps(plan_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    for stage in plan_json.get("stages", []):
        stage_name = stage.get("stage", "mid")
        for step in stage.get("steps", []):
            steps.append({**step, "_stage": stage_name})
    return steps


def _find_plan_step(plan_json: Dict[str, Any], step_id: str) -> Optional[Dict[str, Any]]:
    for step in _flatten_plan_steps(plan_json):
        if step.get("id") == step_id:
            return step
    return None


def _narrative_shift_id(witness_id: str, shift: Dict[str, Any], idx: int) -> str:
    anchor = shift.get("anchor_a") or shift.get("anchor_b") or {}
    doc_id = anchor.get("doc_id") or "doc"
    char_start = anchor.get("char_start") or "pos"
    shift_type = shift.get("shift_type") or "shift"
    return f"{witness_id}:{shift_type}:{doc_id}:{char_start}:{idx}"


def get_db_dependency():
    """Get database session for FastAPI dependency injection"""
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()


async def get_auth_context(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db_dependency)
) -> AuthContext:
    """
    Get auth context from either:
    - `Authorization: Bearer <jwt>` (preferred when present)
    - `X-User-Id` (legacy)
    - `X-User-Email` (demo fallback)
    Uses unified AuthContext from auth.py.
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
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )

    auth_service = get_auth_service(db)
    auth = auth_service.get_auth_context_flexible(effective_user_id, email=effective_email)

    if not auth:
        # Helpful for ops debugging
        logger.warning(
            "Upload auth failed: user_id=%s email=%s",
            effective_user_id,
            effective_email,
        )
        raise HTTPException(
            status_code=401,
            detail="User not found or inactive"
        )

    return auth


# =============================================================================
# ORGANIZATIONS (B1)
# =============================================================================

@router.post("/orgs", response_model=OrganizationResponse)
async def create_org(
    payload: OrganizationCreateRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Create a new organization."""
    try:
        from .db.session import get_db_session
        from .db.models import Organization, OrganizationMember, OrganizationRole

        with get_db_session() as db:
            org = Organization(
                firm_id=auth.firm_id,
                name=payload.name.strip(),
            )
            db.add(org)
            db.flush()

            db.add(OrganizationMember(
                organization_id=org.id,
                user_id=auth.user_id,
                role=OrganizationRole.OWNER,
                added_by_user_id=auth.user_id,
            ))

            return OrganizationResponse(
                id=org.id,
                firm_id=org.firm_id,
                name=org.name,
                created_at=org.created_at,
            )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create organization")
        raise HTTPException(status_code=500, detail="Failed to create organization")


@router.get("/orgs", response_model=List[OrganizationResponse])
async def list_orgs(
    auth: AuthContext = Depends(get_auth_context)
):
    """List organizations for the current user."""
    try:
        from .db.session import get_db_session
        from .db.models import Organization, OrganizationMember

        with get_db_session() as db:
            query = db.query(Organization).filter(Organization.firm_id == auth.firm_id)
            if not _is_firm_admin(auth):
                query = query.join(
                    OrganizationMember,
                    OrganizationMember.organization_id == Organization.id
                ).filter(OrganizationMember.user_id == auth.user_id)

            orgs = query.order_by(Organization.created_at.asc()).all()
            return [
                OrganizationResponse(
                    id=org.id,
                    firm_id=org.firm_id,
                    name=org.name,
                    created_at=org.created_at,
                )
                for org in orgs
            ]

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to list organizations")
        raise HTTPException(status_code=500, detail="Failed to list organizations")


@router.get("/orgs/{org_id}", response_model=OrganizationResponse)
async def get_org(
    org_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """Get organization details."""
    try:
        from .db.session import get_db_session
        from .db.models import Organization

        with get_db_session() as db:
            org = db.query(Organization).filter(
                Organization.id == org_id,
                Organization.firm_id == auth.firm_id
            ).first()
            if not org:
                raise HTTPException(status_code=404, detail="Organization not found")

            _require_org_role(db, auth, org_id)
            return OrganizationResponse(
                id=org.id,
                firm_id=org.firm_id,
                name=org.name,
                created_at=org.created_at,
            )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch organization")
        raise HTTPException(status_code=500, detail="Failed to fetch organization")


@router.get("/orgs/{org_id}/members", response_model=List[OrganizationMemberResponse])
async def list_org_members(
    org_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """List organization members."""
    try:
        from .db.session import get_db_session
        from .db.models import OrganizationMember, User

        with get_db_session() as db:
            _require_org_role(db, auth, org_id)
            members = (
                db.query(OrganizationMember, User)
                .join(User, User.id == OrganizationMember.user_id)
                .filter(OrganizationMember.organization_id == org_id)
                .order_by(User.name.asc())
                .all()
            )
            return [
                OrganizationMemberResponse(
                    user_id=user.id,
                    email=user.email,
                    name=user.name,
                    role=member.role.value if hasattr(member.role, "value") else str(member.role),
                    added_at=member.added_at,
                )
                for member, user in members
            ]

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to list organization members")
        raise HTTPException(status_code=500, detail="Failed to list organization members")


@router.post("/orgs/{org_id}/members", response_model=OrganizationMemberResponse)
async def add_org_member(
    org_id: str,
    payload: OrganizationMemberAddRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Add existing user to organization."""
    try:
        from .db.session import get_db_session
        from .db.models import OrganizationMember, OrganizationRole, User

        with get_db_session() as db:
            _require_org_role(db, auth, org_id, allowed_roles=["owner"])

            user = db.query(User).filter(
                User.id == payload.user_id,
                User.firm_id == auth.firm_id
            ).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            existing = (
                db.query(OrganizationMember)
                .filter(
                    OrganizationMember.organization_id == org_id,
                    OrganizationMember.user_id == user.id,
                )
                .first()
            )
            if existing:
                raise HTTPException(status_code=409, detail="User already in organization")

            try:
                role = OrganizationRole(payload.role)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid role")
            member = OrganizationMember(
                organization_id=org_id,
                user_id=user.id,
                role=role,
                added_by_user_id=auth.user_id,
            )
            db.add(member)

            return OrganizationMemberResponse(
                user_id=user.id,
                email=user.email,
                name=user.name,
                role=role.value,
                added_at=member.added_at,
            )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to add organization member")
        raise HTTPException(status_code=500, detail="Failed to add organization member")


@router.post("/orgs/{org_id}/invites", response_model=OrganizationInviteResponse)
async def create_org_invite(
    org_id: str,
    payload: OrganizationInviteCreateRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Invite a user by email to an organization."""
    try:
        from .db.session import get_db_session
        from .db.models import OrganizationInvite, InviteStatus, OrganizationRole

        with get_db_session() as db:
            _require_org_role(db, auth, org_id, allowed_roles=["owner"])

            token = secrets.token_urlsafe(24)
            expires_at = datetime.utcnow() + timedelta(days=payload.expires_in_days)
            try:
                role = OrganizationRole(payload.role)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid role")

            invite = OrganizationInvite(
                organization_id=org_id,
                email=payload.email.strip().lower(),
                token=token,
                status=InviteStatus.PENDING,
                role=role,
                expires_at=expires_at,
                created_by_user_id=auth.user_id,
            )
            db.add(invite)
            db.flush()

            return OrganizationInviteResponse(
                id=invite.id,
                organization_id=invite.organization_id,
                email=invite.email,
                role=role.value,
                status=invite.status.value,
                expires_at=invite.expires_at,
                token=invite.token,
                created_at=invite.created_at,
            )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create invite")
        raise HTTPException(status_code=500, detail="Failed to create invite")


@router.post("/invites/{token}/accept", response_model=OrganizationInviteAcceptResponse)
async def accept_org_invite(
    token: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """Accept an organization invite."""
    try:
        from .db.session import get_db_session
        from .db.models import OrganizationInvite, InviteStatus, OrganizationMember

        with get_db_session() as db:
            invite = db.query(OrganizationInvite).filter(
                OrganizationInvite.token == token
            ).first()
            if not invite:
                raise HTTPException(status_code=404, detail="Invite not found")

            if invite.status != InviteStatus.PENDING:
                raise HTTPException(status_code=400, detail="Invite already used or invalid")

            if invite.expires_at < datetime.utcnow():
                invite.status = InviteStatus.EXPIRED
                db.commit()
                raise HTTPException(status_code=400, detail="Invite expired")

            if invite.email.lower() != (auth.email or "").lower():
                raise HTTPException(status_code=403, detail="Invite email mismatch")

            existing = db.query(OrganizationMember).filter(
                OrganizationMember.organization_id == invite.organization_id,
                OrganizationMember.user_id == auth.user_id,
            ).first()
            if not existing:
                db.add(OrganizationMember(
                    organization_id=invite.organization_id,
                    user_id=auth.user_id,
                    role=invite.role,
                    added_by_user_id=auth.user_id,
                ))

            invite.status = InviteStatus.ACCEPTED

            return OrganizationInviteAcceptResponse(
                organization_id=invite.organization_id,
                role=invite.role.value,
                status=invite.status.value,
            )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to accept invite")
        raise HTTPException(status_code=500, detail="Failed to accept invite")


@router.get("/users/search", response_model=List[UserSearchResponse])
async def search_users(
    q: str = Query(..., min_length=2, max_length=100),
    auth: AuthContext = Depends(get_auth_context)
):
    """Search users within firm by name or email."""
    try:
        from .db.session import get_db_session
        from .db.models import User

        with get_db_session() as db:
            query = db.query(User).filter(User.firm_id == auth.firm_id, User.is_active == True)
            like = f"%{q.strip()}%"
            query = query.filter((User.email.ilike(like)) | (User.name.ilike(like)))
            users = query.order_by(User.name.asc()).limit(20).all()

            return [
                UserSearchResponse(
                    id=user.id,
                    email=user.email,
                    name=user.name,
                )
                for user in users
            ]

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to search users")
        raise HTTPException(status_code=500, detail="Failed to search users")


# =============================================================================
# FOLDER ENDPOINTS
# =============================================================================

@router.post("/cases/{case_id}/folders", response_model=FolderResponse)
async def create_folder(
    case_id: str,
    folder: FolderCreate,
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Create a new folder within a case.
    """
    try:
        from .db.session import get_db_session
        from .db.models import Folder, FolderScope, Case

        with get_db_session() as db:
            # Verify case access
            case, _ = _require_case_access(db, auth, case_id)

            # Check for duplicate name under parent
            existing = db.query(Folder).filter(
                Folder.firm_id == auth.firm_id,
                Folder.parent_id == folder.parent_id,
                Folder.name == folder.name
            ).first()

            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Folder '{folder.name}' already exists"
                )

            # Create folder
            new_folder = Folder(
                firm_id=auth.firm_id,
                parent_id=folder.parent_id,
                scope_type=FolderScope.CASE,
                scope_id=case_id,
                case_id=case_id,
                name=folder.name,
                created_by_user_id=auth.user_id
            )
            db.add(new_folder)
            db.commit()
            db.refresh(new_folder)

            return FolderResponse(
                id=new_folder.id,
                name=new_folder.name,
                parent_id=new_folder.parent_id,
                scope_type=new_folder.scope_type.value,
                created_at=new_folder.created_at
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create folder")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases/{case_id}/folders/tree", response_model=List[FolderTreeItem])
async def get_folder_tree(
    case_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Get folder tree for a case.
    """
    try:
        from .db.session import get_db_session
        from .db.models import Folder, Document, Case

        with get_db_session() as db:
            # Verify case access
            case, _ = _require_case_access(db, auth, case_id)

            # Get all folders for case
            folders = db.query(Folder).filter(
                Folder.case_id == case_id,
                Folder.firm_id == auth.firm_id
            ).all()

            # Get document counts per folder
            from sqlalchemy import func
            doc_counts = dict(
                db.query(Document.folder_id, func.count(Document.id))
                .filter(Document.case_id == case_id)
                .group_by(Document.folder_id)
                .all()
            )

            # Build tree
            folder_map = {}
            root_folders = []

            for f in folders:
                item = FolderTreeItem(
                    id=f.id,
                    name=f.name,
                    parent_id=f.parent_id,
                    document_count=doc_counts.get(f.id, 0)
                )
                folder_map[f.id] = item

            # Link children to parents
            for f in folders:
                item = folder_map[f.id]
                if f.parent_id and f.parent_id in folder_map:
                    folder_map[f.parent_id].children.append(item)
                else:
                    root_folders.append(item)

            return root_folders

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get folder tree")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: str,
    recursive: bool = Query(default=False, description="Delete folder contents recursively"),
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Delete a folder.

    If recursive=False (default), folder must be empty.
    If recursive=True, deletes all documents and subfolders.
    """
    try:
        from .db.session import get_db_session
        from .db.models import Folder, Document, DocumentPage, DocumentBlock, Claim, Paragraph
        from .storage import get_storage

        with get_db_session() as db:
            folder = db.query(Folder).filter(
                Folder.id == folder_id,
                Folder.firm_id == auth.firm_id
            ).first()

            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found")

            # Check for documents
            docs = db.query(Document).filter(Document.folder_id == folder_id).all()

            # Check for subfolders
            subfolders = db.query(Folder).filter(Folder.parent_id == folder_id).all()

            if (docs or subfolders) and not recursive:
                raise HTTPException(
                    status_code=400,
                    detail="Folder is not empty. Use recursive=true to delete contents."
                )

            # If recursive, delete contents
            if recursive:
                storage = get_storage()

                # Delete documents in this folder
                for doc in docs:
                    # Delete related records
                    db.query(DocumentBlock).filter(DocumentBlock.document_id == doc.id).delete()
                    db.query(DocumentPage).filter(DocumentPage.document_id == doc.id).delete()
                    db.query(Claim).filter(Claim.doc_id == doc.id).delete()
                    db.query(Paragraph).filter(Paragraph.doc_id == doc.id).delete()

                    # Delete from storage
                    if doc.storage_key:
                        try:
                            storage.delete(doc.storage_key)
                        except Exception as e:
                            logger.warning(f"Failed to delete from storage: {e}")

                    db.delete(doc)

                # Recursively delete subfolders
                def delete_subfolder(subfolder_id: str):
                    subfolder_docs = db.query(Document).filter(Document.folder_id == subfolder_id).all()
                    nested_subfolders = db.query(Folder).filter(Folder.parent_id == subfolder_id).all()

                    for doc in subfolder_docs:
                        db.query(DocumentBlock).filter(DocumentBlock.document_id == doc.id).delete()
                        db.query(DocumentPage).filter(DocumentPage.document_id == doc.id).delete()
                        db.query(Claim).filter(Claim.doc_id == doc.id).delete()
                        db.query(Paragraph).filter(Paragraph.doc_id == doc.id).delete()
                        if doc.storage_key:
                            try:
                                storage.delete(doc.storage_key)
                            except:
                                pass
                        db.delete(doc)

                    for nested in nested_subfolders:
                        delete_subfolder(nested.id)
                        db.delete(nested)

                for subfolder in subfolders:
                    delete_subfolder(subfolder.id)
                    db.delete(subfolder)

            # Delete the folder
            db.delete(folder)
            db.commit()

            return {"message": "Folder deleted successfully", "id": folder_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete folder")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# DOCUMENT UPLOAD ENDPOINTS
# =============================================================================

@router.post("/cases/{case_id}/documents", response_model=UploadResponse)
async def upload_documents(
    case_id: str,
    # Accept both "files" (multi-upload) and "file" (single upload, used by static app.html)
    files: Optional[List[UploadFile]] = File(default=None),
    file: Optional[UploadFile] = File(default=None),
    metadata_json: str = Form(default="[]"),
    folder_id: Optional[str] = Form(default=None),
    # Simple UI sends these directly (not in metadata_json)
    party: Optional[str] = Form(default=None),
    role: Optional[str] = Form(default=None),
    author: Optional[str] = Form(default=None),
    version_label: Optional[str] = Form(default=None),
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Upload one or more documents to a case.

    Supports: PDF, DOCX, TXT, images (PNG/JPG).
    """
    try:
        from .db.session import get_db_session
        from .db.models import Document, DocumentStatus, Event, EventType, Case, DocumentPage, DocumentBlock
        from .storage import get_storage
        from .ingest import detect_mime_type, is_supported, parse_document
        from .jobs.queue import enqueue_job
        from .jobs.tasks import task_parse_document

        # Unify file inputs
        all_files: List[UploadFile] = []
        if files:
            all_files.extend(files)
        if file:
            all_files.append(file)
        if not all_files:
            raise HTTPException(status_code=400, detail="No files provided (expected multipart field 'file' or 'files')")

        # Parse metadata
        try:
            metadata_list = json.loads(metadata_json)
        except:
            metadata_list = []

        # Extend metadata list to match files
        while len(metadata_list) < len(all_files):
            metadata_list.append({})

        with get_db_session() as db:
            # Verify case access
            case, _ = _require_case_access(db, auth, case_id)

            storage = get_storage()
            document_ids = []
            job_ids = []
            provider = _storage_provider_name()

            for idx, up in enumerate(all_files):
                safe_filename = os.path.basename(up.filename or "")
                if not safe_filename:
                    raise HTTPException(status_code=400, detail="Invalid filename")

                # Read file
                data = await up.read()

                if not data:
                    continue

                if len(data) > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)}MB)",
                    )

                # Detect MIME type
                mime_type = detect_mime_type(safe_filename, data)

                if not is_supported(mime_type):
                    logger.warning(f"Skipping unsupported file: {safe_filename} ({mime_type})")
                    continue

                # Store file
                storage_key = storage.generate_key(
                    auth.firm_id, case_id, safe_filename
                )
                storage_meta = storage.put(storage_key, data, mime_type)

                # Get metadata for this file
                file_meta = metadata_list[idx] if idx < len(metadata_list) else {}
                # Allow simple-form fields as fallback (static UI)
                if party and "party" not in file_meta:
                    file_meta["party"] = party
                if role and "role" not in file_meta:
                    file_meta["role"] = role
                if author and "author" not in file_meta:
                    file_meta["author"] = author
                if version_label and "version_label" not in file_meta:
                    file_meta["version_label"] = version_label

                normalized_party = _normalize_party(file_meta.get("party"))

                # Create document record
                doc = Document(
                    firm_id=auth.firm_id,
                    case_id=case_id,
                    folder_id=folder_id,
                    doc_name=safe_filename,
                    original_filename=safe_filename,
                    mime_type=mime_type,
                    party=normalized_party,
                    role=file_meta.get('role'),
                    author=file_meta.get('author'),
                    version_label=file_meta.get('version_label'),
                    status=DocumentStatus.UPLOADED,
                    storage_key=storage_key,
                    storage_provider=provider,
                    size_bytes=storage_meta.size_bytes,
                    sha256=storage_meta.sha256,
                    created_by_user_id=auth.user_id
                )
                db.add(doc)
                db.flush()

                document_ids.append(doc.id)

                # Create event
                event = Event(
                    firm_id=auth.firm_id,
                    case_id=case_id,
                    event_type=EventType.DOCUMENT_ADDED,
                    document_id=doc.id,
                    created_by_user_id=auth.user_id
                )
                db.add(event)

                # IMPORTANT (Railway): when using local storage, web and worker run in
                # separate containers and do NOT share a filesystem. If we enqueue a
                # parse job, the worker may not be able to read the stored file and
                # will mark the document FAILED.
                #
                # Therefore, for local storage we parse inline and persist extracted
                # text/blocks immediately, making the document READY for analysis.
                if provider == "local":
                    try:
                        from .ingest.base import ParserError
                        doc.status = DocumentStatus.PROCESSING
                        db.flush()

                        parsed = parse_document(
                            data=data,
                            filename=safe_filename,
                            mime_type=mime_type,
                            force_ocr=False,
                        )

                        doc.full_text = parsed.full_text
                        doc.page_count = parsed.page_count
                        doc.language = parsed.language
                        doc.status = DocumentStatus.READY
                        doc.extra_data = {**(doc.extra_data or {}), **(parsed.metadata or {})}

                        # Persist pages + blocks for snippet/source functionality
                        for page in parsed.pages:
                            db_page = DocumentPage(
                                document_id=doc.id,
                                page_no=page.page_no,
                                text=page.text,
                                width=page.width,
                                height=page.height,
                            )
                            db.add(db_page)
                            for block in page.blocks:
                                db_block = DocumentBlock(
                                    document_id=doc.id,
                                    page_no=block.page_no,
                                    block_index=block.block_index,
                                    text=block.text,
                                    bbox_json=block.bbox,
                                    char_start=block.char_start,
                                    char_end=block.char_end,
                                    paragraph_index=block.paragraph_index,
                                    locator_json=block.to_locator_json(doc_id=doc.id),
                                )
                                db.add(db_block)
                    except ParserError as e:
                        doc.status = DocumentStatus.FAILED
                        doc.extra_data = doc.extra_data or {}
                        doc.extra_data["error"] = e.to_dict()
                        logger.warning("Inline parse failed: %s", e.code)
                        raise HTTPException(status_code=400, detail=e.to_dict())
                    except Exception:
                        doc.status = DocumentStatus.FAILED
                        doc.extra_data = doc.extra_data or {}
                        doc.extra_data["error"] = "שגיאה בעיבוד המסמך"
                        logger.exception("Inline parse failed")
                else:
                    # Enqueue parsing job for shared storage backends (S3, etc.)
                    job_result = enqueue_job(
                        task_parse_document,
                        document_id=doc.id,
                        storage_key=storage_key,
                        mime_type=mime_type,
                        firm_id=auth.firm_id,
                        job_id=f"parse_{doc.id}"
                    )
                    job_ids.append(job_result.get('job_id'))

            db.commit()

            return UploadResponse(
                document_ids=document_ids,
                job_ids=job_ids,
                message=f"Uploaded {len(document_ids)} documents"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cases/{case_id}/documents/zip", response_model=ZipUploadResponse)
async def upload_zip(
    case_id: str,
    file: UploadFile = File(...),
    base_folder_id: Optional[str] = Form(default=None),
    mapping_mode: str = Form(default="auto"),
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Upload a ZIP file with multiple documents.

    Creates folder structure mirroring ZIP contents.
    """
    try:
        from .db.session import get_db_session
        from .db.models import Case
        from .storage import get_storage
        from .jobs.queue import enqueue_job
        from .jobs.tasks import task_ingest_zip

        # Verify it's a ZIP
        if not file.filename.lower().endswith('.zip'):
            raise HTTPException(status_code=400, detail="File must be a ZIP")

        with get_db_session() as db:
            # Verify case access
            case, _ = _require_case_access(db, auth, case_id)

        # Read and store ZIP
        data = await file.read()
        storage = get_storage()
        storage_key = storage.generate_key(
            auth.firm_id, case_id, file.filename, prefix="uploads"
        )
        storage.put(storage_key, data, "application/zip")

        # Enqueue ingest job
        job_result = enqueue_job(
            task_ingest_zip,
            zip_storage_key=storage_key,
            case_id=case_id,
            firm_id=auth.firm_id,
            base_folder_id=base_folder_id,
            created_by_user_id=auth.user_id,
            mapping_mode=mapping_mode,
            queue_name="default",
            job_id=f"ingest_zip_{case_id}_{datetime.utcnow().timestamp()}"
        )

        return ZipUploadResponse(
            job_id=job_result.get('job_id'),
            message="ZIP upload started"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("ZIP upload failed")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# DOCUMENT QUERY ENDPOINTS
# =============================================================================

@router.get("/cases/{case_id}/documents", response_model=List[DocumentResponse])
async def list_documents(
    case_id: str,
    status: Optional[str] = None,
    party: Optional[str] = None,
    role: Optional[str] = None,
    folder_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context)
):
    """
    List documents in a case with optional filters.
    """
    try:
        from .db.session import get_db_session
        from .db.models import Document, Case

        with get_db_session() as db:
            # Verify case access
            case, _ = _require_case_access(db, auth, case_id)

            # Build query
            query = db.query(Document).filter(
                Document.case_id == case_id,
                Document.firm_id == auth.firm_id
            )

            if status:
                query = query.filter(Document.status == status)
            if party:
                query = query.filter(Document.party == party)
            if role:
                query = query.filter(Document.role == role)
            if folder_id:
                query = query.filter(Document.folder_id == folder_id)

            documents = query.order_by(Document.created_at.desc()).all()

            return [
                DocumentResponse(
                    id=d.id,
                    doc_name=d.doc_name,
                    mime_type=d.mime_type,
                    party=d.party.value if d.party else None,
                    role=d.role.value if d.role else None,
                    status=d.status.value,
                    page_count=d.page_count,
                    created_at=d.created_at,
                    # aliases
                    filename=d.doc_name,
                    name=d.doc_name,
                    content_type=d.mime_type,
                    uploaded_at=d.created_at,
                    pages=d.page_count,
                )
                for d in documents
            ]

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list documents")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/folders/{folder_id}/documents", response_model=List[DocumentResponse])
async def list_folder_documents(
    folder_id: str,
    status: Optional[str] = None,
    party: Optional[str] = None,
    role: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
):
    """
    List documents in a folder (UI convenience endpoint).

    Canonical filtering is also supported via:
    `GET /cases/{case_id}/documents?folder_id=...`
    """
    try:
        from .db.session import get_db_session
        from .db.models import Folder, Document

        with get_db_session() as db:
            folder = db.query(Folder).filter(
                Folder.id == folder_id,
                Folder.firm_id == auth.firm_id,
            ).first()
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found")

            query = db.query(Document).filter(
                Document.folder_id == folder_id,
                Document.firm_id == auth.firm_id,
            )

            if status:
                query = query.filter(Document.status == status)
            if party:
                query = query.filter(Document.party == party)
            if role:
                query = query.filter(Document.role == role)

            documents = query.order_by(Document.created_at.desc()).all()

            return [
                DocumentResponse(
                    id=d.id,
                    doc_name=d.doc_name,
                    mime_type=d.mime_type,
                    party=d.party.value if d.party else None,
                    role=d.role.value if d.role else None,
                    status=d.status.value,
                    page_count=d.page_count,
                    created_at=d.created_at,
                    # aliases
                    filename=d.doc_name,
                    name=d.doc_name,
                    content_type=d.mime_type,
                    uploaded_at=d.created_at,
                    pages=d.page_count,
                )
                for d in documents
            ]

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list folder documents")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Get document details.
    """
    try:
        from .db.session import get_db_session
        from .db.models import Document

        with get_db_session() as db:
            doc = db.query(Document).filter(
                Document.id == doc_id,
                Document.firm_id == auth.firm_id
            ).first()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            return {
                "id": doc.id,
                # Canonical fields
                "doc_name": doc.doc_name,
                "original_filename": doc.original_filename,
                "mime_type": doc.mime_type,
                "party": doc.party.value if doc.party else None,
                "role": doc.role.value if doc.role else None,
                "author": doc.author,
                "version_label": doc.version_label,
                "status": doc.status.value,
                "page_count": doc.page_count,
                "language": doc.language,
                "size_bytes": doc.size_bytes,
                "created_at": doc.created_at.isoformat(),
                "metadata": doc.extra_data or {},
                # UI/legacy aliases (to prevent "שגיאה בטעינת מסמך")
                "filename": doc.doc_name,
                "name": doc.doc_name,
                "content_type": doc.mime_type,
                "uploaded_at": doc.created_at.isoformat() if doc.created_at else None,
                "pages": doc.page_count,
                "extracted_text": doc.full_text or "",
                "text": doc.full_text or "",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get document")
        raise HTTPException(status_code=500, detail=str(e))


class UpdateDocumentRequest(BaseModel):
    """Update document metadata request"""
    doc_name: Optional[str] = None
    party: Optional[str] = None
    role: Optional[str] = None
    author: Optional[str] = None
    version_label: Optional[str] = None


@router.patch("/documents/{doc_id}")
async def update_document(
    doc_id: str,
    request: UpdateDocumentRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Update document metadata (name, party, role, etc.)
    """
    try:
        from .db.session import get_db_session
        from .db.models import Document

        with get_db_session() as db:
            doc = db.query(Document).filter(
                Document.id == doc_id,
                Document.firm_id == auth.firm_id
            ).first()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            # Update fields if provided
            if request.doc_name is not None:
                doc.doc_name = request.doc_name.strip()
            if request.party is not None:
                doc.party = _normalize_party(request.party)
            if request.role is not None:
                doc.role = request.role.strip() if request.role else None
            if request.author is not None:
                doc.author = request.author.strip() if request.author else None
            if request.version_label is not None:
                doc.version_label = request.version_label.strip() if request.version_label else None

            db.commit()
            db.refresh(doc)

            return {
                "id": doc.id,
                "doc_name": doc.doc_name,
                "party": _enum_value(doc.party) if doc.party else None,
                "role": doc.role,
                "author": doc.author,
                "version_label": doc.version_label,
                "message": "Document updated successfully"
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update document")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Delete a document and all related data.
    """
    try:
        from .db.session import get_db_session
        from .db.models import Document, DocumentPage, DocumentBlock, Claim, Paragraph
        from .storage import get_storage

        with get_db_session() as db:
            doc = db.query(Document).filter(
                Document.id == doc_id,
                Document.firm_id == auth.firm_id
            ).first()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            # Delete related records
            db.query(DocumentBlock).filter(DocumentBlock.document_id == doc_id).delete()
            db.query(DocumentPage).filter(DocumentPage.document_id == doc_id).delete()
            db.query(Claim).filter(Claim.doc_id == doc_id).delete()
            db.query(Paragraph).filter(Paragraph.doc_id == doc_id).delete()

            # Delete from storage if exists
            if doc.storage_key:
                try:
                    storage = get_storage()
                    storage.delete(doc.storage_key)
                except Exception as e:
                    logger.warning(f"Failed to delete from storage: {e}")

            # Delete document
            db.delete(doc)
            db.commit()

            return {"message": "Document deleted successfully", "id": doc_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete document")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}/download")
async def download_document(
    doc_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Download the original document file.
    """
    try:
        from .db.session import get_db_session
        from .db.models import Document
        from .storage import get_storage
        from fastapi.responses import StreamingResponse
        import io

        with get_db_session() as db:
            doc = db.query(Document).filter(
                Document.id == doc_id,
                Document.firm_id == auth.firm_id
            ).first()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            if not doc.storage_key:
                raise HTTPException(status_code=404, detail="Document file not available")

            storage = get_storage()
            file_data = storage.get(doc.storage_key)

            if not file_data:
                raise HTTPException(status_code=404, detail="Document file not found in storage")

            # Determine content type
            content_type = doc.mime_type or "application/octet-stream"
            filename = doc.original_filename or doc.doc_name or f"document-{doc_id}"

            return StreamingResponse(
                io.BytesIO(file_data),
                media_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to download document")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}/text")
async def get_document_text(
    doc_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Get full extracted text for a document.
    """
    try:
        from .db.session import get_db_session
        from .db.models import Document

        with get_db_session() as db:
            doc = db.query(Document).filter(
                Document.id == doc_id,
                Document.firm_id == auth.firm_id
            ).first()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            return {
                "doc_id": doc.id,
                "doc_name": doc.doc_name,
                "text": doc.full_text or "",
                "page_count": doc.page_count
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get document text")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}/snippet", response_model=SnippetResponse)
async def get_document_snippet(
    doc_id: str,
    page_no: int = Query(..., ge=1),
    block_index: int = Query(..., ge=0),
    context: int = Query(default=1, ge=0, le=3),
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Get a text snippet with context ("Show source" functionality).
    """
    try:
        from .db.session import get_db_session
        from .db.models import Document, DocumentBlock

        with get_db_session() as db:
            doc = db.query(Document).filter(
                Document.id == doc_id,
                Document.firm_id == auth.firm_id
            ).first()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            # Get target block
            block = db.query(DocumentBlock).filter(
                DocumentBlock.document_id == doc_id,
                DocumentBlock.page_no == page_no,
                DocumentBlock.block_index == block_index
            ).first()

            if not block:
                raise HTTPException(status_code=404, detail="Block not found")

            # Get context blocks
            context_before = None
            context_after = None

            if context > 0:
                prev_block = db.query(DocumentBlock).filter(
                    DocumentBlock.document_id == doc_id,
                    DocumentBlock.block_index == block_index - 1
                ).first()
                if prev_block:
                    context_before = prev_block.text

                next_block = db.query(DocumentBlock).filter(
                    DocumentBlock.document_id == doc_id,
                    DocumentBlock.block_index == block_index + 1
                ).first()
                if next_block:
                    context_after = next_block.text

            return SnippetResponse(
                doc_id=doc_id,
                doc_name=doc.doc_name,
                page_no=page_no,
                block_index=block_index,
                text=block.text,
                context_before=context_before,
                context_after=context_after
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get snippet")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/anchors/resolve", response_model=AnchorResolveResponse)
async def resolve_anchor(
    payload: AnchorResolveRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Resolve an evidence anchor into a snippet with highlight offsets.
    """
    try:
        from .db.session import get_db_session
        from .db.models import Document, DocumentBlock
        from .anchors import normalize_anchor_input

        anchor = normalize_anchor_input(payload.anchor.model_dump())

        if not anchor.get("doc_id"):
            raise HTTPException(status_code=400, detail="anchor.doc_id is required")

        with get_db_session() as db:
            doc = db.query(Document).filter(
                Document.id == anchor["doc_id"],
                Document.firm_id == auth.firm_id
            ).first()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            block = None
            page_no = anchor.get("page_no")
            block_index = anchor.get("block_index")
            paragraph_index = anchor.get("paragraph_index")

            if page_no is not None and block_index is not None:
                block = db.query(DocumentBlock).filter(
                    DocumentBlock.document_id == doc.id,
                    DocumentBlock.page_no == page_no,
                    DocumentBlock.block_index == block_index
                ).first()

            if block is None and block_index is not None:
                block = db.query(DocumentBlock).filter(
                    DocumentBlock.document_id == doc.id,
                    DocumentBlock.block_index == block_index
                ).first()

            if block is None and paragraph_index is not None:
                block = db.query(DocumentBlock).filter(
                    DocumentBlock.document_id == doc.id,
                    DocumentBlock.paragraph_index == paragraph_index
                ).first()

            # Fallback: find block by char offsets
            if block is None and anchor.get("char_start") is not None:
                block = db.query(DocumentBlock).filter(
                    DocumentBlock.document_id == doc.id,
                    DocumentBlock.char_start <= int(anchor["char_start"]),
                    DocumentBlock.char_end >= int(anchor["char_start"])
                ).order_by(DocumentBlock.block_index.asc()).first()

            context_before = None
            context_after = None
            highlight_start = None
            highlight_end = None
            highlight_text = None

            if block:
                text = block.text or ""

                # Context blocks (by block index)
                if payload.context > 0 and block.block_index is not None:
                    prev_block = db.query(DocumentBlock).filter(
                        DocumentBlock.document_id == doc.id,
                        DocumentBlock.block_index == block.block_index - 1
                    ).first()
                    if prev_block:
                        context_before = prev_block.text

                    next_block = db.query(DocumentBlock).filter(
                        DocumentBlock.document_id == doc.id,
                        DocumentBlock.block_index == block.block_index + 1
                    ).first()
                    if next_block:
                        context_after = next_block.text

                # Highlight offsets from char positions
                if anchor.get("char_start") is not None and anchor.get("char_end") is not None:
                    if block.char_start is not None:
                        highlight_start = max(0, int(anchor["char_start"]) - int(block.char_start))
                        highlight_end = max(
                            highlight_start,
                            min(len(text), int(anchor["char_end"]) - int(block.char_start))
                        )
                # Fallback highlight by snippet match
                if highlight_start is None and anchor.get("snippet"):
                    idx = text.find(anchor["snippet"])
                    if idx != -1:
                        highlight_start = idx
                        highlight_end = idx + len(anchor["snippet"])

                if highlight_start is not None and highlight_end is not None:
                    highlight_text = text[highlight_start:highlight_end]

                return AnchorResolveResponse(
                    doc_id=doc.id,
                    doc_name=doc.doc_name,
                    page_no=block.page_no,
                    block_index=block.block_index,
                    paragraph_index=block.paragraph_index,
                    char_start=anchor.get("char_start"),
                    char_end=anchor.get("char_end"),
                    text=text,
                    context_before=context_before,
                    context_after=context_after,
                    highlight_start=highlight_start,
                    highlight_end=highlight_end,
                    highlight_text=highlight_text,
                    bbox=block.bbox_json,
                )

            # Fallback: return full text (no block)
            full_text = doc.full_text or ""
            if anchor.get("char_start") is not None and anchor.get("char_end") is not None:
                highlight_start = max(0, int(anchor["char_start"]))
                highlight_end = min(len(full_text), int(anchor["char_end"]))
                highlight_text = full_text[highlight_start:highlight_end]

            return AnchorResolveResponse(
                doc_id=doc.id,
                doc_name=doc.doc_name,
                page_no=page_no,
                block_index=block_index,
                paragraph_index=paragraph_index,
                char_start=anchor.get("char_start"),
                char_end=anchor.get("char_end"),
                text=full_text,
                context_before=None,
                context_after=None,
                highlight_start=highlight_start,
                highlight_end=highlight_end,
                highlight_text=highlight_text,
                bbox=anchor.get("bbox"),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to resolve anchor")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# WITNESSES
# =============================================================================

@router.get("/cases/{case_id}/witnesses", response_model=List[WitnessResponse])
async def list_witnesses(
    case_id: str,
    include_versions: bool = True,
    auth: AuthContext = Depends(get_auth_context)
):
    """List witnesses for a case."""
    try:
        from .db.session import get_db_session
        from .db.models import Case, Witness, WitnessVersion, Document

        with get_db_session() as db:
            case, _ = _require_case_access(db, auth, case_id)

            witnesses = (
                db.query(Witness)
                .filter(Witness.case_id == case_id, Witness.firm_id == auth.firm_id)
                .order_by(Witness.created_at.asc())
                .all()
            )

            version_map: Dict[str, List[WitnessVersionResponse]] = {}
            if include_versions and witnesses:
                witness_ids = [w.id for w in witnesses]
                versions = (
                    db.query(WitnessVersion, Document)
                    .join(Document, Document.id == WitnessVersion.document_id)
                    .filter(WitnessVersion.witness_id.in_(witness_ids))
                    .order_by(WitnessVersion.created_at.asc())
                    .all()
                )
                for version, doc in versions:
                    version_map.setdefault(version.witness_id, []).append(WitnessVersionResponse(
                        id=version.id,
                        witness_id=version.witness_id,
                        document_id=version.document_id,
                        document_name=doc.doc_name if doc else None,
                        version_type=version.version_type,
                        version_date=version.version_date,
                        extra_data=version.extra_data,
                        created_at=version.created_at,
                    ))

            return [
                WitnessResponse(
                    id=w.id,
                    case_id=w.case_id,
                    name=w.name,
                    side=w.side,
                    extra_data=w.extra_data,
                    created_at=w.created_at,
                    versions=version_map.get(w.id, []),
                )
                for w in witnesses
            ]

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list witnesses")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cases/{case_id}/witnesses", response_model=WitnessResponse)
async def create_witness(
    case_id: str,
    payload: WitnessCreateRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Create a witness for a case."""
    try:
        from .db.session import get_db_session
        from .db.models import Case, Witness

        with get_db_session() as db:
            case, _ = _require_case_access(db, auth, case_id)

            witness = Witness(
                firm_id=auth.firm_id,
                case_id=case_id,
                name=payload.name.strip(),
                side=(payload.side or "unknown"),
                extra_data=payload.extra_data or {},
            )
            db.add(witness)
            db.flush()

            return WitnessResponse(
                id=witness.id,
                case_id=witness.case_id,
                name=witness.name,
                side=witness.side,
                extra_data=witness.extra_data,
                created_at=witness.created_at,
                versions=[],
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create witness")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/witnesses/{witness_id}/versions", response_model=List[WitnessVersionResponse])
async def list_witness_versions(
    witness_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """List versions for a witness."""
    try:
        from .db.session import get_db_session
        from .db.models import Witness, WitnessVersion, Document

        with get_db_session() as db:
            witness = db.query(Witness).filter(
                Witness.id == witness_id,
                Witness.firm_id == auth.firm_id
            ).first()
            if not witness:
                raise HTTPException(status_code=404, detail="Witness not found")

            versions = (
                db.query(WitnessVersion, Document)
                .join(Document, Document.id == WitnessVersion.document_id)
                .filter(WitnessVersion.witness_id == witness_id)
                .order_by(WitnessVersion.created_at.asc())
                .all()
            )

            return [
                WitnessVersionResponse(
                    id=v.id,
                    witness_id=v.witness_id,
                    document_id=v.document_id,
                    document_name=doc.doc_name if doc else None,
                    version_type=v.version_type,
                    version_date=v.version_date,
                    extra_data=v.extra_data,
                    created_at=v.created_at,
                )
                for v, doc in versions
            ]

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list witness versions")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/witnesses/{witness_id}/versions", response_model=WitnessVersionResponse)
async def create_witness_version(
    witness_id: str,
    payload: WitnessVersionCreateRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Create a witness version linked to a document."""
    try:
        from .db.session import get_db_session
        from .db.models import Witness, WitnessVersion, Document

        with get_db_session() as db:
            witness = db.query(Witness).filter(
                Witness.id == witness_id,
                Witness.firm_id == auth.firm_id
            ).first()
            if not witness:
                raise HTTPException(status_code=404, detail="Witness not found")

            doc = db.query(Document).filter(
                Document.id == payload.document_id,
                Document.firm_id == auth.firm_id,
                Document.case_id == witness.case_id
            ).first()
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            existing = db.query(WitnessVersion).filter(
                WitnessVersion.document_id == payload.document_id
            ).first()
            if existing:
                raise HTTPException(status_code=409, detail="Document already linked to a witness version")

            version = WitnessVersion(
                witness_id=witness_id,
                document_id=payload.document_id,
                version_type=payload.version_type,
                version_date=payload.version_date,
                extra_data=payload.extra_data or {},
            )
            db.add(version)
            db.flush()

            return WitnessVersionResponse(
                id=version.id,
                witness_id=version.witness_id,
                document_id=version.document_id,
                document_name=doc.doc_name,
                version_type=version.version_type,
                version_date=version.version_date,
                extra_data=version.extra_data,
                created_at=version.created_at,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create witness version")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/witnesses/{witness_id}/versions/diff", response_model=WitnessVersionDiffResponse)
async def diff_witness_versions(
    witness_id: str,
    payload: WitnessVersionDiffRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Compute narrative shifts between two witness versions."""
    try:
        from .db.session import get_db_session
        from .db.models import Witness, WitnessVersion, Document
        from .witness_diff import diff_witness_versions as _diff

        with get_db_session() as db:
            witness = db.query(Witness).filter(
                Witness.id == witness_id,
                Witness.firm_id == auth.firm_id
            ).first()
            if not witness:
                raise HTTPException(status_code=404, detail="Witness not found")

            versions = (
                db.query(WitnessVersion)
                .filter(
                    WitnessVersion.witness_id == witness_id,
                    WitnessVersion.id.in_([payload.version_a_id, payload.version_b_id])
                )
                .all()
            )
            if len(versions) != 2:
                raise HTTPException(status_code=404, detail="Witness versions not found")

            version_a = next(v for v in versions if v.id == payload.version_a_id)
            version_b = next(v for v in versions if v.id == payload.version_b_id)

            # Ensure documents are loaded
            version_a.document = db.query(Document).filter(Document.id == version_a.document_id).first()
            version_b.document = db.query(Document).filter(Document.id == version_b.document_id).first()

            if not version_a.document or not version_b.document:
                raise HTTPException(status_code=404, detail="Version document not found")

            diff = _diff(db, version_a, version_b)
            shifts = [
                VersionShift(
                    shift_type=s.get("shift_type", "unknown"),
                    description=s.get("description", ""),
                    similarity=s.get("similarity"),
                    details=s.get("details"),
                    anchor_a=s.get("anchor_a"),
                    anchor_b=s.get("anchor_b"),
                )
                for s in diff.get("shifts", [])
            ]

            return WitnessVersionDiffResponse(
                witness_id=witness_id,
                version_a_id=version_a.id,
                version_b_id=version_b.id,
                similarity=diff.get("similarity", 0.0),
                shifts=shifts,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to diff witness versions")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# JOB STATUS ENDPOINTS
# =============================================================================

@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Get status of an async job.
    """
    try:
        from .jobs.queue import get_job_status as _get_job_status

        status = _get_job_status(job_id)

        return JobStatusResponse(
            job_id=job_id,
            status=status.get('status', 'unknown'),
            progress=status.get('progress', 0),
            result=status.get('result'),
            error=status.get('error'),
            started_at=status.get('started_at'),
            ended_at=status.get('ended_at')
        )

    except Exception as e:
        logger.exception("Failed to get job status")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ANALYSIS RUNS (RESULTS) ENDPOINTS
# =============================================================================

@router.get("/cases/{case_id}/runs")
async def list_analysis_runs(
    case_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context)
):
    """List recent analysis runs for a case."""
    try:
        from .db.session import get_db_session
        from .db.models import Case, AnalysisRun, Claim, Contradiction

        with get_db_session() as db:
            case, _ = _require_case_access(db, auth, case_id)

            runs = (
                db.query(AnalysisRun)
                .filter(AnalysisRun.case_id == case_id, AnalysisRun.firm_id == auth.firm_id)
                .order_by(AnalysisRun.created_at.desc())
                .limit(limit)
                .all()
            )

            result = []
            for r in runs:
                claims_count = db.query(Claim).filter(Claim.run_id == r.id).count()
                contradictions_count = db.query(Contradiction).filter(Contradiction.run_id == r.id).count()
                result.append({
                    "id": r.id,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    "claims_count": claims_count,
                    "contradictions_count": contradictions_count,
                })
            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list analysis runs")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis-runs/{run_id}")
async def get_analysis_run(
    run_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """Get a specific analysis run with contradictions (for UI display)."""
    try:
        from .db.session import get_db_session
        from .db.models import AnalysisRun, Claim, Contradiction

        with get_db_session() as db:
            run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id, AnalysisRun.firm_id == auth.firm_id).first()
            if not run:
                raise HTTPException(status_code=404, detail="Analysis run not found")

            claims_count = db.query(Claim).filter(Claim.run_id == run.id).count()
            contradictions = (
                db.query(Contradiction)
                .filter(Contradiction.run_id == run.id)
                .order_by(Contradiction.created_at.asc())
                .all()
            )

            # Enrich contradictions with claim text/locator when available
            claim_ids: List[str] = []
            for c in contradictions:
                if c.claim1_id:
                    claim_ids.append(c.claim1_id)
                if c.claim2_id:
                    claim_ids.append(c.claim2_id)
            claim_ids = list(dict.fromkeys(claim_ids))  # stable unique

            claims_by_id = {}
            if claim_ids:
                claims_by_id = {
                    cl.id: cl
                    for cl in db.query(Claim).filter(Claim.id.in_(claim_ids)).all()
                }

            return {
                "id": run.id,
                "case_id": run.case_id,
                "status": run.status,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "input_document_ids": run.input_document_ids or [],
                "metadata": run.metadata_json or {},
                "claims_count": claims_count,
                "contradictions": [
                    {
                        "id": c.id,
                        "type": c.contradiction_type,
                        "status": _enum_value(c.status),
                        "bucket": _enum_value(c.bucket),
                        "confidence": c.confidence,
                        "severity": c.severity,
                        "category": c.category,
                        "explanation": c.explanation,
                        "quote1": c.quote1,
                        "quote2": c.quote2,
                        # Claim linkage (enables UI to show "טענה א/ב" reliably)
                        "claim1_id": c.claim1_id,
                        "claim2_id": c.claim2_id,
                        "claim1_text": (claims_by_id.get(c.claim1_id).text if c.claim1_id and claims_by_id.get(c.claim1_id) else None),
                        "claim2_text": (claims_by_id.get(c.claim2_id).text if c.claim2_id and claims_by_id.get(c.claim2_id) else None),
                        "claim1_locator": (claims_by_id.get(c.claim1_id).locator_json if c.claim1_id and claims_by_id.get(c.claim1_id) else None),
                        "claim2_locator": (claims_by_id.get(c.claim2_id).locator_json if c.claim2_id and claims_by_id.get(c.claim2_id) else None),
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                    }
                    for c in contradictions
                ],
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get analysis run")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis-runs/{run_id}/insights", response_model=List[ContradictionInsightResponse])
async def list_contradiction_insights(
    run_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """List contradiction insights for a run."""
    try:
        from .db.session import get_db_session
        from .db.models import AnalysisRun, Contradiction, ContradictionInsight

        with get_db_session() as db:
            run = db.query(AnalysisRun).filter(
                AnalysisRun.id == run_id,
                AnalysisRun.firm_id == auth.firm_id
            ).first()
            if not run:
                raise HTTPException(status_code=404, detail="Analysis run not found")

            rows = (
                db.query(ContradictionInsight, Contradiction)
                .join(Contradiction, Contradiction.id == ContradictionInsight.contradiction_id)
                .filter(Contradiction.run_id == run_id)
                .all()
            )

            response = []
            for insight, contr in rows:
                composite = round(
                    (insight.impact_score or 0.0)
                    * (insight.risk_score or 0.0)
                    * (insight.verifiability_score or 0.0),
                    4,
                )
                response.append(ContradictionInsightResponse(
                    contradiction_id=insight.contradiction_id,
                    impact_score=insight.impact_score or 0.0,
                    risk_score=insight.risk_score or 0.0,
                    verifiability_score=insight.verifiability_score or 0.0,
                    stage_recommendation=insight.stage_recommendation,
                    prerequisites=insight.prerequisites_json or [],
                    expected_evasions=insight.evasions_json or [],
                    best_counter_questions=insight.counters_json or [],
                    do_not_ask_flag=bool(insight.do_not_ask),
                    do_not_ask_reason=insight.do_not_ask_reason,
                    composite_score=composite,
                ))

            response.sort(key=lambda r: r.composite_score or 0.0, reverse=True)
            return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list insights")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analysis-runs/{run_id}/cross-exam-plan", response_model=CrossExamPlanResponse)
async def generate_cross_exam_plan(
    run_id: str,
    payload: CrossExamPlanRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Generate a cross-exam plan for a run."""
    try:
        from .db.session import get_db_session
        from .db.models import AnalysisRun, Contradiction, ContradictionInsight, CrossExamPlan, Case
        from .insights import compute_insights_for_run
        from .cross_exam_planner import build_cross_exam_plan
        from .entity_usage import record_entity_usages

        with get_db_session() as db:
            run = db.query(AnalysisRun).filter(
                AnalysisRun.id == run_id,
                AnalysisRun.firm_id == auth.firm_id
            ).first()
            if not run:
                raise HTTPException(status_code=404, detail="Analysis run not found")

            query = db.query(Contradiction).filter(Contradiction.run_id == run_id)
            if payload.contradiction_ids:
                query = query.filter(Contradiction.id.in_(payload.contradiction_ids))
            contradictions = query.all()

            if not contradictions:
                raise HTTPException(status_code=400, detail="No contradictions found for plan")

            # Ensure insights exist
            existing_insights = db.query(ContradictionInsight).filter(
                ContradictionInsight.contradiction_id.in_([c.id for c in contradictions])
            ).count()
            if existing_insights == 0:
                compute_insights_for_run(db, run_id)

            insight_map = {
                i.contradiction_id: i
                for i in db.query(ContradictionInsight).filter(
                    ContradictionInsight.contradiction_id.in_([c.id for c in contradictions])
                ).all()
            }

            pairs = [(c, insight_map.get(c.id)) for c in contradictions]
            stages = build_cross_exam_plan(pairs)
            for stage in stages:
                stage["steps"] = [s for s in stage.get("steps", []) if s.get("anchors")]

            if not any(stage.get("steps") for stage in stages):
                raise HTTPException(status_code=400, detail="No anchored plan steps available")

            plan = CrossExamPlan(
                firm_id=auth.firm_id,
                case_id=run.case_id,
                run_id=run_id,
                witness_id=payload.witness_id,
                plan_json={"stages": stages},
            )
            db.add(plan)
            db.flush()

            case = db.query(Case).filter(Case.id == run.case_id).first()
            org_id = case.organization_id if case else None

            usage_entries: List[Tuple[str, str, Optional[Dict]]] = []
            for contr in contradictions:
                if contr.id:
                    usage_entries.append(("contradiction", contr.id, None))
                    if insight_map.get(contr.id):
                        usage_entries.append(("insight", contr.id, None))
            for stage in stages:
                for step in stage.get("steps", []):
                    step_id = step.get("id")
                    if step_id:
                        usage_entries.append(("plan_step", step_id, None))
                        usage_entries.append(("question", step_id, None))
                    contr_id = step.get("contradiction_id")
                    if contr_id:
                        usage_entries.append(("contradiction", contr_id, None))
                        if insight_map.get(contr_id):
                            usage_entries.append(("insight", contr_id, None))

            record_entity_usages(
                db,
                case_id=run.case_id,
                org_id=org_id,
                usage_type="plan",
                entries=usage_entries,
                meta_base={"run_id": run_id, "plan_id": plan.id},
            )

            return CrossExamPlanResponse(
                plan_id=plan.id,
                case_id=plan.case_id,
                run_id=plan.run_id,
                witness_id=plan.witness_id,
                created_at=plan.created_at,
                stages=[
                    CrossExamPlanStage(
                        stage=stage["stage"],
                        steps=[
                            CrossExamPlanStep(
                                id=step["id"],
                                contradiction_id=step.get("contradiction_id"),
                                stage=step["stage"],
                                step_type=step["step_type"],
                                title=step["title"],
                                question=step["question"],
                                purpose=step.get("purpose"),
                                anchors=step.get("anchors", []),
                                branches=[
                                    CrossExamPlanBranch(
                                        trigger=b.get("trigger", ""),
                                        follow_up_questions=b.get("follow_up_questions", []),
                                    )
                                    for b in step.get("branches", [])
                                ],
                                do_not_ask_flag=step.get("do_not_ask_flag", False),
                                do_not_ask_reason=step.get("do_not_ask_reason"),
                            )
                            for step in stage.get("steps", [])
                        ],
                    )
                    for stage in stages
                ],
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to generate cross-exam plan")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis-runs/{run_id}/cross-exam-plan", response_model=CrossExamPlanResponse)
async def get_cross_exam_plan(
    run_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """Get the latest cross-exam plan for a run."""
    try:
        from .db.session import get_db_session
        from .db.models import CrossExamPlan, AnalysisRun

        with get_db_session() as db:
            run = db.query(AnalysisRun).filter(
                AnalysisRun.id == run_id,
                AnalysisRun.firm_id == auth.firm_id
            ).first()
            if not run:
                raise HTTPException(status_code=404, detail="Analysis run not found")

            plan = (
                db.query(CrossExamPlan)
                .filter(CrossExamPlan.run_id == run_id, CrossExamPlan.case_id == run.case_id)
                .order_by(CrossExamPlan.created_at.desc())
                .first()
            )
            if not plan:
                raise HTTPException(status_code=404, detail="Cross-exam plan not found")

            stages = (plan.plan_json or {}).get("stages", [])
            return CrossExamPlanResponse(
                plan_id=plan.id,
                case_id=plan.case_id,
                run_id=plan.run_id,
                witness_id=plan.witness_id,
                created_at=plan.created_at,
                stages=[
                    CrossExamPlanStage(
                        stage=stage.get("stage"),
                        steps=[
                            CrossExamPlanStep(
                                id=step.get("id"),
                                contradiction_id=step.get("contradiction_id"),
                                stage=step.get("stage"),
                                step_type=step.get("step_type"),
                                title=step.get("title"),
                                question=step.get("question"),
                                purpose=step.get("purpose"),
                                anchors=step.get("anchors", []),
                                branches=[
                                    CrossExamPlanBranch(
                                        trigger=b.get("trigger", ""),
                                        follow_up_questions=b.get("follow_up_questions", []),
                                    )
                                    for b in step.get("branches", [])
                                ],
                                do_not_ask_flag=step.get("do_not_ask_flag", False),
                                do_not_ask_reason=step.get("do_not_ask_reason"),
                            )
                            for step in stage.get("steps", [])
                        ],
                    )
                    for stage in stages
                ],
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get cross-exam plan")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cases/{case_id}/training/start", response_model=TrainingSessionResponse)
async def start_training_session(
    case_id: str,
    payload: TrainingStartRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Start a training session for a case."""
    try:
        from .db.session import get_db_session
        from .db.models import CrossExamPlan, TrainingSession, TrainingSessionStatus, Witness, Case
        from .entity_usage import record_entity_usages

        with get_db_session() as db:
            _require_case_access(db, auth, case_id)

            plan = db.query(CrossExamPlan).filter(
                CrossExamPlan.id == payload.plan_id,
                CrossExamPlan.case_id == case_id,
                CrossExamPlan.firm_id == auth.firm_id,
            ).first()
            if not plan:
                raise HTTPException(status_code=404, detail="Cross-exam plan not found")

            witness_id = payload.witness_id or plan.witness_id
            if witness_id:
                witness = db.query(Witness).filter(
                    Witness.id == witness_id,
                    Witness.case_id == case_id,
                ).first()
                if not witness:
                    raise HTTPException(status_code=404, detail="Witness not found")

            session = TrainingSession(
                firm_id=auth.firm_id,
                case_id=case_id,
                plan_id=plan.id,
                witness_id=witness_id,
                persona=payload.persona or "cooperative",
                status=TrainingSessionStatus.ACTIVE,
                back_remaining=2,
            )
            db.add(session)
            db.flush()

            case = db.query(Case).filter(Case.id == case_id).first()
            org_id = case.organization_id if case else None
            steps = _flatten_plan_steps(plan.plan_json or {})
            if steps:
                first = steps[0]
                usage_entries: List[Tuple[str, str, Optional[Dict]]] = []
                step_id = first.get("id")
                if step_id:
                    usage_entries.append(("plan_step", step_id, None))
                    usage_entries.append(("question", step_id, None))
                contr_id = first.get("contradiction_id")
                if contr_id:
                    usage_entries.append(("contradiction", contr_id, None))
                    usage_entries.append(("insight", contr_id, None))

                record_entity_usages(
                    db,
                    case_id=case_id,
                    org_id=org_id,
                    usage_type="training",
                    entries=usage_entries,
                    meta_base={"plan_id": plan.id, "session_id": session.id},
                )

            return TrainingSessionResponse(
                session_id=session.id,
                case_id=session.case_id,
                plan_id=session.plan_id,
                witness_id=session.witness_id,
                persona=session.persona,
                status=session.status.value,
                back_remaining=session.back_remaining,
                created_at=session.created_at,
            )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to start training session")
        raise HTTPException(status_code=500, detail="Failed to start training session")


@router.post("/training/{session_id}/turn", response_model=TrainingTurnResponse)
async def training_turn(
    session_id: str,
    payload: TrainingTurnRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Record a training turn."""
    try:
        from .db.session import get_db_session
        from .db.models import TrainingSession, TrainingTurn, TrainingSessionStatus, CrossExamPlan, Case
        from .witness_simulation import simulate_step
        from .entity_usage import record_entity_usages

        with get_db_session() as db:
            session = db.query(TrainingSession).filter(
                TrainingSession.id == session_id,
                TrainingSession.firm_id == auth.firm_id,
            ).first()
            if not session:
                raise HTTPException(status_code=404, detail="Training session not found")

            _require_case_access(db, auth, session.case_id)

            if session.status != TrainingSessionStatus.ACTIVE:
                raise HTTPException(status_code=400, detail="Training session is not active")

            plan = db.query(CrossExamPlan).filter(
                CrossExamPlan.id == session.plan_id
            ).first()
            if not plan:
                raise HTTPException(status_code=404, detail="Cross-exam plan not found")

            step = _find_plan_step(plan.plan_json or {}, payload.step_id)
            if not step:
                raise HTTPException(status_code=404, detail="Plan step not found")

            sim = simulate_step(step, session.persona, payload.chosen_branch)
            turn = TrainingTurn(
                session_id=session.id,
                step_id=payload.step_id,
                stage=step.get("_stage"),
                question=step.get("question", ""),
                chosen_branch=sim.get("chosen_branch_trigger"),
                witness_reply=sim.get("witness_reply"),
                metadata_json={
                    "warnings": sim.get("warnings", []),
                    "follow_up_questions": sim.get("follow_up_questions", []),
                },
            )
            db.add(turn)
            db.flush()

            case = db.query(Case).filter(Case.id == session.case_id).first()
            org_id = case.organization_id if case else None
            usage_entries: List[Tuple[str, str, Optional[Dict]]] = []
            step_id = step.get("id")
            if step_id:
                usage_entries.append(("plan_step", step_id, None))
                usage_entries.append(("question", step_id, None))
            contr_id = step.get("contradiction_id")
            if contr_id:
                usage_entries.append(("contradiction", contr_id, None))
                usage_entries.append(("insight", contr_id, None))

            record_entity_usages(
                db,
                case_id=session.case_id,
                org_id=org_id,
                usage_type="training",
                entries=usage_entries,
                meta_base={"plan_id": session.plan_id, "session_id": session.id},
            )

            return TrainingTurnResponse(
                turn_id=turn.id,
                session_id=session.id,
                step_id=payload.step_id,
                stage=turn.stage,
                question=turn.question,
                witness_reply=turn.witness_reply,
                chosen_branch=turn.chosen_branch,
                follow_up_questions=turn.metadata_json.get("follow_up_questions", []),
                warnings=turn.metadata_json.get("warnings", []),
            )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to record training turn")
        raise HTTPException(status_code=500, detail="Failed to record training turn")


@router.post("/training/{session_id}/back", response_model=TrainingBackResponse)
async def training_back(
    session_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Undo last training turn (limited)."""
    try:
        from .db.session import get_db_session
        from .db.models import TrainingSession, TrainingTurn, TrainingSessionStatus

        with get_db_session() as db:
            session = db.query(TrainingSession).filter(
                TrainingSession.id == session_id,
                TrainingSession.firm_id == auth.firm_id,
            ).first()
            if not session:
                raise HTTPException(status_code=404, detail="Training session not found")

            _require_case_access(db, auth, session.case_id)

            if session.status != TrainingSessionStatus.ACTIVE:
                raise HTTPException(status_code=400, detail="Training session is not active")
            if session.back_remaining <= 0:
                raise HTTPException(status_code=400, detail="No back steps remaining")

            last_turn = (
                db.query(TrainingTurn)
                .filter(TrainingTurn.session_id == session_id)
                .order_by(TrainingTurn.created_at.desc())
                .first()
            )
            if not last_turn:
                raise HTTPException(status_code=400, detail="No turns to undo")

            removed_id = last_turn.id
            db.delete(last_turn)
            session.back_remaining -= 1

            return TrainingBackResponse(
                session_id=session.id,
                back_remaining=session.back_remaining,
                removed_turn_id=removed_id,
            )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to undo training turn")
        raise HTTPException(status_code=500, detail="Failed to undo training turn")


@router.post("/training/{session_id}/finish", response_model=TrainingFinishResponse)
async def finish_training(
    session_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Finish a training session and return summary."""
    try:
        from .db.session import get_db_session
        from .db.models import TrainingSession, TrainingTurn, TrainingSessionStatus

        with get_db_session() as db:
            session = db.query(TrainingSession).filter(
                TrainingSession.id == session_id,
                TrainingSession.firm_id == auth.firm_id,
            ).first()
            if not session:
                raise HTTPException(status_code=404, detail="Training session not found")

            _require_case_access(db, auth, session.case_id)

            turns = (
                db.query(TrainingTurn)
                .filter(TrainingTurn.session_id == session_id)
                .order_by(TrainingTurn.created_at.asc())
                .all()
            )

            if session.status == TrainingSessionStatus.FINISHED and session.summary_json:
                return TrainingFinishResponse(session_id=session.id, summary=session.summary_json)

            stage_counts: Dict[str, int] = {}
            branch_counts: Dict[str, int] = {}
            warning_count = 0

            for turn in turns:
                if turn.stage:
                    stage_counts[turn.stage] = stage_counts.get(turn.stage, 0) + 1
                if turn.chosen_branch:
                    branch_counts[turn.chosen_branch] = branch_counts.get(turn.chosen_branch, 0) + 1
                warning_count += len(turn.metadata_json.get("warnings", []))

            summary = {
                "total_turns": len(turns),
                "stages": stage_counts,
                "branches": branch_counts,
                "warnings": warning_count,
            }

            session.status = TrainingSessionStatus.FINISHED
            session.finished_at = datetime.utcnow()
            session.summary_json = summary

            return TrainingFinishResponse(session_id=session.id, summary=summary)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to finish training session")
        raise HTTPException(status_code=500, detail="Failed to finish training session")


@router.get("/cases/{case_id}/usage", response_model=List[EntityUsageSummary])
async def list_entity_usage(
    case_id: str,
    entity_type: Optional[str] = Query(default=None),
    usage_type: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
):
    """List usage summary for entities in a case."""
    try:
        from .db.session import get_db_session
        from .db.models import EntityUsage

        with get_db_session() as db:
            _require_case_access(db, auth, case_id)

            query = db.query(EntityUsage).filter(EntityUsage.case_id == case_id)
            if entity_type:
                query = query.filter(EntityUsage.entity_type == entity_type)
            if usage_type:
                query = query.filter(EntityUsage.usage_type == usage_type)

            rows = query.order_by(EntityUsage.created_at.desc()).all()
            summary_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

            for row in rows:
                key = (row.entity_type, row.entity_id)
                entry = summary_map.get(key)
                if not entry:
                    entry = {
                        "entity_type": row.entity_type,
                        "entity_id": row.entity_id,
                        "usage": {},
                        "latest_used_at": None,
                    }
                    summary_map[key] = entry

                ts = row.created_at.isoformat() if row.created_at else None
                if ts:
                    existing = entry["usage"].get(row.usage_type)
                    if not existing or existing < ts:
                        entry["usage"][row.usage_type] = ts
                    if not entry["latest_used_at"] or entry["latest_used_at"] < ts:
                        entry["latest_used_at"] = ts

            return [EntityUsageSummary(**entry) for entry in summary_map.values()]

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list entity usage")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analysis-runs/{run_id}/witness-simulation", response_model=WitnessSimulationResponse)
async def simulate_witness(
    run_id: str,
    payload: WitnessSimulationRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Simulate witness responses based on latest cross-exam plan."""
    try:
        from .db.session import get_db_session
        from .db.models import CrossExamPlan, AnalysisRun
        from .witness_simulation import simulate_plan

        with get_db_session() as db:
            run = db.query(AnalysisRun).filter(
                AnalysisRun.id == run_id,
                AnalysisRun.firm_id == auth.firm_id
            ).first()
            if not run:
                raise HTTPException(status_code=404, detail="Analysis run not found")

            if payload.plan_id:
                plan = db.query(CrossExamPlan).filter(
                    CrossExamPlan.id == payload.plan_id,
                    CrossExamPlan.run_id == run_id
                ).first()
            else:
                plan = (
                    db.query(CrossExamPlan)
                    .filter(CrossExamPlan.run_id == run_id, CrossExamPlan.case_id == run.case_id)
                    .order_by(CrossExamPlan.created_at.desc())
                    .first()
                )
            if not plan:
                raise HTTPException(status_code=404, detail="Cross-exam plan not found")

            steps = simulate_plan(plan.plan_json or {}, payload.persona)
            return WitnessSimulationResponse(
                run_id=run_id,
                plan_id=plan.id,
                persona=payload.persona,
                steps=[
                    WitnessSimulationStep(
                        step_id=s.get("step_id", ""),
                        stage=s.get("stage", ""),
                        question=s.get("question", ""),
                        witness_reply=s.get("witness_reply", ""),
                        chosen_branch_trigger=s.get("chosen_branch_trigger"),
                        follow_up_questions=s.get("follow_up_questions", []),
                        warnings=s.get("warnings", []),
                    )
                    for s in steps
                ],
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to simulate witness")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis-runs/{run_id}/export/cross-exam")
async def export_cross_exam_plan(
    run_id: str,
    format: str = Query(default="docx", pattern="^(docx|pdf)$"),
    auth: AuthContext = Depends(get_auth_context)
):
    """Export cross-examination plan to DOCX/PDF."""
    try:
        from .db.session import get_db_session
        from .db.models import (
            CrossExamPlan,
            AnalysisRun,
            Document,
            Case,
            Contradiction,
            ContradictionInsight,
            Witness,
            WitnessVersion,
        )
        from .exporter import build_cross_exam_docx, build_cross_exam_pdf
        from .insights import compute_insights_for_run
        from .witness_diff import diff_witness_versions
        from .entity_usage import record_entity_usages

        with get_db_session() as db:
            run = db.query(AnalysisRun).filter(
                AnalysisRun.id == run_id,
                AnalysisRun.firm_id == auth.firm_id
            ).first()
            if not run:
                raise HTTPException(status_code=404, detail="Analysis run not found")

            case, member = _require_case_access(db, auth, run.case_id)
            if case.organization_id and member and member.role.value not in ("lawyer", "owner"):
                raise HTTPException(status_code=403, detail={"code": "org_forbidden", "message": "אין הרשאה לייצוא"})

            plan = (
                db.query(CrossExamPlan)
                .filter(CrossExamPlan.run_id == run_id, CrossExamPlan.case_id == run.case_id)
                .order_by(CrossExamPlan.created_at.desc())
                .first()
            )
            if not plan:
                raise HTTPException(status_code=404, detail="Cross-exam plan not found")

            contradictions = (
                db.query(Contradiction)
                .filter(Contradiction.run_id == run_id)
                .order_by(Contradiction.created_at.asc())
                .all()
            )
            if not contradictions:
                raise HTTPException(status_code=400, detail="No contradictions available for export")

            if contradictions:
                insight_count = (
                    db.query(ContradictionInsight)
                    .filter(ContradictionInsight.contradiction_id.in_([c.id for c in contradictions if c.id]))
                    .count()
                )
                if insight_count == 0:
                    compute_insights_for_run(db, run_id)

            insight_map = {
                i.contradiction_id: i
                for i in db.query(ContradictionInsight).filter(
                    ContradictionInsight.contradiction_id.in_([c.id for c in contradictions if c.id])
                )
            }
            if contradictions and not insight_map:
                raise HTTPException(status_code=400, detail="Insights not available for export")

            ranked = []
            for contr in contradictions:
                insight = insight_map.get(contr.id)
                scores = {
                    "impact": float(insight.impact_score) if insight else None,
                    "risk": float(insight.risk_score) if insight else None,
                    "verifiability": float(insight.verifiability_score) if insight else None,
                }
                if insight:
                    scores["composite"] = round(
                        (insight.impact_score or 0.0)
                        * (insight.risk_score or 0.0)
                        * (insight.verifiability_score or 0.0),
                        4,
                    )

                anchors = []
                if contr.locator1_json and contr.locator1_json.get("doc_id"):
                    anchors.append(contr.locator1_json)
                if contr.locator2_json and contr.locator2_json.get("doc_id"):
                    anchors.append(contr.locator2_json)

                ranked.append({
                    "contradiction_id": contr.id,
                    "type": contr.contradiction_type,
                    "severity": contr.severity,
                    "category": contr.category,
                    "quote1": contr.quote1,
                    "quote2": contr.quote2,
                    "anchors": anchors,
                    "scores": scores,
                    "stage": insight.stage_recommendation if insight else None,
                })

            ranked.sort(
                key=lambda item: item.get("scores", {}).get("composite") or 0.0,
                reverse=True,
            )

            version_shifts = []
            witnesses = (
                db.query(Witness)
                .filter(Witness.case_id == run.case_id, Witness.firm_id == auth.firm_id)
                .order_by(Witness.created_at.asc())
                .all()
            )
            for witness in witnesses:
                versions = (
                    db.query(WitnessVersion)
                    .filter(WitnessVersion.witness_id == witness.id)
                    .order_by(WitnessVersion.created_at.asc())
                    .all()
                )
                if len(versions) < 2:
                    continue
                shifts = []
                for idx in range(len(versions) - 1):
                    diff = diff_witness_versions(db, versions[idx], versions[idx + 1])
                    for shift in diff.get("shifts", []):
                        shifts.append({
                            "shift_type": shift.get("shift_type"),
                            "description": shift.get("description"),
                            "anchor_a": shift.get("anchor_a"),
                            "anchor_b": shift.get("anchor_b"),
                        })
                if shifts:
                    version_shifts.append({
                        "witness_id": witness.id,
                        "witness_name": witness.name,
                        "shifts": shifts,
                    })

            doc_ids = []
            for stage in (plan.plan_json or {}).get("stages", []):
                for step in stage.get("steps", []):
                    for anchor in step.get("anchors", []):
                        if anchor.get("doc_id"):
                            doc_ids.append(anchor["doc_id"])
            doc_ids = list(dict.fromkeys(doc_ids))
            docs = db.query(Document).filter(Document.id.in_(doc_ids)).all() if doc_ids else []
            doc_lookup = {d.id: d for d in docs}

            appendix_anchors = []
            seen = set()
            for item in ranked:
                for anchor in item.get("anchors", []):
                    key = (anchor.get("doc_id"), anchor.get("char_start"), anchor.get("char_end"), anchor.get("snippet"))
                    if key in seen or not anchor.get("doc_id"):
                        continue
                    seen.add(key)
                    appendix_anchors.append(anchor)
            for stage in (plan.plan_json or {}).get("stages", []):
                for step in stage.get("steps", []):
                    for anchor in step.get("anchors", []):
                        key = (anchor.get("doc_id"), anchor.get("char_start"), anchor.get("char_end"), anchor.get("snippet"))
                        if key in seen or not anchor.get("doc_id"):
                            continue
                        seen.add(key)
                        appendix_anchors.append(anchor)

            usage_entries: List[Tuple[str, str, Optional[Dict]]] = []
            for item in ranked:
                contr_id = item.get("contradiction_id")
                if contr_id:
                    usage_entries.append(("contradiction", contr_id, None))
                    if insight_map.get(contr_id):
                        usage_entries.append(("insight", contr_id, None))

            for stage in (plan.plan_json or {}).get("stages", []):
                for step in stage.get("steps", []):
                    step_id = step.get("id")
                    if step_id:
                        usage_entries.append(("plan_step", step_id, None))
                        usage_entries.append(("question", step_id, None))

            for witness_item in version_shifts:
                witness_id = witness_item.get("witness_id")
                shifts = witness_item.get("shifts", [])
                for idx, shift in enumerate(shifts):
                    if not witness_id:
                        continue
                    shift_id = _narrative_shift_id(witness_id, shift, idx)
                    usage_entries.append((
                        "narrative_shift",
                        shift_id,
                        {"witness_id": witness_id, "shift_type": shift.get("shift_type")},
                    ))

            record_entity_usages(
                db,
                case_id=run.case_id,
                org_id=case.organization_id,
                usage_type="export",
                entries=usage_entries,
                meta_base={"run_id": run_id, "plan_id": plan.id},
            )

            plan_payload = dict(plan.plan_json or {})
            plan_payload["case_settings"] = {
                "case_number": case.case_number,
                "court": case.court,
                "our_side": case.our_side,
                "client_name": case.client_name,
                "opponent_name": case.opponent_name,
                "case_type": (case.extra_data or {}).get("case_type"),
                "court_level": (case.extra_data or {}).get("court_level"),
                "language": (case.extra_data or {}).get("language"),
            }
            plan_payload["ranked_contradictions"] = ranked
            plan_payload["version_shifts"] = version_shifts
            plan_payload["appendix_anchors"] = appendix_anchors

            if format == "pdf":
                content = build_cross_exam_pdf(plan_payload, case.name, run_id, doc_lookup)
                filename = f"cross_exam_plan_{case.name}_{run_id}.pdf"
                media_type = "application/pdf"
            else:
                content = build_cross_exam_docx(plan_payload, case.name, run_id, doc_lookup)
                filename = f"cross_exam_plan_{case.name}_{run_id}.docx"
                media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

            return Response(
                content=content,
                media_type=media_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to export cross-exam plan")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases/{case_id}/jobs")
async def list_case_jobs(
    case_id: str,
    status: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context)
):
    """
    List jobs for a case.
    """
    try:
        from .db.session import get_db_session
        from .db.models import Job, Case

        with get_db_session() as db:
            # Verify case access
            case, _ = _require_case_access(db, auth, case_id)

            query = db.query(Job).filter(
                Job.case_id == case_id,
                Job.firm_id == auth.firm_id
            )

            if status:
                query = query.filter(Job.status == status)

            jobs = query.order_by(Job.created_at.desc()).limit(100).all()

            return [
                {
                    "id": j.id,
                    "job_type": j.job_type.value,
                    "status": j.status.value,
                    "progress": j.progress,
                    "error_message": j.error_message,
                    "created_at": j.created_at.isoformat()
                }
                for j in jobs
            ]

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list jobs")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ANALYZE ENDPOINT
# =============================================================================

@router.post("/cases/{case_id}/analyze")
async def analyze_case(
    case_id: str,
    request: Optional[AnalyzeCaseRequest] = None,
    auth: AuthContext = Depends(get_auth_context)
):
    """
    Trigger analysis for a case.
    """
    try:
        from .db.session import get_db_session
        from .db.models import Case
        from .jobs.queue import enqueue_job
        from .jobs.tasks import task_analyze_case

        with get_db_session() as db:
            # Verify case access
            case, _ = _require_case_access(db, auth, case_id)

        if request is None:
            request = AnalyzeCaseRequest()

        # Enqueue analysis job
        job_result = enqueue_job(
            task_analyze_case,
            case_id=case_id,
            firm_id=auth.firm_id,
            document_ids=request.document_ids,
            triggered_by_user_id=auth.user_id,
            mode=request.mode,
            queue_name="default",
            job_id=f"analyze_{case_id}_{datetime.utcnow().timestamp()}"
        )

        return {
            "job_id": job_result.get('job_id'),
            "message": "Analysis started"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to start analysis")
        raise HTTPException(status_code=500, detail=str(e))
