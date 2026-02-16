"""
Semantic Triplet Matching — WHO did WHAT about TOPIC (WHEN)
===========================================================

Extracts structured triplets from Hebrew legal claims and provides
a matching function to determine if two claims discuss the same subject.

This is the key Phase 2 quality improvement: instead of comparing
every pair of claims that share a few words (threshold=0.15),
we require that claims share at least one entity AND describe the
same type of legal action on the same topic.

This dramatically reduces false positives where unrelated claims
happen to share common words (e.g., "payment", "signed", "agreement").

Triplet Structure:
    WHO   — entities involved (persons, roles, organizations)
    WHAT  — action category (payment, signing, attendance, etc.)
    TOPIC — legal object being acted upon (agreement, salary, etc.)
    WHEN  — time reference (already extracted by claim_enricher)

Matching Logic:
    1. WHO gate: at least one shared entity (person/role/org) required
    2. WHAT match: same action category = strong signal
    3. TOPIC match: same legal object/event = strong signal
    4. WHEN compatibility: same time period = bonus

Score = requires WHO match, then:
    0.45 * what_match + 0.35 * topic_match + 0.20 * when_compat
"""

import re
import logging
from typing import List, Optional, Set, Tuple
from dataclasses import dataclass, field
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


# =============================================================================
# Action Categories (WHAT)
# =============================================================================

class ActionCategory:
    """Categories of legal actions for WHAT matching."""
    PAYMENT = "payment"         # שילם, העביר, תשלום
    SIGNING = "signing"         # חתם, חתימה
    ATTENDANCE = "attendance"   # נכח, השתתף, היה נוכח
    RECEIPT = "receipt"         # קיבל, קבלה
    DELIVERY = "delivery"      # שלח, מסר, הודיע
    STATEMENT = "statement"    # אמר, הצהיר, טען, ציין, העיד
    DECISION = "decision"      # החליט, קבע, פסק, אישר
    CREATION = "creation"      # הקים, ייסד, פתח, הגיש
    TERMINATION = "termination" # ביטל, סיים, פיטר, הפסיק
    EXISTENCE = "existence"    # קיים, היה, נמצא, שהה
    DAMAGE = "damage"          # ניזוק, נפגע, נגרם נזק
    AGREEMENT = "agreement"    # הסכים, הסכמה, התחייב
    UNKNOWN = "unknown"


# Hebrew verb -> action category mapping
_ACTION_PATTERNS = [
    # PAYMENT
    (re.compile(r'(?:שילם|שילמה|משלם|משלמת|העביר|העבירה|תשלום|שולם|לשלם)', re.UNICODE), ActionCategory.PAYMENT),
    # SIGNING (includes construct forms like חתימת)
    (re.compile(r'(?:חתם|חתמה|חותם|חותמת|חתימ[הת]|נחתם|נחתמה)', re.UNICODE), ActionCategory.SIGNING),
    # ATTENDANCE
    (re.compile(r'(?:נכח|נכחה|נוכח|נוכחת|השתתף|השתתפה|היה\s+נוכח|הייתה\s+נוכחת|שהה|שהתה)', re.UNICODE), ActionCategory.ATTENDANCE),
    # RECEIPT
    (re.compile(r'(?:קיבל|קיבלה|מקבל|מקבלת|קבלה|התקבל|התקבלה)', re.UNICODE), ActionCategory.RECEIPT),
    # DELIVERY
    (re.compile(r'(?:שלח|שלחה|שולח|מסר|מסרה|מוסר|הודיע|הודיעה|נשלח|נשלחה|נמסר|נמסרה)', re.UNICODE), ActionCategory.DELIVERY),
    # STATEMENT
    (re.compile(r'(?:אמר|אמרה|הצהיר|הצהירה|טען|טענה|ציין|ציינה|העיד|העידה|מסר\s+עדות)', re.UNICODE), ActionCategory.STATEMENT),
    # DECISION
    (re.compile(r'(?:החליט|החליטה|קבע|קבעה|פסק|פסקה|אישר|אישרה|נקבע|נפסק|הוחלט)', re.UNICODE), ActionCategory.DECISION),
    # CREATION
    (re.compile(r'(?:הקים|הקימה|ייסד|ייסדה|פתח|פתחה|הגיש|הגישה|הוקם|הוקמה|נוסד|נוסדה)', re.UNICODE), ActionCategory.CREATION),
    # TERMINATION
    (re.compile(r'(?:ביטל|ביטלה|סיים|סיימה|פיטר|פיטרה|התפטר|התפטרה|הפסיק|הפסיקה|בוטל|בוטלה|הסתיים)', re.UNICODE), ActionCategory.TERMINATION),
    # EXISTENCE
    (re.compile(r'(?:קיים|קיימת|היה|הייתה|נמצא|נמצאה|שהה|שהתה|התגורר|התגוררה)', re.UNICODE), ActionCategory.EXISTENCE),
    # DAMAGE
    (re.compile(r'(?:ניזוק|ניזוקה|נפגע|נפגעה|נגרם\s+נזק|ניזק|נזק)', re.UNICODE), ActionCategory.DAMAGE),
    # AGREEMENT (includes passive forms and construct state)
    (re.compile(r'(?:הסכים|הסכימה|התחייב|התחייבה|הסכמ[הת]|התחייבות|הבטיח|הבטיחה|הוסכם)', re.UNICODE), ActionCategory.AGREEMENT),
]


