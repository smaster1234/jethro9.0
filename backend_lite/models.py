"""
LEGACY - Do Not Use in Production API
=======================================

This module contains the original SQLite-based CaseDatabase implementation.
It has been replaced by SQLAlchemy models in backend_lite/db/models.py.

DO NOT use CaseDatabase or get_database() in new code.
Use SQLAlchemy session from backend_lite.db.session instead.

This file is kept for backward compatibility only.

=====================================
Original Documentation:
=====================================

Data Models for Case Management

Minimal SQLite-based storage for:
- Cases (תיקים)
- Documents (מסמכים)
- Analysis Runs (הרצות ניתוח)

No complex permissions, no workflow, no OCR pipeline.
"""

import sqlite3
import hashlib
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class PartySide(str, Enum):
    """Which side in litigation"""
    PLAINTIFF = "plaintiff"      # תובע
    DEFENDANT = "defendant"      # נתבע
    THIRD_PARTY = "third_party"  # צד ג'
    UNKNOWN = "unknown"


class DocumentParty(str, Enum):
    """Which party the document belongs to"""
    OURS = "ours"              # שלנו
    THEIRS = "theirs"          # של הצד השני
    COURT = "court"            # בית משפט
    THIRD_PARTY = "third_party"  # צד ג'
    UNKNOWN = "unknown"        # לא ידוע


class DocumentType(str, Enum):
    """Document types in legal case"""
    COMPLAINT = "complaint"           # כתב תביעה
    DEFENSE = "defense"               # כתב הגנה
    MOTION = "motion"                 # בקשה
    AFFIDAVIT = "affidavit"           # תצהיר
    PROTOCOL = "protocol"             # פרוטוקול
    LETTER = "letter"                 # מכתב
    CONTRACT = "contract"             # חוזה
    EXHIBIT = "exhibit"               # נספח
    EXPERT_OPINION = "expert_opinion" # חוות דעת מומחה
    OTHER = "other"


class SystemRole(str, Enum):
    """System-level roles (firm-wide permissions)"""
    SUPER_ADMIN = "super_admin"   # Full control over firm
    ADMIN = "admin"               # Manage teams/users within scope
    MEMBER = "member"             # Regular user
    VIEWER = "viewer"             # Read-only access


class TeamRole(str, Enum):
    """Team-level roles"""
    TEAM_LEADER = "team_leader"   # מוביל צוות - professional lead
    TEAM_MEMBER = "team_member"   # חבר צוות


class CaseStatus(str, Enum):
    """Case lifecycle status"""
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    ARCHIVED = "archived"
    CLOSED = "closed"


# =============================================================================
# DATA CLASSES - ORGANIZATION
# =============================================================================

@dataclass
class Firm:
    """Law firm / משרד עורכי דין"""
    id: str
    name: str
    domain: Optional[str] = None  # e.g., "cohen-law.co.il"
    settings: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class User:
    """User in the system / משתמש"""
    id: str
    firm_id: str
    email: str
    name: str
    system_role: SystemRole = SystemRole.MEMBER
    professional_role: Optional[str] = None  # e.g., "שותף", "עו״ד בכיר", "מתמחה"
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Team:
    """Team within a firm / צוות"""
    id: str
    firm_id: str
    name: str
    description: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    created_by_user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamMember:
    """Team membership / חברות בצוות"""
    team_id: str
    user_id: str
    team_role: TeamRole = TeamRole.TEAM_MEMBER
    added_at: datetime = field(default_factory=datetime.now)
    added_by_user_id: Optional[str] = None


@dataclass
class AdminTeamScope:
    """Admin's scope of team management / היקף ניהול צוותים"""
    admin_user_id: str
    team_id: str
    granted_at: datetime = field(default_factory=datetime.now)
    granted_by_user_id: Optional[str] = None


@dataclass
class CaseTeam:
    """Case-Team association / שיוך תיק לצוות"""
    case_id: str
    team_id: str
    assigned_at: datetime = field(default_factory=datetime.now)
    assigned_by_user_id: Optional[str] = None


@dataclass
class CaseParticipant:
    """User participation in a case / משתתף בתיק"""
    case_id: str
    user_id: str
    role: Optional[str] = None  # e.g., "lead_attorney", "researcher"
    added_at: datetime = field(default_factory=datetime.now)
    added_by_user_id: Optional[str] = None


# =============================================================================
# DATA CLASSES - CASE MANAGEMENT
# =============================================================================

