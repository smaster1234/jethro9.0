"""
Job Tasks
=========

Async task implementations for document processing.
"""

import os
import io
import zipfile
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Shared error types (stable across reloads)
from .errors import ZipSecurityError

# =============================================================================
# ZIP BOMB PROTECTION CONFIGURATION
# =============================================================================

# Maximum number of files in a ZIP
MAX_ZIP_FILES = int(os.environ.get("MAX_ZIP_FILES", "500"))

# Maximum size of a single file (25MB)
MAX_FILE_BYTES = int(os.environ.get("MAX_FILE_BYTES", str(25 * 1024 * 1024)))

# Maximum total uncompressed size (500MB)
MAX_TOTAL_UNCOMPRESSED_BYTES = int(os.environ.get("MAX_TOTAL_UNCOMPRESSED_BYTES", str(500 * 1024 * 1024)))

# Maximum compression ratio (uncompressed/compressed) - prevent zip bombs
MAX_COMPRESSION_RATIO = int(os.environ.get("MAX_COMPRESSION_RATIO", "100"))


def validate_zip_safe(zf: zipfile.ZipFile) -> List[str]:
    """
    Validate a ZIP file for security issues.

    Checks for:
    - Path traversal attacks (../, absolute paths)
    - ZIP bombs (too many files, high compression ratio, excessive size)
    - Symlinks

    Args:
        zf: Open ZipFile object

    Returns:
        List of valid file paths (excluding directories and hidden files)

    Raises:
        ZipSecurityError: If ZIP fails security checks
    """
    file_list = []
    total_uncompressed = 0

    for info in zf.infolist():
        # Skip directories
        if info.is_dir():
            continue

        # Skip hidden files and macOS metadata
        filename = info.filename
        basename = filename.split('/')[-1]
        if basename.startswith('.') or filename.startswith('__MACOSX'):
            continue

        # === Path Traversal Checks ===

        # Check for .. path components
        if '..' in filename:
            raise ZipSecurityError(f"Path traversal detected: {filename}")

        # Check for absolute paths (Unix)
        if filename.startswith('/'):
            raise ZipSecurityError(f"Absolute path detected: {filename}")

        # Check for Windows absolute paths (C:\, etc.)
        if len(filename) >= 2 and filename[1] == ':':
            raise ZipSecurityError(f"Windows absolute path detected: {filename}")

        # Check for backslash path separators (Windows-style that could be exploited)
        if '\\' in filename:
            # Normalize to forward slashes and re-check for traversal
            normalized = filename.replace('\\', '/')
            if '..' in normalized:
                raise ZipSecurityError(f"Path traversal detected (backslash): {filename}")

        # === ZIP Bomb Checks ===

        # Check file count
        if len(file_list) >= MAX_ZIP_FILES:
            raise ZipSecurityError(f"ZIP contains too many files (max {MAX_ZIP_FILES})")

        # Check individual file size (uncompressed)
        if info.file_size > MAX_FILE_BYTES:
            raise ZipSecurityError(
                f"File too large: {filename} ({info.file_size / (1024*1024):.1f}MB, max {MAX_FILE_BYTES / (1024*1024):.0f}MB)"
            )

        # Check compression ratio (zip bomb detection)
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > MAX_COMPRESSION_RATIO:
                raise ZipSecurityError(
                    f"Suspicious compression ratio: {filename} (ratio {ratio:.0f}x, max {MAX_COMPRESSION_RATIO}x)"
                )

        # Track total uncompressed size
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise ZipSecurityError(
                f"Total uncompressed size exceeds limit ({MAX_TOTAL_UNCOMPRESSED_BYTES / (1024*1024):.0f}MB)"
            )

        # === Symlink Check ===
        # In ZIP, symlinks have external_attr with mode 0xA000
        # (mode >> 16) & 0xF000 == 0xA000
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode != 0 and (mode & 0xF000) == 0xA000:
            raise ZipSecurityError(f"Symlink detected: {filename}")

        file_list.append(filename)

    return file_list


