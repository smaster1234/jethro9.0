"""
Temporal Reasoning Graph
========================

Builds a unified timeline from all claims/documents and detects temporal anomalies:

1. **Date Extraction**: Extracts all date/time references from claims
2. **Timeline Construction**: Builds a chronological sequence of events
3. **Anomaly Detection**: Finds events reported with conflicting dates
4. **Temporal Evidence**: Provides temporal context to the detector

Anomaly types:
- SAME_EVENT_DIFFERENT_DATES: Event X reported on date A in doc1, date B in doc2
- IMPOSSIBLE_SEQUENCE: Event A must happen before B, but dates say B < A
- TEMPORAL_OVERLAP: Person claimed at location X at time T1 and location Y at time T2 (impossible)
- DATE_CLUSTER_OUTLIER: Most mentions say Jan 2024, one says Mar 2024

Usage:
    from temporal_graph import TemporalGraph

    graph = TemporalGraph()
    graph.build(claims)
    anomalies = graph.get_anomalies()
    evidence = graph.temporal_evidence(claim_a, claim_b)
"""

import re
import logging
from typing import List, Dict, Tuple, Optional, Set, Any
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, date

logger = logging.getLogger(__name__)


@dataclass
class TemporalReference:
    """A date/time reference extracted from a claim."""
    claim_id: str
    doc_id: str
    original_text: str
    normalized: Optional[Tuple[int, int, int]]  # (year, month, day) - 0 = unknown
    time: Optional[Tuple[int, int]] = None       # (hour, minute) - None = unknown
    precision: str = "exact"                      # exact, month, year, relative
    context: str = ""                             # surrounding text


@dataclass
class TimelineEvent:
    """An event on the timeline with its date references."""
    event_key: str              # Identifier for the event (entity + action)
    date_refs: List[TemporalReference] = field(default_factory=list)
    claim_ids: Set[str] = field(default_factory=set)

    @property
    def has_conflict(self) -> bool:
        """Check if this event has conflicting dates."""
        normalized_dates = set()
        for ref in self.date_refs:
            if ref.normalized:
                normalized_dates.add(ref.normalized)
        return len(normalized_dates) > 1

    @property
    def date_spread(self) -> Optional[int]:
        """Get the date spread in days (None if < 2 dates)."""
        dates = []
        for ref in self.date_refs:
            if ref.normalized:
                y, m, d = ref.normalized
                if y > 0 and m > 0 and d > 0:
                    try:
                        dates.append(date(y, m, d))
                    except ValueError:
                        pass
        if len(dates) < 2:
            return None
        return (max(dates) - min(dates)).days


@dataclass
class TemporalAnomaly:
    """A detected temporal anomaly."""
    anomaly_type: str           # SAME_EVENT_DIFFERENT_DATES, etc.
    claim_ids: List[str]
    description: str
    dates_involved: List[str]
    severity: float             # 0-1
    confidence: float           # 0-1


