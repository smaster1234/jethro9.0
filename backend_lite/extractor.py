"""
Claim Extractor - Extract claims from Hebrew legal text
========================================================

Rule-based claim extraction with context enrichment:
1. Sanitize input (remove report/meta sections)
2. Split text into paragraphs/sentences
3. Normalize Hebrew text
4. Filter signatures/contact info
5. Enrich with context window, speaker, plane, time, modality
6. Return enriched Claim objects
"""

import re
import uuid
from typing import List, Optional, Set, Dict, Any
from dataclasses import dataclass, field

# Import from sanitize module
from .sanitize import (
    sanitize_input,
    contains_system_text,
    is_signature_block,
    sanitize_claim_text,
    SYSTEM_MARKERS,
    SIGNATURE_PATTERNS
)

# Re-export for backwards compatibility
__all__ = [
    'Claim',
    'ClaimExtractor',
    'extract_claims',
    'get_extractor',
    'sanitize_input',
    'contains_system_text',
    'SYSTEM_MARKERS'
]


# ---------------------------------------------------------------------------
# Plane / Speaker / Modality constants
# ---------------------------------------------------------------------------
PLANE_FACT = "FACT"
PLANE_LAW = "LAW"
PLANE_OPINION = "OPINION"
PLANE_PROCEDURAL = "PROCEDURAL"

SPEAKER_MODE_FINDING = "finding"
SPEAKER_MODE_PARTY_CLAIM = "party_claim"
SPEAKER_MODE_QUOTE = "quote"
SPEAKER_MODE_LAW_CITATION = "law_citation"
SPEAKER_MODE_OPINION = "opinion"

MODALITY_CERTAIN = "certain"
MODALITY_POSSIBLE = "possible"
MODALITY_OBLIGATION = "obligation"
MODALITY_PERMISSION = "permission"
MODALITY_UNCERTAIN = "uncertain"


@dataclass
class Claim:
    """
    Enriched claim representation for detection.

    Includes:
    - Core text and locator fields (backward compatible)
    - Context window (sentences before/after)
    - Speaker / role / speaker_mode
    - Plane (FACT/LAW/OPINION/PROCEDURAL)
    - Time reference and modality
    - Scope/quantifiers, entities, negation
    - Confidence of extraction
    """
    id: str
    text: str
    source: Optional[str] = None
    page: Optional[int] = None
    block_index: Optional[int] = None
    speaker: Optional[str] = None

    # Locator fields for evidence
    doc_id: Optional[str] = None
    paragraph_id: Optional[str] = None
    paragraph_index: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    bbox: Optional[Dict[str, Any]] = None

    # For detection
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None

    # Metadata
    metadata: dict = field(default_factory=dict)

    # --- V2 enrichment fields ---
    # Normalized claim text for comparison
    normalized_claim: Optional[str] = None
    # Context: 1-3 sentences before / after
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    # Section / heading path
    section_path: Optional[str] = None
    # Speaker role
    speaker_role: Optional[str] = None          # court / plaintiff / defendant / witness / counsel / external
    speaker_mode: Optional[str] = None          # finding / party_claim / quote / law_citation / opinion
    # Plane
    plane: Optional[str] = None                 # FACT / LAW / OPINION / PROCEDURAL
    # Time
    time_reference: Optional[str] = None        # date/period text extracted
    # Modality
    modality: Optional[str] = None              # certain / possible / obligation / permission / uncertain
    # Scope / quantifiers
    scope_quantifiers: Optional[str] = None     # all/part/always/usually/conditional
    # Entities and relations
    entities: List[str] = field(default_factory=list)
    relations: Optional[str] = None             # "who did what to whom" summary
    # Negation
    negation: bool = False
    # Extraction confidence
    confidence_extraction: float = 1.0
    
    # --- V3 Source classification fields ---
    # Document ownership and source type for cross-examination
    source_type: Optional[str] = None              # witness_own_statement / supporting_witness / party_pleading / opposing_evidence / court_finding / external_document
    doc_owner_party: Optional[str] = None          # plaintiff / defendant - מי הגיש את המסמך
    doc_owner_name: Optional[str] = None           # שם בעל המסמך (עד, צד)
    doc_date: Optional[str] = None                 # תאריך המסמך
    is_examined_witness_doc: bool = False          # האם זה מסמך של העד הנחקר

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "source": self.source,
            "page": self.page,
            "block_index": self.block_index,
            "speaker": self.speaker,
            "doc_id": self.doc_id,
            "paragraph_id": self.paragraph_id,
            "paragraph_index": self.paragraph_index,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "bbox": self.bbox,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "metadata": self.metadata,
            # V2 fields
            "normalized_claim": self.normalized_claim,
            "context_before": self.context_before,
            "context_after": self.context_after,
            "section_path": self.section_path,
            "speaker_role": self.speaker_role,
            "speaker_mode": self.speaker_mode,
            "plane": self.plane,
            "time_reference": self.time_reference,
            "modality": self.modality,
            "scope_quantifiers": self.scope_quantifiers,
            "entities": self.entities,
            "relations": self.relations,
            "negation": self.negation,
            "confidence_extraction": self.confidence_extraction,
            # V3 source classification fields
            "source_type": self.source_type,
            "doc_owner_party": self.doc_owner_party,
            "doc_owner_name": self.doc_owner_name,
            "doc_date": self.doc_date,
            "is_examined_witness_doc": self.is_examined_witness_doc,
        }