def safe_extract_file(zf: zipfile.ZipFile, filename: str, target_dir: Path) -> Path:
    """
    Safely extract a file from ZIP to target directory.

    Args:
        zf: Open ZipFile object
        filename: File path within ZIP
        target_dir: Target directory for extraction

    Returns:
        Path to extracted file

    Raises:
        ZipSecurityError: If extraction would write outside target_dir
    """
    # Normalize the filename (replace backslashes, remove leading slashes)
    normalized = filename.replace('\\', '/').lstrip('/')

    # Build target path
    target_path = target_dir / normalized

    # Resolve to absolute and check it's under target_dir
    try:
        target_resolved = target_path.resolve()
        target_dir_resolved = target_dir.resolve()

        # Check that resolved path is under target directory
        if not str(target_resolved).startswith(str(target_dir_resolved) + os.sep) and target_resolved != target_dir_resolved:
            raise ZipSecurityError(f"Path escape detected: {filename} -> {target_resolved}")
    except (OSError, ValueError) as e:
        raise ZipSecurityError(f"Invalid path: {filename}: {e}")

    # Create parent directories if needed
    target_resolved.parent.mkdir(parents=True, exist_ok=True)

    # Extract the file
    with zf.open(filename) as source:
        data = source.read()

    with open(target_resolved, 'wb') as target:
        target.write(data)

    return target_resolved


def update_job_progress(progress: int, message: str = None):
    """Update job progress (for RQ meta)"""
    try:
        from rq import get_current_job
        job = get_current_job()
        if job:
            job.meta['progress'] = progress
            if message:
                job.meta['message'] = message
            job.save_meta()
    except:
        pass


def _sanitize_error_message(error: Exception, fallback: str = "שגיאה בעיבוד המשימה") -> str:
    try:
        from ..ingest.base import ParserError
    except Exception:
        ParserError = None  # type: ignore

    if ParserError and isinstance(error, ParserError):
        message = getattr(error, "user_message", fallback)
    else:
        message = str(error) if error else fallback
    compact = " ".join(message.split())
    if not compact:
        compact = fallback
    if len(compact) > 200:
        compact = compact[:200] + "..."
    return compact


def _set_job_error_message(message: str) -> None:
    try:
        from rq import get_current_job
        job = get_current_job()
        if job:
            job.meta["error_message"] = message
            job.save_meta()
    except:
        pass


def task_parse_document(
    document_id: str,
    storage_key: str,
    mime_type: str,
    firm_id: str,
    force_ocr: bool = False
) -> Dict[str, Any]:
    """
    Parse a document and extract text/structure.

    Args:
        document_id: Document ID in database
        storage_key: Storage key for document file
        mime_type: Document MIME type
        firm_id: Firm ID for scoping
        force_ocr: Force OCR even for text PDFs

    Returns:
        Dict with parsing results
    """
    from ..storage import get_storage
    from ..ingest import parse_document
    from ..db.session import get_db_session
    from ..db.models import Document, DocumentPage, DocumentBlock, DocumentStatus

    start_time = datetime.utcnow()
    update_job_progress(10, "Loading document")

    try:
        # Get document from storage
        logger.info("Parsing document %s from storage backend=%s key=%s", document_id, os.environ.get("STORAGE_BACKEND", "local"), storage_key)
        storage = get_storage()
        data = storage.get(storage_key)

        update_job_progress(20, "Parsing document")

        # Mark document as processing
        try:
            with get_db_session() as db:
                doc = db.query(Document).filter(Document.id == document_id).first()
                if doc:
                    doc.status = DocumentStatus.PROCESSING
                    db.commit()
        except Exception:
            pass

        # Parse document
        result = parse_document(
            data=data,
            filename=storage_key.split('/')[-1],
            mime_type=mime_type,
            force_ocr=force_ocr
        )

        update_job_progress(60, "Saving results")

        # Save to database
        with get_db_session() as db:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if not doc:
                raise ValueError(f"Document not found: {document_id}")

            # Update document
            doc.full_text = result.full_text
            doc.page_count = result.page_count
            doc.language = result.language
            doc.status = DocumentStatus.READY
            # SQLAlchemy model uses extra_data (metadata is reserved)
            doc.extra_data = {**(doc.extra_data or {}), **(result.metadata or {})}

            # Ensure idempotency: clear existing pages/blocks for this document
            db.query(DocumentBlock).filter(DocumentBlock.document_id == document_id).delete()
            db.query(DocumentPage).filter(DocumentPage.document_id == document_id).delete()

            # Save pages
            for page in result.pages:
                db_page = DocumentPage(
                    document_id=document_id,
                    page_no=page.page_no,
                    text=page.text,
                    width=page.width,
                    height=page.height
                )
                db.add(db_page)

                # Save blocks
                for block in page.blocks:
                    db_block = DocumentBlock(
                        document_id=document_id,
                        page_no=block.page_no,
                        block_index=block.block_index,
                        text=block.text,
                        bbox_json=block.bbox,
                        char_start=block.char_start,
                        char_end=block.char_end,
                        paragraph_index=block.paragraph_index,
                        locator_json=block.to_locator_json(doc_id=document_id)
                    )
                    db.add(db_block)

            db.commit()

        update_job_progress(100, "Complete")

        elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        return {
            "document_id": document_id,
            "status": "ready",
            "page_count": result.page_count,
            "text_length": len(result.full_text),
            "block_count": len(result.all_blocks),
            "elapsed_ms": elapsed_ms
        }

    except Exception as e:
        logger.exception(f"Failed to parse document {document_id}")
        safe_error = _sanitize_error_message(e, fallback="שגיאה בעיבוד המסמך")
        _set_job_error_message(safe_error)

        # Update document status to failed
        try:
            with get_db_session() as db:
                doc = db.query(Document).filter(Document.id == document_id).first()
                if doc:
                    doc.status = DocumentStatus.FAILED
                    doc.extra_data = doc.extra_data or {}
                    doc.extra_data['error'] = safe_error
                    db.commit()
        except:
            pass

        raise


