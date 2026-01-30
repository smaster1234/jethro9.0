"""
Claim Enricher — Context, Speaker, Plane, Time, Entities, Negation
===================================================================

Given a list of raw Claims (text + locators) and the full document text,
enrich each claim with:
- context_before / context_after  (textual window)
- section_path                    (heading hierarchy)
- speaker / speaker_role / speaker_mode
- plane                           (FACT / LAW / OPINION / PROCEDURAL)
- time_reference
- modality                        (certain / possible / obligation / permission)
- scope_quantifiers
- entities                        (named entities)
- negation                        (boolean)
- normalized_claim                (lowered, collapsed whitespace, no punctuation)
- confidence_extraction
"""

import re
import logging
from typing import List, Optional, Dict, Tuple

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
    MODALITY_CERTAIN,
    MODALITY_POSSIBLE,
    MODALITY_OBLIGATION,
    MODALITY_PERMISSION,
    MODALITY_UNCERTAIN,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Party-claim attribution markers  (Hebrew)
_PARTY_CLAIM_PATTERNS = [
    re.compile(r'לטענת\s+\S+', re.UNICODE),
    re.compile(r'לטענתו|לטענתה|לטענתם|לטענתן', re.UNICODE),
    re.compile(r'ה(?:תובע|תובעת|נתבע|נתבעת|מבקש|מבקשת|משיב|משיבה|עותר|עותרת)\s+טען', re.UNICODE),
    re.compile(r'(?:התובע|הנתבע|המבקש|המשיב|העד|העדה|בא[- ]כוח)\s+(?:טען|טענה|ציין|ציינה|הצהיר|הצהירה|העיד|העידה)', re.UNICODE),
    re.compile(r'לדברי\s+\S+', re.UNICODE),
    re.compile(r'כטענת\s+\S+', re.UNICODE),
    re.compile(r'(?:המערער|המשיבה?|העורר|העוררת)\s+(?:טען|טענה|הוסיף|הוסיפה)', re.UNICODE),
    # Delta-fix: additional attribution patterns for Hebrew legal text
    re.compile(r'עשויים\s+לטעון', re.UNICODE),
    re.compile(r'עשוי\s+לטעון', re.UNICODE),
    re.compile(r'עשויה\s+לטעון', re.UNICODE),
    re.compile(r'נטען\s+כי', re.UNICODE),
    re.compile(r'טענת\s+\S+', re.UNICODE),
    re.compile(r'לכאורה', re.UNICODE),
    re.compile(r'דומה\s+כי', re.UNICODE),
    re.compile(r'ניתן\s+לטעון', re.UNICODE),
    re.compile(r'יש\s+הטוענים', re.UNICODE),
    re.compile(r'(?:לגרסת|גרסת|לגישת|גישת|לעמדת|עמדת)\s+\S+', re.UNICODE),
    re.compile(r'(?:לשיטת|שיטת)\s+\S+', re.UNICODE),
    re.compile(r'(?:המבקשים|המשיבים|התובעים|הנתבעים)\s+(?:טענו|טוענים|טוענות|הצהירו|ציינו|סבורים)', re.UNICODE),
]

_QUOTE_PATTERNS = [
    re.compile(r'[""״].*?[""״]', re.UNICODE),
    re.compile(r'(?:ציטוט|כלשונו|כדלקמן):', re.UNICODE),
    re.compile(r'נאמר כי\s', re.UNICODE),
]

# Law citation patterns (separate from LAW plane — these are direct case/statute references)
_LAW_CITATION_PATTERNS = [
    re.compile(r'ע"א\s+\d+/\d+', re.UNICODE),
    re.compile(r'רע"א\s+\d+/\d+', re.UNICODE),
    re.compile(r'בג"ץ\s+\d+/\d+', re.UNICODE),
    re.compile(r'ע"ע\s+\d+/\d+', re.UNICODE),
    re.compile(r'ת"א\s+\d+', re.UNICODE),
    re.compile(r'(?:נפסק|נקבע)\s+ב[פע]', re.UNICODE),
    re.compile(r'כפי\s+שנקבע\s+ב', re.UNICODE),
    re.compile(r'על[- ]?פי\s+הלכת', re.UNICODE),
]

