"""
Upload & Folder API Endpoints
=============================

FastAPI router for document upload and folder management.
"""

import os
import json
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])


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
            case = db.query(Case).filter(
                Case.id == case_id,
                Case.firm_id == auth.firm_id
            ).first()

            if not case:
                raise HTTPException(status_code=404, detail="Case not found")

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
            case = db.query(Case).filter(
                Case.id == case_id,
                Case.firm_id == auth.firm_id
            ).first()

            if not case:
                raise HTTPException(status_code=404, detail="Case not found")

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
            case = db.query(Case).filter(
                Case.id == case_id,
                Case.firm_id == auth.firm_id
            ).first()

            if not case:
                raise HTTPException(status_code=404, detail="Case not found")

            storage = get_storage()
            document_ids = []
            job_ids = []
            provider = _storage_provider_name()

            for idx, up in enumerate(all_files):
                # Read file
                data = await up.read()

                if not data:
                    continue

                # Detect MIME type
                mime_type = detect_mime_type(up.filename, data)

                if not is_supported(mime_type):
                    logger.warning(f"Skipping unsupported file: {up.filename} ({mime_type})")
                    continue

                # Store file
                storage_key = storage.generate_key(
                    auth.firm_id, case_id, up.filename
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
                    doc_name=up.filename,
                    original_filename=up.filename,
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
                        doc.status = DocumentStatus.PROCESSING
                        db.flush()

                        parsed = parse_document(
                            data=data,
                            filename=up.filename,
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
                                    locator_json=block.to_locator_json(),
                                )
                                db.add(db_block)
                    except Exception as e:
                        doc.status = DocumentStatus.FAILED
                        doc.extra_data = doc.extra_data or {}
                        doc.extra_data["error"] = str(e)
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
            case = db.query(Case).filter(
                Case.id == case_id,
                Case.firm_id == auth.firm_id
            ).first()

            if not case:
                raise HTTPException(status_code=404, detail="Case not found")

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
            case = db.query(Case).filter(
                Case.id == case_id,
                Case.firm_id == auth.firm_id
            ).first()

            if not case:
                raise HTTPException(status_code=404, detail="Case not found")

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
            case = db.query(Case).filter(Case.id == case_id, Case.firm_id == auth.firm_id).first()
            if not case:
                raise HTTPException(status_code=404, detail="Case not found")

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
            case = db.query(Case).filter(
                Case.id == case_id,
                Case.firm_id == auth.firm_id
            ).first()

            if not case:
                raise HTTPException(status_code=404, detail="Case not found")

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
            case = db.query(Case).filter(
                Case.id == case_id,
                Case.firm_id == auth.firm_id
            ).first()

            if not case:
                raise HTTPException(status_code=404, detail="Case not found")

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