# =============================================================================
# Topic Categories (TOPIC)
# =============================================================================

class TopicCategory:
    """Categories of legal objects/topics."""
    CONTRACT = "contract"         # הסכם, חוזה
    PAYMENT_OBJ = "payment_obj"   # תשלום, סכום, כסף, שכר
    PROPERTY = "property"         # נכס, דירה, מקרקעין
    EMPLOYMENT = "employment"     # עבודה, משרה, שכר
    DOCUMENT_OBJ = "document"     # מסמך, מכתב, הודעה
    MEETING = "meeting"           # פגישה, ישיבה, דיון
    ACCIDENT = "accident"         # תאונה, אירוע
    COMPENSATION = "compensation" # פיצוי, פיצויים
    TESTIMONY = "testimony"       # עדות, תצהיר
    RELATIONSHIP = "relationship" # יחסים, קשר
    UNKNOWN = "unknown"


# Hebrew noun -> topic category mapping
_TOPIC_PATTERNS = [
    # CONTRACT
    (re.compile(r'(?:הסכם|חוזה|התקשרות|עסקה)', re.UNICODE), TopicCategory.CONTRACT),
    # PAYMENT_OBJ
    (re.compile(r'(?:תשלום|סכום|כסף|כספים|שכר|משכורת|דמי|עמלה|חשבונית|קבלה)', re.UNICODE), TopicCategory.PAYMENT_OBJ),
    # PROPERTY
    (re.compile(r'(?:נכס|דירה|בית|מקרקעין|קרקע|שטח|מבנה|חנות|משרד)', re.UNICODE), TopicCategory.PROPERTY),
    # EMPLOYMENT
    (re.compile(r'(?:עבודה|משרה|תפקיד|העסקה|פיטורין|פיטורים|התפטרות|יחסי\s+עבודה)', re.UNICODE), TopicCategory.EMPLOYMENT),
    # DOCUMENT_OBJ
    (re.compile(r'(?:מסמך|מכתב|הודעה|דוא"ל|אימייל|פקס|מייל)', re.UNICODE), TopicCategory.DOCUMENT_OBJ),
    # MEETING
    (re.compile(r'(?:פגישה|ישיבה|דיון|שיחה|מפגש)', re.UNICODE), TopicCategory.MEETING),
    # ACCIDENT
    (re.compile(r'(?:תאונה|אירוע|מקרה|נזק|פגיעה)', re.UNICODE), TopicCategory.ACCIDENT),
    # COMPENSATION
    (re.compile(r'(?:פיצוי|פיצויים|שיפוי|גמול|תגמול)', re.UNICODE), TopicCategory.COMPENSATION),
    # TESTIMONY
    (re.compile(r'(?:עדות|תצהיר|הצהרה|גרסה|גירסה)', re.UNICODE), TopicCategory.TESTIMONY),
    # RELATIONSHIP
    (re.compile(r'(?:יחסים|קשר|התקשרות|שיתוף|שותפות)', re.UNICODE), TopicCategory.RELATIONSHIP),
]