@dataclass
class Case:
    """Legal case / תיק"""
    id: str
    name: str
    # Multi-tenancy and ownership
    firm_id: Optional[str] = None
    responsible_user_id: Optional[str] = None  # עו"ד אחראי
    created_by_user_id: Optional[str] = None
    status: CaseStatus = CaseStatus.ACTIVE
    # Case details
    client_name: Optional[str] = None
    our_side: PartySide = PartySide.UNKNOWN
    opponent_name: Optional[str] = None
    court: Optional[str] = None
    case_number: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Document:
    """Document in a case / מסמך"""
    id: str
    case_id: str
    name: str
    doc_type: DocumentType = DocumentType.OTHER
    party: DocumentParty = DocumentParty.UNKNOWN  # Which party: ours/theirs/court/third_party
    role: Optional[str] = None  # Role in case: e.g., "plaintiff_affidavit", "defense_exhibit"
    version: str = "v1"
    author: Optional[str] = None
    date_created: Optional[datetime] = None
    extracted_text: str = ""
    text_hash: str = ""  # For detecting duplicates
    page_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def compute_hash(self) -> str:
        """Compute hash of extracted text"""
        return hashlib.sha256(self.extracted_text.encode()).hexdigest()[:16]


@dataclass
class Paragraph:
    """Paragraph/chunk within a document"""
    id: str  # Stable ID: hash(doc_id + index + normalized_text[:100])
    doc_id: str
    case_id: str
    paragraph_index: int
    text: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)

    @staticmethod
    def compute_id(doc_id: str, index: int, text: str) -> str:
        """Compute stable paragraph ID"""
        normalized = text.strip()[:100].lower()
        combined = f"{doc_id}|{index}|{normalized}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]


@dataclass
class AnalysisRun:
    """Single analysis run / הרצת ניתוח"""
    id: str
    case_id: str
    document_ids: List[str]
    input_fingerprint: str  # Hash of all input docs
    contradictions: List[Dict] = field(default_factory=list)
    cross_exam_questions: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    validation_flags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0

    @staticmethod
    def compute_fingerprint(docs: List[Document], paragraphs: Optional[List['Paragraph']] = None) -> str:
        """
        Compute fingerprint from documents and paragraphs.

        Includes paragraph count and first/last paragraph IDs for cache invalidation
        when document structure changes.
        """
        # Base: document hashes
        doc_hashes = sorted([d.text_hash for d in docs])
        combined = "|".join(doc_hashes)

        # Add paragraph info if available
        if paragraphs:
            para_count = len(paragraphs)
            # Include first and last para IDs to detect structure changes
            first_id = paragraphs[0].id if paragraphs else ""
            last_id = paragraphs[-1].id if paragraphs else ""
            combined += f"|paras:{para_count}|{first_id}|{last_id}"

        return hashlib.sha256(combined.encode()).hexdigest()[:16]


# =============================================================================
# DATABASE
# =============================================================================

