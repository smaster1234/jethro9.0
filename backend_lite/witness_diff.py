"""
Witness Version Diff
====================

Minimal narrative shift detection between witness versions.
"""

from typing import Dict, Any, List, Optional, Set, Tuple
import re

from .detector import RuleBasedDetector
from .anchors import find_anchor_for_snippet


_detector = RuleBasedDetector()

NEGATION_MARKERS = [
    "לא",
    "אין",
    "אינו",
    "אינה",
    "מעולם",
    "אף פעם",
    "בלי",
]


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    return re.findall(r"[\u0590-\u05FF0-9]+", text)


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / max(len(union), 1)


def _extract_dates(text: str) -> Tuple[Set[str], List[str]]:
    raw_dates = []
    normalized = set()
    for orig, norm, _subtype in _detector._extract_dates(text):
        raw_dates.append(orig)
        if norm:
            normalized.add(_detector._format_date(norm))
    return normalized, raw_dates


def _extract_entities(text: str) -> Set[str]:
    words = _detector._get_meaningful_words(text)
    return {w for w in words if len(w) >= 3}


def _extract_negations(text: str) -> Set[str]:
    found = set()
    for marker in NEGATION_MARKERS:
        if marker in text:
            found.add(marker)
    return found


def _anchor_or_fallback(db: Any, document_id: str, snippet: Optional[str]) -> Optional[Dict[str, Any]]:
    return find_anchor_for_snippet(db, document_id, snippet or "")


def diff_witness_versions(
    db: Any,
    version_a: Any,
    version_b: Any,
) -> Dict[str, Any]:
    """
    Compute minimal narrative shifts between two witness versions.
    """
    text_a = _normalize_text(getattr(version_a.document, "full_text", "") or "")
    text_b = _normalize_text(getattr(version_b.document, "full_text", "") or "")

    tokens_a = set(_tokenize(text_a))
    tokens_b = set(_tokenize(text_b))
    similarity = _jaccard(tokens_a, tokens_b)

    shifts: List[Dict[str, Any]] = []

    # 1) Low similarity
    if similarity < 0.35:
        snippet_a = text_a[:30] if text_a else ""
        snippet_b = text_b[:30] if text_b else ""
        shifts.append({
            "shift_type": "low_similarity",
            "description": "דמיון נמוך בין הגרסאות (שינוי נרטיבי רחב).",
            "similarity": similarity,
            "details": {"threshold": 0.35},
            "anchor_a": _anchor_or_fallback(db, version_a.document_id, snippet_a),
            "anchor_b": _anchor_or_fallback(db, version_b.document_id, snippet_b),
        })

    # 2) Time changes
    dates_a_norm, dates_a_raw = _extract_dates(text_a)
    dates_b_norm, dates_b_raw = _extract_dates(text_b)
    if dates_a_norm != dates_b_norm:
        added = sorted(list(dates_b_norm - dates_a_norm))
        removed = sorted(list(dates_a_norm - dates_b_norm))
        anchor_a = None
        anchor_b = None
        if removed:
            anchor_a = _anchor_or_fallback(db, version_a.document_id, removed[0])
        elif dates_a_raw:
            anchor_a = _anchor_or_fallback(db, version_a.document_id, dates_a_raw[0])
        else:
            anchor_a = _anchor_or_fallback(db, version_a.document_id, "")
        if added:
            anchor_b = _anchor_or_fallback(db, version_b.document_id, added[0])
        elif dates_b_raw:
            anchor_b = _anchor_or_fallback(db, version_b.document_id, dates_b_raw[0])
        else:
            anchor_b = _anchor_or_fallback(db, version_b.document_id, "")

        shifts.append({
            "shift_type": "time_change",
            "description": "שינוי במועדים בין הגרסאות.",
            "similarity": similarity,
            "details": {"removed_dates": removed, "added_dates": added},
            "anchor_a": anchor_a,
            "anchor_b": anchor_b,
        })

    # 3) Entity changes (keyword shifts)
    entities_a = _extract_entities(text_a)
    entities_b = _extract_entities(text_b)
    if entities_a != entities_b:
        added = sorted(list(entities_b - entities_a))[:5]
        removed = sorted(list(entities_a - entities_b))[:5]
        anchor_a = _anchor_or_fallback(db, version_a.document_id, removed[0]) if removed else _anchor_or_fallback(db, version_a.document_id, "")
        anchor_b = _anchor_or_fallback(db, version_b.document_id, added[0]) if added else _anchor_or_fallback(db, version_b.document_id, "")
        shifts.append({
            "shift_type": "entity_change",
            "description": "שינוי במונחים/ישויות מרכזיות בין הגרסאות.",
            "similarity": similarity,
            "details": {"removed_entities": removed, "added_entities": added},
            "anchor_a": anchor_a,
            "anchor_b": anchor_b,
        })

    # 4) Negation flips
    neg_a = _extract_negations(text_a)
    neg_b = _extract_negations(text_b)
    if bool(neg_a) != bool(neg_b):
        marker_a = next(iter(neg_a), None)
        marker_b = next(iter(neg_b), None)
        shifts.append({
            "shift_type": "negation_flip",
            "description": "שינוי קוטביות/שלילה בין הגרסאות.",
            "similarity": similarity,
            "details": {"negations_a": sorted(list(neg_a)), "negations_b": sorted(list(neg_b))},
            "anchor_a": _anchor_or_fallback(db, version_a.document_id, marker_a),
            "anchor_b": _anchor_or_fallback(db, version_b.document_id, marker_b),
        })

    return {
        "similarity": similarity,
        "shifts": shifts,
    }
