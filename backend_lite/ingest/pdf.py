"""
PDF Text Parser
===============

PDF parser for text-based PDFs (not scanned).
Uses pypdf for extraction.
"""

import io
from typing import List

from .base import (
    DocumentParser,
    ParseResult,
    PageContent,
    BlockContent,
    ParserError,
    normalize_text,
    split_into_paragraphs
)


class PDFTextParser(DocumentParser):
    """
    PDF text parser.

    Extracts text from PDFs that have embedded text.
    For scanned PDFs, use OCRAdapter instead.
    """

    @property
    def supported_mimes(self) -> List[str]:
        return [
            "application/pdf",
            "application/x-pdf"
        ]

    def parse(self, data: bytes, filename: str = None) -> ParseResult:
        """Parse PDF file"""
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                from PyPDF2 import PdfReader
            except ImportError:
                raise ParserError(
                    "pypdf or PyPDF2 is required for PDF parsing. "
                    "Install with: pip install pypdf"
                )

        try:
            reader = PdfReader(io.BytesIO(data))
            pages = []
            full_text_parts = []
            global_char_offset = 0
            global_block_index = 0

            for page_no, page in enumerate(reader.pages, start=1):
                try:
                    page_text = page.extract_text() or ""
                except Exception:
                    page_text = ""

                page_text = normalize_text(page_text)

                # Split page into blocks (paragraphs)
                paragraphs = split_into_paragraphs(page_text)
                blocks = []
                page_char_offset = 0

                for para_idx, para in enumerate(paragraphs):
                    # Find position in page text
                    pos = page_text.find(para, page_char_offset)
                    if pos == -1:
                        pos = page_char_offset

                    blocks.append(BlockContent(
                        text=para,
                        block_index=global_block_index,
                        page_no=page_no,
                        paragraph_index=para_idx,
                        char_start=global_char_offset + pos,
                        char_end=global_char_offset + pos + len(para)
                    ))

                    global_block_index += 1
                    page_char_offset = pos + len(para)

                # Get page dimensions if available
                width, height = None, None
                try:
                    mediabox = page.mediabox
                    width = int(mediabox.width)
                    height = int(mediabox.height)
                except:
                    pass

                pages.append(PageContent(
                    page_no=page_no,
                    text=page_text,
                    blocks=blocks,
                    width=width,
                    height=height,
                    char_start=global_char_offset,
                    char_end=global_char_offset + len(page_text)
                ))

                full_text_parts.append(page_text)
                global_char_offset += len(page_text) + 1  # +1 for page separator

            full_text = "\n".join(full_text_parts)

            # Check if PDF has text or is scanned
            is_scanned = len(full_text.strip()) < 100 and len(pages) > 0

            # Extract metadata
            metadata = {
                "page_count": len(pages),
                "is_scanned": is_scanned
            }

            try:
                if reader.metadata:
                    if reader.metadata.title:
                        metadata['title'] = reader.metadata.title
                    if reader.metadata.author:
                        metadata['author'] = reader.metadata.author
                    if reader.metadata.creator:
                        metadata['creator'] = reader.metadata.creator
            except:
                pass

            return ParseResult(
                full_text=full_text,
                pages=pages,
                page_count=len(pages),
                language=self._detect_language(full_text),
                metadata=metadata
            )

        except Exception as e:
            raise ParserError(f"Failed to parse PDF file: {e}")

    def _detect_language(self, text: str) -> str:
        """Simple language detection"""
        if not text:
            return "unknown"

        hebrew_chars = sum(1 for c in text if '\u0590' <= c <= '\u05FF')
        total_alpha = sum(1 for c in text if c.isalpha())

        if total_alpha == 0:
            return "unknown"

        return "he" if hebrew_chars / total_alpha > 0.3 else "en"

    def is_scanned(self, data: bytes) -> bool:
        """
        Check if PDF is scanned (no embedded text).

        Returns True if PDF appears to be scanned and needs OCR.
        """
        try:
            result = self.parse(data)
            return result.metadata.get('is_scanned', False)
        except:
            return True