def task_ocr_document(
    document_id: str,
    storage_key: str,
    firm_id: str,
    language: str = "heb+eng"
) -> Dict[str, Any]:
    """
    OCR a scanned document.

    Args:
        document_id: Document ID
        storage_key: Storage key
        firm_id: Firm ID
        language: OCR language

    Returns:
        Dict with OCR results
    """
    # OCR is handled by parse_document with force_ocr=True
    return task_parse_document(
        document_id=document_id,
        storage_key=storage_key,
        mime_type="application/pdf",
        firm_id=firm_id,
        force_ocr=True
    )


def task_ingest_zip(
    zip_storage_key: str,
    case_id: str,
    firm_id: str,
    base_folder_id: Optional[str] = None,
    created_by_user_id: Optional[str] = None,
    mapping_mode: str = "auto"
) -> Dict[str, Any]:
    """
    Ingest a ZIP file with documents.

    Creates folders mirroring ZIP structure and enqueues parsing for each file.

    Security protections:
    - Path traversal prevention
    - ZIP bomb detection (file count, total size, compression ratio)
    - Symlink blocking
    - MIME type validation

    Args:
        zip_storage_key: Storage key for ZIP file
        case_id: Case ID
        firm_id: Firm ID
        base_folder_id: Parent folder ID
        created_by_user_id: User who uploaded
        mapping_mode: auto/manual

    Returns:
        Dict with created documents and folders
    """
    from ..storage import get_storage
    from ..db.session import get_db_session
    from ..db.models import Document, Folder, FolderScope, DocumentStatus
    from ..ingest import detect_mime_type, is_supported
    from .queue import enqueue_job

    start_time = datetime.utcnow()
    update_job_progress(10, "Loading ZIP file")

    storage = get_storage()
    zip_data = storage.get(zip_storage_key)

    created_documents = []
    created_folders = []
    skipped_files = []
    parse_jobs = []

    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            # === SECURITY: Validate ZIP file ===
            try:
                file_list = validate_zip_safe(zf)
            except ZipSecurityError as e:
                logger.warning(f"ZIP security check failed: {e}")
                return {
                    "status": "rejected",
                    "error": str(e),
                    "documents_created": 0,
                    "folders_created": 0,
                    "security_error": True
                }

            total_files = len(file_list)
            update_job_progress(20, f"Processing {total_files} files")

            with get_db_session() as db:
                # Track created folders by path
                folder_cache = {}

                for idx, file_path in enumerate(file_list):
                    progress = 20 + int((idx / total_files) * 60)
                    update_job_progress(progress, f"Processing {file_path}")

                    filename = file_path.split('/')[-1]
                    dir_path = '/'.join(file_path.split('/')[:-1])

                    # Detect MIME type
                    mime_type = detect_mime_type(filename)

                    if not is_supported(mime_type):
                        skipped_files.append({"path": file_path, "reason": "unsupported_format"})
                        continue

                    # Create folder structure
                    folder_id = base_folder_id
                    if dir_path:
                        folder_id = _create_folder_path(
                            db, dir_path, firm_id, case_id, base_folder_id,
                            created_by_user_id, folder_cache, created_folders
                        )

                    # Extract file
                    file_data = zf.read(file_path)

                    # Store file
                    doc_storage_key = storage.generate_key(firm_id, case_id, filename)
                    metadata = storage.put(doc_storage_key, file_data, mime_type)

                    # Auto-detect party/role from path (mapping_mode=auto)
                    party, role = _auto_detect_metadata(file_path) if mapping_mode == "auto" else (None, None)

                    # Create document record
                    doc = Document(
                        firm_id=firm_id,
                        case_id=case_id,
                        folder_id=folder_id,
                        doc_name=filename,
                        original_filename=filename,
                        mime_type=mime_type,
                        party=party,
                        role=role,
                        status=DocumentStatus.UPLOADED,
                        storage_key=doc_storage_key,
                        storage_provider="local",
                        size_bytes=metadata.size_bytes,
                        sha256=metadata.sha256,
                        created_by_user_id=created_by_user_id
                    )
                    db.add(doc)
                    db.flush()  # Get ID

                    created_documents.append({
                        "id": doc.id,
                        "name": filename,
                        "path": file_path,
                        "mime_type": mime_type
                    })

                    # Enqueue parsing job
                    job_result = enqueue_job(
                        task_parse_document,
                        document_id=doc.id,
                        storage_key=doc_storage_key,
                        mime_type=mime_type,
                        firm_id=firm_id,
                        queue_name="default",
                        job_id=f"parse_{doc.id}"
                    )
                    parse_jobs.append(job_result)

                db.commit()

        update_job_progress(100, "Complete")

        elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        return {
            "status": "done",
            "documents_created": len(created_documents),
            "folders_created": len(created_folders),
            "files_skipped": len(skipped_files),
            "documents": created_documents,
            "folders": created_folders,
            "skipped": skipped_files,
            "parse_jobs": parse_jobs,
            "elapsed_ms": elapsed_ms
        }

    except Exception as e:
        logger.exception("Failed to ingest ZIP")
        raise


