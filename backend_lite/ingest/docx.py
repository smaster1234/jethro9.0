"""
DOCX Parser
===========

Microsoft Word document parser using python-docx.
"""

import io
from typing import List

from .base import (
    DocumentParser,
    ParseResult,
    PageContent,
    BlockContent,
    ParserError,
    normalize_text
)


class DOCXParser(DocumentParser):
    """
    Microsoft Word (.docx) parser.

    Uses python-docx to extract text with paragraph structure.
    """

    @property
    def supported_mimes(self) -> List[str]:
        return [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword"  # .doc files (limited support)
        ]

    def parse(self, data: bytes, filename: str = None) -> ParseResult:
        """Parse DOCX file"""
        try:
            from docx import Document
        except ImportError:
            raise ParserError(
                "python-docx is required for DOCX parsing. "
                "Install with: pip install python-docx"
            )

        try:
            # Load document from bytes
            doc = Document(io.BytesIO(data))

            blocks = []
            full_text_parts = []
            char_offset = 0

            # Process paragraphs
            for idx, para in enumerate(doc.paragraphs):
                text = para.text.strip()
                if not text:
                    continue

                text = normalize_text(text)

                blocks.append(BlockContent(
                    text=text,
                    block_index=len(blocks),
                    page_no=1,  # DOCX doesn't have page info without rendering
                    paragraph_index=idx,
                    char_start=char_offset,
                    char_end=char_offset + len(text)
                ))

                full_text_parts.append(text)
                char_offset += len(text) + 1  # +1 for newline

            # Process tables
            for table_idx, table in enumerate(doc.tables):
                for row in table.rows:
                    row_texts = []
                    for cell in row.cells:
                        cell_text = cell.text.strip()
                        if cell_text:
                            row_texts.append(cell_text)

                    if row_texts:
                        text = " | ".join(row_texts)
                        text = normalize_text(text)

                        blocks.append(BlockContent(
                            text=text,
                            block_index=len(blocks),
                            page_no=1,
                            paragraph_index=None,
                            char_start=char_offset,
                            char_end=char_offset + len(text)
                        ))

                        full_text_parts.append(text)
                        char_offset += len(text) + 1

            full_text = "\n".join(full_text_parts)

            # Create single page (DOCX doesn't have native page breaks)
            page = PageContent(
                page_no=1,
                text=full_text,
                blocks=blocks,
                char_start=0,
                char_end=len(full_text)
            )

            # Extract metadata
            metadata = {}
            try:
                core_props = doc.core_properties
                if core_props.author:
                    metadata['author'] = core_props.author
                if core_props.title:
                    metadata['title'] = core_props.title
                if core_props.created:
                    metadata['created'] = core_props.created.isoformat()
                if core_props.modified:
                    metadata['modified'] = core_props.modified.isoformat()
            except:
                pass

            metadata['paragraph_count'] = len(blocks)
            metadata['table_count'] = len(doc.tables)

            return ParseResult(
                full_text=full_text,
                pages=[page],
                page_count=1,
                language=self._detect_language(full_text),
                metadata=metadata
            )

        except Exception as e:
            raise ParserError(f"Failed to parse DOCX file: {e}")

    def _detect_language(self, text: str) -> str:
        """Simple language detection"""
        if not text:
            return "unknown"

        hebrew_chars = sum(1 for c in text if '\u0590' <= c <= '\u05FF')
        total_alpha = sum(1 for c in text if c.isalpha())

        if total_alpha == 0:
            return "unknown"

        return "he" if hebrew_chars / total_alpha > 0.3 else "en"