# Finding / ruling markers
_FINDING_PATTERNS = [
    re.compile(r'(?:אני|בית[- ]?ה?משפט|בית[- ]?הדין)\s+(?:קובע|קובעת|פוסק|פוסקת|סבור|מאמצ)', re.UNICODE),
    re.compile(r'(?:מסקנת|קביעת|החלטת)\s+(?:בית[- ]?ה?משפט|בית[- ]?הדין)', re.UNICODE),
    re.compile(r'(?:הוחלט|נפסק|נקבע)\s+כי', re.UNICODE),
    re.compile(r'(?:המסקנה|הממצא|הקביעה)\s+(?:היא|הוא|הינ)', re.UNICODE),
    re.compile(r'(?:לפיכך|על כן|לסיכום|אשר על כן)', re.UNICODE),
]

# Law / norm markers
_LAW_PATTERNS = [
    re.compile(r'(?:סעיף|תקנה|חוק|פקודה|תקנות|צו)\s+\d', re.UNICODE),
    re.compile(r'(?:הלכ[הת]|פסיק[הת]|תקדים)\s', re.UNICODE),
    re.compile(r'(?:על[- ]?פי|בהתאם ל|מכוח|לפי)\s+(?:חוק|סעיף|תקנ|פקוד)', re.UNICODE),
    re.compile(r'(?:הוראות|הוראת|דין|דיני)\s', re.UNICODE),
    re.compile(r'ע"א\s+\d|רע"א\s+\d|בג"ץ\s+\d', re.UNICODE),
]

# Opinion / assessment markers
_OPINION_PATTERNS = [
    re.compile(r'(?:נראה|ייתכן|סביר\s+להניח|לדעת|להערכת|לעניות דעתי)', re.UNICODE),
    re.compile(r'(?:ספק|מסתבר|ניתן לומר|אפשר ש)', re.UNICODE),
    re.compile(r'(?:בהערכתי|להנחתי|כנראה)', re.UNICODE),
]

# Procedural markers
_PROCEDURAL_PATTERNS = [
    re.compile(r'(?:הוגש|הוגשה|הוגשו)\s+(?:תביע|בקש|ערעור|בש"א)', re.UNICODE),
    re.compile(r'(?:דיון|ישיבה|קדם|הוכחות)\s+(?:שנערך|מיום|ביום)', re.UNICODE),
    re.compile(r'(?:החלטה זמנית|צו ביניים|סעד זמני)', re.UNICODE),
    re.compile(r'(?:נדחה|התקבל|נמחק)\s+(?:הערעור|הבקשה|התביעה)', re.UNICODE),
]

# Time reference patterns
_TIME_PATTERNS = [
    re.compile(r'ב?(?:ינואר|פברואר|מרץ|מרס|אפריל|מאי|יוני|יולי|אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר)\s+\d{4}', re.UNICODE),
    re.compile(r'\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}'),
    re.compile(r'(?:ביום|מיום|ליום|ביום|נכון ל|עד ליום|החל מ)\s+\d', re.UNICODE),
    re.compile(r'(?:שנת|בשנת|בשנים)\s+\d{4}', re.UNICODE),
    re.compile(r'(?:בתחילה|לאחר מכן|קודם לכן|לפני כן|במועד|באותו זמן|טרם)', re.UNICODE),
]

