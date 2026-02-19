"""
Reconciler — "Can be reconciled?" 6-layer test and 9-category outcome
======================================================================

For each candidate pair (A, B) the reconciler attempts to reconcile them
through 6 ordered layers.  If any layer succeeds, the pair is NOT a
TRUE_CONTRADICTION.

Layers (§6 of Cursor 5.2 spec):
    1. Time / period alignment
    2. Scope / condition alignment
    3. Quantifier mismatch ("all" vs "part")
    4. Modality mismatch (obligation vs possibility)
    5. Speaker / role mismatch (finding vs party-claim)
    6. Plane mismatch (FACT vs LAW)

Outcome categories (§7 of Cursor 5.2 spec):
    TRUE_CONTRADICTION
    APPARENT_TENSION_RESOLVABLE
    DISAGREEMENT_BETWEEN_PARTIES
    ROLE_OR_ATTRIBUTION_MISMATCH
    PLANE_MISMATCH
    TIME_OR_STAGE_SHIFT
    AMBIGUITY_OR_VAGUENESS
    INSUFFICIENT_CONTEXT
    DUPLICATE_OR_RESTATEMENT
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set
from difflib import SequenceMatcher

from .extractor import (
    Claim,
    PLANE_FACT,
    PLANE_LAW,
    PLANE_OPINION,
    PLANE_PROCEDURAL,
    SPEAKER_MODE_FINDING,
    SPEAKER_MODE_PARTY_CLAIM,
    SPEAKER_MODE_QUOTE,
    SPEAKER_MODE_LAW_CITATION,
    SPEAKER_MODE_OPINION,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Outcome constants — matching §7 of Cursor 5.2 spec
# ---------------------------------------------------------------------------
OUTCOME_TRUE_CONTRADICTION = "TRUE_CONTRADICTION"
OUTCOME_APPARENT_TENSION = "APPARENT_TENSION_RESOLVABLE"
OUTCOME_DISAGREEMENT = "DISAGREEMENT_BETWEEN_PARTIES"
OUTCOME_ROLE_MISMATCH = "ROLE_OR_ATTRIBUTION_MISMATCH"
OUTCOME_PLANE_MISMATCH = "PLANE_MISMATCH"
OUTCOME_TIME_SHIFT = "TIME_OR_STAGE_SHIFT"
OUTCOME_AMBIGUITY = "AMBIGUITY_OR_VAGUENESS"
OUTCOME_INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
OUTCOME_DUPLICATE = "DUPLICATE_OR_RESTATEMENT"

ALL_OUTCOMES = [
    OUTCOME_TRUE_CONTRADICTION,
    OUTCOME_APPARENT_TENSION,
    OUTCOME_DISAGREEMENT,
    OUTCOME_ROLE_MISMATCH,
    OUTCOME_PLANE_MISMATCH,
    OUTCOME_TIME_SHIFT,
    OUTCOME_AMBIGUITY,
    OUTCOME_INSUFFICIENT_CONTEXT,
    OUTCOME_DUPLICATE,
]

# Confidence threshold below which we refuse to label TRUE_CONTRADICTION
TRUE_CONTRADICTION_THRESHOLD = 0.75


@dataclass
class ReconciliationResult:
    """Output of the reconciliation engine for one (A, B) pair."""
    outcome: str                             # one of ALL_OUTCOMES
    contradiction_score: float = 0.0         # 0-1, 1 = maximally irreconcilable
    severity: str = "low"                    # low / medium / high
    severity_score: float = 0.0              # 0-1
    reconciliation_attempt: str = ""         # short summary of reconciliation try
    rationale: str = ""                      # detailed explanation (Hebrew)
    conflict_predicate: str = ""             # what exactly clashes
    deciding_fields: List[str] = field(default_factory=list)  # which fields decided
    debug: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Legal party role classification — Israeli civil procedure
# ---------------------------------------------------------------------------
#
# In Israeli proceedings, parties have procedural role designations that
# vary by proceeding type (תביעה, ערעור, בקשה, עתירה, קובלנה, עררים).
# Witnesses are separate — they may be aligned with a party but are not
# themselves parties.
#
# Role sides:
#   INITIATOR  — the party who started the proceeding
#   RESPONDENT — the party responding / defending
#   THIRD      — צד ג' (third-party notice)
#   FOURTH     — צד ד' (fourth-party notice)
#   WITNESS    — עד (not a party; may be aligned with a side)
#   EXPERT     — עד מומחה / מומחה מטעם ביהמ"ש (neutral or party-aligned)
#   COURT      — בית המשפט / בית הדין
#   UNKNOWN    — cannot determine
# ---------------------------------------------------------------------------

SIDE_INITIATOR = "initiator"
SIDE_RESPONDENT = "respondent"
SIDE_THIRD = "third_party"
SIDE_FOURTH = "fourth_party"
SIDE_WITNESS = "witness"
SIDE_EXPERT = "expert"
SIDE_COURT = "court"
SIDE_UNKNOWN = "unknown"

# All initiator-side role words (singular, plural, masculine, feminine)
_INITIATOR_ROLES = {
    "תובע", "התובע", "תובעת", "התובעת", "תובעים", "התובעים", "תובעות", "התובעות",
    "מערער", "המערער", "מערערת", "המערערת", "מערערים", "המערערים", "מערערות", "המערערות",
    "מבקש", "המבקש", "מבקשת", "המבקשת", "מבקשים", "המבקשים", "מבקשות", "המבקשות",
    "עותר", "העותר", "עותרת", "העותרת", "עותרים", "העותרים", "עותרות", "העותרות",
    "קובל", "הקובל", "קובלת", "הקובלת", "קובלים", "הקובלים", "קובלות", "הקובלות",
    "עורר", "העורר", "עוררת", "העוררת", "עוררים", "העוררים", "עוררות", "העוררות",
}

# All respondent-side role words
_RESPONDENT_ROLES = {
    "נתבע", "הנתבע", "נתבעת", "הנתבעת", "נתבעים", "הנתבעים", "נתבעות", "הנתבעות",
    "משיב", "המשיב", "משיבה", "המשיבה", "משיבים", "המשיבים", "משיבות", "המשיבות",
    "משיב פורמלי", "המשיב הפורמלי", "משיבה פורמלית", "המשיבה הפורמלית",
}

# Third / fourth party
_THIRD_PARTY_ROLES = {
    "צד ג", "צד שלישי", "צד ג׳", "הצד השלישי", "צד 3",
    "נתבע צד ג", "צד ג 1", "צד ג 2", "צד ג 3",
}
_FOURTH_PARTY_ROLES = {
    "צד ד", "צד רביעי", "צד ד׳", "הצד הרביעי", "צד 4",
}

# Witness roles (not parties)
_WITNESS_ROLES = {
    "עד", "העד", "עדה", "העדה", "עדים", "העדים",
    "עד תביעה", "עד הגנה", "עדת תביעה", "עדת הגנה",
}

# Expert witness roles
_EXPERT_ROLES = {
    "מומחה", "המומחה", "מומחית", "המומחית",
    "עד מומחה", "העד המומחה", "עדת מומחה",
    "מומחה מטעם בית המשפט", "מומחה מטעם ביהמש",
    "מומחה רפואי", "מומחה מטעם התובע", "מומחה מטעם הנתבע",
    "רופא מומחה", "מודד", "שמאי", "רואה חשבון מומחה",
}

# Court
_COURT_ROLES = {
    "בית המשפט", "ביהמש", "בית משפט", "הערכאה",
    "בית הדין", "ביהד", "בית דין",
    "שופט", "שופטת", "השופט", "השופטת", "כבוד השופט", "כבוד השופטת",
    "רשם", "רשמת", "הרשם", "הרשמת",
}

# Regex to extract party number: "תובע 1", "נתבע 2", "צד ג 3"
_PARTY_NUMBER_RE = re.compile(r'(\d+)\s*$')


def _classify_legal_role(name: str) -> tuple:
    """
    Classify an entity name into a legal role side and optional number.

    Returns:
        (side: str, number: Optional[int], base_role: str)

    Examples:
        "התובע"      -> (SIDE_INITIATOR, None, "תובע")
        "נתבע 2"     -> (SIDE_RESPONDENT, 2, "נתבע")
        "העד כהן"    -> (SIDE_WITNESS, None, "עד")
        "צד ג 1"     -> (SIDE_THIRD, 1, "צד ג")
        "יוסי כהן"   -> (SIDE_UNKNOWN, None, "")
    """
    cleaned = name.strip().replace('"', '').replace('״', '').replace('׳', '').replace("'", '')
    lower = cleaned.lower()

    # Extract trailing number
    num_match = _PARTY_NUMBER_RE.search(lower)
    number = int(num_match.group(1)) if num_match else None
    base = _PARTY_NUMBER_RE.sub('', lower).strip() if num_match else lower

    # Check each role set (check multi-word first, then single-word)
    for role_word in sorted(_EXPERT_ROLES, key=len, reverse=True):
        if base == role_word or base.startswith(role_word + " "):
            return (SIDE_EXPERT, number, role_word)

    for role_word in sorted(_COURT_ROLES, key=len, reverse=True):
        if base == role_word or base.startswith(role_word + " "):
            return (SIDE_COURT, number, role_word)

    for role_word in sorted(_FOURTH_PARTY_ROLES, key=len, reverse=True):
        if base == role_word or base.startswith(role_word + " "):
            return (SIDE_FOURTH, number, role_word)

    for role_word in sorted(_THIRD_PARTY_ROLES, key=len, reverse=True):
        if base == role_word or base.startswith(role_word + " "):
            return (SIDE_THIRD, number, role_word)

    for role_word in sorted(_WITNESS_ROLES, key=len, reverse=True):
        if base == role_word or base.startswith(role_word + " "):
            return (SIDE_WITNESS, number, role_word)

    for role_word in sorted(_RESPONDENT_ROLES, key=len, reverse=True):
        if base == role_word or base.startswith(role_word + " "):
            return (SIDE_RESPONDENT, number, role_word)

    for role_word in sorted(_INITIATOR_ROLES, key=len, reverse=True):
        if base == role_word or base.startswith(role_word + " "):
            return (SIDE_INITIATOR, number, role_word)

    return (SIDE_UNKNOWN, number, "")


def _roles_are_opposing(side_a: str, side_b: str) -> bool:
    """
    Check if two role sides are opposing parties in the proceeding.

    Opposing pairs:
    - initiator <-> respondent
    - initiator <-> third_party (in some contexts)
    - witness is NEVER equal to a party (different entity category)

    Returns True if the two sides CANNOT be the same person.
    """
    if side_a == side_b:
        return False

    opposing = {
        frozenset({SIDE_INITIATOR, SIDE_RESPONDENT}),
        frozenset({SIDE_INITIATOR, SIDE_THIRD}),
        frozenset({SIDE_INITIATOR, SIDE_FOURTH}),
        frozenset({SIDE_RESPONDENT, SIDE_THIRD}),
        frozenset({SIDE_RESPONDENT, SIDE_FOURTH}),
        frozenset({SIDE_THIRD, SIDE_FOURTH}),
    }

    # Different known party sides → opposing
    if frozenset({side_a, side_b}) in opposing:
        return True

    # Witness vs party: different category, not the same entity
    # (unless the witness IS a party, but that's resolved by name matching)
    party_sides = {SIDE_INITIATOR, SIDE_RESPONDENT, SIDE_THIRD, SIDE_FOURTH}
    if (side_a == SIDE_WITNESS and side_b in party_sides) or \
       (side_b == SIDE_WITNESS and side_a in party_sides):
        return True

    # Court vs anyone else
    if side_a == SIDE_COURT or side_b == SIDE_COURT:
        return True

    return False


# ---------------------------------------------------------------------------
# Fuzzy entity matching for Hebrew legal names
# ---------------------------------------------------------------------------

# Honorific/title prefixes to strip (NOT party roles — those are classified separately)
_TITLE_PATTERNS = re.compile(
    r'^(?:מר|גב|גברת|עו"ד|עוד|ד"ר|דר|פרופ|רו"ח|רוח|כב|כבוד)\s+',
    re.UNICODE,
)

# Non-party entity aliases — institutions, companies, courts
_LEGAL_ENTITY_ALIASES = {
    # בנקים
    "בנק לאומי": ["הבנק הלאומי", "לאומי", "בנק לאומי לישראל"],
    "בנק הפועלים": ["הבנק הפועלים", "פועלים", "בנק פועלים"],
    "בנק דיסקונט": ["הבנק דיסקונט", "דיסקונט"],
    "בנק מזרחי": ["הבנק המזרחי", "מזרחי", "בנק מזרחי טפחות"],
    "בנק ירושלים": ["הבנק הירושלמי", "ירושלים"],
    "בנק אגוד": ["הבנק האגוד", "אגוד"],

    # חברות ביטוח
    "הפניקס": ["חברת הפניקס", "פניקס", "הפניקס חברה לביטוח"],
    "הראל": ["חברת הראל", "ראל"],
    "מגדל": ["חברת מגדל", "מגדל ביטוח"],

    # מוסדות ממשלתיים
    "ביטוח לאומי": ["המוסד לביטוח לאומי"],
    "המדינה": ["מדינת ישראל"],

    # מונחים משפטיים
    "בית המשפט": ["ביהמש", "בית משפט", "הערכאה"],
    "בית הדין": ["ביהד", "בית דין"],
}

# Build reverse lookup for aliases
_ALIAS_TO_CANONICAL = {}
for canonical, aliases in _LEGAL_ENTITY_ALIASES.items():
    _ALIAS_TO_CANONICAL[canonical.lower()] = canonical
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias.lower()] = canonical


def _normalize_entity(name: str) -> str:
    """Normalize an entity name for fuzzy comparison."""
    name = name.strip()
    # Remove quotes first (before title stripping, since quotes appear in titles)
    name = name.replace('"', '').replace("'", '').replace('״', '').replace('׳', '')
    # Remove common Hebrew suffixes (בע"מ, בע״מ, Ltd, etc.)
    name = re.sub(r'\s*(?:בעמ|ltd\.?|inc\.?)\s*$', '', name, flags=re.IGNORECASE)
    normalized = name.lower().strip()

    # Check alias BEFORE stripping titles — the full name may be a known alias
    if normalized in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[normalized].lower()

    # Remove honorific titles ONLY if doing so leaves content
    stripped = _TITLE_PATTERNS.sub('', name).strip().lower()
    if stripped:
        if stripped in _ALIAS_TO_CANONICAL:
            return _ALIAS_TO_CANONICAL[stripped].lower()
        normalized = stripped

    # Try partial alias lookup: strip single Hebrew prefix letter and re-check
    for prefix_len in (1, 2):
        if len(normalized) > prefix_len + 2 and normalized[0] in 'הבלמושכ':
            partial = normalized[prefix_len:]
            if partial in _ALIAS_TO_CANONICAL:
                return _ALIAS_TO_CANONICAL[partial].lower()

    return normalized


# Hebrew prefix letters that can be stripped for token comparison
_HEBREW_PREFIXES = set('הבלמושכ')


def _tokenize_entity(name: str) -> Set[str]:
    """
    Tokenize an entity name for token-based similarity.
    Strips Hebrew prefix letters and removes very short tokens.
    """
    tokens = set()
    for word in name.split():
        word = re.sub(r'[^\w]', '', word)
        if len(word) < 2:
            continue
        tokens.add(word)
        # Also add prefix-stripped versions
        if len(word) > 3 and word[0] in _HEBREW_PREFIXES:
            tokens.add(word[1:])
    return tokens


def _entities_match(a: str, b: str, threshold: float = 0.75) -> bool:
    """
    Check if two entity names refer to the same entity.

    Uses a role-aware approach for Israeli legal proceedings:
    1. Classify both entities by legal role (initiator/respondent/witness/expert/court)
    2. If both are known roles on OPPOSING sides → never match
    3. If both are the same role with DIFFERENT numbers → never match (תובע 1 ≠ תובע 2)
    4. Otherwise, fall through to name-based matching

    Name-based matching (ordered by reliability):
    - Canonical alias match (dictionary lookup)
    - Exact match after normalization
    - Containment match ("אלפא" in "חברת אלפא בע״מ")
    - Token-based Jaccard similarity
    - Last-name match with additional token overlap
    - Character SequenceMatcher as final fallback
    """
    na = _normalize_entity(a)
    nb = _normalize_entity(b)

    if not na or not nb:
        return False

    # --- Role-aware guard ---
    role_a = _classify_legal_role(a)  # (side, number, base_role)
    role_b = _classify_legal_role(b)
    side_a, num_a, base_a = role_a
    side_b, num_b, base_b = role_b

    # Both are classified party/witness/court roles
    if side_a != SIDE_UNKNOWN and side_b != SIDE_UNKNOWN:
        # Opposing sides → never the same entity
        if _roles_are_opposing(side_a, side_b):
            return False

        # Same side, same role category, different number → different entity
        # (תובע 1 ≠ תובע 2, but תובע = תובע 1 is possible when no number)
        if side_a == side_b and num_a is not None and num_b is not None and num_a != num_b:
            return False

        # Same side, same role, same number (or no numbers) → same entity
        if side_a == side_b and base_a and base_b:
            if num_a == num_b:
                return True

    # --- Name-based matching (for non-role entities or UNKNOWN roles) ---

    # Exact match after normalization (includes alias resolution)
    if na == nb:
        return True

    # One contains the other (handles "אלפא" vs "חברת אלפא בע״מ")
    if na in nb or nb in na:
        return True

    # Token-based Jaccard similarity — handles prefix variations
    tokens_a = _tokenize_entity(na)
    tokens_b = _tokenize_entity(nb)
    if tokens_a and tokens_b:
        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b
        jaccard = len(intersection) / len(union)
        if jaccard >= 0.50:
            return True

    # Last-word match: require last name match AND at least one additional
    # matching token (to avoid "יוסי כהן" == "דוד כהן" false positives).
    words_a = na.split()
    words_b = nb.split()
    if words_a and words_b and len(words_a) >= 2 and len(words_b) >= 2:
        if words_a[-1] == words_b[-1] and len(words_a[-1]) > 2:
            other_a = set(words_a[:-1])
            other_b = set(words_b[:-1])
            if other_a & other_b:
                return True

    # Character-level fallback
    ratio = SequenceMatcher(None, na, nb).ratio()
    return ratio >= threshold


def _fuzzy_entity_overlap(entities_a: List[str], entities_b: List[str]) -> Set[str]:
    """
    Find overlapping entities between two lists using fuzzy matching.
    Returns a set of matched entity names (from list A).
    """
    if not entities_a or not entities_b:
        return set()

    # First try exact intersection (fast path)
    exact = set(entities_a) & set(entities_b)
    if exact:
        return exact

    # Fuzzy matching
    matched: Set[str] = set()
    for ea in entities_a:
        for eb in entities_b:
            if _entities_match(ea, eb):
                matched.add(ea)
                break
    return matched


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def reconcile_pair(
    claim_a: Claim,
    claim_b: Claim,
    detector_type: Optional[str] = None,
    detector_confidence: float = 0.5,
    normalized_a: Optional[str] = None,
    normalized_b: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ReconciliationResult:
    """
    Attempt to reconcile claim pair.  Returns a ReconciliationResult with
    the final 9-category outcome (Cursor 5.2 spec §7).

    The function tries to *resolve* the tension.  If it fails through all
    6 layers, the outcome is TRUE_CONTRADICTION (if confidence is above
    threshold) or AMBIGUITY_OR_VAGUENESS.

    Pre-gates (§3, §4):
    - Claim completeness check → INSUFFICIENT_CONTEXT if missing fields
    - Duplicate / restatement check → DUPLICATE_OR_RESTATEMENT
    """
    metadata = metadata or {}
    debug: Dict[str, Any] = {}

    # --- Pre-gate 0: Claim completeness (§3/§4) ---
    # If critical enrichment fields are missing, we cannot confirm TRUE_CONTRADICTION.
    # "No claim may be interpreted without context."
    incomplete_a = _check_claim_completeness(claim_a)
    incomplete_b = _check_claim_completeness(claim_b)
    debug["claim_a_complete"] = not incomplete_a
    debug["claim_b_complete"] = not incomplete_b

    # --- Pre-gate 1: Duplicate / restatement check ---
    if _is_duplicate(claim_a, claim_b):
        return ReconciliationResult(
            outcome=OUTCOME_DUPLICATE,
            contradiction_score=0.0,
            reconciliation_attempt="הטענות חוזרות על אותו רעיון בניסוח שונה",
            rationale="זיהוי חזרה / שחזור ללא סתירה",
            deciding_fields=["normalized_claim"],
            debug=debug,
        )

    deciding: List[str] = []
    reconciliation_parts: List[str] = []

    # --- Layer 1: Time / period alignment ---
    time_ok, time_note = _check_time_alignment(claim_a, claim_b)
    debug["time_match"] = time_ok
    if not time_ok:
        deciding.append("time_reference")
        reconciliation_parts.append(time_note)
        return ReconciliationResult(
            outcome=OUTCOME_TIME_SHIFT,
            contradiction_score=0.2,
            severity="low",
            severity_score=0.2,
            reconciliation_attempt=time_note,
            rationale="הטענות מתייחסות לזמנים או שלבים שונים — אין סתירה אמיתית",
            conflict_predicate="time_reference",
            deciding_fields=deciding,
            debug=debug,
        )

    # --- Layer 2: Scope / condition alignment ---
    scope_ok, scope_note = _check_scope_alignment(claim_a, claim_b)
    debug["scope_match"] = scope_ok
    if not scope_ok:
        deciding.append("scope_quantifiers")
        return ReconciliationResult(
            outcome=OUTCOME_APPARENT_TENSION,
            contradiction_score=0.35,
            severity="low",
            severity_score=0.3,
            reconciliation_attempt=scope_note,
            rationale="הטענות שונות בהיקף או בתנאי — ניתנות ליישוב",
            conflict_predicate="scope",
            deciding_fields=deciding,
            debug=debug,
        )

    # --- Layer 3: Quantifier mismatch ---
    quant_ok, quant_note = _check_quantifier(claim_a, claim_b)
    debug["quantifier_match"] = quant_ok
    if not quant_ok:
        deciding.append("scope_quantifiers")
        return ReconciliationResult(
            outcome=OUTCOME_APPARENT_TENSION,
            contradiction_score=0.35,
            severity="low",
            severity_score=0.3,
            reconciliation_attempt=quant_note,
            rationale="הפער נובע מכימות שונה (כולם/חלק) — לא סתירה אמיתית",
            conflict_predicate="quantifier",
            deciding_fields=deciding,
            debug=debug,
        )

    # --- Layer 4: Modality mismatch ---
    mod_ok, mod_note = _check_modality(claim_a, claim_b)
    debug["modality_match"] = mod_ok
    if not mod_ok:
        deciding.append("modality")
        return ReconciliationResult(
            outcome=OUTCOME_APPARENT_TENSION,
            contradiction_score=0.25,
            severity="low",
            severity_score=0.2,
            reconciliation_attempt=mod_note,
            rationale="הבדל במודאליות (חובה/רשות/ייתכן) — לא סתירה עובדתית",
            conflict_predicate="modality",
            deciding_fields=deciding,
            debug=debug,
        )

    # --- Layer 5: Speaker / role (finding vs party-claim) ---
    speaker_ok, speaker_note, speaker_outcome = _check_speaker_mode(claim_a, claim_b)
    debug["speaker_match"] = speaker_ok
    if not speaker_ok:
        deciding.append("speaker_mode")
        return ReconciliationResult(
            outcome=speaker_outcome,
            contradiction_score=0.3,
            severity="low",
            severity_score=0.25,
            reconciliation_attempt=speaker_note,
            rationale="מדובר בגרסאות של צדדים שונים — מחלוקת, לא סתירה פנימית"
                      if speaker_outcome == OUTCOME_DISAGREEMENT
                      else "ייחוס/תפקיד שונה — אי-התאמה בייחוס, לא סתירה עובדתית",
            conflict_predicate="speaker_mode",
            deciding_fields=deciding,
            debug=debug,
        )

    # --- Layer 6: Plane mismatch ---
    plane_ok, plane_note = _check_plane(claim_a, claim_b)
    debug["plane_match"] = plane_ok
    if not plane_ok:
        deciding.append("plane")
        return ReconciliationResult(
            outcome=OUTCOME_PLANE_MISMATCH,
            contradiction_score=0.2,
            severity="low",
            severity_score=0.15,
            reconciliation_attempt=plane_note,
            rationale="הטענות שייכות למישורים שונים (עובדה/נורמה/הערכה) — אין השוואה ישירה",
            conflict_predicate="plane",
            deciding_fields=deciding,
            debug=debug,
        )

    # --- All layers passed: attempt final gate for TRUE_CONTRADICTION ---
    # Delta-fix §1: TRUE_CONTRADICTION requires ALL of:
    #   1. same entities/event + same time window + same scope
    #   2. same plane (FACT↔FACT or LAW↔LAW)
    #   3. negation/quantifier conflict that cannot be reconciled
    #   4. reconciliation_attempt failed with rationale

    # §1.a: Entity overlap required (with fuzzy matching for Hebrew names)
    entity_overlap = _fuzzy_entity_overlap(
        claim_a.entities or [], claim_b.entities or []
    )
    has_entity_overlap = bool(entity_overlap)

    # §1.b: Negation opposition
    has_hard_negation = (claim_a.negation != claim_b.negation)

    # §1.c: Same plane (FACT↔FACT or LAW↔LAW)
    same_plane = (claim_a.plane and claim_b.plane and claim_a.plane == claim_b.plane)
    factual_plane = same_plane and claim_a.plane in (PLANE_FACT, PLANE_LAW)

    # §3: OPINION/PROCEDURAL never qualify for TRUE_CONTRADICTION
    if claim_a.plane in (PLANE_OPINION, PLANE_PROCEDURAL) or claim_b.plane in (PLANE_OPINION, PLANE_PROCEDURAL):
        return ReconciliationResult(
            outcome=OUTCOME_APPARENT_TENSION,
            contradiction_score=min(detector_confidence, 0.4),
            severity="low",
            severity_score=0.2,
            reconciliation_attempt="מישור הערכה/פרוצדורלי לא מאפשר סתירה אמיתית",
            rationale="טענות במישור הערכה או פרוצדורלי אינן סותרות עובדתית",
            conflict_predicate="plane_opinion_or_procedural",
            deciding_fields=["plane"],
            debug=debug,
        )

    # §3/§4: Claim completeness — if either claim is missing critical fields
    # and no hard evidence overrides, return INSUFFICIENT_CONTEXT
    # Check early so that missing plane/speaker_mode gets caught before
    # downstream gates that depend on these fields.
    if (incomplete_a or incomplete_b) and not (has_hard_negation and has_entity_overlap and factual_plane):
        missing = incomplete_a or incomplete_b
        return ReconciliationResult(
            outcome=OUTCOME_INSUFFICIENT_CONTEXT,
            contradiction_score=min(detector_confidence, 0.4),
            severity="low",
            severity_score=0.2,
            reconciliation_attempt=f"שדות חסרים בטענה: {', '.join(missing)}",
            rationale="לא ניתן לקבוע סתירה אמיתית ללא כל השדות הנדרשים (§3)",
            conflict_predicate="incomplete_claim",
            deciding_fields=missing,
            debug=debug,
        )

    # §7: Apply confidence threshold ("quiet is better")
    if detector_confidence < TRUE_CONTRADICTION_THRESHOLD:
        # Below threshold → AMBIGUITY unless hard logical conflict
        if has_hard_negation and has_entity_overlap and factual_plane:
            # Hard logical conflict with full evidence — override threshold
            pass
        else:
            return ReconciliationResult(
                outcome=OUTCOME_AMBIGUITY,
                contradiction_score=detector_confidence,
                severity="low",
                severity_score=0.3,
                reconciliation_attempt="ביטחון מתחת לסף — לא ניתן לקבוע סתירה אמיתית",
                rationale="עוצמת הביטחון אינה מספיקה לקביעת סתירה אמיתית",
                conflict_predicate="confidence",
                deciding_fields=["confidence"],
                debug=debug,
            )

    # §1 final gate: require entity overlap + negation/predicate conflict
    if not has_entity_overlap:
        return ReconciliationResult(
            outcome=OUTCOME_APPARENT_TENSION,
            contradiction_score=min(detector_confidence, 0.5),
            severity="low",
            severity_score=0.3,
            reconciliation_attempt="אין חפיפת ישויות — לא ניתן לקבוע סתירה אמיתית",
            rationale="הטענות אינן מתייחסות לאותן ישויות/אירועים — מתח לכאורה",
            conflict_predicate="missing_entity_overlap",
            deciding_fields=["entities"],
            debug=debug,
        )

    if not has_hard_negation and not factual_plane:
        return ReconciliationResult(
            outcome=OUTCOME_AMBIGUITY,
            contradiction_score=min(detector_confidence, 0.5),
            severity="low",
            severity_score=0.3,
            reconciliation_attempt="אין התנגשות לוגית ברורה (שלילה/חיוב) ולא אותו מישור",
            rationale="לא זוהה ניגוד ברור בין הטענות — עמימות",
            conflict_predicate="no_hard_conflict",
            deciding_fields=["negation", "plane"],
            debug=debug,
        )

    # §4: If neither claim has context_before/after, block TRUE_CONTRADICTION
    has_context_a = bool(claim_a.context_before or claim_a.context_after)
    has_context_b = bool(claim_b.context_before or claim_b.context_after)
    if not has_context_a and not has_context_b:
        # No context available → cannot confirm TRUE_CONTRADICTION (§4 rule)
        if not (has_hard_negation and has_entity_overlap):
            return ReconciliationResult(
                outcome=OUTCOME_INSUFFICIENT_CONTEXT,
                contradiction_score=min(detector_confidence, 0.5),
                severity="low",
                severity_score=0.3,
                reconciliation_attempt="אין הקשר מלא (context) — לא ניתן לאשר סתירה אמיתית",
                rationale="ללא הקשר מלא לטענות לא ניתן לאשר סתירה",
                conflict_predicate="missing_context",
                deciding_fields=["context_before", "context_after"],
                debug=debug,
            )

    # Compute severity
    severity, severity_score = _compute_severity(claim_a, claim_b, detector_confidence, metadata)

    return ReconciliationResult(
        outcome=OUTCOME_TRUE_CONTRADICTION,
        contradiction_score=detector_confidence,
        severity=severity,
        severity_score=severity_score,
        reconciliation_attempt="נוסו כל דרכי היישוב — לא נמצא יישוב סביר",
        rationale=_build_true_contradiction_rationale(claim_a, claim_b, metadata),
        conflict_predicate=_describe_conflict(claim_a, claim_b, metadata),
        deciding_fields=["entities", "negation", "plane", "time_reference"],
        debug=debug,
    )


# ---------------------------------------------------------------------------
# Layer implementations
# ---------------------------------------------------------------------------

def _check_claim_completeness(claim: Claim) -> Optional[List[str]]:
    """
    Cursor 5.2 §3: Check if a claim has all mandatory fields populated.

    Returns None if complete, or a list of missing field names if incomplete.
    Fields required for TRUE_CONTRADICTION eligibility:
    - speaker_mode
    - plane
    """
    missing: List[str] = []
    if not claim.speaker_mode:
        missing.append("speaker_mode")
    if not claim.plane:
        missing.append("plane")
    return missing if missing else None


_DUPLICATE_SYNONYMS = {
    'הסכם': 'חוזה', 'חוזה': 'חוזה',
    'שילם': 'תשלום', 'תשלום': 'תשלום', 'סכום': 'תשלום',
    'שלח': 'מסר', 'מסר': 'מסר', 'הודיע': 'מסר',
    'קיבל': 'קיבל', 'קבלה': 'קיבל',
}

_DUPLICATE_STOPWORDS = {
    'את', 'של', 'על', 'עם', 'אל', 'מן', 'כי', 'גם', 'או', 'אם',
    'הוא', 'היא', 'הם', 'הן', 'אני', 'זה', 'זו', 'זאת',
    'כך', 'רק', 'עוד', 'יותר', 'היה', 'היתה', 'היו',
    'ה', 'ו', 'ב', 'ל', 'מ', 'ש', 'כ',
    # NOTE: 'לא' and 'כל' intentionally NOT included — they carry
    # semantic meaning for contradiction vs duplicate detection.
}

_DATE_NORMALIZE_RE = re.compile(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})')
_HEB_MONTH_MAP = {
    'ינואר': '01', 'פברואר': '02', 'מרץ': '03', 'מרס': '03',
    'אפריל': '04', 'מאי': '05', 'יוני': '06', 'יולי': '07',
    'אוגוסט': '08', 'ספטמבר': '09', 'אוקטובר': '10',
    'נובמבר': '11', 'דצמבר': '12',
}
_HEB_DATE_RE = re.compile(
    r'(\d{1,2})\s*ב?(ינואר|פברואר|מרץ|מרס|אפריל|מאי|יוני|יולי|אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר)\s+(\d{4})'
)


def _normalize_for_duplicate(text: str) -> str:
    """Normalize text for duplicate detection: dates, synonyms, stopwords."""
    t = text.lower().strip()
    # Normalize Hebrew dates to DD.MM.YYYY
    for m in _HEB_DATE_RE.finditer(t):
        day, month_name, year = m.group(1), m.group(2), m.group(3)
        mm = _HEB_MONTH_MAP.get(month_name, '00')
        t = t.replace(m.group(0), f"{int(day):02d}.{mm}.{year}")
    # Normalize numeric dates to DD.MM.YYYY
    def _norm_date(m):
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = '20' + y
        return f"{int(d):02d}.{int(mo):02d}.{y}"
    t = _DATE_NORMALIZE_RE.sub(_norm_date, t)
    return t


def _char_ngram_similarity(a: str, b: str, n: int = 3) -> float:
    """Character n-gram (trigram) similarity between two strings."""
    if len(a) < n or len(b) < n:
        return 1.0 if a == b else 0.0
    ngrams_a = set(a[i:i+n] for i in range(len(a) - n + 1))
    ngrams_b = set(b[i:i+n] for i in range(len(b) - n + 1))
    if not ngrams_a or not ngrams_b:
        return 0.0
    return len(ngrams_a & ngrams_b) / len(ngrams_a | ngrams_b)


def _is_duplicate(a: Claim, b: Claim) -> bool:
    na = a.normalized_claim or a.text.lower()
    nb = b.normalized_claim or b.text.lower()
    if na == nb:
        return True

    # Normalize for comparison (dates, synonyms)
    norm_a = _normalize_for_duplicate(a.text)
    norm_b = _normalize_for_duplicate(b.text)
    if norm_a == norm_b:
        return True

    # Token-level comparison with synonym canonicalization
    def _canonical_tokens(text: str) -> set:
        tokens = set(re.sub(r'[^\w\s]', '', text).split())
        result = set()
        for tok in tokens:
            if tok in _DUPLICATE_STOPWORDS or len(tok) < 2:
                continue
            # Try synonym lookup: as-is, then with one prefix stripped,
            # then with two prefixes stripped.
            canon = _DUPLICATE_SYNONYMS.get(tok)
            if canon is None and len(tok) > 3 and tok[0] in 'הבלמושכ':
                canon = _DUPLICATE_SYNONYMS.get(tok[1:])
            if canon is None and len(tok) > 4 and tok[0] in 'הבלמושכ' and tok[1] in 'הבלמושכ':
                canon = _DUPLICATE_SYNONYMS.get(tok[2:])
            if canon is None:
                # Use the most-stripped form as the token
                stripped = tok
                if len(tok) > 3 and tok[0] in 'הבלמושכ':
                    stripped = tok[1:]
                canon = stripped
            result.add(canon)
        return result

    wa = _canonical_tokens(norm_a)
    wb = _canonical_tokens(norm_b)
    if not wa or not wb:
        return False

    # Token Jaccard >= 0.75, but NOT if the only difference is a negation word
    _NEGATION_WORDS = {'לא', 'אינו', 'אינה', 'אינם', 'אין', 'מעולם', 'כלל'}
    jaccard = len(wa & wb) / len(wa | wb)
    if jaccard >= 0.80:
        diff = (wa - wb) | (wb - wa)
        # If the sets differ only in negation words, this is a contradiction, not a duplicate
        if diff and diff <= _NEGATION_WORDS:
            return False
        return True

    # Character trigram similarity >= 0.90
    if _char_ngram_similarity(norm_a, norm_b) >= 0.90:
        return True

    return False


def _check_time_alignment(a: Claim, b: Claim):
    """If both have time references and they clearly differ → TIME_SHIFT."""
    ta = a.time_reference
    tb = b.time_reference
    if not ta or not tb:
        return True, ""  # Cannot determine → pass
    if ta == tb:
        return True, ""
    # Different time markers → reconcilable by time
    return False, f"הטענות מתייחסות לזמנים שונים: «{ta}» לעומת «{tb}»"


def _check_scope_alignment(a: Claim, b: Claim):
    sa = a.scope_quantifiers
    sb = b.scope_quantifiers
    if not sa or not sb:
        return True, ""
    if sa == sb:
        return True, ""
    # "conditional" vs anything → resolvable
    if "conditional" in (sa, sb):
        return False, "אחת הטענות מותנית — ההיקף שונה"
    return False, f"הטענות שונות בהיקף: «{sa}» לעומת «{sb}»"


def _check_quantifier(a: Claim, b: Claim):
    sa = a.scope_quantifiers
    sb = b.scope_quantifiers
    if not sa or not sb:
        return True, ""
    if (sa == "all" and sb == "part") or (sa == "part" and sb == "all"):
        return False, "אחת הטענות מתייחסת ל'כולם' ואחרת ל'חלק' — פער כימותי ניתן ליישוב"
    return True, ""


def _check_modality(a: Claim, b: Claim):
    ma = a.modality
    mb = b.modality
    if not ma or not mb:
        return True, ""
    if ma == mb:
        return True, ""
    # Different modalities → reconcilable
    return False, f"הטענות שונות במודאליות: «{ma}» לעומת «{mb}»"


def _check_speaker_mode(a: Claim, b: Claim):
    """
    Cursor 5.2 §5/§6: Block TRUE_CONTRADICTION when claims come from
    different speaker modes.

    Returns 3-tuple: (ok, note, outcome_category).
    - ok=True  → pass through (modes are compatible)
    - ok=False → block, use the returned outcome category

    Outcome routing:
    - Quote/law_citation/opinion → ROLE_OR_ATTRIBUTION_MISMATCH
    - Cross-party claims → DISAGREEMENT_BETWEEN_PARTIES
    - party_claim vs non-party_claim → ROLE_OR_ATTRIBUTION_MISMATCH
    """
    sa = a.speaker_mode
    sb = b.speaker_mode
    ra = a.speaker_role
    rb = b.speaker_role

    # §2.5: OPINION speaker mode — speculation, not assertive → ROLE_OR_ATTRIBUTION_MISMATCH
    if sa == SPEAKER_MODE_OPINION or sb == SPEAKER_MODE_OPINION:
        return False, "אחת הטענות היא הערכה/ספקולציה — לא קביעה עובדתית", OUTCOME_ROLE_MISMATCH

    # One is a quote → not a real assertion → ROLE_OR_ATTRIBUTION_MISMATCH
    if sa == SPEAKER_MODE_QUOTE or sb == SPEAKER_MODE_QUOTE:
        return False, "אחת הטענות היא ציטוט — לא קביעה של הדובר", OUTCOME_ROLE_MISMATCH

    # One is a law citation → citing precedent → ROLE_OR_ATTRIBUTION_MISMATCH
    if sa == SPEAKER_MODE_LAW_CITATION or sb == SPEAKER_MODE_LAW_CITATION:
        return False, "אחת הטענות היא ציטוט פסיקה/חקיקה — לא עובדה של הדובר", OUTCOME_ROLE_MISMATCH

    # Both are party claims from different parties → DISAGREEMENT
    if sa == SPEAKER_MODE_PARTY_CLAIM and sb == SPEAKER_MODE_PARTY_CLAIM:
        if ra and rb and ra != rb:
            return False, f"מחלוקת בין צדדים: {ra} לעומת {rb}", OUTCOME_DISAGREEMENT

    # party_claim vs non-party_claim → ROLE_OR_ATTRIBUTION_MISMATCH
    if sa == SPEAKER_MODE_PARTY_CLAIM and sb != SPEAKER_MODE_PARTY_CLAIM:
        if sb is not None:
            return False, f"טענת צד ({ra or 'צד'}) מול {sb} — אי-התאמה בייחוס", OUTCOME_ROLE_MISMATCH
    if sb == SPEAKER_MODE_PARTY_CLAIM and sa != SPEAKER_MODE_PARTY_CLAIM:
        if sa is not None:
            return False, f"טענת צד ({rb or 'צד'}) מול {sa} — אי-התאמה בייחוס", OUTCOME_ROLE_MISMATCH

    return True, "", OUTCOME_DISAGREEMENT  # default (unused when ok=True)


def _check_plane(a: Claim, b: Claim):
    pa = a.plane
    pb = b.plane
    if not pa or not pb:
        return True, ""
    if pa == pb:
        return True, ""
    # FACT ↔ FACT or LAW ↔ LAW is fine
    # Cross-plane: not comparable
    comparable = {
        (PLANE_FACT, PLANE_FACT),
        (PLANE_LAW, PLANE_LAW),
    }
    if (pa, pb) not in comparable and (pb, pa) not in comparable:
        return False, f"הטענות שייכות למישורים שונים: {pa} לעומת {pb}"
    return True, ""


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

def _compute_severity(
    a: Claim, b: Claim, confidence: float, metadata: Dict[str, Any]
) -> tuple:
    """Compute severity based on claim centrality, irreconcilability, confidence."""
    score = 0.0

    # Centrality: findings > party claims
    if a.speaker_mode == SPEAKER_MODE_FINDING or b.speaker_mode == SPEAKER_MODE_FINDING:
        score += 0.3
    # Negation opposition
    if a.negation != b.negation:
        score += 0.2
    # High confidence
    if confidence >= 0.9:
        score += 0.2
    elif confidence >= 0.75:
        score += 0.1
    # Entity overlap → more specific → more severe (fuzzy match)
    overlap = _fuzzy_entity_overlap(a.entities or [], b.entities or [])
    if len(overlap) >= 2:
        score += 0.2
    elif len(overlap) >= 1:
        score += 0.1

    score = min(score, 1.0)

    if score >= 0.7:
        return "high", score
    elif score >= 0.4:
        return "medium", score
    return "low", score


# ---------------------------------------------------------------------------
# Rationale helpers
# ---------------------------------------------------------------------------

def _build_true_contradiction_rationale(a: Claim, b: Claim, metadata: Dict[str, Any]) -> str:
    parts = []
    if a.negation != b.negation:
        parts.append("ניגוד ישיר בשלילה/חיוב")
    overlap = _fuzzy_entity_overlap(a.entities or [], b.entities or [])
    if overlap:
        parts.append(f"אותן ישויות: {', '.join(list(overlap)[:3])}")
    if a.plane and a.plane == b.plane:
        parts.append(f"אותו מישור ({a.plane})")
    if a.time_reference and b.time_reference and a.time_reference == b.time_reference:
        parts.append(f"אותה תקופה ({a.time_reference})")

    if not parts:
        return "שתי הטענות אינן יכולות להיות נכונות בו-זמנית — לא נמצא יישוב סביר"
    return "סתירה אמיתית: " + "; ".join(parts)


def _describe_conflict(a: Claim, b: Claim, metadata: Dict[str, Any]) -> str:
    if a.negation != b.negation:
        return "negation_opposition"
    return "factual_clash"
