"""
Contradiction Detector - Rule-based detection for Hebrew legal text
===================================================================

Tier 1 Detection Types (MVP):
1. TEMPORAL_DATE - Date conflicts (verified by normalization)
2. QUANT_AMOUNT - Amount/number conflicts (verified by parsing)
3. ACTOR_ATTRIBUTION - Who did what conflicts
4. PRESENCE_PARTICIPATION - Was/wasn't present, did/didn't do
5. DOCUMENT_EXISTENCE - Document exists/doesn't exist
6. IDENTITY_BASIC - ID number/name conflicts

Status Levels:
- VERIFIED: Deterministically confirmed (normalized values don't match)
- LIKELY: High confidence from pattern matching
- SUSPICIOUS: Candidate that needs review

Approach:
- Rule-based detection with deterministic verification where possible
- Status reflects confidence level based on verification method
"""

import re
import uuid
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime

from .extractor import Claim
from .schemas import (
    Severity,
    ContradictionType,
    ContradictionSubtype,
    ContradictionStatus,
    ContradictionCategory,
    AmbiguityExplanation,
    ClaimEvidence,
    Locator
)

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DetectedContradiction:
    """Internal contradiction representation with full evidence"""
    id: str
    claim1: Claim
    claim2: Claim
    type: ContradictionType
    subtype: Optional[ContradictionSubtype]
    status: ContradictionStatus
    severity: Severity
    confidence: float
    same_event_confidence: float
    explanation: str
    quote1: str
    quote2: str
    normalized1: Optional[str] = None  # Normalized value from claim1
    normalized2: Optional[str] = None  # Normalized value from claim2
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Category fields (hard contradiction vs narrative ambiguity)
    category: Optional[ContradictionCategory] = None
    ambiguity_explanation: Optional[AmbiguityExplanation] = None
    category_badge: Optional[str] = None
    category_label_short: Optional[str] = None

    def to_claim_evidence(self, claim: Claim, quote: str, normalized: Optional[str]) -> ClaimEvidence:
        """Convert to ClaimEvidence schema"""
        locator = None
        if hasattr(claim, 'doc_id') and claim.doc_id:
            locator = Locator(
                doc_id=claim.doc_id,
                page=getattr(claim, 'page', None),
                paragraph=getattr(claim, 'paragraph', None)
            )

        return ClaimEvidence(
            claim_id=claim.id,
            doc_id=getattr(claim, 'doc_id', None),
            locator=locator,
            quote=quote,
            normalized=normalized
        )


@dataclass
class DetectionResult:
    """Result from detection"""
    contradictions: List[DetectedContradiction]
    detection_time_ms: float
    method: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Rule-Based Detector
# =============================================================================