class ClaimExtractor:
    """
    Extract claims from Hebrew legal text.

    Strategies:
    1. Paragraph-based: Each paragraph = one claim
    2. Sentence-based: Each sentence = one claim
    3. Numbered clauses: Legal document numbered sections

    Features:
    - Input sanitization (removes report/meta sections)
    - Signature/contact info filtering
    - Sentence-level splitting for long paragraphs
    """

    # Maximum characters for a single claim before splitting
    MAX_CLAIM_LENGTH = 500

    def __init__(self):
        # Hebrew sentence endings (including Hebrew period maqaf)
        self.sentence_pattern = re.compile(r'[.!?:](?:\s|$)')

        # Case number pattern — must NOT be split as sentence boundary
        # Matches: 17682-06-25, ת"א 12345-01-22, ע"א 5678/20
        self._case_number_re = re.compile(
            r'(?:ת"א|רמ"ש|תמ"ש|רע"א|ע"א|ה"פ|בש"א|ע"ע|ת"ע|ע"מ|תיק)\s*'
            r'(?:\d{3,6}[-/]\d{2}[-/]\d{2}|\d{3,6}/\d{2,4})'
        )

        # Numbered clause pattern (e.g., "1.", "1.1", "א.", "א.1")
        self.clause_pattern = re.compile(
            r'^[\s]*'
            r'(?:'
            r'\d+(?:\.\d+)*\.?'   # 1. 1.1 1.1.1
            r'|[א-ת](?:\.\d+)?\.?'  # א. א.1
            r')'
            r'[\s]+'
        )

        # Paragraph indicators
        self.paragraph_pattern = re.compile(r'\n\s*\n')

        # Hebrew stopwords for filtering empty claims
        self.min_meaningful_words = 3
        self.stopwords = {
            'את', 'של', 'על', 'עם', 'אל', 'מן', 'כי', 'לא', 'גם', 'או', 'אם',
            'הוא', 'היא', 'הם', 'הן', 'אני', 'אנחנו', 'אתה', 'אתם',
            'זה', 'זו', 'זאת', 'אלה', 'כל', 'כך', 'רק', 'עוד', 'יותר',
            'היה', 'היתה', 'היו', 'יהיה', 'להיות',
            'ה', 'ו', 'ב', 'ל', 'מ', 'ש', 'כ'
        }

    def extract_from_text(
        self,
        text: str,
        source_name: str = "document",
        strategy: str = "auto",
        doc_id: Optional[str] = None,
        paragraph_id: Optional[str] = None,
        paragraph_index: Optional[int] = None,
        char_offset: int = 0,
        page_no: Optional[int] = None,
        block_index: Optional[int] = None,
        bbox: Optional[Dict[str, Any]] = None,
        sanitize: bool = True,
    ) -> List[Claim]:
        """
        Extract claims from free text.

        Args:
            text: Hebrew text to analyze
            source_name: Name of source document
            strategy: "auto", "paragraph", "sentence", "clause"
            doc_id: Document ID for locator
            paragraph_id: Paragraph ID for locator
            paragraph_index: Paragraph index for locator
            char_offset: Character offset for locators (for nested extraction)

        Returns:
            List of Claim objects
        """
        if not text or not text.strip():
            return []

        # STEP 1: Sanitize input - remove report/meta sections
        if sanitize:
            text = sanitize_input(text)
            if not text:
                return []

        # Normalize text (positions are computed on normalized text)
        text = self._normalize_text(text)
        if not text:
            return []

        # Store normalized text for position tracking
        original_text = text

        # Choose extraction strategy
        if strategy == "auto":
            strategy = self._detect_strategy(text)

        # Extract based on strategy
        if strategy == "clause":
            segments = self._split_by_clauses(text)
        elif strategy == "sentence":
            segments = self._split_by_sentences(text)
        else:  # paragraph
            segments = self._split_by_paragraphs(text)

        # Convert to claims
        claims = []
        current_pos = 0
        for i, segment in enumerate(segments, 1):
            segment = segment.strip()

            # Skip empty or too short segments
            if not self._is_meaningful(segment):
                continue

            # Find position in original text
            seg_start = original_text.find(segment, current_pos)
            if seg_start == -1:
                seg_start = current_pos
            seg_end = seg_start + len(segment)
            current_pos = seg_end

            claim = Claim(
                id=f"claim_{i}",
                text=segment,
                source=source_name,
                page=page_no,
                block_index=block_index,
                speaker=None,  # Can be enhanced with speaker detection
                doc_id=doc_id,
                paragraph_id=paragraph_id,
                paragraph_index=paragraph_index,
                char_start=char_offset + seg_start,
                char_end=char_offset + seg_end,
                bbox=bbox,
                metadata={
                    "extraction_strategy": strategy,
                    "segment_index": i
                }
            )
            claims.append(claim)

        return claims

    def extract_from_claims_input(
        self,
        claims_input: List[dict]
    ) -> List[Claim]:
        """
        Convert input claim dicts to Claim objects.

        Args:
            claims_input: List of claim dictionaries

        Returns:
            List of Claim objects
        """
        claims = []
        for i, item in enumerate(claims_input, 1):
            claim_id = item.get("id") or f"claim_{i}"
            claim = Claim(
                id=claim_id,
                text=item.get("text", ""),
                source=item.get("source"),
                page=item.get("page"),
                block_index=item.get("block_index"),
                speaker=item.get("speaker"),
                doc_id=item.get("doc_id"),
                paragraph_id=item.get("paragraph_id"),
                paragraph_index=(
                    item.get("paragraph_index")
                    if item.get("paragraph_index") is not None
                    else item.get("paragraph")
                ),
                char_start=item.get("char_start"),
                char_end=item.get("char_end"),
                bbox=item.get("bbox"),
                metadata=item.get("metadata", {})
            )

            if self._is_meaningful(claim.text):
                claims.append(claim)

        return claims

    def _normalize_text(self, text: str) -> str:
        """Normalize Hebrew text"""
        # Remove extra whitespace
        text = re.sub(r'[ \t]+', ' ', text)

        # Normalize line endings
        text = re.sub(r'\r\n', '\n', text)

        # Remove page markers if present
        text = re.sub(r'---\s*עמוד\s*\d+\s*---', '\n\n', text)

        # Normalize Hebrew punctuation
        text = text.replace('״', '"').replace('׳', "'")

        return text.strip()

    def _detect_strategy(self, text: str) -> str:
        """Auto-detect best extraction strategy"""
        # Check for numbered clauses
        clause_matches = self.clause_pattern.findall(text)
        if len(clause_matches) >= 3:
            return "clause"

        # Check for clear paragraph structure
        paragraphs = self.paragraph_pattern.split(text)
        meaningful_paragraphs = [p for p in paragraphs if self._is_meaningful(p)]

        if len(meaningful_paragraphs) >= 3:
            # Check average paragraph length
            avg_len = sum(len(p) for p in meaningful_paragraphs) / len(meaningful_paragraphs)
            if avg_len < 500:  # Short paragraphs = likely structured
                return "paragraph"

        # Default to sentence for dense text
        return "sentence"

    def _split_by_paragraphs(self, text: str) -> List[str]:
        """Split text by paragraphs"""
        return [p.strip() for p in self.paragraph_pattern.split(text) if p.strip()]

    def _split_by_sentences(self, text: str) -> List[str]:
        """
        Split text by sentences — quote/parenthesis/case-number aware.

        Improvements over naive regex split:
        1. Does NOT break inside quotes ("..." or «...»)
        2. Does NOT break inside parentheses (...)
        3. Does NOT break on periods in case numbers (ת"א 12345-01-22)
        4. Does NOT break on decimal numbers (5.5, 3.14)
        5. Preserves section references (סעיף 5. לעיל)
        """
        paragraphs = self._split_by_paragraphs(text)

        sentences = []
        for para in paragraphs:
            parts = self._smart_sentence_split(para)
            for part in parts:
                part = part.strip()
                if part:
                    sentences.append(part)

        return sentences

    def _smart_sentence_split(self, text: str) -> List[str]:
        """
        Context-aware sentence splitter for Hebrew legal text.

        Tracks quote depth and parenthesis depth to avoid splitting
        inside quoted text or parenthetical expressions.
        """
        if not text or len(text) < 10:
            return [text] if text else []

        # Protect case numbers from being split
        protected = text
        case_placeholders = {}
        for i, m in enumerate(self._case_number_re.finditer(text)):
            placeholder = f"\x00CASE{i}\x00"
            case_placeholders[placeholder] = m.group()
            protected = protected.replace(m.group(), placeholder, 1)

        sentences = []
        current = []
        quote_depth = 0  # Inside "..." or «...»
        paren_depth = 0  # Inside (...)

        i = 0
        chars = protected
        while i < len(chars):
            ch = chars[i]

            # Track quote depth
            if ch in '"«':
                quote_depth += 1
            elif ch in '"»' and quote_depth > 0:
                quote_depth -= 1
            # Track parenthesis depth
            elif ch == '(':
                paren_depth += 1
            elif ch == ')' and paren_depth > 0:
                paren_depth -= 1

            # Only split on sentence-ending punctuation when NOT inside
            # quotes or parentheses
            if ch in '.!?:' and quote_depth == 0 and paren_depth == 0:
                # Check: is this actually a sentence boundary?
                is_boundary = False

                if ch in '!?':
                    # Exclamation and question marks are always boundaries
                    is_boundary = True
                elif ch == ':':
                    # Colon: boundary only if followed by whitespace+newline
                    # or end of text
                    next_pos = i + 1
                    if next_pos >= len(chars) or chars[next_pos] in '\n\r':
                        is_boundary = True
                elif ch == '.':
                    # Period: check it's not part of a number, abbreviation,
                    # or section reference
                    is_boundary = self._is_sentence_boundary(chars, i)

                if is_boundary:
                    current.append(ch)
                    sentence = ''.join(current).strip()
                    if sentence:
                        # Restore case number placeholders
                        for ph, orig in case_placeholders.items():
                            sentence = sentence.replace(ph, orig)
                        sentences.append(sentence)
                    current = []
                    i += 1
                    # Skip trailing whitespace
                    while i < len(chars) and chars[i] in ' \t':
                        i += 1
                    continue

            current.append(ch)
            i += 1

        # Flush remaining text
        remainder = ''.join(current).strip()
        if remainder:
            for ph, orig in case_placeholders.items():
                remainder = remainder.replace(ph, orig)
            sentences.append(remainder)

        return sentences

    def _is_sentence_boundary(self, text: str, pos: int) -> bool:
        """
        Determine if period at `pos` is a real sentence boundary.

        Returns False for:
        - Decimal numbers: 5.5, 3.14
        - Section refs: סעיף 5.
        - Abbreviations: ד"ר, עו"ד, בע"מ
        - Continuation periods inside abbreviations
        """
        # Must be followed by whitespace or end-of-string to be a boundary
        next_pos = pos + 1
        if next_pos < len(text) and text[next_pos] not in ' \t\n\r':
            # Period followed by a digit = decimal number (e.g. 5.5)
            if text[next_pos].isdigit():
                return False
            # Period followed by a letter = likely abbreviation continuation
            return False

        # Check if preceded by a single digit (section ref like "סעיף 5.")
        if pos > 0 and text[pos - 1].isdigit():
            # Look further back: if there's "סעיף" or "סעיפים" → not a boundary
            lookback = text[max(0, pos - 15):pos].strip()
            section_words = ['סעיף', 'סעיפים', 'פסקה', 'פרק', 'חלק', 'נספח', 'עמוד', 'עמ']
            for sw in section_words:
                if lookback.endswith(sw) or sw in lookback:
                    return False

        # End of text = always a boundary
        if next_pos >= len(text):
            return True

        # Followed by whitespace = boundary
        return True

    def _split_by_clauses(self, text: str) -> List[str]:
        """Split text by numbered clauses"""
        lines = text.split('\n')
        clauses = []
        current_clause = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if this starts a new clause
            if self.clause_pattern.match(line):
                # Save previous clause
                if current_clause:
                    clauses.append(' '.join(current_clause))
                current_clause = [line]
            else:
                # Continue current clause
                current_clause.append(line)

        # Don't forget last clause
        if current_clause:
            clauses.append(' '.join(current_clause))

        return clauses

    def _is_meaningful(self, text: str) -> bool:
        """Check if text has enough meaningful content"""
        if not text or len(text) < 10:
            return False

        # Filter out system text (report output)
        if contains_system_text(text):
            return False

        # Filter out signature/contact blocks
        if self._is_signature_block(text):
            return False

        # Count meaningful words
        words = text.split()
        meaningful_words = [
            w for w in words
            if len(w) > 1 and w.lower() not in self.stopwords
        ]

        return len(meaningful_words) >= self.min_meaningful_words

    def _is_signature_block(self, text: str) -> bool:
        """Check if text is a signature/contact info block."""
        return is_signature_block(text)

    def _split_long_segment(self, text: str) -> List[str]:
        """Split a long segment into sentences if it exceeds MAX_CLAIM_LENGTH."""
        if len(text) <= self.MAX_CLAIM_LENGTH:
            return [text]

        # Split by sentence endings
        parts = self.sentence_pattern.split(text)
        sentences = []
        current = ""

        for part in parts:
            part = part.strip()
            if not part:
                continue

            if len(current) + len(part) < self.MAX_CLAIM_LENGTH:
                current = (current + ". " + part).strip() if current else part
            else:
                if current:
                    sentences.append(current)
                current = part

        if current:
            sentences.append(current)

        return sentences if sentences else [text]


