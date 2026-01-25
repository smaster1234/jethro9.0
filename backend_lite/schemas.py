"""
Pydantic Schemas for Contradiction Service
==========================================

Stable, minimal schemas for input/output.
All outputs are guaranteed valid JSON.

Taxonomy Tiers:
- Tier 1 (MVP): Temporal, Quantitative, Actor, Presence, DocumentExistence, Identity
- Tier 2 (Next): TimelineSequence, Location, CommunicationChannel, PartyPosition, Version
- Tier 3 (Advanced): MultiDocInference, Aggregation, DefinitionScope
- Tier 4 (Experimental): Reserved for credibility/legal analysis

Note: AttackAngles are separate from Contradictions. Contradictions are factual/logical
conflicts between statements. AttackAngles are legal/credibility attack vectors.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


# =============================================================================
# ENUMS - Contradiction Types (Tiered Taxonomy)
# =============================================================================

class ContradictionType(str, Enum):
    """
    Contradiction types by tier.

    Tier 1 (MVP - deterministic verification):
    - TEMPORAL_DATE: Different dates for same event
    - QUANT_AMOUNT: Different amounts/quantities
    - ACTOR_ATTRIBUTION: Different person did action
    - PRESENCE_PARTICIPATION: Was/wasn't present or did/didn't act
    - DOCUMENT_EXISTENCE: Document exists/doesn't exist
    - IDENTITY_BASIC: Basic identity conflicts (ID numbers, names)

    Tier 2 (Next phase - rules + verifier):
    - TIMELINE_SEQUENCE: Order of events conflicts
    - LOCATION: Different locations for same event
    - COMMUNICATION_CHANNEL: Different communication method
    - PARTY_POSITION: Position/stance changed
    - VERSION: Story changed between versions

    Tier 3+ reserved for future.
    """
    # Tier 1 - MVP Core
    TEMPORAL_DATE = "temporal_date_conflict"
    QUANT_AMOUNT = "quant_amount_conflict"
    ACTOR_ATTRIBUTION = "actor_attribution_conflict"
    PRESENCE_PARTICIPATION = "presence_participation_conflict"
    DOCUMENT_EXISTENCE = "document_existence_conflict"
    IDENTITY_BASIC = "identity_basic_conflict"

    # Tier 2 - Next Phase
    TIMELINE_SEQUENCE = "timeline_sequence_conflict"
    LOCATION = "location_conflict"
    COMMUNICATION_CHANNEL = "communication_channel_conflict"
    PARTY_POSITION = "party_position_conflict"
    VERSION = "version_conflict"

    # Legacy (for backwards compatibility)
    TEMPORAL = "temporal_conflict"
    QUANTITATIVE = "quantitative_conflict"
    ATTRIBUTION = "attribution_conflict"
    FACTUAL = "factual_conflict"
    WITNESS = "witness_conflict"
    DOCUMENT = "document_conflict"


class ContradictionSubtype(str, Enum):
    """
    Subtypes for more granular classification.
    """
    # Temporal subtypes
    EXACT_DATE = "exact_date"
    MONTH_ONLY = "month_only"
    RANGE_OVERLAP = "range_overlap"
    RELATIVE_DATE = "relative_date"

    # Quantitative subtypes
    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    COUNT = "count"
    DURATION = "duration"

    # Actor attribution subtypes
    SENDER = "sender"
    DECISION_MAKER = "decision_maker"
    SIGNER = "signer"
    PAYER = "payer"
    RECEIVER = "receiver"

    # Presence subtypes
    ATTENDED = "attended"
    SIGNED = "signed"
    PAID = "paid"
    DELIVERED = "delivered"
    RECEIVED = "received"

    # Document existence subtypes
    CONTRACT_EXISTS = "contract_exists"
    NOTICE_SENT = "notice_sent"
    EMAIL_EXISTS = "email_exists"
    SIGNATURE_EXISTS = "signature_exists"

    # General
    OTHER = "other"


class ContradictionStatus(str, Enum):
    """
    Verification status of contradiction.

    - VERIFIED: Deterministically confirmed (normalized values don't match)
    - LIKELY: High confidence from verifier/NLI
    - SUSPICIOUS: Candidate from rules, needs review
    """
    VERIFIED = "verified"
    LIKELY = "likely"
    SUSPICIOUS = "suspicious"


class ContradictionCategory(str, Enum):
    """
    Category that distinguishes hard contradictions from narrative ambiguity.

    - HARD_CONTRADICTION: Clear factual contradiction - both claims cannot be true together.
      Same object, same aspect, same timeframe, no reasonable reconciliation.
    - LOGICAL_INCONSISTENCY: Logically incompatible statements about the same situation.
      Not necessarily direct contradiction, but cannot coexist.
    - NARRATIVE_AMBIGUITY: Apparent discrepancy that may have a reasonable explanation.
      Different aspects, different timeframes, or possible reconciliation exists.
    - RHETORICAL_SHIFT: Change in emphasis or framing without factual contradiction.
      Same facts presented differently, may affect credibility but not factual truth.
    """
    HARD_CONTRADICTION = "hard_contradiction"  # סתירה מוכרחת
    LOGICAL_INCONSISTENCY = "logical_inconsistency"  # אי-עקביות לוגית
    NARRATIVE_AMBIGUITY = "narrative_ambiguity"  # עמימות נרטיבית
    RHETORICAL_SHIFT = "rhetorical_shift"  # שינוי רטורי


class AmbiguityExplanation(BaseModel):
    """
    Explanation for narrative ambiguity findings.

    Provides structured explanation of why something is ambiguity rather than
    hard contradiction, and why it's still litigatively important.
    """
    gap_description: str = Field(..., description="מה הפער הנראה בין הטענות")
    why_not_contradiction: str = Field(..., description="למה זה לא סתירה מוכרחת")
    litigation_importance: str = Field(..., description="למה זה עדיין חשוב ליטיגציה")
    possible_reconciliations: List[str] = Field(
        default_factory=list,
        description="פרשנויות אפשריות שמיישבות את הפער"
    )


class Severity(str, Enum):
    """
    Contradiction severity levels (1-4 scale).

    - CRITICAL (4): Fundamental contradiction that destroys credibility
    - HIGH (3): Significant contradiction on material fact
    - MEDIUM (2): Notable inconsistency worth exploring
    - LOW (1): Minor discrepancy, may be innocent
    """
    CRITICAL = "critical"  # Level 4
    HIGH = "high"          # Level 3
    MEDIUM = "medium"      # Level 2
    LOW = "low"            # Level 1


class LLMMode(str, Enum):
    """LLM usage mode"""
    NONE = "none"           # Rule-based only
    OPENROUTER = "openrouter"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"   # DeepSeek API (primary analyzer)


# =============================================================================
# ENUMS - Attack Angles (Future - NOT in MVP)
# =============================================================================

class AttackAngleType(str, Enum):
    """
    Attack angle types (for future implementation).
    These are NOT contradictions - they are legal/credibility attack vectors.

    DO NOT implement in MVP. Reserved for future expansion.
    """
    SHIFTING_VERSION = "shifting_version"      # Story changed
    LATE_DISCLOSURE = "late_disclosure"        # Delayed testimony
    EVASIVE_LANGUAGE = "evasive_language"      # "As far as I know", "I believe"
    HEARSAY_MARKERS = "hearsay_markers"        # Second-hand testimony
    MISSING_SUPPORT = "missing_support"        # Claim without evidence
    OVERBROAD_CLAIM = "overbroad_claim"        # "Always", "Never"
    INTERNAL_INCOHERENCE = "internal_incoherence"  # Logic gaps


# =============================================================================
# INPUT SCHEMAS
# =============================================================================

class EvidenceAnchor(BaseModel):
    """
    Evidence anchor with precise location and snippet.

    This is the canonical schema for evidence anchoring across the system.
    """
    doc_id: str = Field(..., description="Document ID")
    page_no: Optional[int] = Field(None, description="Page number (if available)")
    block_index: Optional[int] = Field(None, description="Block/paragraph index within document")
    paragraph_index: Optional[int] = Field(None, description="Paragraph index (if available)")
    char_start: Optional[int] = Field(None, description="Character start offset in normalized text")
    char_end: Optional[int] = Field(None, description="Character end offset in normalized text")
    snippet: Optional[str] = Field(None, description="Snippet text around the anchor")
    bbox: Optional[Dict[str, float]] = Field(None, description="Bounding box (future OCR)")


class ClaimInput(BaseModel):
    """Single claim for analysis"""
    id: str = Field(..., description="Unique claim identifier")
    text: str = Field(..., description="Claim text in Hebrew")
    source: Optional[str] = Field(None, description="Source document name")
    doc_id: Optional[str] = Field(None, description="Document ID for locator")
    page: Optional[int] = Field(None, description="Page number")
    block_index: Optional[int] = Field(None, description="Block/paragraph index")
    paragraph: Optional[int] = Field(None, description="Paragraph number")
    char_start: Optional[int] = Field(None, description="Character start offset")
    char_end: Optional[int] = Field(None, description="Character end offset")
    speaker: Optional[str] = Field(None, description="Who made this claim")
    anchor: Optional[EvidenceAnchor] = Field(None, description="Optional evidence anchor")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "claim_1",
                "text": "החוזה נחתם ביום 15.3.2020",
                "source": "תצהיר תובע",
                "doc_id": "doc_123",
                "page": 3,
                "paragraph": 5,
                "speaker": "יוסי כהן"
            }
        }


class AnalyzeTextRequest(BaseModel):
    """Request to analyze free text"""
    text: str = Field(..., description="Free text to analyze (Hebrew)")
    source_name: Optional[str] = Field("document", description="Name of the source document")
    doc_id: Optional[str] = Field(None, description="Document ID for locators")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "ביום 15.3.2020 נחתם החוזה...",
                "source_name": "כתב תביעה",
                "doc_id": "doc_001"
            }
        }


class AnalyzeClaimsRequest(BaseModel):
    """Request to analyze pre-extracted claims"""
    claims: List[ClaimInput] = Field(..., description="List of claims to analyze")

    class Config:
        json_schema_extra = {
            "example": {
                "claims": [
                    {"id": "1", "text": "החוזה נחתם ב-15.3.2020", "source": "תצהיר"},
                    {"id": "2", "text": "החוזה נחתם ב-20.5.2021", "source": "עדות"}
                ]
            }
        }


# =============================================================================
# INPUT SCHEMAS - Case Management
# =============================================================================

class CreateCaseRequest(BaseModel):
    """Request to create a new case"""
    name: str = Field(..., description="Case name")
    client_name: Optional[str] = Field(None, description="Client name")
    our_side: Optional[str] = Field("unknown", description="plaintiff/defendant/third_party/unknown")
    opponent_name: Optional[str] = Field(None, description="Opponent name")
    court: Optional[str] = Field(None, description="Court name")
    case_number: Optional[str] = Field(None, description="Official case number")
    description: Optional[str] = Field(None, description="Case description")
    organization_id: Optional[str] = Field(None, description="Organization ID")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "כהן נ' לוי",
                "client_name": "ישראל כהן",
                "our_side": "plaintiff",
                "opponent_name": "דוד לוי",
                "court": "שלום תל אביב",
                "case_number": "12345-01-24",
                "description": "תביעה בגין הפרת חוזה",
                "organization_id": "org_123"
            }
        }


class AddDocumentRequest(BaseModel):
    """Request to add a document to a case"""
    name: str = Field(..., description="Document name")
    doc_type: str = Field("other", description="Document type: complaint/defense/motion/affidavit/etc.")
    party: str = Field("unknown", description="Which party: ours/theirs/court/third_party/unknown")
    role: Optional[str] = Field(None, description="Role in case: e.g., 'plaintiff_affidavit', 'defense_exhibit'")
    version: Optional[str] = Field("v1", description="Document version")
    author: Optional[str] = Field(None, description="Document author")
    extracted_text: str = Field(..., description="Full text content of the document")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "כתב תביעה",
                "doc_type": "complaint",
                "party": "theirs",
                "role": "defendant_main_claim",
                "version": "v1",
                "author": "עו\"ד כהן",
                "extracted_text": "1. התובע הגיש תביעה זו..."
            }
        }


class AnalyzeCaseRequest(BaseModel):
    """Request to analyze a case"""
    document_ids: Optional[List[str]] = Field(None, description="Specific doc IDs to analyze (all if None)")
    force: bool = Field(False, description="Force re-analysis, bypass cache")
    sensitivity_mode: Optional[str] = Field("normal", description="normal/strict/lenient")
    rag_top_k: Optional[int] = Field(None, description="Top K paragraphs for retrieval (default from config)")

    class Config:
        json_schema_extra = {
            "example": {
                "document_ids": ["doc_1", "doc_2"],
                "force": False,
                "sensitivity_mode": "normal",
                "rag_top_k": 8
            }
        }


# =============================================================================
# INPUT/OUTPUT SCHEMAS - Organizations (B1)
# =============================================================================

class OrganizationCreateRequest(BaseModel):
    name: str = Field(..., description="Organization name")


class OrganizationMemberAddRequest(BaseModel):
    user_id: str = Field(..., description="Existing user ID")
    role: str = Field("viewer", description="viewer/intern/lawyer/owner")


class OrganizationInviteCreateRequest(BaseModel):
    email: str = Field(..., description="Invitee email")
    role: str = Field("viewer", description="viewer/intern/lawyer/owner")
    expires_in_days: int = Field(7, ge=1, le=60, description="Invite expiry in days")


class OrganizationResponse(BaseModel):
    id: str
    firm_id: str
    name: str
    created_at: Optional[datetime] = None


class OrganizationMemberResponse(BaseModel):
    user_id: str
    email: str
    name: str
    role: str
    added_at: Optional[datetime] = None


class OrganizationInviteResponse(BaseModel):
    id: str
    organization_id: str
    email: str
    role: str
    status: str
    expires_at: datetime
    token: Optional[str] = None
    created_at: Optional[datetime] = None


class OrganizationInviteAcceptResponse(BaseModel):
    organization_id: str
    role: str
    status: str


class UserSearchResponse(BaseModel):
    id: str
    email: str
    name: str


# =============================================================================
# INPUT/OUTPUT SCHEMAS - Training (C1)
# =============================================================================

class TrainingStartRequest(BaseModel):
    plan_id: str = Field(..., description="Cross-exam plan ID")
    witness_id: Optional[str] = Field(None, description="Witness ID")
    persona: Optional[str] = Field("cooperative", description="Persona: cooperative/evasive/hostile")


class TrainingSessionResponse(BaseModel):
    session_id: str
    case_id: str
    plan_id: str
    witness_id: Optional[str] = None
    persona: Optional[str] = None
    status: str
    back_remaining: int
    created_at: Optional[datetime] = None


class TrainingTurnRequest(BaseModel):
    step_id: str = Field(..., description="Plan step ID")
    chosen_branch: Optional[str] = Field(None, description="Chosen branch trigger")


class TrainingTurnResponse(BaseModel):
    turn_id: str
    session_id: str
    step_id: str
    stage: Optional[str] = None
    question: str
    witness_reply: Optional[str] = None
    chosen_branch: Optional[str] = None
    follow_up_questions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class TrainingBackResponse(BaseModel):
    session_id: str
    back_remaining: int
    removed_turn_id: Optional[str] = None


class TrainingFinishResponse(BaseModel):
    session_id: str
    summary: Dict[str, Any]


# =============================================================================
# OUTPUT SCHEMAS - Entity Usage (C2)
# =============================================================================

class EntityUsageSummary(BaseModel):
    entity_type: str
    entity_id: str
    usage: Dict[str, str]
    latest_used_at: Optional[str] = None


# =============================================================================
# INPUT SCHEMAS - Witnesses
# =============================================================================

class WitnessCreateRequest(BaseModel):
    """Create witness request"""
    name: str = Field(..., description="Witness name")
    side: Optional[str] = Field(None, description="ours/theirs/unknown")
    extra_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


class WitnessVersionCreateRequest(BaseModel):
    """Create witness version request"""
    document_id: str = Field(..., description="Document ID for this version")
    version_type: Optional[str] = Field(None, description="statement/affidavit/testimony/etc")
    version_date: Optional[datetime] = Field(None, description="Date of version")
    extra_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


# =============================================================================
# OUTPUT SCHEMAS - Locators
# =============================================================================
class Locator(BaseModel):
    """Location reference for evidence"""
    doc_id: Optional[str] = Field(None, description="Document ID")
    page: Optional[int] = Field(None, description="Page number")
    block_index: Optional[int] = Field(None, description="Block/paragraph index within document")
    paragraph: Optional[int] = Field(None, description="Paragraph number")
    char_start: Optional[int] = Field(None, description="Character start offset")
    char_end: Optional[int] = Field(None, description="Character end offset")


class ClaimEvidence(BaseModel):
    """Evidence for one side of a contradiction"""
    claim_id: str = Field(..., description="Claim ID")
    doc_id: Optional[str] = Field(None, description="Document ID")
    locator: Optional[Locator] = Field(None, description="Location in document")
    anchor: Optional[EvidenceAnchor] = Field(None, description="Evidence anchor (preferred)")
    quote: str = Field(..., description="Relevant quote")
    normalized: Optional[str] = Field(None, description="Normalized value (date, amount, etc.)")


class TextSpan(BaseModel):
    """Location within text (legacy)"""
    start: int = Field(..., description="Start character position")
    end: int = Field(..., description="End character position")


# =============================================================================
# OUTPUT SCHEMAS - Claims Table
# =============================================================================

class ClaimStatus(str, Enum):
    """Status of a claim based on contradiction analysis"""
    NO_ISSUES = "no_issues"
    POTENTIAL_CONTRADICTION = "potential_contradiction"
    VERIFIED_CONTRADICTION = "verified_contradiction"
    NEEDS_REVIEW = "needs_review"


class ClaimFeatures(BaseModel):
    """Extracted features from a claim"""
    dates: List[str] = Field(default_factory=list, description="Extracted dates")
    amounts: List[str] = Field(default_factory=list, description="Extracted amounts")
    case_numbers: List[str] = Field(default_factory=list, description="Extracted case numbers")
    entities: List[str] = Field(default_factory=list, description="Extracted entities")


class ClaimOutput(BaseModel):
    """
    Output schema for a single claim in the claims table.

    Provides full audit trail with locator information and party attribution.
    """
    id: str = Field(..., description="Unique claim ID")
    text: str = Field(..., description="Claim text")
    doc_id: Optional[str] = Field(None, description="Document ID")
    doc_name: Optional[str] = Field(None, description="Document name")
    party: Optional[str] = Field(None, description="Which party: ours/theirs/court/third_party/unknown")
    role: Optional[str] = Field(None, description="Document role in case")
    author: Optional[str] = Field(None, description="Document author")
    witness_version_id: Optional[str] = Field(None, description="Linked witness version ID")
    locator: Optional[Locator] = Field(None, description="Location in document")
    anchor: Optional[EvidenceAnchor] = Field(None, description="Evidence anchor (preferred)")
    features: Optional[ClaimFeatures] = Field(None, description="Extracted features")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "claim_1",
                "text": "החוזה נחתם ביום 15.3.2020",
                "doc_id": "doc_001",
                "doc_name": "תצהיר תובע",
                "party": "ours",
                "role": "plaintiff_affidavit",
                "author": "ישראל כהן",
                "locator": {"paragraph": 5, "char_start": 100, "char_end": 130},
                "features": {"dates": ["2020-03-15"], "amounts": []}
            }
        }


class ClaimResult(BaseModel):
    """
    Computed result for a claim based on contradiction analysis.

    Provides summary status for the claims table display.
    """
    claim_id: str = Field(..., description="Reference to claim ID")
    status: ClaimStatus = Field(..., description="Computed status based on contradictions")
    contradiction_count: int = Field(0, description="Number of contradictions involving this claim")
    max_severity: Optional[Severity] = Field(None, description="Highest severity of related contradictions")
    types: List[ContradictionType] = Field(default_factory=list, description="Types of related contradictions")
    top_contradiction_ids: List[str] = Field(
        default_factory=list,
        max_length=3,
        description="Top 3 most severe contradiction IDs"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "claim_id": "claim_1",
                "status": "verified_contradiction",
                "contradiction_count": 2,
                "max_severity": "high",
                "types": ["temporal_date_conflict", "quant_amount_conflict"],
                "top_contradiction_ids": ["contr_001", "contr_002"]
            }
        }


# =============================================================================
# OUTPUT SCHEMAS - Contradiction Bucketing (Attribution Layer)
# =============================================================================

class ContradictionBucket(str, Enum):
    """
    Bucket for contradiction based on party attribution.

    - internal_contradiction: Both claims from same party (ours or theirs)
    - dispute: Cross-party conflict (ours vs theirs)
    - needs_classification: Unknown party attribution
    """
    INTERNAL_CONTRADICTION = "internal_contradiction"  # סתירה פנימית
    DISPUTE = "dispute"  # פלוגתא / מחלוקת
    NEEDS_CLASSIFICATION = "needs_classification"  # דורש סיווג


class ContradictionRelation(str, Enum):
    """
    Relation type between claims in a contradiction.

    - internal: Same party, same or different documents
    - cross_party: Different parties
    - cross_doc: Same party, different documents (within internal)
    """
    INTERNAL = "internal"  # פנימי
    CROSS_PARTY = "cross_party"  # בין צדדים
    CROSS_DOC = "cross_doc"  # בין מסמכים


# =============================================================================
# OUTPUT SCHEMAS - Contradictions
# =============================================================================

class ContradictionOutput(BaseModel):
    """
    Single detected contradiction.

    A contradiction is a factual/logical conflict between two claims
    about the same event, person, or subject matter.
    """
    id: str = Field(..., description="Unique contradiction ID")

    # Type classification
    type: ContradictionType = Field(..., description="Type of contradiction")
    subtype: Optional[ContradictionSubtype] = Field(None, description="More specific subtype")

    # Verification status
    status: ContradictionStatus = Field(
        default=ContradictionStatus.SUSPICIOUS,
        description="Verification status: verified/likely/suspicious"
    )

    # Scoring
    severity: Severity = Field(..., description="Severity level (1-4)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence")
    same_event_confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Confidence that claims refer to same event"
    )

    # Evidence (dual-sided)
    claim1: ClaimEvidence = Field(..., description="Evidence from first claim")
    claim2: ClaimEvidence = Field(..., description="Evidence from second claim")

    # Legacy fields (for backwards compatibility)
    claim1_id: Optional[str] = Field(None, description="First claim ID (legacy)")
    claim2_id: Optional[str] = Field(None, description="Second claim ID (legacy)")
    quote1: Optional[str] = Field(None, description="Quote from claim 1 (legacy)")
    quote2: Optional[str] = Field(None, description="Quote from claim 2 (legacy)")
    span1: Optional[TextSpan] = Field(None, description="Location in claim 1 (legacy)")
    span2: Optional[TextSpan] = Field(None, description="Location in claim 2 (legacy)")

    # Explanation
    explanation: str = Field(..., description="Explanation in Hebrew (1-3 sentences)")

    # Category (hard contradiction vs narrative ambiguity)
    category: Optional[ContradictionCategory] = Field(
        None,
        description="Category: hard_contradiction/logical_inconsistency/narrative_ambiguity/rhetorical_shift"
    )
    ambiguity_explanation: Optional[AmbiguityExplanation] = Field(
        None,
        description="Structured explanation for narrative_ambiguity findings"
    )

    # UI display helpers
    category_badge: Optional[str] = Field(
        None,
        description="UI badge: 🔴 סתירה מוכרחת / 🟠 אי-עקביות / 🟡 עמימות נרטיבית"
    )
    category_label_short: Optional[str] = Field(
        None,
        description="Short label for UI: סתירה / אי-עקביות / עמימות"
    )

    # Attribution Layer (party-based bucketing)
    bucket: Optional[ContradictionBucket] = Field(
        None,
        description="Bucket: internal_contradiction/dispute/needs_classification"
    )
    relation: Optional[ContradictionRelation] = Field(
        None,
        description="Relation type: internal/cross_party/cross_doc"
    )
    claim1_party: Optional[str] = Field(None, description="Party of claim 1: ours/theirs/court/etc")
    claim2_party: Optional[str] = Field(None, description="Party of claim 2: ours/theirs/court/etc")
    issue_id: Optional[str] = Field(None, description="Issue ID for grouped disputes")

    # Optional metadata
    tags: List[str] = Field(default_factory=list, description="Optional tags")

    # "Only What I Can Use" computed flag
    usable: bool = Field(
        default=False,
        description="Computed flag: True when status is verified/likely, has locators, and quotes"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "contr_001",
                "type": "temporal_date_conflict",
                "subtype": "exact_date",
                "status": "verified",
                "severity": "high",
                "confidence": 0.95,
                "same_event_confidence": 0.9,
                "bucket": "internal_contradiction",
                "relation": "internal",
                "claim1_party": "theirs",
                "claim2_party": "theirs",
                "claim1": {
                    "claim_id": "claim_1",
                    "doc_id": "doc_001",
                    "quote": "החוזה נחתם ביום 15.3.2020",
                    "normalized": "2020-03-15"
                },
                "claim2": {
                    "claim_id": "claim_2",
                    "doc_id": "doc_002",
                    "quote": "החוזה נחתם ביום 20.5.2021",
                    "normalized": "2021-05-20"
                },
                "explanation": "סתירה בתאריך חתימת החוזה: 15.3.2020 מול 20.5.2021"
            }
        }


# =============================================================================
# OUTPUT SCHEMAS - Cross Examination
# =============================================================================

class CrossExamQuestion(BaseModel):
    """Single cross-examination question"""
    id: str = Field(..., description="Question ID")
    question: str = Field(..., description="The question in Hebrew")
    purpose: str = Field(..., description="Purpose of the question")
    severity: Severity = Field(..., description="Related contradiction severity")
    follow_up: Optional[str] = Field(None, description="Suggested follow-up")


class CrossExamTarget(BaseModel):
    """Target for cross-examination"""
    party: Optional[str] = Field(None, description="Target party name")
    witness: Optional[str] = Field(None, description="Target witness name")


class CrossExamQuestionsOutput(BaseModel):
    """Cross-examination questions for a contradiction"""
    contradiction_id: str = Field(..., description="Related contradiction ID")
    target: Optional[CrossExamTarget] = Field(None, description="Target party/witness")
    target_party: Optional[str] = Field(None, description="Target (legacy)")
    questions: List[CrossExamQuestion] = Field(..., description="3-7 questions")
    goal: Optional[str] = Field(None, description="Overall goal of this question set")

    class Config:
        json_schema_extra = {
            "example": {
                "contradiction_id": "contr_001",
                "target": {"party": "נתבע", "witness": "יוסי כהן"},
                "questions": [
                    {
                        "id": "q_1",
                        "question": "אתה מאשר שהחוזה נחתם ב-15.3.2020?",
                        "purpose": "קיבוע מועד מוקדם",
                        "severity": "high"
                    }
                ],
                "goal": "לחשוף סתירה בתאריך החתימה"
            }
        }


# =============================================================================
# OUTPUT SCHEMAS - Analysis Response
# =============================================================================

class RuleStats(BaseModel):
    """Statistics from rule-based detection"""
    temporal_count: int = Field(0, description="Temporal contradiction count")
    quantitative_count: int = Field(0, description="Quantitative contradiction count")
    attribution_count: int = Field(0, description="Attribution contradiction count")
    presence_count: int = Field(0, description="Presence contradiction count")
    doc_existence_count: int = Field(0, description="Document existence contradiction count")
    identity_count: int = Field(0, description="Identity contradiction count")
    pairs_total: int = Field(0, description="Total claim pairs analyzed")
    pairs_filtered_in: int = Field(0, description="Pairs that passed filtering")
    pairs_filtered_out: int = Field(0, description="Pairs filtered out")


class VerifierStats(BaseModel):
    """Statistics from verifier layer"""
    calls: int = Field(0, description="Number of verifier calls made")
    promoted: int = Field(0, description="Contradictions promoted by verifier")
    rejected: int = Field(0, description="Contradictions rejected by verifier")
    unclear: int = Field(0, description="Contradictions marked unclear by verifier")


class AnalysisMetadata(BaseModel):
    """Metadata about the analysis - unified output contract"""
    # Timing
    duration_ms: float = Field(..., description="Total processing time in ms")
    rule_based_time_ms: Optional[float] = Field(None, description="Rule-based detection time")
    llm_time_ms: Optional[float] = Field(None, description="LLM detection time if used")
    total_time_ms: Optional[float] = Field(None, description="Total processing time (legacy)")

    # Counts
    claims_total: int = Field(..., description="Total number of claims analyzed")
    claims_ok: int = Field(0, description="Claims with no issues")
    claims_with_issues: int = Field(0, description="Claims with potential/verified issues")
    contradictions_total: int = Field(0, description="Total contradictions found")

    # LLM status
    llm_mode: LLMMode = Field(..., description="LLM mode used")
    mode: Optional[LLMMode] = Field(None, description="LLM mode (legacy)")
    model_used: Optional[str] = Field(None, description="LLM model if used")
    llm_parse_ok: bool = Field(True, description="Whether LLM response was parsed successfully")
    llm_empty: bool = Field(False, description="Whether LLM returned empty response")

    # Validation
    validation_flags: List[str] = Field(default_factory=list, description="Validation warnings/flags")

    # Legacy
    claims_count: Optional[int] = Field(None, description="Number of claims (legacy)")

    # Detailed stats
    rule_stats: Optional[RuleStats] = Field(None, description="Rule-based detection stats")
    verifier_stats: Optional[VerifierStats] = Field(None, description="Verifier layer stats")

    # Status breakdown
    contradictions_by_status: Optional[Dict[str, int]] = Field(
        None, description="Count by status"
    )
    tier1_count: Optional[int] = Field(None, description="Tier 1 contradiction count")

    class Config:
        json_schema_extra = {
            "example": {
                "duration_ms": 150.5,
                "claims_total": 12,
                "claims_ok": 10,
                "claims_with_issues": 2,
                "contradictions_total": 1,
                "llm_mode": "openrouter",
                "llm_parse_ok": True,
                "llm_empty": False,
                "validation_flags": [],
                "rule_stats": {
                    "temporal_count": 1,
                    "quantitative_count": 0,
                    "pairs_total": 66,
                    "pairs_filtered_in": 20
                },
                "verifier_stats": {
                    "calls": 3,
                    "promoted": 1,
                    "rejected": 2,
                    "unclear": 0
                }
            }
        }


# =============================================================================
# OUTPUT SCHEMAS - Dispute Issues (Grouped by Topic)
# =============================================================================

class DisputeIssue(BaseModel):
    """
    A grouped dispute issue representing a topic of contention.

    Groups multiple cross-party contradictions that relate to the same subject.
    """
    issue_id: str = Field(..., description="Unique issue ID")
    title: str = Field(..., description="Issue title in Hebrew")
    ours_claims: List[str] = Field(default_factory=list, description="Claim IDs from our side")
    theirs_claims: List[str] = Field(default_factory=list, description="Claim IDs from their side")
    contradiction_ids: List[str] = Field(default_factory=list, description="Related contradiction IDs")
    evidence_refs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Evidence references: [{doc_id, paragraph, quote}]"
    )
    type: Optional[ContradictionType] = Field(None, description="Primary contradiction type")
    severity: Optional[Severity] = Field(None, description="Maximum severity")

    class Config:
        json_schema_extra = {
            "example": {
                "issue_id": "issue_date_contract",
                "title": "מועד חתימת החוזה",
                "ours_claims": ["claim_12", "claim_15"],
                "theirs_claims": ["claim_3", "claim_8"],
                "contradiction_ids": ["contr_001", "contr_005"],
                "evidence_refs": [
                    {"doc_id": "doc_001", "paragraph": 5, "quote": "נחתם ב-15.3.2020"}
                ],
                "type": "temporal_date_conflict",
                "severity": "high"
            }
        }


class AttributionSummary(BaseModel):
    """Summary of attribution layer buckets"""
    internal_theirs: int = Field(0, description="Count of internal contradictions in their documents")
    internal_ours: int = Field(0, description="Count of internal contradictions in our documents")
    disputes: int = Field(0, description="Count of cross-party disputes")
    needs_classification: int = Field(0, description="Count of unclassified (no party)")
    has_party_attribution: bool = Field(False, description="Whether any documents have party set")


class AnalysisResponse(BaseModel):
    """
    Full analysis response with claims table support and attribution layer.

    Now includes:
    - claims: All extracted claims with locators and party attribution
    - claim_results: Computed status for each claim
    - contradictions: Detected contradictions with bucket/relation
    - disputes: Grouped dispute issues (cross-party contradictions)
    - attribution_summary: Summary counts by bucket
    - cross_exam_questions: Questions for cross-examination
    """
    # Claims table data
    claims: List[ClaimOutput] = Field(
        default_factory=list,
        description="All extracted claims with locator info"
    )
    claim_results: List[ClaimResult] = Field(
        default_factory=list,
        description="Computed results for each claim"
    )

    # Existing fields
    contradictions: List[ContradictionOutput] = Field(..., description="Detected contradictions")
    cross_exam_questions: List[CrossExamQuestionsOutput] = Field(..., description="Cross-exam questions")
    metadata: AnalysisMetadata = Field(..., description="Analysis metadata")

    # Attribution Layer additions
    disputes: List[DisputeIssue] = Field(
        default_factory=list,
        description="Grouped dispute issues (cross-party contradictions)"
    )
    attribution_summary: Optional[AttributionSummary] = Field(
        None,
        description="Summary of attribution layer buckets"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "claims": [
                    {"id": "claim_1", "text": "החוזה נחתם ב-15.3.2020", "doc_id": "doc_1", "party": "ours"}
                ],
                "claim_results": [
                    {"claim_id": "claim_1", "status": "no_issues", "contradiction_count": 0}
                ],
                "contradictions": [],
                "cross_exam_questions": [],
                "disputes": [],
                "attribution_summary": {
                    "internal_theirs": 2,
                    "internal_ours": 0,
                    "disputes": 3,
                    "needs_classification": 1,
                    "has_party_attribution": True
                },
                "metadata": {
                    "mode": "none",
                    "rule_based_time_ms": 45.2,
                    "total_time_ms": 45.2,
                    "claims_count": 12,
                    "validation_flags": []
                }
            }
        }


# =============================================================================
# OUTPUT SCHEMAS - Snippet (Show Source)
# =============================================================================

class SnippetResponse(BaseModel):
    """
    Snippet response for "Show me the source" functionality.

    Returns paragraph with optional context (paragraphs before/after).
    """
    doc_id: str = Field(..., description="Document ID")
    doc_name: Optional[str] = Field(None, description="Document name")
    paragraph_index: int = Field(..., description="Target paragraph index")
    text: str = Field(..., description="Main paragraph text")
    context_before: Optional[str] = Field(None, description="Previous paragraph text")
    context_after: Optional[str] = Field(None, description="Next paragraph text")
    highlight_quote: Optional[str] = Field(None, description="Quote to highlight within text")
    char_start: Optional[int] = Field(None, description="Character start position")
    char_end: Optional[int] = Field(None, description="Character end position")


# =============================================================================
# OUTPUT SCHEMAS - Witnesses
# =============================================================================

class WitnessVersionResponse(BaseModel):
    """Witness version response"""
    id: str
    witness_id: str
    document_id: str
    document_name: Optional[str] = None
    version_type: Optional[str] = None
    version_date: Optional[datetime] = None
    extra_data: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class WitnessResponse(BaseModel):
    """Witness response"""
    id: str
    case_id: str
    name: str
    side: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    versions: List[WitnessVersionResponse] = Field(default_factory=list)


class VersionShift(BaseModel):
    """Narrative shift between witness versions"""
    shift_type: str
    description: str
    similarity: Optional[float] = None
    details: Optional[Dict[str, Any]] = None
    anchor_a: Optional[EvidenceAnchor] = None
    anchor_b: Optional[EvidenceAnchor] = None


class WitnessVersionDiffResponse(BaseModel):
    """Diff response for two witness versions"""
    witness_id: str
    version_a_id: str
    version_b_id: str
    similarity: float
    shifts: List[VersionShift] = Field(default_factory=list)


# =============================================================================
# OUTPUT SCHEMAS - Contradiction Insights
# =============================================================================

class ContradictionInsightResponse(BaseModel):
    """Contradiction insight response"""
    contradiction_id: str
    impact_score: float
    risk_score: float
    verifiability_score: float
    stage_recommendation: Optional[str] = None
    prerequisites: List[str] = Field(default_factory=list)
    expected_evasions: List[str] = Field(default_factory=list)
    best_counter_questions: List[str] = Field(default_factory=list)
    do_not_ask_flag: bool = False
    do_not_ask_reason: Optional[str] = None
    composite_score: Optional[float] = None


# =============================================================================
# OUTPUT SCHEMAS - Cross-Examination Plan
# =============================================================================

class CrossExamPlanBranch(BaseModel):
    """Branching follow-up for an evasion or trap"""
    trigger: str
    follow_up_questions: List[str] = Field(default_factory=list)


class CrossExamPlanStep(BaseModel):
    """Single step in a cross-exam plan"""
    id: str
    contradiction_id: Optional[str] = None
    stage: str
    step_type: str
    title: str
    question: str
    purpose: Optional[str] = None
    anchors: List[EvidenceAnchor] = Field(default_factory=list)
    branches: List[CrossExamPlanBranch] = Field(default_factory=list)
    do_not_ask_flag: bool = False
    do_not_ask_reason: Optional[str] = None


class CrossExamPlanStage(BaseModel):
    """Stage in a cross-exam plan"""
    stage: str
    steps: List[CrossExamPlanStep] = Field(default_factory=list)


class CrossExamPlanResponse(BaseModel):
    """Cross-examination plan response"""
    plan_id: str
    case_id: str
    run_id: str
    witness_id: Optional[str] = None
    created_at: Optional[datetime] = None
    stages: List[CrossExamPlanStage] = Field(default_factory=list)


# =============================================================================
# OUTPUT SCHEMAS - Witness Simulation
# =============================================================================

class WitnessSimulationStep(BaseModel):
    """Single simulated witness response"""
    step_id: str
    stage: str
    question: str
    witness_reply: str
    chosen_branch_trigger: Optional[str] = None
    follow_up_questions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class WitnessSimulationResponse(BaseModel):
    """Witness simulation response"""
    run_id: str
    plan_id: str
    persona: str
    steps: List[WitnessSimulationStep] = Field(default_factory=list)


# OUTPUT SCHEMAS - Health & Errors
# =============================================================================

class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="Service version")
    llm_mode: LLMMode = Field(..., description="Current LLM mode")
    timestamp: datetime = Field(..., description="Current timestamp")


class ErrorDetail(BaseModel):
    """Structured error detail"""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Any] = Field(None, description="Optional error details")


class ErrorResponse(BaseModel):
    """Structured error response"""
    error: ErrorDetail


# =============================================================================
# OUTPUT SCHEMAS - Cross-Exam Tracks (Litigator Dashboard)
# =============================================================================

class TrackStep(BaseModel):
    """A single step in a cross-exam track"""
    step: str = Field(..., description="Step type: pin_fact_a, pin_fact_b, confront, close_gap")
    question: str = Field(..., description="Question text (max 160 chars)")
    expected_answer: str = Field(..., description="Expected answer type")


class TrackEvidence(BaseModel):
    """Evidence for a claim in a track"""
    claim_id: Optional[str] = Field(None, description="Claim ID")
    doc_name: Optional[str] = Field(None, description="Document name")
    locator: Optional[Locator] = Field(None, description="Location in document")
    quote: str = Field("", description="Quote from the claim (max 200 chars)")


class StyleVariants(BaseModel):
    """Question style variants for cross-exam"""
    calm: List[TrackStep] = Field(default_factory=list, description="Calm style questions")
    aggressive: List[TrackStep] = Field(default_factory=list, description="Aggressive style questions")
    judicial: List[TrackStep] = Field(default_factory=list, description="Judicial style questions")


class CrossExamTrack(BaseModel):
    """
    Full cross-examination track for a contradiction.

    Contains goal, style variants, and evidence for cross-examination.
    """
    track_id: str = Field(..., description="Unique track ID")
    contradiction_id: str = Field(..., description="Related contradiction ID")
    type: str = Field(..., description="Contradiction type: temporal|quant|presence|actor|document|identity")
    status: str = Field(..., description="Status: verified|likely|suspicious")
    severity: str = Field(..., description="Severity: high|medium|low")
    confidence: float = Field(0.0, description="Confidence score 0.0-1.0")
    goal: str = Field("", description="Track goal (one sentence)")
    style_variants: StyleVariants = Field(..., description="Question variants by style")
    evidence: Dict[str, TrackEvidence] = Field(
        default_factory=dict,
        description="Evidence for claim1 and claim2"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "track_id": "track_c123",
                "contradiction_id": "c123",
                "type": "temporal",
                "status": "verified",
                "severity": "high",
                "confidence": 0.85,
                "goal": "להראות שינוי גרסה בנוגע לתאריכים",
                "style_variants": {
                    "calm": [
                        {"step": "pin_fact_a", "question": "האם נכון שהחוזה נחתם ב-15.3.2020?", "expected_answer": "כן"},
                        {"step": "pin_fact_b", "question": "האם נכון שטענת שהחוזה נחתם ב-20.5.2021?", "expected_answer": "כן"},
                        {"step": "confront", "question": "אתה מסכים שיש סתירה בין שתי הטענות?", "expected_answer": "הימנעות"},
                        {"step": "close_gap", "question": "איך מיישבים את הפער בין הגרסאות?", "expected_answer": "הסבר"}
                    ],
                    "aggressive": [],
                    "judicial": []
                },
                "evidence": {
                    "claim1": {
                        "claim_id": "claim_36",
                        "doc_name": "כתב טענות",
                        "quote": "החוזה נחתם ב-15.3.2020"
                    },
                    "claim2": {
                        "claim_id": "claim_57",
                        "doc_name": "תצהיר",
                        "quote": "החוזה נחתם ב-20.5.2021"
                    }
                }
            }
        }


class CrossExamTracksResponse(BaseModel):
    """Response containing all cross-exam tracks"""
    cross_exam_tracks: List[CrossExamTrack] = Field(
        default_factory=list,
        description="List of cross-examination tracks"
    )
    total_tracks: int = Field(0, description="Total number of tracks")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


# =============================================================================
# TODO ROADMAP
# =============================================================================
"""
Implementation Roadmap:

TIER 1 (NOW - MVP Core):
- [x] TEMPORAL_DATE_CONFLICT: Date normalization, comparison
- [x] QUANT_AMOUNT_CONFLICT: Amount extraction, currency handling
- [x] ACTOR_ATTRIBUTION_CONFLICT: NER for actors, verb matching
- [x] PRESENCE_PARTICIPATION_CONFLICT: Polarity detection (yes/no)
- [ ] DOCUMENT_EXISTENCE_CONFLICT: Document existence vs. claims
- [ ] IDENTITY_BASIC_CONFLICT: ID number/name matching

TIER 2 (NEXT - After MVP stable):
- [ ] TIMELINE_SEQUENCE_CONFLICT: Event ordering (A before B vs B before A)
- [ ] LOCATION_CONFLICT: Place NER, same-event matching
- [ ] COMMUNICATION_CHANNEL_CONFLICT: Email/mail/hand delivery patterns
- [ ] PARTY_POSITION_CONFLICT: Position/stance NLI verification
- [ ] VERSION_CONFLICT: Document versioning (v1/v2 comparison)

TIER 3 (ADVANCED - Requires Case-RAG):
- [ ] MULTI_DOC_INFERENCE: Cross-document contradictions
- [ ] QUANT_AGGREGATION: Sum vs parts, net/gross, inflation
- [ ] DEFINITION_SCOPE: Term definition conflicts

TIER 4 (EXPERIMENTAL):
- [ ] Credibility scoring (not contradiction, move to AttackAngle)
- [ ] Legal standard analysis (not contradiction)

ATTACK ANGLES (FUTURE - Not MVP):
- [ ] SHIFTING_VERSION
- [ ] LATE_DISCLOSURE
- [ ] EVASIVE_LANGUAGE
- [ ] HEARSAY_MARKERS
- [ ] MISSING_SUPPORT
- [ ] OVERBROAD_CLAIM
"""
