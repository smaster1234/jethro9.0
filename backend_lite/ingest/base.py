"""
Ingest Base Types
=================

Unified output types for all parsers.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


class ParserError(Exception):
    """Base exception for parser errors"""
    pass


class UnsupportedFormatError(ParserError):
    """File format not supported"""
    pass


@dataclass
class BlockContent:
    """
    Single text block within a page.

    Represents a paragraph, section, or text region.
    """
    text: str
    block_index: int
    page_no: int
    paragraph_index: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    bbox: Optional[Dict[str, float]] = None  # {x, y, width, height}
    confidence: Optional[float] = None  # OCR confidence

    def to_locator_json(self, doc_id: Optional[str] = None) -> Dict[str, Any]:
        """Convert to locator JSON for storage"""
        locator = {
            "page_no": self.page_no,
            "block_index": self.block_index,
            "paragraph_index": self.paragraph_index,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "bbox": self.bbox
        }
        if doc_id:
            locator["doc_id"] = doc_id
        return locator


@dataclass
class PageContent:
    """
    Single page of a document.
    """
    page_no: int
    text: str
    blocks: List[BlockContent] = field(default_factory=list)
    width: Optional[int] = None
    height: Optional[int] = None
    char_start: Optional[int] = None  # Start position in full_text
    char_end: Optional[int] = None  # End position in full_text


@dataclass
class ParseResult:
    """
    Unified result from any parser.

    Contains full text plus structured page/block information.
    """
    full_text: str
    pages: List[PageContent]
    page_count: int
    language: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def all_blocks(self) -> List[BlockContent]:
        """Get all blocks across all pages"""
        return [block for page in self.pages for block in page.blocks]

    def get_block_by_locator(
        self,
        page_no: int,
        block_index: int
    ) -> Optional[BlockContent]:
        """Find a block by page and index"""
        for page in self.pages:
            if page.page_no == page_no:
                for block in page.blocks:
                    if block.block_index == block_index:
                        return block
        return None


class DocumentParser(ABC):
    """
    Abstract base class for document parsers.
    """

    @property
    @abstractmethod
    def supported_mimes(self) -> List[str]:
        """List of supported MIME types"""
        pass

    @abstractmethod
    def parse(self, data: bytes, filename: str = None) -> ParseResult:
        """
        Parse document data.

        Args:
            data: Binary document data
            filename: Optional filename for type hints

        Returns:
            ParseResult with full text and structured content
        """
        pass

    def can_parse(self, mime_type: str) -> bool:
        """Check if this parser supports the MIME type"""
        return mime_type.lower() in [m.lower() for m in self.supported_mimes]


def normalize_text(text: str) -> str:
    """
    Normalize text for storage.

    - Normalize whitespace
    - Fix common encoding issues
    - Handle RTL markers
    """
    if not text:
        return ""

    # Normalize whitespace
    text = ' '.join(text.split())

    # Remove zero-width characters (except RTL/LTR markers)
    text = text.replace('\u200b', '')  # Zero-width space
    text = text.replace('\ufeff', '')  # BOM

    return text.strip()


def split_into_paragraphs(text: str, min_length: int = 20) -> List[str]:
    """
    Split text into paragraphs.

    Uses double newlines, numbered sections, and bullet points as delimiters.
    """
    import re

    if not text:
        return []

    # Split on double newlines
    paragraphs = re.split(r'\n\s*\n', text)

    # Also split on numbered sections
    refined = []
    for para in paragraphs:
        # Check for numbered sections
        if re.search(r'^\s*\d+\.', para, re.MULTILINE):
            # Split by numbered items
            sub_paras = re.split(r'(?=^\s*\d+\.)', para, flags=re.MULTILINE)
            refined.extend([p.strip() for p in sub_paras if p.strip()])
        else:
            if para.strip():
                refined.append(para.strip())

    # Filter by minimum length
    return [p for p in refined if len(p) >= min_length]