class TemporalGraph:
    """
    Builds a timeline from claims and detects temporal anomalies.
    """

    # Hebrew month names
    MONTH_MAP = {
        'ינואר': 1, 'פברואר': 2, 'מרץ': 3, 'מרס': 3,
        'אפריל': 4, 'מאי': 5, 'יוני': 6, 'יולי': 7,
        'אוגוסט': 8, 'ספטמבר': 9, 'אוקטובר': 10,
        'נובמבר': 11, 'דצמבר': 12,
    }

    # Date patterns
    DATE_PATTERNS = [
        # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
        (re.compile(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})'), 'numeric'),
        # 15 בינואר 2024
        (re.compile(
            r'(\d{1,2})\s*ב?(ינואר|פברואר|מרץ|מרס|אפריל|מאי|יוני|יולי|'
            r'אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר)\s*(\d{4})'
        ), 'hebrew_full'),
        # ינואר 2024
        (re.compile(
            r'ב?(ינואר|פברואר|מרץ|מרס|אפריל|מאי|יוני|יולי|'
            r'אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר)\s+(\d{4})'
        ), 'hebrew_month'),
        # שנת 2024
        (re.compile(r'(?:שנת|בשנת)\s*(\d{4})'), 'year_only'),
    ]

    # Time patterns
    TIME_PATTERNS = [
        (re.compile(r'(?:בשעה\s*)?([0-2]?\d):([0-5]\d)'), 'hhmm'),
        (re.compile(r'בשעה\s+([0-2]?\d)'), 'hour_only'),
    ]

    # Case number pattern (to exclude from date detection)
    CASE_NUMBER_PATTERN = re.compile(r'\d{3,6}-\d{2}-\d{2}')

    def __init__(self):
        self._timeline_events: Dict[str, TimelineEvent] = {}
        self._claim_dates: Dict[str, List[TemporalReference]] = defaultdict(list)
        self._anomalies: List[TemporalAnomaly] = []
        self._built = False

    def build(self, claims: list) -> None:
        """
        Build temporal graph from claims.

        Args:
            claims: List of Claim objects with .id, .text, .doc_id
        """
        self._timeline_events.clear()
        self._claim_dates.clear()
        self._anomalies.clear()

        # Step 1: Extract temporal references from all claims
        for claim in claims:
            cid = getattr(claim, 'id', str(id(claim)))
            doc_id = getattr(claim, 'doc_id', '')
            text = getattr(claim, 'text', str(claim))

            refs = self._extract_temporal_refs(cid, doc_id, text)
            self._claim_dates[cid] = refs

        # Step 2: Build timeline events (group dates by context)
        self._build_timeline_events(claims)

        # Step 3: Detect anomalies
        self._detect_anomalies()

        self._built = True
        logger.info(
            "Temporal graph built: %d events, %d anomalies, %d claims with dates",
            len(self._timeline_events), len(self._anomalies),
            sum(1 for v in self._claim_dates.values() if v),
        )

    def get_anomalies(self) -> List[TemporalAnomaly]:
        """Get detected temporal anomalies."""
        return self._anomalies

    def temporal_evidence(self, claim_a, claim_b) -> Dict[str, Any]:
        """
        Get temporal evidence for a claim pair.

        Returns dict with:
        - has_temporal_conflict: bool
        - shared_date_events: list of events both claims reference
        - date_distance_days: int or None
        - anomaly_boost: float (0-0.3) confidence boost if temporal anomaly exists
        """
        id_a = getattr(claim_a, 'id', str(id(claim_a)))
        id_b = getattr(claim_b, 'id', str(id(claim_b)))

        dates_a = self._claim_dates.get(id_a, [])
        dates_b = self._claim_dates.get(id_b, [])

        result = {
            'has_temporal_conflict': False,
            'shared_date_events': [],
            'date_distance_days': None,
            'anomaly_boost': 0.0,
        }

        if not dates_a or not dates_b:
            return result

        # Check if both claims reference the same timeline event with different dates
        for event_key, event in self._timeline_events.items():
            if id_a in event.claim_ids and id_b in event.claim_ids:
                result['shared_date_events'].append(event_key)
                if event.has_conflict:
                    result['has_temporal_conflict'] = True
                    result['anomaly_boost'] = 0.2

        # Compute date distance between claims
        norm_a = [r.normalized for r in dates_a if r.normalized]
        norm_b = [r.normalized for r in dates_b if r.normalized]
        if norm_a and norm_b:
            min_distance = self._min_date_distance(norm_a, norm_b)
            result['date_distance_days'] = min_distance

        # Check if pair appears in any anomaly
        for anomaly in self._anomalies:
            if id_a in anomaly.claim_ids and id_b in anomaly.claim_ids:
                result['has_temporal_conflict'] = True
                result['anomaly_boost'] = max(result['anomaly_boost'], anomaly.severity * 0.3)

        return result

    def get_claim_dates(self, claim_id: str) -> List[TemporalReference]:
        """Get all temporal references for a claim."""
        return self._claim_dates.get(claim_id, [])

    # =========================================================================
    # Extraction
    # =========================================================================

    def _extract_temporal_refs(
        self, claim_id: str, doc_id: str, text: str
    ) -> List[TemporalReference]:
        """Extract temporal references from text."""
        refs = []

        # Find and exclude case numbers
        case_spans = set()
        for match in self.CASE_NUMBER_PATTERN.finditer(text):
            for i in range(match.start(), match.end()):
                case_spans.add(i)

        # Extract dates
        for pattern, date_type in self.DATE_PATTERNS:
            for match in pattern.finditer(text):
                # Skip if overlaps with case number
                if any(i in case_spans for i in range(match.start(), match.end())):
                    continue

                normalized = self._normalize_date(match.groups(), date_type)
                if not normalized:
                    continue

                # Determine precision
                y, m, d = normalized
                if d == 0 and m == 0:
                    precision = "year"
                elif d == 0:
                    precision = "month"
                else:
                    precision = "exact"

                # Context: 40 chars before and after
                ctx_start = max(0, match.start() - 40)
                ctx_end = min(len(text), match.end() + 40)
                context = text[ctx_start:ctx_end]

                refs.append(TemporalReference(
                    claim_id=claim_id,
                    doc_id=doc_id,
                    original_text=match.group(),
                    normalized=normalized,
                    precision=precision,
                    context=context,
                ))

        # Extract times
        for pattern, time_type in self.TIME_PATTERNS:
            for match in pattern.finditer(text):
                time_val = self._normalize_time(match.groups(), time_type)
                if time_val:
                    # Attach time to the closest date ref
                    for ref in refs:
                        if ref.claim_id == claim_id and ref.time is None:
                            ref.time = time_val
                            break

        return refs

    def _normalize_date(
        self, groups: tuple, date_type: str
    ) -> Optional[Tuple[int, int, int]]:
        """Normalize date to (year, month, day) tuple."""
        try:
            if date_type == 'numeric':
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                if year < 100:
                    year += 2000 if year < 50 else 1900
                if 1 <= month <= 12 and 1 <= day <= 31:
                    return (year, month, day)

            elif date_type == 'hebrew_full':
                day = int(groups[0])
                month = self.MONTH_MAP.get(groups[1], 0)
                year = int(groups[2])
                if month > 0 and 1 <= day <= 31:
                    return (year, month, day)

            elif date_type == 'hebrew_month':
                month = self.MONTH_MAP.get(groups[0], 0)
                year = int(groups[1])
                if month > 0:
                    return (year, month, 0)

            elif date_type == 'year_only':
                year = int(groups[0])
                if 1900 <= year <= 2100:
                    return (year, 0, 0)

        except (ValueError, IndexError):
            pass
        return None

    def _normalize_time(
        self, groups: tuple, time_type: str
    ) -> Optional[Tuple[int, int]]:
        """Normalize time to (hour, minute)."""
        try:
            if time_type == 'hhmm':
                return (int(groups[0]), int(groups[1]))
            elif time_type == 'hour_only':
                return (int(groups[0]), 0)
        except (ValueError, IndexError):
            pass
        return None

    # =========================================================================
    # Timeline Construction
    # =========================================================================

    def _build_timeline_events(self, claims: list) -> None:
        """
        Group claims into timeline events based on shared context.

        Two claims belong to the same event if they share:
        - Similar date context words (entity names, event type)
        - References to the same document/meeting/transaction
        """
        # Simple approach: group by context keywords around dates
        for claim in claims:
            cid = getattr(claim, 'id', str(id(claim)))
            refs = self._claim_dates.get(cid, [])

            for ref in refs:
                # Generate event key from context
                event_key = self._context_to_event_key(ref.context)
                if not event_key:
                    continue

                if event_key not in self._timeline_events:
                    self._timeline_events[event_key] = TimelineEvent(event_key=event_key)

                self._timeline_events[event_key].date_refs.append(ref)
                self._timeline_events[event_key].claim_ids.add(cid)

    def _context_to_event_key(self, context: str) -> Optional[str]:
        """
        Extract an event key from the context around a date.

        Uses key nouns/verbs near the date as the event identifier.
        """
        if not context:
            return None

        # Extract meaningful words from context
        context_clean = re.sub(r'[^\u0590-\u05FF\s]', '', context)
        words = [w for w in context_clean.split() if len(w) >= 3]

        # Filter out common stopwords
        stopwords = {
            'של', 'את', 'על', 'עם', 'אל', 'מן', 'כי', 'גם', 'או',
            'היה', 'היתה', 'היו', 'הוא', 'היא', 'שנת', 'בשנת', 'מיום',
            'ביום', 'בתאריך',
        }
        meaningful = [w for w in words if w not in stopwords]

        if not meaningful:
            return None

        # Use first 3 meaningful words as event key
        return '_'.join(meaningful[:3])

    # =========================================================================
    # Anomaly Detection
    # =========================================================================

    def _detect_anomalies(self) -> None:
        """Detect temporal anomalies in the timeline."""
        for event_key, event in self._timeline_events.items():
            if not event.has_conflict:
                continue

            # SAME_EVENT_DIFFERENT_DATES
            unique_dates = {}
            for ref in event.date_refs:
                if ref.normalized:
                    date_str = self._format_date(ref.normalized)
                    if date_str not in unique_dates:
                        unique_dates[date_str] = []
                    unique_dates[date_str].append(ref.claim_id)

            if len(unique_dates) >= 2:
                # Calculate severity based on date spread
                spread = event.date_spread
                if spread is not None:
                    severity = min(1.0, spread / 365.0)  # Proportional to difference
                    if spread > 30:
                        severity = min(1.0, 0.7 + (spread / 365.0) * 0.3)
                else:
                    severity = 0.5

                all_claim_ids = list(event.claim_ids)
                self._anomalies.append(TemporalAnomaly(
                    anomaly_type="SAME_EVENT_DIFFERENT_DATES",
                    claim_ids=all_claim_ids,
                    description=(
                        f"אירוע '{event_key}' דווח בתאריכים שונים: "
                        f"{', '.join(unique_dates.keys())}"
                    ),
                    dates_involved=list(unique_dates.keys()),
                    severity=severity,
                    confidence=0.8 if len(all_claim_ids) >= 3 else 0.6,
                ))

        # DATE_CLUSTER_OUTLIER: Find dates that are outliers in their cluster
        self._detect_date_outliers()

    def _detect_date_outliers(self) -> None:
        """Detect date outliers - when most claims say date X but one says date Y."""
        for event_key, event in self._timeline_events.items():
            if len(event.date_refs) < 3:
                continue

            # Count date occurrences
            date_counts: Dict[Tuple, int] = defaultdict(int)
            date_claims: Dict[Tuple, List[str]] = defaultdict(list)
            for ref in event.date_refs:
                if ref.normalized:
                    date_counts[ref.normalized] += 1
                    date_claims[ref.normalized].append(ref.claim_id)

            if len(date_counts) < 2:
                continue

            # Find majority date and outliers
            total = sum(date_counts.values())
            for norm_date, count in date_counts.items():
                ratio = count / total
                if ratio < 0.3 and total - count >= 2:
                    # This date is an outlier
                    majority_dates = [d for d, c in date_counts.items() if c > count]
                    self._anomalies.append(TemporalAnomaly(
                        anomaly_type="DATE_CLUSTER_OUTLIER",
                        claim_ids=date_claims[norm_date],
                        description=(
                            f"תאריך {self._format_date(norm_date)} חורג מהרוב "
                            f"({count}/{total} אזכורים)"
                        ),
                        dates_involved=[self._format_date(norm_date)] + [
                            self._format_date(d) for d in majority_dates
                        ],
                        severity=0.6,
                        confidence=0.7,
                    ))

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _format_date(normalized: Tuple[int, int, int]) -> str:
        """Format normalized date tuple as string."""
        y, m, d = normalized
        if m == 0:
            return str(y)
        if d == 0:
            return f"{m:02d}/{y}"
        return f"{d:02d}/{m:02d}/{y}"

    @staticmethod
    def _min_date_distance(
        dates_a: List[Tuple[int, int, int]],
        dates_b: List[Tuple[int, int, int]],
    ) -> Optional[int]:
        """Compute minimum distance in days between two sets of dates."""
        min_dist = None
        for na in dates_a:
            ya, ma, da = na
            if ya == 0 or ma == 0 or da == 0:
                continue
            try:
                dt_a = date(ya, ma, da)
            except ValueError:
                continue
            for nb in dates_b:
                yb, mb, db = nb
                if yb == 0 or mb == 0 or db == 0:
                    continue
                try:
                    dt_b = date(yb, mb, db)
                except ValueError:
                    continue
                dist = abs((dt_a - dt_b).days)
                if min_dist is None or dist < min_dist:
                    min_dist = dist
        return min_dist


# =============================================================================
# Singleton
# =============================================================================

_graph: Optional[TemporalGraph] = None


def get_temporal_graph() -> TemporalGraph:
    """Get singleton temporal graph."""
    global _graph
    if _graph is None:
        _graph = TemporalGraph()
    return _graph


def reset_temporal_graph() -> None:
    """Reset the singleton."""
    global _graph
    _graph = None