# =============================================================================
# Entity Extraction for WHO (lightweight, regex-based)
# =============================================================================

# Legal roles (longer forms first to avoid prefix matching: הנתבעים before הנתבע)
_WHO_ROLE_PATTERN = re.compile(
    r'(?:המבקשים|המשיבים|התובעים|הנתבעים|הנאשמים|העדים|'
    r'הנתבעת|התובעת|המשיבה|הנאשמת|העדה|המומחית|השופטת|'
    r'הנתבע|התובע|המשיב|המערער|המבקש|המערערת|'
    r'הנאשם|העד|המומחה|השופט|'
    r'השוכר|המשכיר|הקונה|המוכר|העובד|המעביד|החייב|הנושה|הערב)',
    re.UNICODE,
)

# Organizations (word boundary: preceded by space/start/ה, not inside another word)
_WHO_ORG_PATTERN = re.compile(
    r'(?:^|(?<=\s))ה?(?:חברת|חברה|עמותת|קרן|בנק|משרד|מוסד|ועד|קופת)\s+'
    r'([\u0590-\u05FF\w]{2,}(?:\s+[\u0590-\u05FF\w]{2,}){0,3})',
    re.UNICODE,
)

# Person names with title
_WHO_PERSON_PATTERN = re.compile(
    r'(?:מר|גב|גברת|עו"ד|ד"ר|פרופ|רו"ח)\s+'
    r'([\u0590-\u05FF]{2,}(?:\s+[\u0590-\u05FF]{2,})?)',
    re.UNICODE,
)

# Role aliases for normalization
_ROLE_ALIASES = {
    "המשיב": "הנתבע",
    "המשיבה": "הנתבעת",
    "המערער": "התובע",
    "המערערת": "התובעת",
    "העותר": "התובע",
    "העותרת": "התובעת",
    "המבקש": "התובע",
    "המבקשת": "התובעת",
    "המשיבים": "הנתבעים",
    "התובעים": "התובעים",
    "הנתבעים": "הנתבעים",
}


# =============================================================================
# Semantic Triplet Dataclass
# =============================================================================

@dataclass
class SemanticTriplet:
    """
    Structured representation of a claim's semantic content.

    WHO did WHAT about TOPIC (WHEN).
    """
    # WHO: normalized entity names involved
    who: List[str] = field(default_factory=list)
    # WHAT: action category (payment, signing, attendance, etc.)
    what: Optional[str] = None
    # WHAT detail: specific matched verb/phrase
    what_detail: Optional[str] = None
    # TOPIC: legal object/topic category
    topic: Optional[str] = None
    # TOPIC detail: specific matched noun/phrase
    topic_detail: Optional[str] = None
    # WHEN: time reference (from enricher or extracted here)
    when: Optional[str] = None

    @property
    def has_who(self) -> bool:
        return bool(self.who)

    @property
    def has_what(self) -> bool:
        return self.what is not None and self.what != ActionCategory.UNKNOWN

    @property
    def has_topic(self) -> bool:
        return self.topic is not None and self.topic != TopicCategory.UNKNOWN

    @property
    def completeness(self) -> float:
        """How complete is this triplet (0-1). Higher = more matchable."""
        score = 0.0
        if self.has_who:
            score += 0.4
        if self.has_what:
            score += 0.35
        if self.has_topic:
            score += 0.25
        return score


# =============================================================================
# Triplet Extraction
# =============================================================================

