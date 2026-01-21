"""
SQLAlchemy Models for Database
==============================

Complete schema for legal case management including:
- Multi-tenant organization (Firms, Users, Teams)
- Case management with RBAC
- Folder system (firm/team/case scoped)
- Document storage with versions
- Async job queue
- Timeline events
- Analysis results (claims, contradictions, issues)

Supports both PostgreSQL and SQLite via SQLAlchemy.
"""

import os
import enum
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime, Enum, ForeignKey,
    BigInteger, UniqueConstraint, Index, JSON, CheckConstraint
)
from sqlalchemy.orm import relationship, declarative_base
import uuid

# Use JSON for cross-database compatibility (works with both PostgreSQL and SQLite)
# PostgreSQL will use native JSONB, SQLite will use TEXT with JSON serialization
JSONB = JSON

Base = declarative_base()


def generate_uuid():
    return str(uuid.uuid4())


# =============================================================================
# ENUMS
# =============================================================================

class SystemRole(str, enum.Enum):
    """System-level roles (firm-wide permissions)"""
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class TeamRole(str, enum.Enum):
    """Team-level roles"""
    TEAM_LEADER = "team_leader"
    TEAM_MEMBER = "team_member"


class CaseStatus(str, enum.Enum):
    """Case lifecycle status"""
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    ARCHIVED = "archived"
    CLOSED = "closed"


class DocumentParty(str, enum.Enum):
    """Which party the document belongs to"""
    OURS = "ours"
    THEIRS = "theirs"
    COURT = "court"
    THIRD_PARTY = "third_party"
    UNKNOWN = "unknown"


class DocumentRole(str, enum.Enum):
    """Document role in legal case"""
    STATEMENT_OF_CLAIM = "statement_of_claim"
    DEFENSE = "defense"
    REPLY = "reply"
    MOTION = "motion"
    RESPONSE = "response"
    SUMMATIONS = "summations"
    JUDGMENT = "judgment"
    EXHIBIT = "exhibit"
    AFFIDAVIT = "affidavit"
    PROTOCOL = "protocol"
    EXPERT_OPINION = "expert_opinion"
    CONTRACT = "contract"
    LETTER = "letter"
    UNKNOWN = "unknown"


class DocumentStatus(str, enum.Enum):
    """Document processing status"""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class FolderScope(str, enum.Enum):
    """Folder scope type"""
    FIRM = "firm"
    TEAM = "team"
    CASE = "case"
    USER = "user"


class JobType(str, enum.Enum):
    """Async job types"""
    INGEST_ZIP = "ingest_zip"
    PARSE_DOC = "parse_doc"
    OCR_DOC = "ocr_doc"
    INDEX_DOC = "index_doc"
    EXTRACT_CLAIMS = "extract_claims"
    ANALYZE = "analyze"
    VERIFY = "verify"
    EXPORT = "export"


class JobStatus(str, enum.Enum):
    """Job status"""
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(str, enum.Enum):
    """Timeline event types"""
    DOCUMENT_ADDED = "document_added"
    DOCUMENT_UPDATED = "document_updated"
    DOCUMENT_DELETED = "document_deleted"
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETED = "analysis_completed"
    COURT_FINDING_ADDED = "court_finding_added"
    ISSUE_STATUS_CHANGED = "issue_status_changed"
    EXPORT_GENERATED = "export_generated"
    CASE_CREATED = "case_created"
    CASE_STATUS_CHANGED = "case_status_changed"


class IssueStatus(str, enum.Enum):
    """Issue lifecycle status"""
    OPEN = "open"
    CONTESTED = "contested"
    SUPPORTED = "supported"
    NARROWED = "narrowed"
    STRUCK = "struck"
    ADMITTED = "admitted"
    RESOLVED = "resolved"


class ContradictionStatus(str, enum.Enum):
    """Contradiction verification status"""
    VERIFIED = "verified"
    LIKELY = "likely"
    SUSPICIOUS = "suspicious"
    REJECTED = "rejected"


class ContradictionBucket(str, enum.Enum):
    """Contradiction bucketing"""
    INTERNAL_OURS = "internal_ours"
    INTERNAL_THEIRS = "internal_theirs"
    DISPUTE = "dispute"
    UNKNOWN = "unknown"


# =============================================================================
# ORGANIZATION MODELS
# =============================================================================