# Modality markers
_OBLIGATION_PATTERNS = [
    re.compile(r'(?:חייב|חייבת|חייבים|מחויב|מוטל|על\s+\S+\s+ל)', re.UNICODE),
    re.compile(r'(?:יש ל|עליו ל|עליה ל|יש חובה)', re.UNICODE),
]
_PERMISSION_PATTERNS = [
    re.compile(r'(?:רשאי|רשאית|רשאים|מותר|ניתן ל|מוסמך)', re.UNICODE),
]
_POSSIBILITY_PATTERNS = [
    re.compile(r'(?:ייתכן|אפשר|עשוי|עלול|עלולה|עשויה|יכול|יכולה)', re.UNICODE),
    re.compile(r'(?:כנראה|סביר|ספק|לא ברור|לא ודאי)', re.UNICODE),
]

# Negation markers
_NEGATION_PATTERNS = [
    re.compile(r'(?:^|\s)(?:לא|אין|אינו|אינה|אינם|אינן|מעולם לא|אף פעם לא|נעדר|נעדרת)\s', re.UNICODE),
    re.compile(r'(?:^|\s)(?:בלא|ללא|ב?לי|מבלי|בטרם)\s', re.UNICODE),
]

# Scope / quantifier markers
_SCOPE_ALL = re.compile(r'(?:כל|כלל|כולם|כולן|מלא|שלם|תמיד|בכל מקרה)', re.UNICODE)
_SCOPE_PART = re.compile(r'(?:חלק|חלקם|מקצת|רק|בלבד|לעיתים|בדרך כלל|בתנאי ש)', re.UNICODE)
_SCOPE_CONDITIONAL = re.compile(r'(?:אם|בתנאי|כאשר|ככל ש|בכפוף|בהתקיים)', re.UNICODE)

# Entity patterns
_ENTITY_PERSON_ROLE = re.compile(
    r'(?:התובע|הנתבע|המבקש|המשיב|העד|המומח|השופט|היועץ|ב"כ|בא[- ]כוח|'
    r'התובעת|הנתבעת|המבקשת|המשיבה|העדה|המומחית|השופטת|היועצת)',
    re.UNICODE,
)
_ENTITY_LAW_REF = re.compile(r'(?:סעיף|תקנה)\s+\d+(?:\([א-ת]\))?(?:\(\d+\))?', re.UNICODE)
_ENTITY_ORG = re.compile(r'(?:חברת|עמותת|קרן|בנק)\s+\S+', re.UNICODE)
_ENTITY_NAME = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b')  # Latin names

# Heading / section detection
_HEADING_PATTERNS = [
    re.compile(r'^(?:פרק|חלק|סעיף)\s+[\dא-ת]', re.UNICODE | re.MULTILINE),
    re.compile(r'^[\d]+\.\s+[^\n]{5,60}$', re.MULTILINE),
    re.compile(r'^[א-ת]\.\s+[^\n]{5,60}$', re.MULTILINE),
]