def _create_folder_path(
    db,
    path: str,
    firm_id: str,
    case_id: str,
    base_folder_id: Optional[str],
    created_by_user_id: Optional[str],
    folder_cache: dict,
    created_folders: list
) -> str:
    """Create folder hierarchy and return leaf folder ID"""
    from ..db.models import Folder, FolderScope

    parts = path.split('/')
    current_parent_id = base_folder_id

    for i, part in enumerate(parts):
        if not part:
            continue

        cache_key = '/'.join(parts[:i+1])

        if cache_key in folder_cache:
            current_parent_id = folder_cache[cache_key]
            continue

        # Check if folder exists
        existing = db.query(Folder).filter(
            Folder.firm_id == firm_id,
            Folder.parent_id == current_parent_id,
            Folder.name == part
        ).first()

        if existing:
            current_parent_id = existing.id
            folder_cache[cache_key] = existing.id
        else:
            # Create folder
            folder = Folder(
                firm_id=firm_id,
                parent_id=current_parent_id,
                scope_type=FolderScope.CASE,
                scope_id=case_id,
                case_id=case_id,
                name=part,
                created_by_user_id=created_by_user_id
            )
            db.add(folder)
            db.flush()

            current_parent_id = folder.id
            folder_cache[cache_key] = folder.id
            created_folders.append({"id": folder.id, "name": part, "path": cache_key})

    return current_parent_id


def _auto_detect_metadata(file_path: str) -> tuple:
    """Auto-detect party and role from file path"""
    from ..db.models import DocumentParty, DocumentRole

    path_lower = file_path.lower()

    # Party detection
    party = None
    if 'plaintiff' in path_lower or 'תובע' in file_path:
        party = DocumentParty.THEIRS  # Assuming we're defendant
    elif 'defendant' in path_lower or 'נתבע' in file_path:
        party = DocumentParty.OURS
    elif 'court' in path_lower or 'בית משפט' in file_path:
        party = DocumentParty.COURT

    # Role detection
    role = None
    if 'claim' in path_lower or 'תביעה' in file_path:
        role = DocumentRole.STATEMENT_OF_CLAIM
    elif 'defense' in path_lower or 'הגנה' in file_path:
        role = DocumentRole.DEFENSE
    elif 'motion' in path_lower or 'בקשה' in file_path:
        role = DocumentRole.MOTION
    elif 'affidavit' in path_lower or 'תצהיר' in file_path:
        role = DocumentRole.AFFIDAVIT
    elif 'exhibit' in path_lower or 'נספח' in file_path:
        role = DocumentRole.EXHIBIT
    elif 'judgment' in path_lower or 'פסק' in file_path:
        role = DocumentRole.JUDGMENT

    return party, role