def extract_triplet(text: str, entities: Optional[List[str]] = None,
                    time_reference: Optional[str] = None) -> SemanticTriplet:
    """
    Extract a semantic triplet (WHO/WHAT/TOPIC/WHEN) from a Hebrew legal claim.

    Uses the pre-computed entities and time_reference from the claim enricher
    when available, falls back to regex extraction.

    Args:
        text: Claim text (Hebrew)
        entities: Pre-extracted entities from claim enricher (optional)
        time_reference: Pre-extracted time reference (optional)

    Returns:
        SemanticTriplet with extracted fields
    """
    triplet = SemanticTriplet()

    # --- WHO ---
    who_set: Set[str] = set()

    # Use pre-extracted entities if available
    if entities:
        for ent in entities:
            normalized = _ROLE_ALIASES.get(ent, ent)
            who_set.add(normalized)

    # Also extract from text directly (catch entities the enricher missed)
    for match in _WHO_ROLE_PATTERN.finditer(text):
        role = match.group()
        normalized = _ROLE_ALIASES.get(role, role)
        who_set.add(normalized)

    for match in _WHO_ORG_PATTERN.finditer(text):
        org = match.group().strip()
        who_set.add(org)

    for match in _WHO_PERSON_PATTERN.finditer(text):
        person = match.group(1).strip() if match.groups() else match.group().strip()
        if len(person) >= 4:  # Filter out noise
            who_set.add(person)

    triplet.who = sorted(who_set)

    # --- WHAT ---
    for pattern, category in _ACTION_PATTERNS:
        m = pattern.search(text)
        if m:
            triplet.what = category
            triplet.what_detail = m.group()
            break

    if triplet.what is None:
        triplet.what = ActionCategory.UNKNOWN

    # --- TOPIC ---
    for pattern, category in _TOPIC_PATTERNS:
        m = pattern.search(text)
        if m:
            triplet.topic = category
            triplet.topic_detail = m.group()
            break

    if triplet.topic is None:
        triplet.topic = TopicCategory.UNKNOWN

    # --- WHEN ---
    triplet.when = time_reference

    return triplet


# =============================================================================
# Triplet Matching
# =============================================================================

# Action categories that are semantically related (cross-match OK)
_ACTION_COMPAT = {
    # Payment <-> Receipt are related actions from different perspectives
    (ActionCategory.PAYMENT, ActionCategory.RECEIPT),
    (ActionCategory.RECEIPT, ActionCategory.PAYMENT),
    # Delivery <-> Receipt
    (ActionCategory.DELIVERY, ActionCategory.RECEIPT),
    (ActionCategory.RECEIPT, ActionCategory.DELIVERY),
    # Signing <-> Agreement
    (ActionCategory.SIGNING, ActionCategory.AGREEMENT),
    (ActionCategory.AGREEMENT, ActionCategory.SIGNING),
    # Creation <-> Termination (opposites about same thing)
    (ActionCategory.CREATION, ActionCategory.TERMINATION),
    (ActionCategory.TERMINATION, ActionCategory.CREATION),
    # Statement <-> Testimony
    (ActionCategory.STATEMENT, ActionCategory.STATEMENT),
}

# Topic categories that are semantically related
_TOPIC_COMPAT = {
    # Contract <-> Payment (payments under a contract)
    (TopicCategory.CONTRACT, TopicCategory.PAYMENT_OBJ),
    (TopicCategory.PAYMENT_OBJ, TopicCategory.CONTRACT),
    # Employment <-> Compensation
    (TopicCategory.EMPLOYMENT, TopicCategory.COMPENSATION),
    (TopicCategory.COMPENSATION, TopicCategory.EMPLOYMENT),
    # Employment <-> Payment
    (TopicCategory.EMPLOYMENT, TopicCategory.PAYMENT_OBJ),
    (TopicCategory.PAYMENT_OBJ, TopicCategory.EMPLOYMENT),
    # Document <-> Testimony
    (TopicCategory.DOCUMENT_OBJ, TopicCategory.TESTIMONY),
    (TopicCategory.TESTIMONY, TopicCategory.DOCUMENT_OBJ),
    # Accident <-> Compensation
    (TopicCategory.ACCIDENT, TopicCategory.COMPENSATION),
    (TopicCategory.COMPENSATION, TopicCategory.ACCIDENT),
}


