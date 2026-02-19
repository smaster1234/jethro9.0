"""
Expert Contradiction Notebook - strict contradiction engine.

Implements the "single source of truth" spec:
- Only irreconcilable contradictions are surfaced.
- Missing context => insufficient context.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .detector import RuleBasedDetector
from .extractor import Claim
from .schemas import (
    ClaimPlane,
    OutcomeCategory,
    SpeakerMode,
    SpeakerRole,
    Severity,
    ContradictionType,
    ContradictionStatus,
    ContradictionCategory,
)
from .detector import DetectedContradiction

_HE_WORD_RE = re.compile(r"[\u0590-\u05FF]+")
_NUM_RE = re.compile(r"\d+")
_SENT_END_RE = re.compile(r"[.!?]")

_ATTR_MARKERS = [
    r"\u05dc\u05d8\u05e2\u05e0\u05ea",  # לטענת
    r"\u05dc\u05d8\u05e2\u05e0\u05ea\u05d5",  # לטענתו
    r"\u05dc\u05d8\u05e2\u05e0\u05ea\u05d4",  # לטענתה
    r"\u05e0\u05d8\u05e2\u05df",  # נטען
    r"\u05d8\u05d5\u05e2\u05df",  # טוען
    r"\u05dc\u05d3\u05d1\u05e8\u05d9",  # לדבריו
    r"\u05dc\u05e4\u05d9",  # לפי
    r"\u05e2\u05dc\s+\u05e4\u05d9",  # על פי
]
_QUOTE_MARKERS = [
    r"\"",
    r"\u201c",
    r"\u201d",
]
_LAW_MARKERS = [
    r"\u05e1\u05e2\u05d9\u05e3",  # סעיף
    r"\u05d7\u05d5\u05e7",  # חוק
    r"\u05e4\u05e1\u05d9\u05e7\u05d4",  # פסיקה
]
_COURT_MARKERS = [
    r"\u05d1\u05d9\u05ea\s+\u05d4\u05de\u05e9\u05e4\u05d8",  # בית המשפט
    r"\u05e4\u05e1\u05e7\s+\u05d3\u05d9\u05df",  # פסק דין
]
_WITNESS_MARKERS = [
    r"\u05e2\u05d3",  # עד
    r"\u05d4\u05e2\u05d9\u05d3",  # העיד
]
_ATTORNEY_MARKERS = [
    r"\u05e2\u05d5\"\u05d3",  # עו"ד
    r"\u05e2\u05d5'\u05d3",  # עו'ד
]
_PROCEDURAL_MARKERS = [
    r"\u05d1\u05e7\u05e9\u05d4",  # בקשה
    r"\u05d4\u05dc\u05d9\u05da",  # הליך
    r"\u05d3\u05d9\u05d5\u05df",  # דיון
    r"\u05e4\u05e1\u05e7\u05d3\u05d9\u05df",  # פסקדין
]
_OPINION_MARKERS = [
    r"\u05e1\u05d1\u05d5\u05e8",  # סבור
    r"\u05e0\u05e8\u05d0\u05d4",  # נראה
]
_SCOPE_MARKERS = [
    r"\u05d0\u05dd",  # אם
    r"\u05d1\u05db\u05e4\u05d5\u05e3",  # בכפוף
    r"\u05d1\u05ea\u05e0\u05d0\u05d9",  # בתנאי
    r"\u05db\u05d0\u05e9\u05e8",  # כאשר
]
_NEGATION_MARKERS = [
    r"\u05dc\u05d0",  # לא
    r"\u05d0\u05d9\u05df",  # אין
    r"\u05d0\u05d9\u05e0\u05d5",  # אינו
    r"\u05d0\u05d9\u05e0\u05d4",  # אינה
    r"\u05de\u05e2\u05d5\u05dc\u05dd",  # מעולם
]
_MODALITY_MUST = [
    r"\u05d7\u05d9\u05d9\u05d1",  # חייב
    r"\u05d7\u05d5\u05d1\u05d4",  # חובה
    r"\u05d0\u05e1\u05d5\u05e8",  # אסור
]
_MODALITY_MAY = [
    r"\u05de\u05d5\u05ea\u05e8",  # מותר
    r"\u05e8\u05e9\u05d0\u05d9",  # רשאי
]
_MODALITY_POSSIBLE = [
    r"\u05d0\u05e4\u05e9\u05e8",  # אפשר
    r"\u05d9\u05ea\u05db\u05df",  # ייתכן
    r"\u05e2\u05e9\u05d5\u05d9",  # עשוי
    r"\u05e2\u05dc\u05d5\u05dc",  # עלול
]
_MODALITY_UNCERTAIN = [
    r"\u05d1\u05e1\u05e4\u05e7",  # בספק
]
_POS_QUANTIFIERS = [
    r"\u05db\u05dc",  # כל
    r"\u05ea\u05de\u05d9\u05d3",  # תמיד
    r"\u05db\u05d5\u05dc\u05dd",  # כולם
]
_NEG_QUANTIFIERS = [
    r"\u05d0\u05e3",  # אף
    r"\u05e9\u05d5\u05dd",  # שום
    r"\u05dc\u05e2\u05d5\u05dc\u05dd",  # לעולם
]
_MIN_QUANTIFIERS = [
    r"\u05dc\u05e4\u05d7\u05d5\u05ea",  # לפחות
    r"\u05d9\u05d5\u05ea\u05e8\s+\u05de",  # יותר מ
]
_MAX_QUANTIFIERS = [
    r"\u05dc\u05db\u05dc\s+\u05d4\u05d9\u05d5\u05ea\u05e8",  # לכל היותר
    r"\u05e4\u05d7\u05d5\u05ea\s+\u05de",  # פחות מ
]

_STOPWORDS = {
    "\u05d0\u05ea",
    "\u05e9\u05dc",
    "\u05e2\u05dc",
    "\u05e2\u05dd",
    "\u05d0\u05dc",
    "\u05de\u05df",
    "\u05db\u05d9",
    "\u05dc\u05d0",
    "\u05d2\u05dd",
    "\u05d0\u05d5",
    "\u05d0\u05dd",
    "\u05d4\u05d5\u05d0",
    "\u05d4\u05d9\u05d0",
    "\u05d4\u05dd",
    "\u05d4\u05df",
    "\u05d0\u05e0\u05d9",
    "\u05d0\u05e0\u05d7\u05e0\u05d5",
    "\u05d0\u05ea\u05d4",
    "\u05d0\u05ea\u05dd",
    "\u05d6\u05d4",
    "\u05d6\u05d5",
    "\u05d6\u05d0\u05ea",
    "\u05d0\u05dc\u05d4",
    "\u05db\u05dc",
    "\u05db\u05da",
    "\u05e8\u05e7",
    "\u05e2\u05d5\u05d3",
    "\u05d9\u05d5\u05ea\u05e8",
    "\u05d4\u05d9\u05d4",
    "\u05d4\u05d9\u05ea\u05d4",
    "\u05d4\u05d9\u05d5",
    "\u05d9\u05d4\u05d9\u05d4",
    "\u05dc\u05d4\u05d9\u05d5\u05ea",
}


@dataclass
class ExpertClaim:
    claim_id: str
    doc_id: Optional[str]
    text_span: str
    context_before: str
    context_after: str
    section_path: str
    speaker_role: str
    speaker_mode: str
    plane: str
    time_reference: str
    scope_conditions: str
    quantifiers: List[str]
    modality: str
    negation: bool
    entities_relations: List[str]
    extraction_confidence: float
    raw_claim: Claim
    tokens: List[str] = field(default_factory=list)
    time_values: List[Tuple[int, int, int]] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    eligible: bool = False


@dataclass
class PairAnalysisRow:
    claimA_id: str
    claimB_id: str
    outcome_category: OutcomeCategory
    contradiction_score: float
    reconciliation_attempt: Dict[str, Any]
    rationale: str
    evidence_A: Dict[str, Any]
    evidence_B: Dict[str, Any]


@dataclass
class ExpertSummaryReport:
    true_contradictions: int
    distribution: Dict[str, int]
    top_findings: List[Dict[str, Any]]
    noise_to_signal_ratio: float


@dataclass
class ExpertAnalysisResult:
    pair_rows: List[PairAnalysisRow]
    true_contradictions: List[DetectedContradiction]
    summary_report: ExpertSummaryReport
    stats: Dict[str, int]
    validation_flags: List[str]


def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _normalize_enum(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _tokenize(text: str) -> List[str]:
    tokens = [t for t in _HE_WORD_RE.findall(text or "")]
    return [t for t in tokens if len(t) > 1 and t not in _STOPWORDS]


def _extract_sentences(text: str) -> List[Tuple[int, int, str]]:
    sentences = []
    if not text:
        return sentences
    start = 0
    for match in _SENT_END_RE.finditer(text):
        end = match.end()
        sentence = text[start:end].strip()
        if sentence:
            sentences.append((start, end, sentence))
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append((start, len(text), tail))
    return sentences


def _extract_context(text: Optional[str], char_start: Optional[int], char_end: Optional[int]) -> Tuple[str, str]:
    if not text or char_start is None or char_end is None:
        return "", ""
    sentences = _extract_sentences(text)
    if not sentences:
        return "", ""
    idx = None
    for i, (s, e, _) in enumerate(sentences):
        if s <= char_start <= e:
            idx = i
            break
    if idx is None:
        idx = 0
    before = " ".join(s[2] for s in sentences[max(0, idx - 3):idx])
    after = " ".join(s[2] for s in sentences[idx + 1:idx + 4])
    return before.strip(), after.strip()


def _derive_section_path(claim: Claim) -> str:
    if claim.paragraph_index is not None:
        return f"paragraph:{claim.paragraph_index}"
    if claim.page is not None:
        return f"page:{claim.page}"
    return ""


def _derive_speaker_role(text: str, source: Optional[str], speaker: Optional[str]) -> str:
    haystack = " ".join(x or "" for x in [text, source, speaker])
    if _matches_any(haystack, _COURT_MARKERS):
        return SpeakerRole.COURT.value
    if _matches_any(haystack, _ATTORNEY_MARKERS):
        return SpeakerRole.ATTORNEY.value
    if _matches_any(haystack, _WITNESS_MARKERS):
        return SpeakerRole.WITNESS.value
    return SpeakerRole.PARTY.value


def _derive_speaker_mode(text: str, speaker_role: str) -> str:
    if _matches_any(text, _ATTR_MARKERS):
        return SpeakerMode.PARTY_CLAIM.value
    if _matches_any(text, _QUOTE_MARKERS):
        return SpeakerMode.QUOTE.value
    if _matches_any(text, _LAW_MARKERS):
        return SpeakerMode.LAW_CITATION.value
    if speaker_role == SpeakerRole.COURT.value:
        return SpeakerMode.COURT_FINDING.value
    if _matches_any(text, _OPINION_MARKERS):
        return SpeakerMode.OPINION.value
    return SpeakerMode.PARTY_CLAIM.value


def _derive_plane(text: str, speaker_mode: str) -> str:
    if speaker_mode == SpeakerMode.LAW_CITATION.value:
        return ClaimPlane.LAW.value
    if speaker_mode == SpeakerMode.OPINION.value:
        return ClaimPlane.OPINION.value
    if _matches_any(text, _PROCEDURAL_MARKERS):
        return ClaimPlane.PROCEDURAL.value
    return ClaimPlane.FACT.value


def _extract_scope_conditions(text: str) -> str:
    return "conditional" if _matches_any(text, _SCOPE_MARKERS) else "unconditional"


def _extract_quantifiers(text: str) -> List[str]:
    found = []
    for group in (_POS_QUANTIFIERS, _NEG_QUANTIFIERS, _MIN_QUANTIFIERS, _MAX_QUANTIFIERS):
        for pattern in group:
            if re.search(pattern, text):
                found.append(pattern)
    return found


def _derive_modality(text: str) -> str:
    if _matches_any(text, _MODALITY_MUST):
        return "must"
    if _matches_any(text, _MODALITY_MAY):
        return "may"
    if _matches_any(text, _MODALITY_POSSIBLE):
        return "possible"
    if _matches_any(text, _MODALITY_UNCERTAIN):
        return "uncertain"
    return "must"


def _detect_negation(text: str) -> bool:
    return _matches_any(text, _NEGATION_MARKERS)


def _extract_entities(text: str, metadata: Optional[Dict[str, Any]]) -> List[str]:
    entities = []
    if metadata:
        meta_entities = metadata.get("entities")
        if isinstance(meta_entities, list):
            entities.extend([str(e) for e in meta_entities if str(e).strip()])
    tokens = _tokenize(text)
    for token in tokens:
        if token not in entities:
            entities.append(token)
    numbers = _NUM_RE.findall(text or "")
    for num in numbers:
        if num not in entities:
            entities.append(num)
    return entities


def _extract_confidence(text: str, metadata: Optional[Dict[str, Any]]) -> float:
    if metadata and isinstance(metadata.get("extraction_confidence"), (int, float)):
        return float(metadata["extraction_confidence"])
    base = 0.4 + min(len(text or ""), 400) / 1000
    return max(0.3, min(0.9, base))


def build_expert_claims(
    claims: List[Claim],
    claims_data: List[Dict[str, Any]],
    source_text: Optional[str] = None,
    source_text_lookup: Optional[Dict[str, str]] = None,
) -> List[ExpertClaim]:
    data_lookup = {d.get("id", f"claim_{i}"): d for i, d in enumerate(claims_data)}
    detector = RuleBasedDetector()
    expert_claims: List[ExpertClaim] = []

    for claim in claims:
        data = data_lookup.get(claim.id, {})
        text_span = data.get("text_span") or claim.text or ""
        doc_id = claim.doc_id or data.get("doc_id")
        src_text = source_text_lookup.get(doc_id) if source_text_lookup and doc_id else source_text
        context_before = data.get("context_before")
        context_after = data.get("context_after")
        if context_before is None or context_after is None:
            cb, ca = _extract_context(src_text, claim.char_start, claim.char_end)
            context_before = context_before or cb
            context_after = context_after or ca

        section_path = data.get("section_path") or _derive_section_path(claim)
        speaker_role = _normalize_enum(data.get("speaker_role")) or _derive_speaker_role(text_span, data.get("source"), claim.speaker)
        speaker_mode = _normalize_enum(data.get("speaker_mode")) or _derive_speaker_mode(text_span, speaker_role)
        plane = _normalize_enum(data.get("plane")) or _derive_plane(text_span, speaker_mode)
        scope_conditions = data.get("scope_conditions") or _extract_scope_conditions(text_span)
        quantifiers = data.get("quantifiers") if data.get("quantifiers") is not None else _extract_quantifiers(text_span)
        if isinstance(quantifiers, str):
            quantifiers = [quantifiers]
        modality = data.get("modality") or _derive_modality(text_span)
        negation = data.get("negation") if data.get("negation") is not None else _detect_negation(text_span)
        entities_relations = data.get("entities_relations") if data.get("entities_relations") is not None else _extract_entities(text_span, claim.metadata)
        if isinstance(entities_relations, str):
            entities_relations = [entities_relations]
        extraction_confidence = data.get("extraction_confidence")
        if extraction_confidence is None:
            extraction_confidence = _extract_confidence(text_span, claim.metadata)

        time_reference = data.get("time_reference")
        time_values = []
        if time_reference:
            time_reference = str(time_reference)
        else:
            dates = detector._extract_dates(text_span)
            time_values = [d[1] for d in dates]
            time_reference = "dates" if dates else ""

        tokens = _tokenize(text_span)
        missing_fields = _missing_claim_fields(
            text_span=text_span,
            context_before=context_before,
            context_after=context_after,
            section_path=section_path,
            speaker_role=speaker_role,
            speaker_mode=speaker_mode,
            plane=plane,
            time_reference=time_reference,
            scope_conditions=scope_conditions,
            quantifiers=quantifiers,
            modality=modality,
            entities_relations=entities_relations,
            extraction_confidence=extraction_confidence,
        )

        expert_claims.append(ExpertClaim(
            claim_id=claim.id,
            doc_id=doc_id,
            text_span=text_span,
            context_before=context_before or "",
            context_after=context_after or "",
            section_path=section_path or "",
            speaker_role=speaker_role,
            speaker_mode=speaker_mode,
            plane=plane,
            time_reference=time_reference or "",
            scope_conditions=scope_conditions or "",
            quantifiers=quantifiers or [],
            modality=modality,
            negation=bool(negation),
            entities_relations=entities_relations or [],
            extraction_confidence=float(extraction_confidence),
            raw_claim=claim,
            tokens=tokens,
            time_values=time_values,
            missing_fields=missing_fields,
            eligible=len(missing_fields) == 0,
        ))

    return expert_claims


def _missing_claim_fields(
    text_span: str,
    context_before: Optional[str],
    context_after: Optional[str],
    section_path: Optional[str],
    speaker_role: Optional[str],
    speaker_mode: Optional[str],
    plane: Optional[str],
    time_reference: Optional[str],
    scope_conditions: Optional[str],
    quantifiers: Optional[List[str]],
    modality: Optional[str],
    entities_relations: Optional[List[str]],
    extraction_confidence: Optional[float],
) -> List[str]:
    missing = []
    if not text_span:
        missing.append("text_span")
    if not context_before:
        missing.append("context_before")
    if not context_after:
        missing.append("context_after")
    if not section_path:
        missing.append("section_path")
    if not speaker_role:
        missing.append("speaker_role")
    if not speaker_mode:
        missing.append("speaker_mode")
    if not plane:
        missing.append("plane")
    if not time_reference:
        missing.append("time_reference")
    if not scope_conditions:
        missing.append("scope_conditions")
    if quantifiers is None:
        missing.append("quantifiers")
    if not modality:
        missing.append("modality")
    if entities_relations is None or not entities_relations:
        missing.append("entities_relations")
    if extraction_confidence is None:
        missing.append("extraction_confidence")
    return missing


def _subject_overlap(a: ExpertClaim, b: ExpertClaim) -> bool:
    if not a.entities_relations or not b.entities_relations:
        return False
    overlap = set(a.entities_relations) & set(b.entities_relations)
    return len(overlap) >= 1


def _token_overlap(a: ExpertClaim, b: ExpertClaim) -> float:
    if not a.tokens or not b.tokens:
        return 0.0
    sa = set(a.tokens)
    sb = set(b.tokens)
    return len(sa & sb) / max(len(sa | sb), 1)


def _duplicate_restatement(a: ExpertClaim, b: ExpertClaim) -> bool:
    overlap = _token_overlap(a, b)
    return overlap >= 0.9


def _stage_shift(a: ExpertClaim, b: ExpertClaim) -> bool:
    before_marker = "\u05dc\u05e4\u05e0\u05d9"  # לפני
    after_marker = "\u05dc\u05d0\u05d7\u05e8"    # לאחר
    a_before = before_marker in a.text_span
    a_after = after_marker in a.text_span
    b_before = before_marker in b.text_span
    b_after = after_marker in b.text_span
    # One claim says "before" and the other says "after" (or vice versa)
    return (a_before and b_after) or (a_after and b_before)


def _extract_time_values(detector: RuleBasedDetector, claim: ExpertClaim) -> List[Tuple[int, int, int]]:
    if claim.time_values:
        return claim.time_values
    dates = detector._extract_dates(claim.text_span)
    return [d[1] for d in dates]


def _time_conflict(detector: RuleBasedDetector, a: ExpertClaim, b: ExpertClaim) -> bool:
    da = _extract_time_values(detector, a)
    db = _extract_time_values(detector, b)
    if not da or not db:
        return False
    return len(set(da) & set(db)) == 0


def _amount_conflict(detector: RuleBasedDetector, a: ExpertClaim, b: ExpertClaim) -> bool:
    amounts_a = detector._extract_amounts(a.text_span)
    amounts_b = detector._extract_amounts(b.text_span)
    if not amounts_a or not amounts_b:
        return False
    return detector._amounts_conflict(amounts_a, amounts_b) is not None


def _quantifier_conflict(a: ExpertClaim, b: ExpertClaim) -> bool:
    a_has_pos = _matches_any(a.text_span, _POS_QUANTIFIERS)
    b_has_pos = _matches_any(b.text_span, _POS_QUANTIFIERS)
    a_has_neg = _matches_any(a.text_span, _NEG_QUANTIFIERS)
    b_has_neg = _matches_any(b.text_span, _NEG_QUANTIFIERS)
    if (a_has_pos and b_has_neg) or (b_has_pos and a_has_neg):
        return True
    a_has_min = _matches_any(a.text_span, _MIN_QUANTIFIERS)
    b_has_max = _matches_any(b.text_span, _MAX_QUANTIFIERS)
    b_has_min = _matches_any(b.text_span, _MIN_QUANTIFIERS)
    a_has_max = _matches_any(a.text_span, _MAX_QUANTIFIERS)
    return (a_has_min and b_has_max) or (b_has_min and a_has_max)


def _negation_conflict(a: ExpertClaim, b: ExpertClaim) -> bool:
    return a.negation != b.negation and _token_overlap(a, b) >= 0.2


def _direct_conflict(detector: RuleBasedDetector, a: ExpertClaim, b: ExpertClaim) -> Tuple[bool, str, Optional[ContradictionType]]:
    if _time_conflict(detector, a, b):
        return True, "time_conflict", ContradictionType.TEMPORAL_DATE
    if _amount_conflict(detector, a, b):
        return True, "amount_conflict", ContradictionType.QUANT_AMOUNT
    if _negation_conflict(a, b):
        return True, "negation_conflict", ContradictionType.FACTUAL
    if _quantifier_conflict(a, b):
        return True, "quantifier_conflict", ContradictionType.FACTUAL
    return False, "no_direct_conflict", None


def _can_be_reconciled(a: ExpertClaim, b: ExpertClaim) -> Tuple[bool, str]:
    if _stage_shift(a, b):
        return True, "stage_shift"
    if a.scope_conditions and b.scope_conditions and a.scope_conditions != b.scope_conditions:
        return True, "scope_conditions"
    if a.modality != b.modality:
        return True, "modality_differs"
    return False, "irreconcilable"


def _score_contradiction(
    a: ExpertClaim,
    b: ExpertClaim,
    direct_conflict: bool,
    same_subject: bool,
    plane_match: bool,
    confidence: float,
) -> float:
    score = 0.0
    if direct_conflict:
        score += 0.4
    if same_subject:
        score += 0.2
    if plane_match:
        score += 0.1
    score += 0.3 * confidence
    if a.modality in ("possible", "uncertain") or b.modality in ("possible", "uncertain"):
        score -= 0.1
    return max(0.0, min(1.0, score))


def _severity_from_score(score: float, confidence: float, reconciled: bool) -> Severity:
    if reconciled:
        return Severity.LOW
    if score >= 0.9 and confidence >= 0.8:
        return Severity.CRITICAL
    if score >= 0.82:
        return Severity.HIGH
    if score >= 0.75:
        return Severity.MEDIUM
    return Severity.LOW


def analyze_expert_pairs(
    expert_claims: List[ExpertClaim],
    candidate_contradictions: Optional[List[DetectedContradiction]] = None,
    max_pairs: int = 2000,
) -> ExpertAnalysisResult:
    claim_lookup = {c.claim_id: c for c in expert_claims}
    detector = RuleBasedDetector()
    validation_flags: List[str] = []

    pair_ids: List[Tuple[str, str, Optional[DetectedContradiction]]] = []
    if candidate_contradictions:
        for contr in candidate_contradictions:
            cid1 = contr.claim1.id
            cid2 = contr.claim2.id
            pair_key = tuple(sorted([cid1, cid2]))
            pair_ids.append((pair_key[0], pair_key[1], contr))
    else:
        ids = list(claim_lookup.keys())
        for i, a_id in enumerate(ids):
            for b_id in ids[i + 1:]:
                pair_ids.append((a_id, b_id, None))

    # Dedup pairs
    seen = set()
    unique_pairs = []
    for a_id, b_id, contr in pair_ids:
        key = (a_id, b_id)
        if key in seen:
            continue
        seen.add(key)
        unique_pairs.append((a_id, b_id, contr))

    if len(unique_pairs) > max_pairs:
        validation_flags.append("PAIR_ANALYSIS_TRUNCATED")
        unique_pairs = unique_pairs[:max_pairs]

    pair_rows: List[PairAnalysisRow] = []
    true_contradictions: List[DetectedContradiction] = []
    outcome_counts: Dict[str, int] = {}

    for a_id, b_id, candidate in unique_pairs:
        a = claim_lookup.get(a_id)
        b = claim_lookup.get(b_id)
        if not a or not b:
            continue

        if not _subject_overlap(a, b):
            continue

        outcome, score, rationale, reconciliation, detected_type = _evaluate_pair(detector, a, b, candidate)
        outcome_counts[outcome.value] = outcome_counts.get(outcome.value, 0) + 1

        pair_rows.append(PairAnalysisRow(
            claimA_id=a.claim_id,
            claimB_id=b.claim_id,
            outcome_category=outcome,
            contradiction_score=score,
            reconciliation_attempt=reconciliation,
            rationale=rationale,
            evidence_A=_build_evidence(a),
            evidence_B=_build_evidence(b),
        ))

        if outcome == OutcomeCategory.TRUE_CONTRADICTION and score >= 0.75 and detected_type:
            conf = min(a.extraction_confidence, b.extraction_confidence)
            direct_conflict = True
            plane_match = a.plane == b.plane
            same_subject = True
            contr_score = _score_contradiction(a, b, direct_conflict, same_subject, plane_match, conf)
            reconciled = reconciliation.get("reconciled", False)
            severity = _severity_from_score(contr_score, conf, reconciled)
            status = ContradictionStatus.VERIFIED if score >= 0.85 else ContradictionStatus.LIKELY

            true_contradictions.append(DetectedContradiction(
                id=f"contr_expert_{uuid.uuid4().hex[:8]}",
                claim1=a.raw_claim,
                claim2=b.raw_claim,
                type=detected_type,
                subtype=None,
                status=status,
                severity=severity,
                confidence=score,
                same_event_confidence=1.0,
                explanation=rationale,
                quote1=a.text_span,
                quote2=b.text_span,
                normalized1=None,
                normalized2=None,
                metadata={"outcome_category": outcome.value},
                category=ContradictionCategory.HARD_CONTRADICTION,
            ))

    top_findings = sorted(
        [r for r in pair_rows if r.outcome_category == OutcomeCategory.TRUE_CONTRADICTION],
        key=lambda r: r.contradiction_score,
        reverse=True,
    )[:5]

    signal = len(top_findings)
    noise = max(len(pair_rows) - signal, 0)
    ratio = noise / max(signal, 1)

    summary_report = ExpertSummaryReport(
        true_contradictions=signal,
        distribution=outcome_counts,
        top_findings=[_row_to_summary(r) for r in top_findings],
        noise_to_signal_ratio=ratio,
    )

    stats = {
        "pairs_total": len(unique_pairs),
        "pairs_filtered_in": len(pair_rows),
        "pairs_filtered_out": max(len(unique_pairs) - len(pair_rows), 0),
    }

    return ExpertAnalysisResult(
        pair_rows=pair_rows,
        true_contradictions=true_contradictions,
        summary_report=summary_report,
        stats=stats,
        validation_flags=validation_flags,
    )


def _evaluate_pair(
    detector: RuleBasedDetector,
    a: ExpertClaim,
    b: ExpertClaim,
    candidate: Optional[DetectedContradiction],
) -> Tuple[OutcomeCategory, float, str, Dict[str, Any], Optional[ContradictionType]]:
    if not a.eligible or not b.eligible:
        missing = list(set(a.missing_fields + b.missing_fields))
        return (
            OutcomeCategory.INSUFFICIENT_CONTEXT,
            0.0,
            f"insufficient_context: {', '.join(sorted(missing))}",
            {"reconciled": True, "reason": "missing_fields"},
            None,
        )

    if a.speaker_mode == SpeakerMode.PARTY_CLAIM.value and b.speaker_mode == SpeakerMode.COURT_FINDING.value:
        return (
            OutcomeCategory.ROLE_OR_ATTRIBUTION_MISMATCH,
            0.1,
            "party_claim_vs_court_finding",
            {"reconciled": True, "reason": "speaker_attribution"},
            None,
        )

    if a.plane != b.plane:
        return (
            OutcomeCategory.PLANE_MISMATCH,
            0.1,
            "plane_mismatch",
            {"reconciled": True, "reason": "plane_mismatch"},
            None,
        )

    if _stage_shift(a, b):
        return (
            OutcomeCategory.TIME_OR_STAGE_SHIFT,
            0.1,
            "stage_shift",
            {"reconciled": True, "reason": "stage_shift"},
            None,
        )

    if _duplicate_restatement(a, b):
        return (
            OutcomeCategory.DUPLICATE_RESTATEMENT,
            0.0,
            "duplicate_restatement",
            {"reconciled": True, "reason": "duplicate"},
            None,
        )

    reconciled, reason = _can_be_reconciled(a, b)
    reconciliation = {"reconciled": reconciled, "reason": reason}
    if reconciled and reason != "irreconcilable":
        return (
            OutcomeCategory.APPARENT_TENSION_RESOLVABLE,
            0.35,
            f"reconciled:{reason}",
            reconciliation,
            None,
        )

    direct_conflict, conflict_reason, detected_type = _direct_conflict(detector, a, b)
    confidence = min(a.extraction_confidence, b.extraction_confidence)
    score = _score_contradiction(
        a,
        b,
        direct_conflict=direct_conflict,
        same_subject=True,
        plane_match=True,
        confidence=confidence,
    )

    if a.speaker_mode == SpeakerMode.PARTY_CLAIM.value or b.speaker_mode == SpeakerMode.PARTY_CLAIM.value:
        return (
            OutcomeCategory.DISAGREEMENT_BETWEEN_PARTIES,
            min(score, 0.6),
            "party_disagreement",
            reconciliation,
            None,
        )

    if a.speaker_mode == SpeakerMode.QUOTE.value or b.speaker_mode == SpeakerMode.QUOTE.value:
        return (
            OutcomeCategory.ROLE_OR_ATTRIBUTION_MISMATCH,
            min(score, 0.5),
            "quote_attribution",
            reconciliation,
            None,
        )

    if a.modality in ("possible", "uncertain") or b.modality in ("possible", "uncertain"):
        return (
            OutcomeCategory.AMBIGUITY_OR_VAGUENESS,
            min(score, 0.5),
            "modality_ambiguity",
            reconciliation,
            None,
        )

    if direct_conflict and score >= 0.75:
        return (
            OutcomeCategory.TRUE_CONTRADICTION,
            score,
            f"direct_conflict:{conflict_reason}",
            reconciliation,
            detected_type or (candidate.type if candidate else None),
        )

    return (
        OutcomeCategory.APPARENT_TENSION_RESOLVABLE,
        min(score, 0.6),
        "no_strong_contradiction",
        reconciliation,
        None,
    )


def _build_evidence(claim: ExpertClaim) -> Dict[str, Any]:
    return {
        "quote": claim.text_span,
        "context_before": claim.context_before,
        "context_after": claim.context_after,
        "doc_id": claim.doc_id,
        "section_path": claim.section_path,
    }


def _row_to_summary(row: PairAnalysisRow) -> Dict[str, Any]:
    return {
        "claimA_id": row.claimA_id,
        "claimB_id": row.claimB_id,
        "contradiction_score": row.contradiction_score,
        "rationale": row.rationale,
    }

