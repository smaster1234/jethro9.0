"""
Parser Factory
==============

Factory functions for document parsing.
"""

import mimetypes
from typing import Optional

from .base import DocumentParser, ParseResult, ParserError, UnsupportedFormatError
from .txt import TXTParser
from .docx import DOCXParser
from .pdf import PDFTextParser
from .ocr import get_ocr_adapter, OCRNotImplementedError


# Initialize parsers
_txt_parser = TXTParser()
_docx_parser = DOCXParser()
_pdf_parser = PDFTextParser()

# MIME type to parser mapping
_parsers = {
    "text/plain": _txt_parser,
    "text/csv": _txt_parser,
    "text/markdown": _txt_parser,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": _docx_parser,
    "application/msword": _docx_parser,
    "application/pdf": _pdf_parser,
}

# Image MIME types (require OCR)
_image_mimes = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/tiff",
    "image/bmp",
    "image/gif",
    "image/webp"
}


def detect_mime_type(filename: str, data: bytes = None) -> str:
    """
    Detect MIME type from filename and optionally file content.

    Args:
        filename: File name
        data: Optional file content for magic number detection

    Returns:
        MIME type string
    """
    # Try mimetypes first
    mime_type, _ = mimetypes.guess_type(filename)

    if mime_type:
        return mime_type

    # Fallback to extension mapping
    ext = filename.lower().split('.')[-1] if '.' in filename else ''

    ext_mapping = {
        'txt': 'text/plain',
        'csv': 'text/csv',
        'md': 'text/markdown',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'doc': 'application/msword',
        'pdf': 'application/pdf',
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'tiff': 'image/tiff',
        'tif': 'image/tiff',
        'bmp': 'image/bmp',
        'gif': 'image/gif',
        'webp': 'image/webp',
    }

    if ext in ext_mapping:
        return ext_mapping[ext]

    # Try magic numbers if data provided
    if data:
        # PDF
        if data[:4] == b'%PDF':
            return 'application/pdf'
        # PNG
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return 'image/png'
        # JPEG
        if data[:2] == b'\xff\xd8':
            return 'image/jpeg'
        # DOCX (ZIP with specific content)
        if data[:4] == b'PK\x03\x04':
            # Could be DOCX or ZIP
            if b'word/' in data[:2000]:
                return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

    return 'application/octet-stream'


def get_parser(mime_type: str) -> Optional[DocumentParser]:
    """
    Get parser for MIME type.

    Args:
        mime_type: MIME type string

    Returns:
        DocumentParser or None if not supported
    """
    return _parsers.get(mime_type.lower())


def parse_document(
    data: bytes,
    filename: str,
    mime_type: str = None,
    force_ocr: bool = False,
    ocr_language: str = "heb+eng"
) -> ParseResult:
    """
    Parse document with appropriate parser.

    Automatically detects MIME type if not provided.
    Uses OCR for images and scanned PDFs.

    Args:
        data: Document bytes
        filename: Original filename
        mime_type: Optional MIME type (auto-detected if not provided)
        force_ocr: Force OCR even for text PDFs
        ocr_language: OCR language code

    Returns:
        ParseResult with extracted text and structure

    Raises:
        UnsupportedFormatError: If format not supported
        ParserError: If parsing fails
        OCRNotImplementedError: If OCR needed but not available
    """
    # Detect MIME type if not provided
    if not mime_type:
        mime_type = detect_mime_type(filename, data)

    mime_type = mime_type.lower()

    # Check for images (require OCR)
    if mime_type in _image_mimes:
        ocr = get_ocr_adapter()
        return ocr.process_image(data, language=ocr_language)

    # Check for PDF
    if mime_type == 'application/pdf':
        # Try text extraction first
        if not force_ocr:
            try:
                result = _pdf_parser.parse(data, filename)
                # Check if PDF has meaningful text
                if result.full_text and len(result.full_text.strip()) > 100:
                    return result
            except ParserError:
                pass

        # Fall back to OCR
        ocr = get_ocr_adapter()
        # Check if OCR is actually available (not StubOCR)
        if ocr.name == "stub":
            # No OCR available - return minimal result with warning
            # This allows the document to be processed without crashing
            from .base import ParseResult, PageContent
            return ParseResult(
                full_text="[המסמך הוא סריקה ודורש OCR לחילוץ טקסט. אנא התקן Tesseract או הגדר ספק OCR בענן.]",
                pages=[PageContent(
                    page_no=1,
                    text="[המסמך הוא סריקה ודורש OCR לחילוץ טקסט.]",
                    blocks=[]
                )],
                page_count=1,
                language="he",
                metadata={
                    "needs_ocr": True,
                    "ocr_available": False,
                    "warning": "Document requires OCR but no OCR engine is configured"
                }
            )
        return ocr.process_pdf(data, language=ocr_language)

    # Get parser for MIME type
    parser = get_parser(mime_type)

    if parser is None:
        raise UnsupportedFormatError(
            f"Unsupported file format: {mime_type}. "
            f"Supported: {list(_parsers.keys()) + list(_image_mimes)}"
        )

    return parser.parse(data, filename)


def is_supported(mime_type: str) -> bool:
    """Check if MIME type is supported"""
    mime_type = mime_type.lower()
    return mime_type in _parsers or mime_type in _image_mimes


def list_supported_formats() -> dict:
    """List all supported formats"""
    return {
        "text": list(_txt_parser.supported_mimes),
        "word": list(_docx_parser.supported_mimes),
        "pdf": list(_pdf_parser.supported_mimes),
        "images": list(_image_mimes)
    }