# Singleton instance
_extractor = None

def get_extractor() -> ClaimExtractor:
    """Get singleton extractor instance"""
    global _extractor
    if _extractor is None:
        _extractor = ClaimExtractor()
    return _extractor


def extract_claims(
    text: str,
    source_name: str = "document",
    strategy: str = "auto",
    doc_id: Optional[str] = None,
    paragraph_id: Optional[str] = None,
    paragraph_index: Optional[int] = None,
    char_offset: int = 0,
    page_no: Optional[int] = None,
    block_index: Optional[int] = None,
    bbox: Optional[Dict[str, Any]] = None,
    sanitize: bool = True,
) -> List[Claim]:
    """
    Convenience function to extract claims from text.

    Args:
        text: Hebrew text
        source_name: Source document name
        strategy: "auto", "paragraph", "sentence", "clause"
        doc_id: Document ID for locator
        paragraph_id: Paragraph ID for locator
        paragraph_index: Paragraph index for locator
        char_offset: Character offset for locators

    Returns:
        List of Claim objects
    """
    return get_extractor().extract_from_text(
        text=text,
        source_name=source_name,
        strategy=strategy,
        doc_id=doc_id,
        paragraph_id=paragraph_id,
        paragraph_index=paragraph_index,
        char_offset=char_offset,
        page_no=page_no,
        block_index=block_index,
        bbox=bbox,
        sanitize=sanitize,
    )

# Alias for backwards compatibility
extract_claims_from_text = extract_claims
