"""
Reconciler — "Can be reconciled?" 6-layer test and 7-category outcome
======================================================================

For each candidate pair (A, B) the reconciler attempts to reconcile them
through 6 ordered layers.  If any layer succeeds, the pair is NOT a
TRUE_CONTRADICTION.

Layers (§5.2 of spec):
    1. Time / period alignment
    2. Scope / condition alignment
    3. Quantifier mismatch ("all" vs "part")
    4. Modality mismatch (obligation vs possibility)
    5. Speaker / role mismatch (finding vs party-claim)
    6. Plane mismatch (FACT vs LAW)

Outcome categories (§5.1):
    TRUE_CONTRADICTION
    APPARENT_TENSION_RESOLVABLE
    DISAGREEMENT_BETWEEN_PARTIES
    PLANE_MISMATCH
    TIME_OR_STAGE_SHIFT
    AMBIGUITY_OR_VAGUENESS
    DUPLICATE_OR_RESTATEMENT
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from .extractor import (
    Claim,
    PLANE_FACT,
    PLANE_LAW,
    PLANE_OPINION,
    PLANE_PROCEDURAL,
    SPEAKER_MODE_FINDING,
    SPEAKER_MODE_PARTY_CLAIM,
    SPEAKER_MODE_QUOTE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Outcome constants — matching §5.1
# ---------------------------------------------------------------------------
OUTCOME_TRUE_CONTRADICTION = "TRUE_CONTRADICTION"
OUTCOME_APPARENT_TENSION = "APPARENT_TENSION_RESOLVABLE"
OUTCOME_DISAGREEMENT = "DISAGREEMENT_BETWEEN_PARTIES"
OUTCOME_PLANE_MISMATCH = "PLANE_MISMATCH"
OUTCOME_TIME_SHIFT = "TIME_OR_STAGE_SHIFT"
OUTCOME_AMBIGUITY = "AMBIGUITY_OR_VAGUENESS"
OUTCOME_DUPLICATE = "DUPLICATE_OR_RESTATEMENT"

ALL_OUTCOMES = [
    OUTCOME_TRUE_CONTRADICTION,
    OUTCOME_APPARENT_TENSION,
    OUTCOME_DISAGREEMENT,
    OUTCOME_PLANE_MISMATCH,
    OUTCOME_TIME_SHIFT,
    OUTCOME_AMBIGUITY,
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
    the final 7-category outcome.

    The function tries to *resolve* the tension.  If it fails through all
    6 layers, the outcome is TRUE_CONTRADICTION (if confidence is above
    threshold) or AMBIGUITY_OR_VAGUENESS.
    """
    metadata = metadata or {}
    debug: Dict[str, Any] = {}

    # --- Pre-checks ---

    # 0. Duplicate / restatement check
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
    speaker_ok, speaker_note = _check_speaker_mode(claim_a, claim_b)
    debug["speaker_match"] = speaker_ok
    if not speaker_ok:
        deciding.append("speaker_mode")
        return ReconciliationResult(
            outcome=OUTCOME_DISAGREEMENT,
            contradiction_score=0.3,
            severity="low",
            severity_score=0.25,
            reconciliation_attempt=speaker_note,
            rationale="מדובר בגרסאות של צדדים שונים — מחלוקת, לא סתירה פנימית",
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

    # --- All layers passed: irreconcilable ---
    # Apply confidence threshold (§8.1 "quiet is better")
    if detector_confidence < TRUE_CONTRADICTION_THRESHOLD:
        # Below threshold → AMBIGUITY unless hard logical conflict
        has_hard_negation = (claim_a.negation != claim_b.negation)
        same_entities = bool(set(claim_a.entities) & set(claim_b.entities))
        if has_hard_negation and same_entities:
            # Hard logical conflict — override threshold
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

def _is_duplicate(a: Claim, b: Claim) -> bool:
    na = a.normalized_claim or a.text.lower()
    nb = b.normalized_claim or b.text.lower()
    if na == nb:
        return True
    # Jaccard similarity > 0.85 → restatement
    wa = set(na.split())
    wb = set(nb.split())
    if not wa or not wb:
        return False
    jaccard = len(wa & wb) / len(wa | wb)
    return jaccard > 0.85


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
    """Two party-claims from different sides → DISAGREEMENT."""
    sa = a.speaker_mode
    sb = b.speaker_mode
    ra = a.speaker_role
    rb = b.speaker_role

    # Both are party claims from different parties
    if sa == SPEAKER_MODE_PARTY_CLAIM and sb == SPEAKER_MODE_PARTY_CLAIM:
        if ra and rb and ra != rb:
            return False, f"מחלוקת בין צדדים: {ra} לעומת {rb}"

    # One is a quote → don't treat as contradiction
    if sa == SPEAKER_MODE_QUOTE or sb == SPEAKER_MODE_QUOTE:
        return False, "אחת הטענות היא ציטוט — לא קביעה של הדובר"

    return True, ""


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
    # Entity overlap → more specific → more severe
    overlap = set(a.entities) & set(b.entities)
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
    overlap = set(a.entities) & set(b.entities)
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