class CaseDatabase:
    """SQLite database for case management"""

    def __init__(self, db_path: str = "cases.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # =====================================================================
        # ORGANIZATION TABLES
        # =====================================================================

        # Firms table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS firms (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                domain TEXT,
                settings TEXT DEFAULT '{}',
                created_at TEXT,
                metadata TEXT DEFAULT '{}'
            )
        """)

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                firm_id TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                system_role TEXT DEFAULT 'member',
                professional_role TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                last_login TEXT,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (firm_id) REFERENCES firms(id)
            )
        """)

        # Teams table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id TEXT PRIMARY KEY,
                firm_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT,
                created_by_user_id TEXT,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (firm_id) REFERENCES firms(id),
                FOREIGN KEY (created_by_user_id) REFERENCES users(id)
            )
        """)

        # Team members table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS team_members (
                team_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                team_role TEXT DEFAULT 'team_member',
                added_at TEXT,
                added_by_user_id TEXT,
                PRIMARY KEY (team_id, user_id),
                FOREIGN KEY (team_id) REFERENCES teams(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (added_by_user_id) REFERENCES users(id)
            )
        """)

        # Admin team scope table (which teams an admin can manage)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_team_scope (
                admin_user_id TEXT NOT NULL,
                team_id TEXT NOT NULL,
                granted_at TEXT,
                granted_by_user_id TEXT,
                PRIMARY KEY (admin_user_id, team_id),
                FOREIGN KEY (admin_user_id) REFERENCES users(id),
                FOREIGN KEY (team_id) REFERENCES teams(id),
                FOREIGN KEY (granted_by_user_id) REFERENCES users(id)
            )
        """)

        # =====================================================================
        # CASE MANAGEMENT TABLES
        # =====================================================================

        # Cases table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                firm_id TEXT,
                responsible_user_id TEXT,
                created_by_user_id TEXT,
                status TEXT DEFAULT 'active',
                client_name TEXT,
                our_side TEXT DEFAULT 'unknown',
                opponent_name TEXT,
                court TEXT,
                case_number TEXT,
                tags TEXT DEFAULT '[]',
                created_at TEXT,
                updated_at TEXT,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (firm_id) REFERENCES firms(id),
                FOREIGN KEY (responsible_user_id) REFERENCES users(id),
                FOREIGN KEY (created_by_user_id) REFERENCES users(id)
            )
        """)

        # Case-Team associations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS case_teams (
                case_id TEXT NOT NULL,
                team_id TEXT NOT NULL,
                assigned_at TEXT,
                assigned_by_user_id TEXT,
                PRIMARY KEY (case_id, team_id),
                FOREIGN KEY (case_id) REFERENCES cases(id),
                FOREIGN KEY (team_id) REFERENCES teams(id),
                FOREIGN KEY (assigned_by_user_id) REFERENCES users(id)
            )
        """)

        # Case participants (users directly assigned to a case)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS case_participants (
                case_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT,
                added_at TEXT,
                added_by_user_id TEXT,
                PRIMARY KEY (case_id, user_id),
                FOREIGN KEY (case_id) REFERENCES cases(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (added_by_user_id) REFERENCES users(id)
            )
        """)

        # Migration: Add new columns to cases if they don't exist
        for col, default in [
            ("firm_id", None),
            ("responsible_user_id", None),
            ("created_by_user_id", None),
            ("status", "'active'")
        ]:
            try:
                sql = f"ALTER TABLE cases ADD COLUMN {col} TEXT"
                if default:
                    sql += f" DEFAULT {default}"
                cursor.execute(sql)
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Documents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                name TEXT NOT NULL,
                doc_type TEXT DEFAULT 'other',
                party TEXT DEFAULT 'unknown',
                role TEXT,
                version TEXT DEFAULT 'v1',
                author TEXT,
                date_created TEXT,
                extracted_text TEXT,
                text_hash TEXT,
                page_count INTEGER DEFAULT 0,
                created_at TEXT,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (case_id) REFERENCES cases(id)
            )
        """)

        # Migration: Add party and role columns if they don't exist
        try:
            cursor.execute("ALTER TABLE documents ADD COLUMN party TEXT DEFAULT 'unknown'")
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute("ALTER TABLE documents ADD COLUMN role TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Paragraphs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paragraphs (
                id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                paragraph_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                char_start INTEGER,
                char_end INTEGER,
                created_at TEXT,
                FOREIGN KEY (doc_id) REFERENCES documents(id),
                FOREIGN KEY (case_id) REFERENCES cases(id)
            )
        """)

        # Analysis runs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                document_ids TEXT NOT NULL,
                input_fingerprint TEXT,
                contradictions TEXT DEFAULT '[]',
                cross_exam_questions TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                validation_flags TEXT DEFAULT '[]',
                created_at TEXT,
                duration_ms REAL DEFAULT 0,
                FOREIGN KEY (case_id) REFERENCES cases(id)
            )
        """)

        # Indexes - Organization
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_firm ON users(firm_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_teams_firm ON teams(firm_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_admin_scope_admin ON admin_team_scope(admin_user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_admin_scope_team ON admin_team_scope(team_id)")

        # Indexes - Case Management
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_firm ON cases(firm_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_responsible ON cases(responsible_user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_case_teams_case ON case_teams(case_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_case_teams_team ON case_teams(team_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_case_participants_case ON case_participants(case_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_case_participants_user ON case_participants(user_id)")

        # Indexes - Documents & Analysis
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_docs_case ON documents(case_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_paragraphs_doc ON paragraphs(doc_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_paragraphs_case ON paragraphs(case_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_case ON analysis_runs(case_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_fingerprint ON analysis_runs(input_fingerprint)")

        conn.commit()
        conn.close()

    # -------------------------------------------------------------------------
    # CASE OPERATIONS
    # -------------------------------------------------------------------------

    def create_case(self, name: str, **kwargs) -> Case:
        """Create a new case"""
        case = Case(
            id=str(uuid.uuid4()),
            name=name,
            firm_id=kwargs.get("firm_id"),
            created_by_user_id=kwargs.get("created_by_user_id"),
            responsible_user_id=kwargs.get("responsible_user_id"),
            client_name=kwargs.get("client_name"),
            our_side=kwargs.get("our_side", PartySide.UNKNOWN),
            opponent_name=kwargs.get("opponent_name"),
            court=kwargs.get("court"),
            case_number=kwargs.get("case_number"),
            tags=kwargs.get("tags", []),
            metadata=kwargs.get("metadata", {})
        )

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cases (id, name, firm_id, created_by_user_id, client_name, our_side, opponent_name,
                             court, case_number, tags, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            case.id, case.name, case.firm_id, case.created_by_user_id,
            case.client_name, case.our_side.value,
            case.opponent_name, case.court, case.case_number,
            json.dumps(case.tags), case.created_at.isoformat(),
            case.updated_at.isoformat(), json.dumps(case.metadata)
        ))
        conn.commit()
        conn.close()

        return case

    def get_case(self, case_id: str) -> Optional[Case]:
        """Get case by ID"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable named column access
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cases WHERE id = ?", (case_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        # Parse status enum
        try:
            status = CaseStatus(row["status"]) if row["status"] else CaseStatus.ACTIVE
        except (ValueError, KeyError):
            status = CaseStatus.ACTIVE

        return Case(
            id=row["id"],
            name=row["name"],
            firm_id=row["firm_id"],
            responsible_user_id=row["responsible_user_id"],
            created_by_user_id=row["created_by_user_id"],
            status=status,
            client_name=row["client_name"],
            our_side=PartySide(row["our_side"]) if row["our_side"] else PartySide.UNKNOWN,
            opponent_name=row["opponent_name"],
            court=row["court"],
            case_number=row["case_number"],
            tags=json.loads(row["tags"] or "[]"),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now(),
            metadata=json.loads(row["metadata"] or "{}")
        )

    def list_cases(self) -> List[Case]:
        """List all cases"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM cases ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        conn.close()

        return [self.get_case(row[0]) for row in rows]

    # -------------------------------------------------------------------------
    # DOCUMENT OPERATIONS
    # -------------------------------------------------------------------------

    def add_document(self, case_id: str, name: str, text: str, **kwargs) -> Document:
        """Add document to case"""
        doc = Document(
            id=str(uuid.uuid4()),
            case_id=case_id,
            name=name,
            doc_type=kwargs.get("doc_type", DocumentType.OTHER),
            party=kwargs.get("party", DocumentParty.UNKNOWN),
            role=kwargs.get("role"),
            version=kwargs.get("version", "v1"),
            author=kwargs.get("author"),
            date_created=kwargs.get("date_created"),
            extracted_text=text,
            page_count=kwargs.get("page_count", 0),
            metadata=kwargs.get("metadata", {})
        )
        doc.text_hash = doc.compute_hash()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documents (id, case_id, name, doc_type, party, role, version, author,
                                 date_created, extracted_text, text_hash, page_count,
                                 created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doc.id, doc.case_id, doc.name, doc.doc_type.value,
            doc.party.value, doc.role, doc.version,
            doc.author, doc.date_created.isoformat() if doc.date_created else None,
            doc.extracted_text, doc.text_hash, doc.page_count,
            doc.created_at.isoformat(), json.dumps(doc.metadata)
        ))
        conn.commit()
        conn.close()

        return doc

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get document by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, case_id, name, doc_type, party, role, version, author,
                   date_created, extracted_text, text_hash, page_count, created_at, metadata
            FROM documents WHERE id = ?
        """, (doc_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        # Handle party enum safely
        try:
            party = DocumentParty(row[4]) if row[4] else DocumentParty.UNKNOWN
        except ValueError:
            party = DocumentParty.UNKNOWN

        return Document(
            id=row[0], case_id=row[1], name=row[2],
            doc_type=DocumentType(row[3]) if row[3] else DocumentType.OTHER,
            party=party,
            role=row[5],
            version=row[6] or "v1",
            author=row[7],
            date_created=datetime.fromisoformat(row[8]) if row[8] else None,
            extracted_text=row[9] or "",
            text_hash=row[10] or "",
            page_count=row[11] or 0,
            created_at=datetime.fromisoformat(row[12]) if row[12] else datetime.now(),
            metadata=json.loads(row[13] or "{}")
        )

    def get_case_documents(self, case_id: str) -> List[Document]:
        """Get all documents for a case"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM documents WHERE case_id = ? ORDER BY created_at", (case_id,))
        rows = cursor.fetchall()
        conn.close()

        return [self.get_document(row[0]) for row in rows]

    # -------------------------------------------------------------------------
    # PARAGRAPH OPERATIONS
    # -------------------------------------------------------------------------

    def add_paragraphs(self, doc_id: str, case_id: str, paragraphs: List[Paragraph]) -> List[Paragraph]:
        """Add paragraphs for a document"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for para in paragraphs:
            cursor.execute("""
                INSERT OR REPLACE INTO paragraphs
                (id, doc_id, case_id, paragraph_index, text, char_start, char_end, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                para.id, para.doc_id, para.case_id, para.paragraph_index,
                para.text, para.char_start, para.char_end,
                para.created_at.isoformat()
            ))

        conn.commit()
        conn.close()
        return paragraphs

    def get_document_paragraphs(self, doc_id: str) -> List[Paragraph]:
        """Get all paragraphs for a document"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, doc_id, case_id, paragraph_index, text, char_start, char_end, created_at
            FROM paragraphs WHERE doc_id = ? ORDER BY paragraph_index
        """, (doc_id,))
        rows = cursor.fetchall()
        conn.close()

        return [
            Paragraph(
                id=row[0], doc_id=row[1], case_id=row[2],
                paragraph_index=row[3], text=row[4],
                char_start=row[5], char_end=row[6],
                created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now()
            )
            for row in rows
        ]

    def get_case_paragraphs(self, case_id: str) -> List[Paragraph]:
        """Get all paragraphs for a case"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, doc_id, case_id, paragraph_index, text, char_start, char_end, created_at
            FROM paragraphs WHERE case_id = ? ORDER BY doc_id, paragraph_index
        """, (case_id,))
        rows = cursor.fetchall()
        conn.close()

        return [
            Paragraph(
                id=row[0], doc_id=row[1], case_id=row[2],
                paragraph_index=row[3], text=row[4],
                char_start=row[5], char_end=row[6],
                created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now()
            )
            for row in rows
        ]

    def get_paragraph(self, paragraph_id: str) -> Optional[Paragraph]:
        """Get paragraph by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, doc_id, case_id, paragraph_index, text, char_start, char_end, created_at
            FROM paragraphs WHERE id = ?
        """, (paragraph_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return Paragraph(
            id=row[0], doc_id=row[1], case_id=row[2],
            paragraph_index=row[3], text=row[4],
            char_start=row[5], char_end=row[6],
            created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now()
        )

    def delete_document_paragraphs(self, doc_id: str):
        """Delete all paragraphs for a document"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM paragraphs WHERE doc_id = ?", (doc_id,))
        conn.commit()
        conn.close()

    # -------------------------------------------------------------------------
    # ANALYSIS RUN OPERATIONS
    # -------------------------------------------------------------------------

    def save_analysis_run(self, run: AnalysisRun) -> AnalysisRun:
        """Save analysis run"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO analysis_runs (id, case_id, document_ids, input_fingerprint,
                                      contradictions, cross_exam_questions, metadata,
                                      validation_flags, created_at, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run.id, run.case_id, json.dumps(run.document_ids), run.input_fingerprint,
            json.dumps(run.contradictions), json.dumps(run.cross_exam_questions),
            json.dumps(run.metadata), json.dumps(run.validation_flags),
            run.created_at.isoformat(), run.duration_ms
        ))
        conn.commit()
        conn.close()
        return run

    def get_run_by_fingerprint(self, case_id: str, fingerprint: str) -> Optional[AnalysisRun]:
        """Check if we already have analysis for these exact documents"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM analysis_runs
            WHERE case_id = ? AND input_fingerprint = ?
            ORDER BY created_at DESC LIMIT 1
        """, (case_id, fingerprint))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return AnalysisRun(
            id=row[0], case_id=row[1],
            document_ids=json.loads(row[2] or "[]"),
            input_fingerprint=row[3],
            contradictions=json.loads(row[4] or "[]"),
            cross_exam_questions=json.loads(row[5] or "[]"),
            metadata=json.loads(row[6] or "{}"),
            validation_flags=json.loads(row[7] or "[]"),
            created_at=datetime.fromisoformat(row[8]) if row[8] else datetime.now(),
            duration_ms=row[9] or 0.0
        )

    def get_case_runs(self, case_id: str) -> List[AnalysisRun]:
        """Get all analysis runs for a case"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, case_id, document_ids, input_fingerprint, contradictions,
                   cross_exam_questions, metadata, validation_flags, created_at, duration_ms
            FROM analysis_runs WHERE case_id = ? ORDER BY created_at DESC
        """, (case_id,))
        rows = cursor.fetchall()
        conn.close()

        runs = []
        for row in rows:
            runs.append(AnalysisRun(
                id=row[0], case_id=row[1],
                document_ids=json.loads(row[2] or "[]"),
                input_fingerprint=row[3],
                contradictions=json.loads(row[4] or "[]"),
                cross_exam_questions=json.loads(row[5] or "[]"),
                metadata=json.loads(row[6] or "{}"),
                validation_flags=json.loads(row[7] or "[]"),
                created_at=datetime.fromisoformat(row[8]) if row[8] else datetime.now(),
                duration_ms=row[9] or 0.0
            ))
        return runs

    # -------------------------------------------------------------------------
    # FIRM OPERATIONS
    # -------------------------------------------------------------------------

    def create_firm(self, name: str, **kwargs) -> Firm:
        """Create a new firm"""
        firm = Firm(
            id=str(uuid.uuid4()),
            name=name,
            domain=kwargs.get("domain"),
            settings=kwargs.get("settings", {}),
            metadata=kwargs.get("metadata", {})
        )

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO firms (id, name, domain, settings, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            firm.id, firm.name, firm.domain,
            json.dumps(firm.settings), firm.created_at.isoformat(),
            json.dumps(firm.metadata)
        ))
        conn.commit()
        conn.close()

        return firm

    def get_firm(self, firm_id: str) -> Optional[Firm]:
        """Get firm by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, domain, settings, created_at, metadata
            FROM firms WHERE id = ?
        """, (firm_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return Firm(
            id=row[0], name=row[1], domain=row[2],
            settings=json.loads(row[3] or "{}"),
            created_at=datetime.fromisoformat(row[4]) if row[4] else datetime.now(),
            metadata=json.loads(row[5] or "{}")
        )

    def list_firms(self) -> List[Firm]:
        """List all firms"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM firms ORDER BY name")
        rows = cursor.fetchall()
        conn.close()

        return [self.get_firm(row[0]) for row in rows]

    # -------------------------------------------------------------------------
    # USER OPERATIONS
    # -------------------------------------------------------------------------

    def create_user(self, firm_id: str, email: str, name: str, **kwargs) -> User:
        """Create a new user"""
        user = User(
            id=str(uuid.uuid4()),
            firm_id=firm_id,
            email=email,
            name=name,
            system_role=kwargs.get("system_role", SystemRole.MEMBER),
            professional_role=kwargs.get("professional_role"),
            is_active=kwargs.get("is_active", True),
            metadata=kwargs.get("metadata", {})
        )

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (id, firm_id, email, name, system_role, professional_role,
                             is_active, created_at, last_login, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user.id, user.firm_id, user.email, user.name,
            user.system_role.value, user.professional_role,
            1 if user.is_active else 0, user.created_at.isoformat(),
            None, json.dumps(user.metadata)
        ))
        conn.commit()
        conn.close()

        return user

    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, firm_id, email, name, system_role, professional_role,
                   is_active, created_at, last_login, metadata
            FROM users WHERE id = ?
        """, (user_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return User(
            id=row[0], firm_id=row[1], email=row[2], name=row[3],
            system_role=SystemRole(row[4]) if row[4] else SystemRole.MEMBER,
            professional_role=row[5],
            is_active=bool(row[6]),
            created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(),
            last_login=datetime.fromisoformat(row[8]) if row[8] else None,
            metadata=json.loads(row[9] or "{}")
        )

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None
        return self.get_user(row[0])

    def list_users_by_firm(self, firm_id: str, active_only: bool = True) -> List[User]:
        """List all users in a firm"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if active_only:
            cursor.execute(
                "SELECT id FROM users WHERE firm_id = ? AND is_active = 1 ORDER BY name",
                (firm_id,)
            )
        else:
            cursor.execute(
                "SELECT id FROM users WHERE firm_id = ? ORDER BY name",
                (firm_id,)
            )
        rows = cursor.fetchall()
        conn.close()

        return [self.get_user(row[0]) for row in rows]

    def update_user_last_login(self, user_id: str):
        """Update user's last login timestamp"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.now().isoformat(), user_id)
        )
        conn.commit()
        conn.close()

    # -------------------------------------------------------------------------
    # TEAM OPERATIONS
    # -------------------------------------------------------------------------

    def create_team(self, firm_id: str, name: str, **kwargs) -> Team:
        """Create a new team"""
        team = Team(
            id=str(uuid.uuid4()),
            firm_id=firm_id,
            name=name,
            description=kwargs.get("description"),
            created_by_user_id=kwargs.get("created_by_user_id"),
            metadata=kwargs.get("metadata", {})
        )

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO teams (id, firm_id, name, description, created_at, created_by_user_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            team.id, team.firm_id, team.name, team.description,
            team.created_at.isoformat(), team.created_by_user_id,
            json.dumps(team.metadata)
        ))
        conn.commit()
        conn.close()

        return team

    def get_team(self, team_id: str) -> Optional[Team]:
        """Get team by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, firm_id, name, description, created_at, created_by_user_id, metadata
            FROM teams WHERE id = ?
        """, (team_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return Team(
            id=row[0], firm_id=row[1], name=row[2], description=row[3],
            created_at=datetime.fromisoformat(row[4]) if row[4] else datetime.now(),
            created_by_user_id=row[5],
            metadata=json.loads(row[6] or "{}")
        )

    def list_teams_by_firm(self, firm_id: str) -> List[Team]:
        """List all teams in a firm"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM teams WHERE firm_id = ? ORDER BY name",
            (firm_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        return [self.get_team(row[0]) for row in rows]

    # -------------------------------------------------------------------------
    # TEAM MEMBER OPERATIONS
    # -------------------------------------------------------------------------

    def add_team_member(
        self, team_id: str, user_id: str,
        team_role: TeamRole = TeamRole.TEAM_MEMBER,
        added_by_user_id: Optional[str] = None
    ) -> TeamMember:
        """Add user to team"""
        member = TeamMember(
            team_id=team_id,
            user_id=user_id,
            team_role=team_role,
            added_by_user_id=added_by_user_id
        )

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO team_members (team_id, user_id, team_role, added_at, added_by_user_id)
            VALUES (?, ?, ?, ?, ?)
        """, (
            member.team_id, member.user_id, member.team_role.value,
            member.added_at.isoformat(), member.added_by_user_id
        ))
        conn.commit()
        conn.close()

        return member

    def remove_team_member(self, team_id: str, user_id: str):
        """Remove user from team"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, user_id)
        )
        conn.commit()
        conn.close()

    def get_team_members(self, team_id: str) -> List[TeamMember]:
        """Get all members of a team"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT team_id, user_id, team_role, added_at, added_by_user_id
            FROM team_members WHERE team_id = ?
        """, (team_id,))
        rows = cursor.fetchall()
        conn.close()

        return [
            TeamMember(
                team_id=row[0], user_id=row[1],
                team_role=TeamRole(row[2]) if row[2] else TeamRole.TEAM_MEMBER,
                added_at=datetime.fromisoformat(row[3]) if row[3] else datetime.now(),
                added_by_user_id=row[4]
            )
            for row in rows
        ]

    def get_user_teams(self, user_id: str) -> List[Team]:
        """Get all teams a user belongs to"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT team_id FROM team_members WHERE user_id = ?",
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        return [self.get_team(row[0]) for row in rows if self.get_team(row[0])]

    def get_user_team_role(self, team_id: str, user_id: str) -> Optional[TeamRole]:
        """Get user's role in a specific team"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT team_role FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, user_id)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None
        return TeamRole(row[0]) if row[0] else TeamRole.TEAM_MEMBER

    # -------------------------------------------------------------------------
    # ADMIN SCOPE OPERATIONS
    # -------------------------------------------------------------------------

    def set_admin_team_scope(
        self, admin_user_id: str, team_id: str,
        granted_by_user_id: Optional[str] = None
    ) -> AdminTeamScope:
        """Grant admin scope over a team"""
        scope = AdminTeamScope(
            admin_user_id=admin_user_id,
            team_id=team_id,
            granted_by_user_id=granted_by_user_id
        )

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO admin_team_scope
            (admin_user_id, team_id, granted_at, granted_by_user_id)
            VALUES (?, ?, ?, ?)
        """, (
            scope.admin_user_id, scope.team_id,
            scope.granted_at.isoformat(), scope.granted_by_user_id
        ))
        conn.commit()
        conn.close()

        return scope

    def remove_admin_team_scope(self, admin_user_id: str, team_id: str):
        """Remove admin scope over a team"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM admin_team_scope WHERE admin_user_id = ? AND team_id = ?",
            (admin_user_id, team_id)
        )
        conn.commit()
        conn.close()

    def get_admin_team_scope(self, admin_user_id: str) -> List[str]:
        """Get list of team IDs an admin can manage"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT team_id FROM admin_team_scope WHERE admin_user_id = ?",
            (admin_user_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        return [row[0] for row in rows]

    # -------------------------------------------------------------------------
    # CASE-TEAM OPERATIONS
    # -------------------------------------------------------------------------

    def assign_case_to_team(
        self, case_id: str, team_id: str,
        assigned_by_user_id: Optional[str] = None
    ) -> CaseTeam:
        """Assign case to a team"""
        ct = CaseTeam(
            case_id=case_id,
            team_id=team_id,
            assigned_by_user_id=assigned_by_user_id
        )

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO case_teams (case_id, team_id, assigned_at, assigned_by_user_id)
            VALUES (?, ?, ?, ?)
        """, (ct.case_id, ct.team_id, ct.assigned_at.isoformat(), ct.assigned_by_user_id))
        conn.commit()
        conn.close()

        return ct

    def unassign_case_from_team(self, case_id: str, team_id: str):
        """Remove case from team"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM case_teams WHERE case_id = ? AND team_id = ?",
            (case_id, team_id)
        )
        conn.commit()
        conn.close()

    def get_case_teams(self, case_id: str) -> List[Team]:
        """Get all teams assigned to a case"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT team_id FROM case_teams WHERE case_id = ?", (case_id,))
        rows = cursor.fetchall()
        conn.close()

        return [self.get_team(row[0]) for row in rows if self.get_team(row[0])]

    def get_team_cases(self, team_id: str) -> List[str]:
        """Get all case IDs assigned to a team"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT case_id FROM case_teams WHERE team_id = ?", (team_id,))
        rows = cursor.fetchall()
        conn.close()

        return [row[0] for row in rows]

    # -------------------------------------------------------------------------
    # CASE PARTICIPANT OPERATIONS
    # -------------------------------------------------------------------------

    def add_case_participant(
        self, case_id: str, user_id: str,
        role: Optional[str] = None,
        added_by_user_id: Optional[str] = None
    ) -> CaseParticipant:
        """Add user as participant to a case"""
        cp = CaseParticipant(
            case_id=case_id,
            user_id=user_id,
            role=role,
            added_by_user_id=added_by_user_id
        )

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO case_participants
            (case_id, user_id, role, added_at, added_by_user_id)
            VALUES (?, ?, ?, ?, ?)
        """, (cp.case_id, cp.user_id, cp.role, cp.added_at.isoformat(), cp.added_by_user_id))
        conn.commit()
        conn.close()

        return cp

    def remove_case_participant(self, case_id: str, user_id: str):
        """Remove user from case participants"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM case_participants WHERE case_id = ? AND user_id = ?",
            (case_id, user_id)
        )
        conn.commit()
        conn.close()

    def get_case_participants(self, case_id: str) -> List[CaseParticipant]:
        """Get all participants of a case"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT case_id, user_id, role, added_at, added_by_user_id
            FROM case_participants WHERE case_id = ?
        """, (case_id,))
        rows = cursor.fetchall()
        conn.close()

        return [
            CaseParticipant(
                case_id=row[0], user_id=row[1], role=row[2],
                added_at=datetime.fromisoformat(row[3]) if row[3] else datetime.now(),
                added_by_user_id=row[4]
            )
            for row in rows
        ]

    def get_user_cases(self, user_id: str) -> List[str]:
        """Get all case IDs a user participates in (directly)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT case_id FROM case_participants WHERE user_id = ?",
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        return [row[0] for row in rows]

    # -------------------------------------------------------------------------
    # FIRM-SCOPED CASE QUERIES
    # -------------------------------------------------------------------------

    def list_cases_by_firm(self, firm_id: str, status: Optional[CaseStatus] = None) -> List[Case]:
        """List all cases for a firm, optionally filtered by status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if status:
            cursor.execute(
                "SELECT id FROM cases WHERE firm_id = ? AND status = ? ORDER BY updated_at DESC",
                (firm_id, status.value)
            )
        else:
            cursor.execute(
                "SELECT id FROM cases WHERE firm_id = ? ORDER BY updated_at DESC",
                (firm_id,)
            )
        rows = cursor.fetchall()
        conn.close()

        return [self.get_case(row[0]) for row in rows if self.get_case(row[0])]

    def update_case_firm(self, case_id: str, firm_id: str):
        """Update case's firm assignment"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cases SET firm_id = ?, updated_at = ? WHERE id = ?",
            (firm_id, datetime.now().isoformat(), case_id)
        )
        conn.commit()
        conn.close()

    def update_case_status(self, case_id: str, status: CaseStatus):
        """Update case status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cases SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, datetime.now().isoformat(), case_id)
        )
        conn.commit()
        conn.close()

    def update_case_responsible_user(self, case_id: str, user_id: Optional[str]):
        """Update case's responsible user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cases SET responsible_user_id = ?, updated_at = ? WHERE id = ?",
            (user_id, datetime.now().isoformat(), case_id)
        )
        conn.commit()
        conn.close()


# =============================================================================
# SINGLETON
# =============================================================================

_db: Optional[CaseDatabase] = None

def get_database(db_path: str = "cases.db") -> CaseDatabase:
    """Get singleton database instance"""
    global _db
    if _db is None:
        _db = CaseDatabase(db_path)
    return _db