class Firm(Base):
    """Law firm / משרד עורכי דין"""
    __tablename__ = "firms"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    domain = Column(String(255), nullable=True)  # e.g., "cohen-law.co.il"
    settings = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    extra_data = Column(JSONB, default=dict)  # Note: 'metadata' is reserved by SQLAlchemy

    # Relationships
    users = relationship("User", back_populates="firm", cascade="all, delete-orphan")
    teams = relationship("Team", back_populates="firm", cascade="all, delete-orphan")
    cases = relationship("Case", back_populates="firm", cascade="all, delete-orphan")
    folders = relationship("Folder", back_populates="firm", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="firm", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="firm", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="firm", cascade="all, delete-orphan")


class User(Base):
    """User in the system / משתמש"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    firm_id = Column(String(36), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    system_role = Column(Enum(SystemRole), default=SystemRole.MEMBER, nullable=False)
    professional_role = Column(String(100), nullable=True)  # שותף, עו"ד בכיר, מתמחה
    password_hash = Column(String(255), nullable=True)  # For future auth
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    extra_data = Column(JSONB, default=dict)  # Note: 'metadata' is reserved by SQLAlchemy

    # Unique email per firm
    __table_args__ = (
        UniqueConstraint("firm_id", "email", name="uq_user_firm_email"),
    )

    # Relationships
    firm = relationship("Firm", back_populates="users")
    team_memberships = relationship("TeamMember", back_populates="user", cascade="all, delete-orphan", foreign_keys="TeamMember.user_id")
    admin_scopes = relationship("AdminTeamScope", back_populates="admin_user", cascade="all, delete-orphan", foreign_keys="AdminTeamScope.admin_user_id")
    case_participations = relationship("CaseParticipant", back_populates="user", cascade="all, delete-orphan", foreign_keys="CaseParticipant.user_id")
    responsible_cases = relationship("Case", back_populates="responsible_user", foreign_keys="Case.responsible_user_id")


class Team(Base):
    """Team within a firm / צוות"""
    __tablename__ = "teams"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    firm_id = Column(String(36), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    extra_data = Column(JSONB, default=dict)  # Note: 'metadata' is reserved by SQLAlchemy

    # Relationships
    firm = relationship("Firm", back_populates="teams")
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    admin_scopes = relationship("AdminTeamScope", back_populates="team", cascade="all, delete-orphan")
    case_teams = relationship("CaseTeam", back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    """Team membership / חברות בצוות"""
    __tablename__ = "team_members"

    team_id = Column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    team_role = Column(Enum(TeamRole), default=TeamRole.TEAM_MEMBER, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)
    added_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships", foreign_keys=[user_id])


class AdminTeamScope(Base):
    """Admin's scope of team management / היקף ניהול צוותים לאדמין"""
    __tablename__ = "admin_team_scope"

    admin_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    team_id = Column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    granted_at = Column(DateTime, default=datetime.utcnow)
    granted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    admin_user = relationship("User", back_populates="admin_scopes", foreign_keys=[admin_user_id])
    team = relationship("Team", back_populates="admin_scopes")


# =============================================================================
# CASE MANAGEMENT MODELS
# =============================================================================

class Case(Base):
    """Legal case / תיק"""
    __tablename__ = "cases"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    firm_id = Column(String(36), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    responsible_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(Enum(CaseStatus), default=CaseStatus.ACTIVE, nullable=False)

    # Case details
    client_name = Column(String(255), nullable=True)
    our_side = Column(String(50), nullable=True)  # plaintiff/defendant/third_party
    opponent_name = Column(String(255), nullable=True)
    court = Column(String(255), nullable=True)
    case_number = Column(String(100), nullable=True)
    tags = Column(JSONB, default=list)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    extra_data = Column(JSONB, default=dict)  # Note: 'metadata' is reserved by SQLAlchemy

    # Relationships
    firm = relationship("Firm", back_populates="cases")
    responsible_user = relationship("User", back_populates="responsible_cases", foreign_keys=[responsible_user_id])
    participants = relationship("CaseParticipant", back_populates="case", cascade="all, delete-orphan")
    case_teams = relationship("CaseTeam", back_populates="case", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    folders = relationship("Folder", back_populates="case", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="case", cascade="all, delete-orphan")
    issues = relationship("Issue", back_populates="case", cascade="all, delete-orphan")
    analysis_runs = relationship("AnalysisRun", back_populates="case", cascade="all, delete-orphan")


class CaseParticipant(Base):
    """User participation in a case / משתתף בתיק"""
    __tablename__ = "case_participants"

    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String(50), nullable=True)  # owner/editor/viewer
    added_at = Column(DateTime, default=datetime.utcnow)
    added_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    case = relationship("Case", back_populates="participants")
    user = relationship("User", back_populates="case_participations", foreign_keys=[user_id])


class CaseTeam(Base):
    """Case-Team association / שיוך תיק לצוות"""
    __tablename__ = "case_teams"

    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True)
    team_id = Column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    assigned_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    case = relationship("Case", back_populates="case_teams")
    team = relationship("Team", back_populates="case_teams")