def _who_overlap(who_a: List[str], who_b: List[str]) -> float:
    """
    Compute WHO overlap between two entity lists.

    Uses fuzzy matching for Hebrew names.
    Returns 0.0 if no overlap, 1.0 if perfect overlap.
    """
    if not who_a or not who_b:
        return 0.0

    set_a = set(who_a)
    set_b = set(who_b)

    # Fast path: exact intersection
    exact = set_a & set_b
    if exact:
        union = set_a | set_b
        return len(exact) / len(union)

    # Fuzzy matching
    matched = 0
    for a in set_a:
        for b in set_b:
            if _entity_fuzzy_match(a, b):
                matched += 1
                break

    if matched == 0:
        return 0.0

    union = len(set_a | set_b)
    return matched / union if union > 0 else 0.0


def _entity_fuzzy_match(a: str, b: str) -> bool:
    """Check if two entity names refer to the same entity (Hebrew-aware)."""
    # Exact
    if a == b:
        return True

    # Normalize aliases
    na = _ROLE_ALIASES.get(a, a)
    nb = _ROLE_ALIASES.get(b, b)
    if na == nb:
        return True

    # Legal roles must match exactly (הנתבע ≠ התובע)
    # They are short, visually similar, but legally opposite
    if _WHO_ROLE_PATTERN.fullmatch(a) or _WHO_ROLE_PATTERN.fullmatch(b):
        return na == nb

    # One contains the other (for org/person names)
    na_lower = na.lower()
    nb_lower = nb.lower()
    if len(na_lower) >= 4 and len(nb_lower) >= 4:
        if na_lower in nb_lower or nb_lower in na_lower:
            return True

    # SequenceMatcher for person names / organizations
    ratio = SequenceMatcher(None, na_lower, nb_lower).ratio()
    return ratio >= 0.80


def _what_match(what_a: Optional[str], what_b: Optional[str]) -> float:
    """
    Compute WHAT (action) compatibility score.

    Returns:
        1.0 if same category
        0.7 if compatible categories
        0.3 if one is UNKNOWN
        0.0 if incompatible
    """
    if what_a is None or what_b is None:
        return 0.3

    if what_a == what_b:
        return 1.0

    if what_a == ActionCategory.UNKNOWN or what_b == ActionCategory.UNKNOWN:
        return 0.3

    if (what_a, what_b) in _ACTION_COMPAT:
        return 0.7

    return 0.0


def _topic_match(topic_a: Optional[str], topic_b: Optional[str]) -> float:
    """
    Compute TOPIC compatibility score.

    Returns:
        1.0 if same topic
        0.6 if compatible topics
        0.3 if one is UNKNOWN
        0.0 if incompatible
    """
    if topic_a is None or topic_b is None:
        return 0.3

    if topic_a == topic_b:
        return 1.0

    if topic_a == TopicCategory.UNKNOWN or topic_b == TopicCategory.UNKNOWN:
        return 0.3

    if (topic_a, topic_b) in _TOPIC_COMPAT:
        return 0.6

    return 0.0


def _when_match(when_a: Optional[str], when_b: Optional[str]) -> float:
    """
    Compute WHEN (time) compatibility score.

    Simple heuristic: if both have time references and they share
    any numeric overlap (same year, same month), score higher.

    Returns:
        1.0 if same time reference
        0.6 if sharing numeric components
        0.5 if one or both are None (neutral)
        0.2 if clearly different
    """
    if when_a is None or when_b is None:
        return 0.5  # Neutral - don't penalize missing time

    if when_a == when_b:
        return 1.0

    # Extract year numbers for quick comparison
    years_a = set(re.findall(r'20\d{2}|19\d{2}', when_a))
    years_b = set(re.findall(r'20\d{2}|19\d{2}', when_b))

    if years_a and years_b:
        if years_a & years_b:
            return 0.8  # Same year
        else:
            return 0.2  # Different years

    # Extract month/day numbers
    nums_a = set(re.findall(r'\d+', when_a))
    nums_b = set(re.findall(r'\d+', when_b))
    if nums_a and nums_b and (nums_a & nums_b):
        return 0.6

    return 0.4  # Can't determine