class RuleBasedDetector:
    """
    Rule-based contradiction detector for Hebrew legal text.

    Implements Tier 1 types with deterministic verification:
    - TEMPORAL_DATE: Date normalization and comparison
    - QUANT_AMOUNT: Amount extraction and comparison
    - ACTOR_ATTRIBUTION: NER-like patterns for actors
    - PRESENCE_PARTICIPATION: Polarity detection (yes/no)
    - DOCUMENT_EXISTENCE: Document existence patterns
    - IDENTITY_BASIC: ID number/name patterns
    """

    def __init__(self):
        # Case number patterns - these should NOT be detected as dates
        # Format: NNNNN-NN-NN (e.g., 17682-06-25, תיק 12345-01-22)
        self.case_number_pattern = re.compile(
            r'(?:'
            r'(?:תיק|רמ"ש|ת"א|תמ"ש|רע"א|ע"א|ה"פ|בש"א|ע"ע|ת"ע|ע"מ)\s*'  # Court prefixes
            r')?'
            r'\d{3,6}-\d{2}-\d{2}'  # Case number format
        )

        # Context words that indicate a case number (not a date)
        self.case_context_words = {
            'תיק', 'רמ"ש', 'ת"א', 'תמ"ש', 'רע"א', 'ע"א', 'ה"פ',
            'בש"א', 'ע"ע', 'ת"ע', 'ע"מ', 'הליך', 'תביעה', 'ערעור'
        }

        # Hebrew date patterns
        self.date_patterns = [
            # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
            (r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})', 'numeric', ContradictionSubtype.EXACT_DATE),
            # 15 בינואר 2024
            (r'(\d{1,2})\s*ב?(ינואר|פברואר|מרץ|מרס|אפריל|מאי|יוני|יולי|אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר)\s*(\d{4})',
             'hebrew_full', ContradictionSubtype.EXACT_DATE),
            # ינואר 2024
            (r'ב?(ינואר|פברואר|מרץ|מרס|אפריל|מאי|יוני|יולי|אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר)\s+(\d{4})',
             'hebrew_month', ContradictionSubtype.MONTH_ONLY),
            # שנת 2024
            (r'(?:שנת|בשנת)\s*(\d{4})', 'year_only', ContradictionSubtype.MONTH_ONLY),
        ]

        # Hebrew month names to numbers
        self.month_map = {
            'ינואר': 1, 'פברואר': 2, 'מרץ': 3, 'מרס': 3,
            'אפריל': 4, 'מאי': 5, 'יוני': 6, 'יולי': 7,
            'אוגוסט': 8, 'ספטמבר': 9, 'אוקטובר': 10,
            'נובמבר': 11, 'דצמבר': 12
        }

        # Amount patterns with subtypes
        self.amount_patterns = [
            # ₪10,000 or 10,000 ש"ח
            (r'₪\s*([\d,]+(?:\.\d+)?)', 'shekel', ContradictionSubtype.CURRENCY),
            (r'([\d,]+(?:\.\d+)?)\s*(?:ש״ח|ש"ח|שקלים?|שקל)', 'shekel', ContradictionSubtype.CURRENCY),
            # $10,000 or 10,000 דולר
            (r'\$\s*([\d,]+(?:\.\d+)?)', 'dollar', ContradictionSubtype.CURRENCY),
            (r'([\d,]+(?:\.\d+)?)\s*(?:דולרים?|דולר|\$)', 'dollar', ContradictionSubtype.CURRENCY),
            # Thousands/millions
            (r'([\d,]+)\s*(?:אלף|אלפים)', 'thousands', ContradictionSubtype.CURRENCY),
            (r'([\d,]+)\s*מיליון', 'millions', ContradictionSubtype.CURRENCY),
            # Percentages
            (r'(\d+(?:\.\d+)?)\s*%', 'percent', ContradictionSubtype.PERCENTAGE),
            (r'(\d+(?:\.\d+)?)\s*אחוז', 'percent', ContradictionSubtype.PERCENTAGE),
            # Time periods
            (r'(\d+)\s*(?:שנים?|שנה)', 'years', ContradictionSubtype.DURATION),
            (r'(\d+)\s*(?:חודשים?|חודש)', 'months', ContradictionSubtype.DURATION),
            (r'(\d+)\s*(?:ימים?|יום)', 'days', ContradictionSubtype.DURATION),
            # Counts
            (r'(\d+)\s*(?:פעמים?|פעם)', 'count', ContradictionSubtype.COUNT),
            (r'(\d+)\s*(?:יחידות|יחידה)', 'units', ContradictionSubtype.COUNT),
        ]

        # Attribution patterns with subtypes
        self.attribution_patterns = [
            # Signer patterns
            (r'(\S+)\s+(?:חתם|חתמה|חותם)', ContradictionSubtype.SIGNER),
            # Sender patterns
            (r'(\S+)\s+(?:שלח|שלחה|שולח|מסר|מסרה)', ContradictionSubtype.SENDER),
            # Payer patterns
            (r'(\S+)\s+(?:שילם|שילמה|משלם|העביר|העבירה)', ContradictionSubtype.PAYER),
            # Decision maker patterns
            (r'(\S+)\s+(?:החליט|החליטה|קבע|קבעה|אישר|אישרה)', ContradictionSubtype.DECISION_MAKER),
            # Receiver patterns
            (r'(\S+)\s+(?:קיבל|קיבלה|מקבל)', ContradictionSubtype.RECEIVER),
            # General action
            (r'(?:על ידי|ע"י|באמצעות)\s+(\S+)', ContradictionSubtype.OTHER),
            (r'(\S+)\s+(?:עשה|ביצע|ביצעה|אמר|אמרה|כתב|כתבה)', ContradictionSubtype.OTHER),
        ]

        # Presence/participation patterns (positive and negative)
        self.presence_positive = [
            r'(?:הייתי|היה|הייתה|היו)\s+(?:נוכח|נוכחת|נוכחים|שם)',
            r'(?:נכחתי|נכח|נכחה|נכחו)\s+ב',
            r'(?:השתתפתי|השתתף|השתתפה)\s+ב',
            r'(?:חתמתי|חתם|חתמה)\s+על',
            r'(?:שילמתי|שילם|שילמה)\s+',
            r'(?:קיבלתי|קיבל|קיבלה)\s+',
            r'(?:מסרתי|מסר|מסרה)\s+',
        ]

        self.presence_negative = [
            r'לא\s+(?:הייתי|היה|הייתה|היו)\s+(?:נוכח|נוכחת|נוכחים|שם)',
            r'לא\s+(?:נכחתי|נכח|נכחה|נכחו)',
            r'לא\s+(?:השתתפתי|השתתף|השתתפה)',
            r'לא\s+(?:חתמתי|חתם|חתמה)',
            r'לא\s+(?:שילמתי|שילם|שילמה)',
            r'לא\s+(?:קיבלתי|קיבל|קיבלה)',
            r'לא\s+(?:מסרתי|מסר|מסרה)',
            r'מעולם\s+לא',
            r'אף\s+פעם\s+לא',
        ]

        # Document existence patterns
        self.doc_exists_positive = [
            r'(?:קיים|קיימת|יש)\s+(?:הסכם|חוזה|מסמך|מכתב|הודעה)',
            r'(?:נחתם|נחתמה)\s+(?:הסכם|חוזה)',
            r'(?:נשלח|נשלחה)\s+(?:הודעה|מכתב|דוא"ל|אימייל)',
            r'(?:קיבלתי|קיבל|קיבלה)\s+(?:הודעה|מכתב)',
            r'(?:הסכם|חוזה|מסמך).+(?:נחתם|קיים)',
        ]

        self.doc_exists_negative = [
            r'(?:אין|לא קיים|לא קיימת)\s+(?:הסכם|חוזה|מסמך|מכתב|הודעה)',
            r'לא\s+(?:נחתם|נחתמה)\s+(?:הסכם|חוזה)',
            r'לא\s+(?:נשלח|נשלחה)\s+(?:הודעה|מכתב)',
            r'לא\s+(?:קיבלתי|קיבל|קיבלה)\s+(?:הודעה|מכתב)',
            r'(?:הסכם|חוזה|מסמך).+(?:לא נחתם|אינו קיים)',
        ]

        # Identity patterns (ID numbers, company numbers)
        self.identity_patterns = [
            (r'ת\.?ז\.?\s*[:\-]?\s*(\d{9})', 'id_number'),
            (r'תעודת זהות\s*[:\-]?\s*(\d{9})', 'id_number'),
            (r'ח\.?פ\.?\s*[:\-]?\s*(\d{9})', 'company_id'),
            (r'מספר חברה\s*[:\-]?\s*(\d{9})', 'company_id'),
        ]

        # Hebrew stopwords
        self.stopwords = {
            'את', 'של', 'על', 'עם', 'אל', 'מן', 'כי', 'לא', 'גם', 'או', 'אם',
            'הוא', 'היא', 'הם', 'הן', 'אני', 'אנחנו', 'זה', 'זו', 'זאת',
            'כל', 'כך', 'רק', 'עוד', 'יותר', 'היה', 'היתה', 'היו',
            'ה', 'ו', 'ב', 'ל', 'מ', 'ש', 'כ', 'התובע', 'הנתבע'
        }

    def detect(self, claims: List[Claim]) -> DetectionResult:
        """
        Detect contradictions in claims using rule-based methods.

        Args:
            claims: List of claims to analyze

        Returns:
            DetectionResult with contradictions
        """
        start_time = datetime.now()
        contradictions = []

        logger.info(f"Rule-based detection: analyzing {len(claims)} claims")

        # Tier 1 detection
        temporal = self._detect_temporal(claims)
        contradictions.extend(temporal)

        quantitative = self._detect_quantitative(claims)
        contradictions.extend(quantitative)

        attribution = self._detect_attribution(claims)
        contradictions.extend(attribution)

        presence = self._detect_presence(claims)
        contradictions.extend(presence)

        doc_existence = self._detect_document_existence(claims)
        contradictions.extend(doc_existence)

        identity = self._detect_identity(claims)
        contradictions.extend(identity)

        # Deduplicate
        contradictions = self._deduplicate(contradictions)

        # Apply categorization (hard contradiction vs narrative ambiguity)
        contradictions = self._apply_categorization(contradictions)

        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Count by status
        status_counts = {}
        for c in contradictions:
            status_counts[c.status.value] = status_counts.get(c.status.value, 0) + 1

        logger.info(
            f"Rule-based detection complete: {len(contradictions)} contradictions "
            f"(temporal={len(temporal)}, quant={len(quantitative)}, "
            f"attr={len(attribution)}, presence={len(presence)}, "
            f"doc={len(doc_existence)}, identity={len(identity)}) "
            f"in {elapsed_ms:.1f}ms"
        )

        return DetectionResult(
            contradictions=contradictions,
            detection_time_ms=elapsed_ms,
            method="rule_based",
            metadata={
                "temporal_count": len(temporal),
                "quantitative_count": len(quantitative),
                "attribution_count": len(attribution),
                "presence_count": len(presence),
                "doc_existence_count": len(doc_existence),
                "identity_count": len(identity),
                "claims_analyzed": len(claims),
                "status_counts": status_counts,
                "tier1_count": len(contradictions)
            }
        )

    # =========================================================================
    # T1.1 TEMPORAL_DATE_CONFLICT
    # =========================================================================

    def _detect_temporal(self, claims: List[Claim]) -> List[DetectedContradiction]:
        """Detect temporal (date/time) contradictions - VERIFIED status possible"""
        contradictions = []

        # Extract dates from each claim
        claims_with_dates = []
        for claim in claims:
            dates = self._extract_dates(claim.text)
            if dates:
                claims_with_dates.append((claim, dates))

        # Compare pairs
        for i, (claim1, dates1) in enumerate(claims_with_dates):
            for claim2, dates2 in claims_with_dates[i + 1:]:
                # Check if claims are related
                relatedness = self._claims_relatedness(claim1.text, claim2.text)
                if relatedness < 0.15:
                    continue

                # Check for conflicting dates
                conflict = self._dates_conflict(dates1, dates2)
                if conflict:
                    orig1, norm1, orig2, norm2, subtype = conflict

                    # VERIFIED if normalized dates are deterministically different
                    status = ContradictionStatus.VERIFIED if norm1 != norm2 else ContradictionStatus.LIKELY

                    contradictions.append(DetectedContradiction(
                        id=f"contr_{uuid.uuid4().hex[:8]}",
                        claim1=claim1,
                        claim2=claim2,
                        type=ContradictionType.TEMPORAL_DATE,
                        subtype=subtype,
                        status=status,
                        severity=Severity.HIGH,
                        confidence=0.95 if status == ContradictionStatus.VERIFIED else 0.80,
                        same_event_confidence=relatedness,
                        explanation=f"סתירה בתאריכים: {orig1} לעומת {orig2}",
                        quote1=self._extract_quote_around(claim1.text, orig1),
                        quote2=self._extract_quote_around(claim2.text, orig2),
                        normalized1=self._format_date(norm1),
                        normalized2=self._format_date(norm2),
                        metadata={"date1": orig1, "date2": orig2, "norm1": norm1, "norm2": norm2}
                    ))

        return contradictions

    def _extract_dates(self, text: str) -> List[Tuple[str, Tuple[int, int, int], ContradictionSubtype]]:
        """Extract dates from text with normalized values"""
        dates = []

        # First, find all case numbers to exclude them
        case_number_matches = set()
        for match in self.case_number_pattern.finditer(text):
            case_number_matches.add(match.group())

        # Also check for case number context
        has_case_context = any(word in text for word in self.case_context_words)

        for pattern, date_type, subtype in self.date_patterns:
            for match in re.finditer(pattern, text):
                try:
                    match_text = match.group()

                    # Skip if this looks like a case number
                    if self._is_case_number(text, match.start(), match.end()):
                        continue

                    # Skip if match is part of a case number
                    if any(match_text in cn for cn in case_number_matches):
                        continue

                    groups = match.groups()
                    normalized = self._normalize_date(groups, date_type)
                    if normalized:
                        if isinstance(groups, tuple):
                            original = ' '.join(str(m) for m in groups)
                        else:
                            original = str(groups)
                        dates.append((original, normalized, subtype))
                except Exception:
                    pass

        return dates

    def _is_case_number(self, text: str, start: int, end: int) -> bool:
        """Check if the match at position is actually a case number, not a date."""
        # Check surrounding context (50 chars before)
        context_start = max(0, start - 50)
        context = text[context_start:start]

        # Check for case number indicators in context
        for word in self.case_context_words:
            if word in context:
                return True

        # Check if match follows case number format (NNNNN-NN-NN)
        match_text = text[start:end]
        if re.match(r'^\d{3,6}-\d{2}-\d{2}$', match_text):
            return True

        # Additional check: if the format is NN-NN-NN with first part > 31, it's likely a case
        parts = match_text.split('-')
        if len(parts) == 3:
            try:
                first_num = int(parts[0])
                # If first number > 31 (max days), it's a case number
                if first_num > 31:
                    return True
            except ValueError:
                pass

        return False

    def _normalize_date(self, match: Any, date_type: str) -> Optional[Tuple[int, int, int]]:
        """Normalize date to (year, month, day) tuple"""
        try:
            if date_type == 'numeric':
                day, month, year = int(match[0]), int(match[1]), int(match[2])
                if year < 100:
                    year += 2000 if year < 50 else 1900
                return (year, month, day)

            elif date_type == 'hebrew_full':
                day = int(match[0])
                month = self.month_map.get(match[1], 1)
                year = int(match[2])
                return (year, month, day)

            elif date_type == 'hebrew_month':
                month = self.month_map.get(match[0], 1)
                year = int(match[1])
                return (year, month, 0)  # Day unknown

            elif date_type == 'year_only':
                year = int(match[0]) if isinstance(match, tuple) else int(match)
                return (year, 0, 0)  # Month/day unknown

        except (ValueError, IndexError):
            pass

        return None

    def _dates_conflict(
        self,
        dates1: List[Tuple[str, Tuple[int, int, int], ContradictionSubtype]],
        dates2: List[Tuple[str, Tuple[int, int, int], ContradictionSubtype]]
    ) -> Optional[Tuple[str, Tuple, str, Tuple, ContradictionSubtype]]:
        """Check if two date sets have conflicting dates"""
        for orig1, norm1, sub1 in dates1:
            for orig2, norm2, sub2 in dates2:
                if norm1 and norm2 and norm1 != norm2:
                    y1, m1, d1 = norm1
                    y2, m2, d2 = norm2

                    # Different years = definite conflict
                    if y1 != y2:
                        subtype = sub1 if sub1 == sub2 else ContradictionSubtype.EXACT_DATE
                        return (orig1, norm1, orig2, norm2, subtype)

                    # Different months (if both known)
                    if m1 != m2 and m1 != 0 and m2 != 0:
                        return (orig1, norm1, orig2, norm2, ContradictionSubtype.MONTH_ONLY)

                    # Different days (if both known)
                    if d1 != d2 and d1 != 0 and d2 != 0:
                        return (orig1, norm1, orig2, norm2, ContradictionSubtype.EXACT_DATE)

        return None

    def _format_date(self, date_tuple: Tuple[int, int, int]) -> str:
        """Format date tuple as ISO string"""
        y, m, d = date_tuple
        if m == 0:
            return f"{y}"
        if d == 0:
            return f"{y}-{m:02d}"
        return f"{y}-{m:02d}-{d:02d}"

    # =========================================================================
    # T1.2 QUANT_AMOUNT_CONFLICT
    # =========================================================================

    def _detect_quantitative(self, claims: List[Claim]) -> List[DetectedContradiction]:
        """Detect quantitative (amount/number) contradictions - VERIFIED status possible"""
        contradictions = []

        # Extract amounts from each claim
        claims_with_amounts = []
        for claim in claims:
            amounts = self._extract_amounts(claim.text)
            if amounts:
                claims_with_amounts.append((claim, amounts))

        # Compare pairs
        for i, (claim1, amounts1) in enumerate(claims_with_amounts):
            for claim2, amounts2 in claims_with_amounts[i + 1:]:
                # Check if claims are related
                relatedness = self._claims_relatedness(claim1.text, claim2.text)
                if relatedness < 0.15:
                    continue

                # Check for conflicting amounts of same type
                conflict = self._amounts_conflict(amounts1, amounts2)
                if conflict:
                    val1, val2, amt_type, subtype = conflict

                    # VERIFIED if parsed amounts are deterministically different
                    status = ContradictionStatus.VERIFIED

                    # Severity based on difference magnitude
                    diff_pct = abs(val1 - val2) / max(val1, val2, 1)
                    if diff_pct > 0.5:
                        severity = Severity.HIGH
                    elif diff_pct > 0.2:
                        severity = Severity.MEDIUM
                    else:
                        severity = Severity.LOW

                    contradictions.append(DetectedContradiction(
                        id=f"contr_{uuid.uuid4().hex[:8]}",
                        claim1=claim1,
                        claim2=claim2,
                        type=ContradictionType.QUANT_AMOUNT,
                        subtype=subtype,
                        status=status,
                        severity=severity,
                        confidence=0.90,
                        same_event_confidence=relatedness,
                        explanation=f"סתירה בסכומים: {self._format_amount(val1, amt_type)} לעומת {self._format_amount(val2, amt_type)}",
                        quote1=self._extract_quote_around(claim1.text, str(int(val1))),
                        quote2=self._extract_quote_around(claim2.text, str(int(val2))),
                        normalized1=str(val1),
                        normalized2=str(val2),
                        metadata={"amount1": val1, "amount2": val2, "type": amt_type, "diff_pct": diff_pct}
                    ))

        return contradictions

    def _extract_amounts(self, text: str) -> List[Tuple[float, str, ContradictionSubtype]]:
        """Extract amounts from text with type"""
        amounts = []

        for pattern, amt_type, subtype in self.amount_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    num_str = match if isinstance(match, str) else match[0]
                    num_str = num_str.replace(',', '')
                    value = float(num_str)

                    # Apply multipliers
                    if amt_type == 'thousands':
                        value *= 1000
                        amt_type = 'shekel'  # Normalize type
                    elif amt_type == 'millions':
                        value *= 1000000
                        amt_type = 'shekel'

                    amounts.append((value, amt_type, subtype))
                except (ValueError, IndexError):
                    pass

        return amounts

    def _amounts_conflict(
        self,
        amounts1: List[Tuple[float, str, ContradictionSubtype]],
        amounts2: List[Tuple[float, str, ContradictionSubtype]]
    ) -> Optional[Tuple[float, float, str, ContradictionSubtype]]:
        """Check if two amount sets conflict"""
        for val1, type1, sub1 in amounts1:
            for val2, type2, sub2 in amounts2:
                # Same type but different value (>10% difference)
                if type1 == type2 and val1 != val2:
                    diff = abs(val1 - val2) / max(val1, val2, 1)
                    if diff > 0.1:
                        return (val1, val2, type1, sub1)

        return None

    def _format_amount(self, value: float, amt_type: str) -> str:
        """Format amount for display"""
        if amt_type in ('shekel', 'thousands', 'millions'):
            return f"₪{value:,.0f}"
        elif amt_type == 'dollar':
            return f"${value:,.0f}"
        elif amt_type == 'percent':
            return f"{value}%"
        else:
            return f"{value:,.0f}"

    # =========================================================================
    # T1.3 ACTOR_ATTRIBUTION_CONFLICT
    # =========================================================================

    def _detect_attribution(self, claims: List[Claim]) -> List[DetectedContradiction]:
        """Detect attribution (who did what) contradictions"""
        contradictions = []

        # Extract attributions from each claim
        claims_with_attr = []
        for claim in claims:
            attributions = self._extract_attributions(claim.text)
            if attributions:
                claims_with_attr.append((claim, attributions))

        # Compare pairs
        for i, (claim1, attr1) in enumerate(claims_with_attr):
            for claim2, attr2 in claims_with_attr[i + 1:]:
                # Check if claims are related (same event/action)
                relatedness = self._claims_relatedness(claim1.text, claim2.text)
                if relatedness < 0.15:
                    continue

                # Check for conflicting attributions of same action type
                conflict = self._attributions_conflict(attr1, attr2)
                if conflict:
                    actors1, actors2, subtype = conflict

                    # LIKELY status - NER-based, not fully deterministic
                    status = ContradictionStatus.LIKELY

                    contradictions.append(DetectedContradiction(
                        id=f"contr_{uuid.uuid4().hex[:8]}",
                        claim1=claim1,
                        claim2=claim2,
                        type=ContradictionType.ACTOR_ATTRIBUTION,
                        subtype=subtype,
                        status=status,
                        severity=Severity.HIGH,
                        confidence=0.75,
                        same_event_confidence=relatedness,
                        explanation=f"סתירה בייחוס: {', '.join(actors1)} לעומת {', '.join(actors2)}",
                        quote1=claim1.text[:200],
                        quote2=claim2.text[:200],
                        normalized1=', '.join(actors1),
                        normalized2=', '.join(actors2),
                        metadata={"actors1": actors1, "actors2": actors2}
                    ))

        return contradictions

    def _extract_attributions(self, text: str) -> List[Tuple[str, ContradictionSubtype]]:
        """Extract attributions (who did what) from text"""
        attributions = []

        for pattern, subtype in self.attribution_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                name = match.strip() if isinstance(match, str) else match[0].strip()

                # Filter out stopwords and short matches
                if name and len(name) > 2 and name.lower() not in self.stopwords:
                    attributions.append((name, subtype))

        return attributions

    def _attributions_conflict(
        self,
        attr1: List[Tuple[str, ContradictionSubtype]],
        attr2: List[Tuple[str, ContradictionSubtype]]
    ) -> Optional[Tuple[List[str], List[str], ContradictionSubtype]]:
        """Check for conflicting attributions"""
        # Group by subtype
        by_subtype1: Dict[ContradictionSubtype, Set[str]] = {}
        by_subtype2: Dict[ContradictionSubtype, Set[str]] = {}

        for name, subtype in attr1:
            if subtype not in by_subtype1:
                by_subtype1[subtype] = set()
            by_subtype1[subtype].add(name.lower())

        for name, subtype in attr2:
            if subtype not in by_subtype2:
                by_subtype2[subtype] = set()
            by_subtype2[subtype].add(name.lower())

        # Check for conflicts in same subtype
        for subtype in by_subtype1:
            if subtype in by_subtype2:
                set1 = by_subtype1[subtype]
                set2 = by_subtype2[subtype]

                # Conflict if no overlap
                if set1 and set2 and not (set1 & set2):
                    return (list(set1), list(set2), subtype)

        return None

    # =========================================================================
    # T1.4 PRESENCE_PARTICIPATION_CONFLICT
    # =========================================================================

    def _detect_presence(self, claims: List[Claim]) -> List[DetectedContradiction]:
        """Detect presence/participation contradictions (did/didn't)"""
        contradictions = []

        # Tag claims with presence polarity
        claims_with_presence = []
        for claim in claims:
            polarity = self._extract_presence_polarity(claim.text)
            if polarity is not None:
                claims_with_presence.append((claim, polarity))

        # Compare pairs
        for i, (claim1, pol1) in enumerate(claims_with_presence):
            for claim2, pol2 in claims_with_presence[i + 1:]:
                # Check if claims are related
                relatedness = self._claims_relatedness(claim1.text, claim2.text)
                if relatedness < 0.20:  # Higher threshold for presence
                    continue

                # Conflict if opposite polarity
                if pol1 != pol2:
                    # Determine subtype from action
                    subtype = self._determine_presence_subtype(claim1.text, claim2.text)

                    # LIKELY status - polarity detection is pattern-based
                    status = ContradictionStatus.LIKELY

                    contradictions.append(DetectedContradiction(
                        id=f"contr_{uuid.uuid4().hex[:8]}",
                        claim1=claim1,
                        claim2=claim2,
                        type=ContradictionType.PRESENCE_PARTICIPATION,
                        subtype=subtype,
                        status=status,
                        severity=Severity.HIGH,
                        confidence=0.80,
                        same_event_confidence=relatedness,
                        explanation=f"סתירה בנוכחות/ביצוע: {'חיובי' if pol1 else 'שלילי'} לעומת {'חיובי' if pol2 else 'שלילי'}",
                        quote1=claim1.text[:200],
                        quote2=claim2.text[:200],
                        normalized1="positive" if pol1 else "negative",
                        normalized2="positive" if pol2 else "negative",
                        metadata={"polarity1": pol1, "polarity2": pol2}
                    ))

        return contradictions

    def _extract_presence_polarity(self, text: str) -> Optional[bool]:
        """Extract presence polarity: True=positive, False=negative, None=unknown"""
        # Check negative first (more specific)
        for pattern in self.presence_negative:
            if re.search(pattern, text):
                return False

        # Then check positive
        for pattern in self.presence_positive:
            if re.search(pattern, text):
                return True

        return None

    def _determine_presence_subtype(self, text1: str, text2: str) -> ContradictionSubtype:
        """Determine presence subtype from action keywords"""
        combined = text1 + " " + text2

        if re.search(r'חתם|חתימה', combined):
            return ContradictionSubtype.SIGNED
        elif re.search(r'שילם|תשלום', combined):
            return ContradictionSubtype.PAID
        elif re.search(r'נוכח|נכח|השתתף', combined):
            return ContradictionSubtype.ATTENDED
        elif re.search(r'קיבל|קבלה', combined):
            return ContradictionSubtype.RECEIVED
        elif re.search(r'מסר|מסירה', combined):
            return ContradictionSubtype.DELIVERED

        return ContradictionSubtype.ATTENDED

    # =========================================================================
    # T1.5 DOCUMENT_EXISTENCE_CONFLICT
    # =========================================================================

    def _detect_document_existence(self, claims: List[Claim]) -> List[DetectedContradiction]:
        """Detect document existence contradictions"""
        contradictions = []

        # Tag claims with document existence polarity
        claims_with_doc = []
        for claim in claims:
            polarity = self._extract_doc_existence_polarity(claim.text)
            if polarity is not None:
                claims_with_doc.append((claim, polarity))

        # Compare pairs
        for i, (claim1, pol1) in enumerate(claims_with_doc):
            for claim2, pol2 in claims_with_doc[i + 1:]:
                # Check if claims are related (same document type)
                relatedness = self._claims_relatedness(claim1.text, claim2.text)
                if relatedness < 0.20:
                    continue

                # Conflict if opposite polarity
                if pol1 != pol2:
                    # Determine subtype from document type
                    subtype = self._determine_doc_subtype(claim1.text, claim2.text)

                    # LIKELY status - pattern based
                    status = ContradictionStatus.LIKELY

                    contradictions.append(DetectedContradiction(
                        id=f"contr_{uuid.uuid4().hex[:8]}",
                        claim1=claim1,
                        claim2=claim2,
                        type=ContradictionType.DOCUMENT_EXISTENCE,
                        subtype=subtype,
                        status=status,
                        severity=Severity.HIGH,
                        confidence=0.80,
                        same_event_confidence=relatedness,
                        explanation=f"סתירה בקיום מסמך: {'קיים' if pol1 else 'לא קיים'} לעומת {'קיים' if pol2 else 'לא קיים'}",
                        quote1=claim1.text[:200],
                        quote2=claim2.text[:200],
                        normalized1="exists" if pol1 else "not_exists",
                        normalized2="exists" if pol2 else "not_exists",
                        metadata={"exists1": pol1, "exists2": pol2}
                    ))

        return contradictions

    def _extract_doc_existence_polarity(self, text: str) -> Optional[bool]:
        """Extract document existence polarity"""
        # Check negative first
        for pattern in self.doc_exists_negative:
            if re.search(pattern, text):
                return False

        # Then positive
        for pattern in self.doc_exists_positive:
            if re.search(pattern, text):
                return True

        return None

    def _determine_doc_subtype(self, text1: str, text2: str) -> ContradictionSubtype:
        """Determine document subtype"""
        combined = text1 + " " + text2

        if re.search(r'הסכם|חוזה', combined):
            return ContradictionSubtype.CONTRACT_EXISTS
        elif re.search(r'הודעה|מכתב', combined):
            return ContradictionSubtype.NOTICE_SENT
        elif re.search(r'דוא"ל|אימייל|מייל', combined):
            return ContradictionSubtype.EMAIL_EXISTS
        elif re.search(r'חתימה', combined):
            return ContradictionSubtype.SIGNATURE_EXISTS

        return ContradictionSubtype.CONTRACT_EXISTS

    # =========================================================================
    # T1.6 IDENTITY_BASIC_CONFLICT
    # =========================================================================

    def _detect_identity(self, claims: List[Claim]) -> List[DetectedContradiction]:
        """Detect basic identity conflicts (ID numbers)"""
        contradictions = []

        # Extract identities from each claim
        claims_with_id = []
        for claim in claims:
            identities = self._extract_identities(claim.text)
            if identities:
                claims_with_id.append((claim, identities))

        # Compare pairs
        for i, (claim1, ids1) in enumerate(claims_with_id):
            for claim2, ids2 in claims_with_id[i + 1:]:
                # Check if claims are related
                relatedness = self._claims_relatedness(claim1.text, claim2.text)
                if relatedness < 0.15:
                    continue

                # Check for conflicting IDs of same type
                conflict = self._identities_conflict(ids1, ids2)
                if conflict:
                    id1, id2, id_type = conflict

                    # VERIFIED if ID numbers are deterministically different
                    status = ContradictionStatus.VERIFIED

                    contradictions.append(DetectedContradiction(
                        id=f"contr_{uuid.uuid4().hex[:8]}",
                        claim1=claim1,
                        claim2=claim2,
                        type=ContradictionType.IDENTITY_BASIC,
                        subtype=ContradictionSubtype.OTHER,
                        status=status,
                        severity=Severity.CRITICAL,
                        confidence=0.95,
                        same_event_confidence=relatedness,
                        explanation=f"סתירה במספר זיהוי: {id1} לעומת {id2}",
                        quote1=self._extract_quote_around(claim1.text, id1),
                        quote2=self._extract_quote_around(claim2.text, id2),
                        normalized1=id1,
                        normalized2=id2,
                        metadata={"id1": id1, "id2": id2, "type": id_type}
                    ))

        return contradictions

    def _extract_identities(self, text: str) -> List[Tuple[str, str]]:
        """Extract identity numbers from text"""
        identities = []

        for pattern, id_type in self.identity_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                id_num = match if isinstance(match, str) else match[0]
                identities.append((id_num, id_type))

        return identities

    def _identities_conflict(
        self,
        ids1: List[Tuple[str, str]],
        ids2: List[Tuple[str, str]]
    ) -> Optional[Tuple[str, str, str]]:
        """Check for conflicting identities"""
        for id1, type1 in ids1:
            for id2, type2 in ids2:
                if type1 == type2 and id1 != id2:
                    return (id1, id2, type1)

        return None

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _claims_relatedness(self, text1: str, text2: str) -> float:
        """Calculate relatedness score between two claims (0-1)"""
        words1 = self._get_meaningful_words(text1)
        words2 = self._get_meaningful_words(text2)

        if not words1 or not words2:
            return 0.5  # Uncertain

        common = words1 & words2
        min_len = min(len(words1), len(words2))

        if min_len == 0:
            return 0.5

        return len(common) / min_len

    def _claims_related(self, text1: str, text2: str) -> bool:
        """Check if two claims are related (legacy method)"""
        return self._claims_relatedness(text1, text2) > 0.15

    def _get_meaningful_words(self, text: str) -> set:
        """Extract meaningful words from text"""
        words = set()
        for word in text.lower().split():
            word = re.sub(r'[^\w\s]', '', word)
            if len(word) >= 3 and word not in self.stopwords:
                words.add(word)
        return words

    def _extract_quote_around(self, text: str, target: str, context_chars: int = 50) -> str:
        """Extract context around a target string"""
        idx = text.find(target)
        if idx == -1:
            return text[:200]

        start = max(0, idx - context_chars)
        end = min(len(text), idx + len(target) + context_chars)

        quote = text[start:end]
        if start > 0:
            quote = "..." + quote
        if end < len(text):
            quote = quote + "..."

        return quote

    def _deduplicate(
        self,
        contradictions: List[DetectedContradiction]
    ) -> List[DetectedContradiction]:
        """Remove duplicate contradictions"""
        seen = set()
        unique = []

        for contr in contradictions:
            # Key by claim pair (sorted) and type
            key = (
                tuple(sorted([contr.claim1.id, contr.claim2.id])),
                contr.type
            )

            if key not in seen:
                seen.add(key)
                unique.append(contr)

        return unique

    def _apply_categorization(
        self,
        contradictions: List[DetectedContradiction]
    ) -> List[DetectedContradiction]:
        """
        Apply categorization to distinguish hard contradictions from narrative ambiguity.

        For each contradiction, determines if it's a:
        - HARD_CONTRADICTION: Clear factual conflict, both claims cannot be true
        - LOGICAL_INCONSISTENCY: Logically incompatible statements
        - NARRATIVE_AMBIGUITY: Apparent discrepancy with possible reconciliation
        - RHETORICAL_SHIFT: Change in emphasis without factual contradiction
        """
        from .categorizer import categorize_contradiction

        categorized = []

        for contr in contradictions:
            # Get categorization result
            result = categorize_contradiction(
                claim1_text=contr.claim1.text,
                claim2_text=contr.claim2.text,
                contradiction_type=contr.type,
                normalized1=contr.normalized1,
                normalized2=contr.normalized2,
                metadata=contr.metadata
            )

            # Apply category
            contr.category = result.category
            contr.category_badge = result.badge
            contr.category_label_short = result.label_short

            # For narrative ambiguity, set explanation and possibly adjust severity
            if result.ambiguity_explanation:
                contr.ambiguity_explanation = result.ambiguity_explanation

            # Adjust severity for ambiguity (lower than hard contradictions)
            if result.severity_adjustment and result.category == ContradictionCategory.NARRATIVE_AMBIGUITY:
                contr.severity = result.severity_adjustment

            # Update explanation for narrative ambiguity - don't use "both can't be true"
            if result.category == ContradictionCategory.NARRATIVE_AMBIGUITY:
                contr.explanation = self._build_ambiguity_explanation(contr, result)

            categorized.append(contr)

            logger.debug(
                f"Categorized {contr.id}: {result.category.value} - {result.reasoning[:50]}"
            )

        return categorized

    def _build_ambiguity_explanation(
        self,
        contr: DetectedContradiction,
        result: 'CategorizationResult'
    ) -> str:
        """Build explanation text for narrative ambiguity (avoids 'both cannot be true' phrase)"""
        # For ambiguity, use softer language
        if contr.type == ContradictionType.QUANT_AMOUNT:
            return f"פער מספרי: {contr.normalized1} לעומת {contr.normalized2}. {result.reasoning}"
        elif contr.type == ContradictionType.TEMPORAL_DATE:
            return f"אי-התאמה בתאריכים: {contr.normalized1} לעומת {contr.normalized2}. {result.reasoning}"
        else:
            return f"אי-עקביות נרטיבית: {result.reasoning}"


# =============================================================================
# Singleton & Convenience Functions
# =============================================================================

_detector = None

def get_rule_detector() -> RuleBasedDetector:
    """Get singleton detector instance"""
    global _detector
    if _detector is None:
        _detector = RuleBasedDetector()
    return _detector


def detect_contradictions(claims: List[Claim]) -> DetectionResult:
    """
    Convenience function to detect contradictions.

    Args:
        claims: List of claims

    Returns:
        DetectionResult
    """
    return get_rule_detector().detect(claims)