# =============================================================================
# FOLDER SYSTEM
# =============================================================================

class Folder(Base):
    """Folder for organizing documents / תיקייה"""
    __tablename__ = "folders"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    firm_id = Column(String(36), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(String(36), ForeignKey("folders.id", ondelete="CASCADE"), nullable=True)
    scope_type = Column(Enum(FolderScope), nullable=False)  # firm/team/case/user
    scope_id = Column(String(36), nullable=True)  # team_id or case_id depending on scope_type
    name = Column(String(255), nullable=False)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    extra_data = Column(JSONB, default=dict)  # Note: 'metadata' is reserved by SQLAlchemy

    # Case relationship (for case-scoped folders)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True)

    # Unique folder name within parent
    __table_args__ = (
        UniqueConstraint("parent_id", "name", "firm_id", name="uq_folder_parent_name"),
        Index("ix_folder_scope", "scope_type", "scope_id"),
    )

    # Relationships
    firm = relationship("Firm", back_populates="folders")
    case = relationship("Case", back_populates="folders")
    parent = relationship("Folder", remote_side=[id], backref="children")
    documents = relationship("Document", back_populates="folder")


# =============================================================================
# DOCUMENT MODELS
# =============================================================================

class Document(Base):
    """Document in a case / מסמך"""
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    firm_id = Column(String(36), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(String(36), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True)

    # Document info
    doc_name = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)

    # Legal metadata
    party = Column(Enum(DocumentParty), default=DocumentParty.UNKNOWN)
    role = Column(Enum(DocumentRole), default=DocumentRole.UNKNOWN)
    author = Column(String(255), nullable=True)
    version_label = Column(String(50), nullable=True)  # "מתוקן", "טיוטה", "הוגש"
    occurred_at = Column(DateTime, nullable=True)  # When the document was created/signed

    # Processing status
    status = Column(Enum(DocumentStatus), default=DocumentStatus.UPLOADED)

    # Storage
    storage_key = Column(String(500), nullable=False)  # Path or S3 key
    storage_provider = Column(String(50), default="local")  # local/s3
    size_bytes = Column(BigInteger, nullable=True)
    sha256 = Column(String(64), nullable=True)

    # Extracted info
    page_count = Column(Integer, nullable=True)
    language = Column(String(10), nullable=True)
    full_text = Column(Text, nullable=True)  # Full extracted text

    # Timestamps
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    extra_data = Column(JSONB, default=dict)  # Note: 'metadata' is reserved by SQLAlchemy

    __table_args__ = (
        Index("ix_document_case_status", "case_id", "status"),
        Index("ix_document_firm", "firm_id"),
    )

    # Relationships
    firm = relationship("Firm", back_populates="documents")
    case = relationship("Case", back_populates="documents")
    folder = relationship("Folder", back_populates="documents")
    pages = relationship("DocumentPage", back_populates="document", cascade="all, delete-orphan")
    blocks = relationship("DocumentBlock", back_populates="document", cascade="all, delete-orphan")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")
    claims = relationship("Claim", back_populates="document", cascade="all, delete-orphan")


class DocumentPage(Base):
    """Page within a document"""
    __tablename__ = "document_pages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_no = Column(Integer, nullable=False)
    text = Column(Text, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("document_id", "page_no", name="uq_page_doc_no"),
        Index("ix_page_document", "document_id"),
    )

    # Relationships
    document = relationship("Document", back_populates="pages")


class DocumentBlock(Base):
    """Text block within a document (paragraph/section)"""
    __tablename__ = "document_blocks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_no = Column(Integer, nullable=False)
    block_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    bbox_json = Column(JSONB, nullable=True)  # {x, y, width, height}
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    paragraph_index = Column(Integer, nullable=True)
    locator_json = Column(JSONB, nullable=True)  # Full locator info
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_block_document_page", "document_id", "page_no"),
    )

    # Relationships
    document = relationship("Document", back_populates="blocks")


class DocumentVersion(Base):
    """Document version history"""
    __tablename__ = "document_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version_no = Column(Integer, nullable=False)
    storage_key = Column(String(500), nullable=False)
    sha256 = Column(String(64), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="uq_doc_version"),
    )

    # Relationships
    document = relationship("Document", back_populates="versions")


# =============================================================================
# JOB QUEUE
# =============================================================================