def triplet_relatedness(t1: SemanticTriplet, t2: SemanticTriplet) -> float:
    """
    Compute semantic relatedness between two triplets.

    This is the core matching function that determines if two claims
    discuss the same subject and should be compared for contradictions.

    The WHO overlap is a required gate — without shared entities,
    no comparison makes sense. WHAT and TOPIC provide the signal.

    Returns:
        0.0 if no WHO overlap (claims are about different entities)
        0.0-1.0 weighted score if WHO overlaps
    """
    # Gate: WHO overlap required
    who_score = _who_overlap(t1.who, t2.who)
    if who_score < 0.01:
        # Special case: if BOTH have no entities (who is empty),
        # fall through to word-based matching (return neutral score)
        if not t1.who and not t2.who:
            # Both have no entities - can't filter, return moderate score
            # to let word-overlap-based matching handle it
            what_score = _what_match(t1.what, t2.what)
            topic_score = _topic_match(t1.topic, t2.topic)
            # Only allow comparison if WHAT and TOPIC strongly match
            combined = 0.5 * what_score + 0.5 * topic_score
            return combined * 0.6  # Cap at 0.6 since no entity evidence
        return 0.0

    # Compute WHAT and TOPIC scores
    what_score = _what_match(t1.what, t2.what)
    topic_score = _topic_match(t1.topic, t2.topic)
    when_score = _when_match(t1.when, t2.when)

    # Weighted combination
    # WHO gate already passed, so we weight the signals
    semantic_score = (
        0.45 * what_score +
        0.35 * topic_score +
        0.20 * when_score
    )

    # Scale by WHO overlap strength
    # Strong entity overlap boosts the score
    who_boost = min(1.0, 0.5 + who_score)

    return semantic_score * who_boost


# =============================================================================
# Batch Triplet Extraction and Matching
# =============================================================================

def extract_claim_triplets(claims: list) -> dict:
    """
    Extract triplets for a list of claims.

    Args:
        claims: List of Claim objects (with .id, .text, .entities, .time_reference)

    Returns:
        Dict mapping claim_id -> SemanticTriplet
    """
    triplets = {}
    for claim in claims:
        cid = getattr(claim, 'id', str(id(claim)))
        text = getattr(claim, 'text', str(claim))
        entities = getattr(claim, 'entities', None)
        time_ref = getattr(claim, 'time_reference', None)

        triplets[cid] = extract_triplet(text, entities, time_ref)

    return triplets


def should_compare_claims(
    claim_a,
    claim_b,
    triplets: Optional[dict] = None,
    threshold: float = 0.20,
) -> Tuple[bool, float]:
    """
    Determine if two claims should be compared for contradictions.

    Uses triplet matching as the primary signal, with a low threshold
    to maintain recall while filtering obviously unrelated pairs.

    Args:
        claim_a: First claim
        claim_b: Second claim
        triplets: Pre-computed triplet dict (claim_id -> SemanticTriplet)
        threshold: Minimum triplet relatedness to allow comparison

    Returns:
        (should_compare, relatedness_score) tuple
    """
    id_a = getattr(claim_a, 'id', str(id(claim_a)))
    id_b = getattr(claim_b, 'id', str(id(claim_b)))

    # Get or extract triplets
    if triplets and id_a in triplets and id_b in triplets:
        t_a = triplets[id_a]
        t_b = triplets[id_b]
    else:
        text_a = getattr(claim_a, 'text', str(claim_a))
        text_b = getattr(claim_b, 'text', str(claim_b))
        entities_a = getattr(claim_a, 'entities', None)
        entities_b = getattr(claim_b, 'entities', None)
        time_a = getattr(claim_a, 'time_reference', None)
        time_b = getattr(claim_b, 'time_reference', None)

        t_a = extract_triplet(text_a, entities_a, time_a)
        t_b = extract_triplet(text_b, entities_b, time_b)

    score = triplet_relatedness(t_a, t_b)
    return score >= threshold, score
