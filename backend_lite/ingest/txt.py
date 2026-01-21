"""
TXT Parser
==========

Simple text file parser.
"""

from typing import List
import chardet

from .base import (
    DocumentParser,
    ParseResult,
    PageContent,
    BlockContent,
    ParserError,
    normalize_text,
    split_into_paragraphs
)


class TXTParser(DocumentParser):
    """
    Plain text file parser.

    Handles encoding detection and paragraph splitting.
    """

    @property
    def supported_mimes(self) -> List[str]:
        return [
            "text/plain",
            "text/csv",
            "text/markdown",
            "text/x-markdown",
            "application/x-empty"
        ]

    def parse(self, data: bytes, filename: str = None) -> ParseResult:
        """Parse plain text file"""
        try:
            # Detect encoding
            detected = chardet.detect(data)
            encoding = detected.get('encoding', 'utf-8') or 'utf-8'

            # Handle Hebrew-specific encodings
            if encoding.lower() in ['iso-8859-8', 'windows-1255', 'cp1255']:
                # Try UTF-8 first for Hebrew
                try:
                    text = data.decode('utf-8')
                except UnicodeDecodeError:
                    text = data.decode(encoding, errors='replace')
            else:
                try:
                    text = data.decode(encoding)
                except (UnicodeDecodeError, LookupError):
                    text = data.decode('utf-8', errors='replace')

            # Normalize
            text = normalize_text(text)

            # Split into paragraphs
            paragraphs = split_into_paragraphs(text)

            # Build blocks
            blocks = []
            char_offset = 0
            for idx, para in enumerate(paragraphs):
                # Find position in original text
                pos = text.find(para, char_offset)
                if pos == -1:
                    pos = char_offset

                blocks.append(BlockContent(
                    text=para,
                    block_index=idx,
                    page_no=1,
                    paragraph_index=idx,
                    char_start=pos,
                    char_end=pos + len(para)
                ))

                char_offset = pos + len(para)

            # Single page for text files
            page = PageContent(
                page_no=1,
                text=text,
                blocks=blocks,
                char_start=0,
                char_end=len(text)
            )

            return ParseResult(
                full_text=text,
                pages=[page],
                page_count=1,
                language=self._detect_language(text),
                metadata={
                    "encoding": encoding,
                    "confidence": detected.get('confidence', 0),
                    "paragraph_count": len(paragraphs)
                }
            )

        except Exception as e:
            raise ParserError(f"Failed to parse text file: {e}")

    def _detect_language(self, text: str) -> str:
        """Simple language detection based on character ranges"""
        if not text:
            return "unknown"

        # Count Hebrew characters
        hebrew_chars = sum(1 for c in text if '\u0590' <= c <= '\u05FF')
        total_alpha = sum(1 for c in text if c.isalpha())

        if total_alpha == 0:
            return "unknown"

        hebrew_ratio = hebrew_chars / total_alpha

        if hebrew_ratio > 0.3:
            return "he"
        else:
            return "en"
