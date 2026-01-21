"""
Ingest Pipeline
===============

Document parsing and OCR for multiple formats.
Produces unified output: pages + blocks + locators.
"""

from .base import ParseResult, PageContent, BlockContent, ParserError
from .txt import TXTParser
from .docx import DOCXParser
from .pdf import PDFTextParser
from .ocr import OCRAdapter, TesseractOCR, OCRNotImplementedError
from .factory import get_parser, parse_document, detect_mime_type, is_supported, list_supported_formats

__all__ = [
    # Base types
    "ParseResult", "PageContent", "BlockContent", "ParserError",
    # Parsers
    "TXTParser", "DOCXParser", "PDFTextParser",
    # OCR
    "OCRAdapter", "TesseractOCR", "OCRNotImplementedError",
    # Factory
    "get_parser", "parse_document", "detect_mime_type", "is_supported", "list_supported_formats",
]
