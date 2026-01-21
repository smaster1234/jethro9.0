"""
Claim Extractor - Extract claims from Hebrew legal text
========================================================

Simple, rule-based claim extraction:
1. Sanitize input (remove report/meta sections)
2. Split text into paragraphs/sentences
3. Normalize Hebrew text
4. Filter signatures/contact info
5. Return minimal Claim objects (max 500 chars)
"""

import re
import uuid
from typing import List, Optional, Set
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


@dataclass
class Claim:
    """
    Minimal claim representation for detection.
    Compatible with core/models.py Claim but standalone.

    Now includes locator fields for evidence tracking.
    """
    id: str
    text: str
    source: Optional[str] = None
    page: Optional[int] = None
    speaker: Optional[str] = None

    # Locator fields for evidence
    doc_id: Optional[str] = None
    paragraph_id: Optional[str] = None
    paragraph_index: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None

    # For detection
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None

    # Metadata
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "source": self.source,
            "page": self.page,
            "speaker": self.speaker,
            "doc_id": self.doc_id,
            "paragraph_id": self.paragraph_id,
            "paragraph_index": self.paragraph_index,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "metadata": self.metadata
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
        char_offset: int = 0
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
        text = sanitize_input(text)
        if not text:
            return []

        # Store original text for position tracking
        original_text = text

        # Normalize text
        text = self._normalize_text(text)

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
                page=None,  # Can be enhanced if page markers exist
                speaker=None,  # Can be enhanced with speaker detection
                doc_id=doc_id,
                paragraph_id=paragraph_id,
                paragraph_index=paragraph_index,
                char_start=char_offset + seg_start,
                char_end=char_offset + seg_end,
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
                speaker=item.get("speaker"),
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
        """Split text by sentences"""
        # First split by paragraphs to maintain structure
        paragraphs = self._split_by_paragraphs(text)

        sentences = []
        for para in paragraphs:
            # Split paragraph into sentences
            parts = self.sentence_pattern.split(para)
            for part in parts:
                part = part.strip()
                if part:
                    sentences.append(part)

        return sentences

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
    char_offset: int = 0
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
        char_offset=char_offset
    )

# Alias for backwards compatibility
extract_claims_from_text = extract_claims