def task_index_document(document_id: str, firm_id: str) -> Dict[str, Any]:
    """
    Index a document for search (future use).

    Args:
        document_id: Document ID
        firm_id: Firm ID

    Returns:
        Dict with indexing results
    """
    # Placeholder for vector indexing (future)
    return {
        "document_id": document_id,
        "status": "indexed",
        "message": "Indexing not yet implemented"
    }


def task_analyze_case(
    case_id: str,
    firm_id: str,
    document_ids: Optional[List[str]] = None,
    triggered_by_user_id: Optional[str] = None,
    mode: str = "full"
) -> Dict[str, Any]:
    """
    Analyze a case for contradictions.

    Args:
        case_id: Case ID
        firm_id: Firm ID
        document_ids: Specific documents to analyze (all if None)
        triggered_by_user_id: User who triggered
        mode: Analysis mode (fast/full)

    Returns:
        Dict with analysis results
    """
    from ..db.session import get_db_session
    from ..db.models import (
        Document, DocumentStatus, AnalysisRun, Claim, Contradiction,
        Event, EventType, DocumentBlock, WitnessVersion
    )
    from ..extractor import extract_claims_from_text, Claim as ExtractedClaim
    from ..detector import detect_contradictions
    from ..anchors import build_anchor_from_claim
    from ..insights import compute_insights_for_run

    start_time = datetime.utcnow()
    update_job_progress(10, "Loading documents")

    try:
        with get_db_session() as db:
            # Get documents to analyze (READY only)
            query = db.query(Document).filter(
                Document.case_id == case_id,
                Document.firm_id == firm_id,
            )
            if document_ids:
                query = query.filter(Document.id.in_(document_ids))

            all_docs = query.all()
            documents = [d for d in all_docs if d.status == DocumentStatus.READY]

            if not documents:
                # Provide actionable diagnostics to the UI
                by_status: Dict[str, int] = {}
                docs_debug = []
                for d in all_docs:
                    status_val = d.status.value if hasattr(d.status, "value") else str(d.status)
                    by_status[status_val] = by_status.get(status_val, 0) + 1
                    err = None
                    if isinstance(d.extra_data, dict):
                        err = d.extra_data.get("error")
                    docs_debug.append({
                        "id": d.id,
                        "doc_name": d.doc_name,
                        "status": status_val,
                        "error": err,
                    })

                return {
                    "status": "error",
                    "message": "No ready documents found for analysis",
                    "documents_total": len(all_docs),
                    "documents_by_status": by_status,
                    "documents": docs_debug[:20],
                }

            update_job_progress(20, f"Analyzing {len(documents)} documents")

            # Create analysis run
            run = AnalysisRun(
                firm_id=firm_id,
                case_id=case_id,
                status="running",
                triggered_by_user_id=triggered_by_user_id,
                input_document_ids=[d.id for d in documents]
            )
            db.add(run)
            db.flush()

            # Create event
            event = Event(
                firm_id=firm_id,
                case_id=case_id,
                event_type=EventType.ANALYSIS_STARTED,
                created_by_user_id=triggered_by_user_id,
                related_ids_json={"analysis_run_id": run.id}
            )
            db.add(event)

            # Preload witness versions by document
            doc_ids = [d.id for d in documents]
            witness_version_map: Dict[str, str] = {}
            if doc_ids:
                versions = (
                    db.query(WitnessVersion)
                    .filter(WitnessVersion.document_id.in_(doc_ids))
                    .all()
                )
                witness_version_map = {v.document_id: v.id for v in versions}

            # Extract claims from each document (prefer block-level for anchors)
            all_claims = []
            claim_pairs = []
            for idx, doc in enumerate(documents):
                progress = 20 + int((idx / len(documents)) * 30)
                update_job_progress(progress, f"Extracting claims from {doc.doc_name}")

                if not doc.full_text:
                    continue

                extracted = []
                blocks = (
                    db.query(DocumentBlock)
                    .filter(DocumentBlock.document_id == doc.id)
                    .order_by(DocumentBlock.block_index.asc())
                    .all()
                )

                if blocks:
                    for block in blocks:
                        block_claims = extract_claims_from_text(
                            text=block.text,
                            source_name=doc.doc_name,
                            doc_id=doc.id,
                            paragraph_id=block.id,
                            paragraph_index=block.paragraph_index,
                            char_offset=block.char_start or 0,
                            page_no=block.page_no,
                            block_index=block.block_index,
                            bbox=block.bbox_json,
                            sanitize=False,
                        )

                        # Make claim IDs unique across blocks/documents for detection
                        for claim in block_claims:
                            segment_index = None
                            if getattr(claim, "metadata", None):
                                segment_index = claim.metadata.get("segment_index")
                            if segment_index is not None:
                                claim.id = f"{doc.id}_{block.block_index}_{segment_index}"
                            else:
                                claim.id = f"{doc.id}_{block.block_index}_{uuid.uuid4().hex[:6]}"

                        extracted.extend(block_claims)
                else:
                    # Fallback: extract from full text (less precise anchors)
                    extracted = extract_claims_from_text(
                        text=doc.full_text,
                        source_name=doc.doc_name,
                        doc_id=doc.id,
                        sanitize=True,
                    )
                    for claim in extracted:
                        claim.id = f"{doc.id}_{claim.id}"

                # Track DB claim objects so we can link contradictions -> claims later
                for claim in extracted:
                    # Save claim to DB
                    anchor = build_anchor_from_claim(claim)
                    db_claim = Claim(
                        run_id=run.id,
                        document_id=doc.id,
                        witness_version_id=witness_version_map.get(doc.id),
                        text=claim.text,
                        party=doc.party.value if doc.party else None,
                        role=doc.role.value if doc.role else None,
                        locator_json=anchor,
                    )
                    db.add(db_claim)
                    claim_pairs.append((claim, db_claim))
                    all_claims.append(claim)

            db.flush()

            # After flush, DB IDs exist. Attach DB IDs to in-memory claim objects so the
            # detector output can be persisted with stable foreign keys.
            for claim, db_claim in claim_pairs:
                try:
                    setattr(claim, "_db_id", db_claim.id)
                except Exception:
                    pass

            update_job_progress(60, "Detecting contradictions")

            # Detect contradictions
            if all_claims:
                detection_result = detect_contradictions(all_claims)

                for contr in detection_result.contradictions:
                    claim1_db_id = getattr(contr.claim1, "_db_id", None)
                    claim2_db_id = getattr(contr.claim2, "_db_id", None)

                    locator1 = build_anchor_from_claim(contr.claim1)
                    locator2 = build_anchor_from_claim(contr.claim2)
                    db_contr = Contradiction(
                        run_id=run.id,
                        claim1_id=claim1_db_id,
                        claim2_id=claim2_db_id,
                        contradiction_type=contr.type.value,
                        status=contr.status.value if hasattr(contr, 'status') else 'suspicious',
                        confidence=contr.confidence,
                        severity=contr.severity.value,
                        category=contr.category.value if contr.category else None,
                        explanation=contr.explanation,
                        quote1=contr.quote1,
                        quote2=contr.quote2,
                        locator1_json=locator1,
                        locator2_json=locator2,
                    )
                    db.add(db_contr)

            update_job_progress(85, "Generating insights")

            # Generate contradiction insights
            compute_insights_for_run(db, run.id)

            update_job_progress(90, "Saving results")

            # Update run status
            run.status = "done"
            run.completed_at = datetime.utcnow()

            # Create completion event
            event2 = Event(
                firm_id=firm_id,
                case_id=case_id,
                event_type=EventType.ANALYSIS_COMPLETED,
                created_by_user_id=triggered_by_user_id,
                related_ids_json={
                    "analysis_run_id": run.id,
                    "claims_count": len(all_claims),
                    "contradictions_count": len(detection_result.contradictions) if all_claims else 0
                }
            )
            db.add(event2)

            db.commit()

            update_job_progress(100, "Complete")

            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            return {
                "status": "done",
                "analysis_run_id": run.id,
                "documents_analyzed": len(documents),
                "claims_extracted": len(all_claims),
                "contradictions_found": len(detection_result.contradictions) if all_claims else 0,
                "elapsed_ms": elapsed_ms
            }

    except Exception as e:
        logger.exception("Analysis failed")
        safe_error = _sanitize_error_message(e, fallback="שגיאה בניתוח התיק")
        _set_job_error_message(safe_error)

        # Update run status
        try:
            with get_db_session() as db:
                run = db.query(AnalysisRun).filter(
                    AnalysisRun.case_id == case_id
                ).order_by(AnalysisRun.created_at.desc()).first()
                if run and run.status == "running":
                    run.status = "failed"
                    run.metadata_json = run.metadata_json or {}
                    run.metadata_json["error"] = safe_error
                    db.commit()
        except:
            pass

        raise