class Job(Base):
    """Async job for processing"""
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    firm_id = Column(String(36), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)

    job_type = Column(Enum(JobType), nullable=False)
    status = Column(Enum(JobStatus), default=JobStatus.QUEUED)
    progress = Column(Integer, default=0)  # 0-100
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)

    # Timing
    timing_json = Column(JSONB, default=dict)  # {queued_at, started_at, finished_at, ...}

    # Input/output
    input_json = Column(JSONB, default=dict)
    output_json = Column(JSONB, default=dict)

    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_job_status", "status"),
        Index("ix_job_firm_status", "firm_id", "status"),
    )

    # Relationships
    firm = relationship("Firm", back_populates="jobs")


# =============================================================================
# TIMELINE / EVENTS
# =============================================================================

class Event(Base):
    """Timeline event for audit trail"""
    __tablename__ = "events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    firm_id = Column(String(36), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True)
    event_type = Column(Enum(EventType), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    related_ids_json = Column(JSONB, default=dict)  # {analysis_run_id, issue_id, ...}
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    occurred_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    note = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_event_case", "case_id", "occurred_at"),
    )

    # Relationships
    firm = relationship("Firm", back_populates="events")
    case = relationship("Case", back_populates="events")


# =============================================================================
# ANALYSIS MODELS
# =============================================================================

class AnalysisRun(Base):
    """Single analysis run"""
    __tablename__ = "analysis_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    firm_id = Column(String(36), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default="queued")  # queued/running/done/failed
    triggered_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    input_document_ids = Column(JSONB, default=list)
    metadata_json = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    case = relationship("Case", back_populates="analysis_runs")
    claims = relationship("Claim", back_populates="analysis_run", cascade="all, delete-orphan")
    contradictions = relationship("Contradiction", back_populates="analysis_run", cascade="all, delete-orphan")


class Claim(Base):
    """Extracted claim from document"""
    __tablename__ = "claims"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    run_id = Column(String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    claim_hash = Column(String(64), nullable=True)
    text = Column(Text, nullable=False)
    party = Column(String(50), nullable=True)
    role = Column(String(50), nullable=True)
    locator_json = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_claim_run", "run_id"),
        Index("ix_claim_document", "document_id"),
    )

    # Relationships
    analysis_run = relationship("AnalysisRun", back_populates="claims")
    document = relationship("Document", back_populates="claims")


class Issue(Base):
    """Legal issue / פלוגתא"""
    __tablename__ = "issues"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    firm_id = Column(String(36), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    issue_type = Column(String(100), nullable=True)
    status = Column(Enum(IssueStatus), default=IssueStatus.OPEN)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    case = relationship("Case", back_populates="issues")
    links = relationship("IssueLink", back_populates="issue", cascade="all, delete-orphan")


class IssueLink(Base):
    """Link between issue and claim/contradiction"""
    __tablename__ = "issue_links"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    issue_id = Column(String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    claim_id = Column(String(36), ForeignKey("claims.id", ondelete="CASCADE"), nullable=True)
    contradiction_id = Column(String(36), ForeignKey("contradictions.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    issue = relationship("Issue", back_populates="links")


class Contradiction(Base):
    """Detected contradiction"""
    __tablename__ = "contradictions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    run_id = Column(String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    claim1_id = Column(String(36), ForeignKey("claims.id", ondelete="CASCADE"), nullable=True)
    claim2_id = Column(String(36), ForeignKey("claims.id", ondelete="CASCADE"), nullable=True)
    contradiction_type = Column(String(100), nullable=False)  # temporal/quant/fact/...
    status = Column(Enum(ContradictionStatus), default=ContradictionStatus.SUSPICIOUS)
    bucket = Column(Enum(ContradictionBucket), default=ContradictionBucket.UNKNOWN)
    confidence = Column(Float, default=0.0)
    severity = Column(String(20), default="medium")  # low/medium/high/critical
    category = Column(String(50), nullable=True)  # hard_contradiction/narrative_ambiguity/...
    explanation = Column(Text, nullable=True)
    quote1 = Column(Text, nullable=True)
    quote2 = Column(Text, nullable=True)
    locator1_json = Column(JSONB, default=dict)
    locator2_json = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_contradiction_run", "run_id"),
    )

    # Relationships
    analysis_run = relationship("AnalysisRun", back_populates="contradictions")


class Finding(Base):
    """Court finding / קביעה שיפוטית"""
    __tablename__ = "findings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    event_id = Column(String(36), ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    finding_type = Column(String(50), nullable=False)  # issue_struck/narrowed/fact_found/...
    target_issue_id = Column(String(36), ForeignKey("issues.id", ondelete="SET NULL"), nullable=True)
    target_contradiction_id = Column(String(36), ForeignKey("contradictions.id", ondelete="SET NULL"), nullable=True)
    quote = Column(Text, nullable=True)
    locator_json = Column(JSONB, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