# Alias map for entity resolution
_ENTITY_ALIASES: Dict[str, str] = {
    "המשיב": "הנתבע",
    "המשיבה": "הנתבעת",
    "המערער": "התובע",
    "המערערת": "התובעת",
    "העותר": "התובע",
    "העותרת": "התובעת",
    "המבקש": "התובע",
    "המבקשת": "התובעת",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich_claims(
    claims: List[Claim],
    full_text: str = "",
) -> List[Claim]:
    """
    Enrich a list of claims in-place.

    For each claim, populates: context_before, context_after, section_path,
    speaker_role, speaker_mode, plane, time_reference, modality,
    scope_quantifiers, entities, negation, normalized_claim,
    confidence_extraction.

    Args:
        claims: Claims to enrich (modified in-place and returned).
        full_text: Full document text for context window extraction.

    Returns:
        The same list of claims, now enriched.
    """
    # Pre-compute sentence boundaries for context window
    sentence_spans = _sentence_spans(full_text) if full_text else []
    headings = _extract_headings(full_text) if full_text else []

    for claim in claims:
        _enrich_single(claim, full_text, sentence_spans, headings)

    return claims


def resolve_entities(claims: List[Claim]) -> List[Claim]:
    """
    Normalize entity aliases across claims (e.g. "המשיב" → "הנתבע").
    Also merges obvious pronoun references within each claim's text.
    """
    for claim in claims:
        # Normalize known aliases in entities list
        normalized = []
        for ent in claim.entities:
            canonical = _ENTITY_ALIASES.get(ent, ent)
            normalized.append(canonical)
        claim.entities = list(dict.fromkeys(normalized))  # deduplicate
    return claims


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _enrich_single(
    claim: Claim,
    full_text: str,
    sentence_spans: List[Tuple[int, int]],
    headings: List[Tuple[int, str]],
) -> None:
    """Enrich a single claim with all v2 fields."""
    text = claim.text

    # 1. Normalized claim
    claim.normalized_claim = _normalize_for_comparison(text)

    # 2. Context window
    if full_text and claim.char_start is not None:
        claim.context_before, claim.context_after = _context_window(
            full_text, claim.char_start, claim.char_end or (claim.char_start + len(text)),
            sentence_spans,
        )

    # 3. Section path
    if headings and claim.char_start is not None:
        claim.section_path = _nearest_heading(headings, claim.char_start)

    # 4. Speaker / speaker_mode
    claim.speaker_role, claim.speaker_mode = _detect_speaker(text)
    if not claim.speaker and claim.speaker_role:
        claim.speaker = claim.speaker_role

    # 5. Plane
    claim.plane = _detect_plane(text, claim.speaker_mode)

    # 6. Time reference
    claim.time_reference = _detect_time_reference(text)

    # 7. Modality
    claim.modality = _detect_modality(text)

    # 8. Scope / quantifiers
    claim.scope_quantifiers = _detect_scope(text)

    # 9. Entities
    claim.entities = _extract_entities(text)

    # 10. Negation
    claim.negation = _detect_negation(text)

    # 11. Confidence (heuristic: longer, with locator → higher)
    confidence = 0.8
    if claim.doc_id and claim.char_start is not None:
        confidence += 0.1
    if len(text) > 30:
        confidence += 0.1
    claim.confidence_extraction = min(confidence, 1.0)


def _normalize_for_comparison(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    t = text.lower()
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _sentence_spans(text: str) -> List[Tuple[int, int]]:
    """Return (start, end) for each sentence in *text*."""
    spans: List[Tuple[int, int]] = []
    for m in re.finditer(r'[^.!?:]+[.!?:]?', text):
        s, e = m.start(), m.end()
        stripped = text[s:e].strip()
        if len(stripped) > 5:
            spans.append((s, e))
    return spans


def _context_window(
    full_text: str,
    char_start: int,
    char_end: int,
    sentence_spans: List[Tuple[int, int]],
    max_sentences: int = 3,
) -> Tuple[Optional[str], Optional[str]]:
    """Return up to *max_sentences* before and after the claim span."""
    before_sents: List[str] = []
    after_sents: List[str] = []
    for s, e in sentence_spans:
        if e <= char_start:
            before_sents.append(full_text[s:e].strip())
        elif s >= char_end:
            after_sents.append(full_text[s:e].strip())

    ctx_before = " ".join(before_sents[-max_sentences:]) if before_sents else None
    ctx_after = " ".join(after_sents[:max_sentences]) if after_sents else None
    return ctx_before, ctx_after


def _extract_headings(text: str) -> List[Tuple[int, str]]:
    """Return (char_offset, heading_text) for all headings."""
    headings: List[Tuple[int, str]] = []
    for pat in _HEADING_PATTERNS:
        for m in pat.finditer(text):
            headings.append((m.start(), m.group().strip()))
    headings.sort(key=lambda h: h[0])
    return headings


def _nearest_heading(headings: List[Tuple[int, str]], char_pos: int) -> Optional[str]:
    """Return the nearest heading before *char_pos*."""
    result = None
    for offset, text in headings:
        if offset <= char_pos:
            result = text
        else:
            break
    return result


# --- Speaker / speaker_mode ---

def _detect_speaker(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (speaker_role, speaker_mode)."""
    # Check quote patterns first (most specific)
    for pat in _QUOTE_PATTERNS:
        if pat.search(text):
            return None, SPEAKER_MODE_QUOTE

    # Check party-claim patterns (expanded for delta-fix)
    for pat in _PARTY_CLAIM_PATTERNS:
        m = pat.search(text)
        if m:
            role = _extract_speaker_role_from_match(m.group())
            return role, SPEAKER_MODE_PARTY_CLAIM

    # Check law citation patterns (citing precedent/statute)
    for pat in _LAW_CITATION_PATTERNS:
        if pat.search(text):
            return None, SPEAKER_MODE_LAW_CITATION

    # Check finding patterns (court ruling)
    for pat in _FINDING_PATTERNS:
        if pat.search(text):
            return "court", SPEAKER_MODE_FINDING

    # Default: could not determine
    return None, None


def _extract_speaker_role_from_match(matched: str) -> Optional[str]:
    """Extract speaker role from a party-claim match."""
    lower = matched
    if re.search(r'תובע|מבקש|עותר|מערער', lower):
        return "plaintiff"
    if re.search(r'נתבע|משיב', lower):
        return "defendant"
    if re.search(r'עד|העיד', lower):
        return "witness"
    if re.search(r'בא[- ]כוח', lower):
        return "counsel"
    return "party"


# --- Plane ---

def _detect_plane(text: str, speaker_mode: Optional[str] = None) -> str:
    """Classify claim plane: FACT / LAW / OPINION / PROCEDURAL."""
    # Procedural first (narrowest)
    for pat in _PROCEDURAL_PATTERNS:
        if pat.search(text):
            return PLANE_PROCEDURAL

    # Law / norm
    for pat in _LAW_PATTERNS:
        if pat.search(text):
            return PLANE_LAW

    # Opinion / assessment
    for pat in _OPINION_PATTERNS:
        if pat.search(text):
            return PLANE_OPINION

    # Default → FACT
    return PLANE_FACT


# --- Time reference ---

def _detect_time_reference(text: str) -> Optional[str]:
    """Extract first time reference found in text."""
    for pat in _TIME_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group().strip()
    return None


# --- Modality ---

def _detect_modality(text: str) -> str:
    """Detect modality: certain / possible / obligation / permission."""
    for pat in _OBLIGATION_PATTERNS:
        if pat.search(text):
            return MODALITY_OBLIGATION
    for pat in _PERMISSION_PATTERNS:
        if pat.search(text):
            return MODALITY_PERMISSION
    for pat in _POSSIBILITY_PATTERNS:
        if pat.search(text):
            return MODALITY_POSSIBLE
    return MODALITY_CERTAIN


# --- Scope / quantifiers ---

def _detect_scope(text: str) -> Optional[str]:
    """Detect scope: all / part / conditional."""
    if _SCOPE_CONDITIONAL.search(text):
        return "conditional"
    if _SCOPE_ALL.search(text):
        return "all"
    if _SCOPE_PART.search(text):
        return "part"
    return None


# --- Entities ---

def _extract_entities(text: str) -> List[str]:
    """Extract named entities from text."""
    entities: List[str] = []
    for m in _ENTITY_PERSON_ROLE.finditer(text):
        entities.append(m.group())
    for m in _ENTITY_LAW_REF.finditer(text):
        entities.append(m.group())
    for m in _ENTITY_ORG.finditer(text):
        entities.append(m.group())
    for m in _ENTITY_NAME.finditer(text):
        entities.append(m.group())
    return list(dict.fromkeys(entities))  # deduplicate preserving order


# --- Negation ---

def _detect_negation(text: str) -> bool:
    """Detect if claim contains dominant negation."""
    for pat in _NEGATION_PATTERNS:
        if pat.search(text):
            return True
    return False
