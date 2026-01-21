"""
OCR Adapter
===========

OCR support for scanned documents and images.
"""

import io
import os
import json
import logging
from abc import ABC, abstractmethod
from typing import List, Optional

from .base import (
    ParseResult,
    PageContent,
    BlockContent,
    ParserError,
    normalize_text
)

logger = logging.getLogger(__name__)


class OCRNotImplementedError(ParserError):
    """OCR is not available"""
    pass


class OCRAdapter(ABC):
    """
    Abstract base class for OCR engines.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """OCR engine name"""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if OCR engine is available"""
        pass

    @abstractmethod
    def process_image(
        self,
        image_data: bytes,
        language: str = "heb+eng"
    ) -> ParseResult:
        """
        Process a single image.

        Args:
            image_data: Image bytes (PNG/JPG/etc.)
            language: OCR language code

        Returns:
            ParseResult with extracted text
        """
        pass

    @abstractmethod
    def process_pdf(
        self,
        pdf_data: bytes,
        language: str = "heb+eng"
    ) -> ParseResult:
        """
        Process a scanned PDF.

        Args:
            pdf_data: PDF bytes
            language: OCR language code

        Returns:
            ParseResult with extracted text
        """
        pass


class DocumentAIOCR(OCRAdapter):
    """
    Google Document AI OCR implementation.

    Requires Google Cloud credentials and Document AI processor.
    """

    def __init__(self):
        self._available = None
        self._client = None
        self._processor_path = None

        # Support multiple env var names for project/processor
        self.project_id = (
            os.getenv("DOCUMENTAI_PROJECT_ID") or
            os.getenv("GOOGLE_CLOUD_PROJECT") or
            os.getenv("GCP_PROJECT_ID")
        )
        self.processor_id = (
            os.getenv("DOCUMENTAI_PROCESSOR_ID") or
            os.getenv("DOCAI_PROCESSOR_ID") or
            os.getenv("DOCUMENT_AI_PROCESSOR_ID")
        )
        self.location = (
            os.getenv("GOOGLE_CLOUD_LOCATION") or
            os.getenv("DOCUMENT_AI_LOCATION") or
            "us"
        )
        self.credentials_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

    @property
    def name(self) -> str:
        return "document_ai"

    @property
    def is_available(self) -> bool:
        if self._available is None:
            try:
                from google.cloud import documentai
                # Check if configured
                if self.project_id and self.processor_id:
                    self._available = True
                    logger.info(
                        f"✅ Document AI OCR available: project={self.project_id}, "
                        f"processor={self.processor_id}, location={self.location}"
                    )
                else:
                    self._available = False
                    logger.debug("Document AI not configured (missing project_id or processor_id)")
            except ImportError:
                self._available = False
                logger.debug("google-cloud-documentai not installed")
        return self._available

    def _get_client(self):
        """Get or create Document AI client"""
        if self._client is None:
            from google.cloud import documentai
            from google.api_core.client_options import ClientOptions

            credentials = None

            # Try to load credentials from JSON env var
            if self.credentials_json:
                try:
                    from google.oauth2 import service_account
                    creds_dict = json.loads(self.credentials_json)
                    credentials = service_account.Credentials.from_service_account_info(creds_dict)
                    logger.info("✅ Document AI: Using credentials from GOOGLE_APPLICATION_CREDENTIALS_JSON")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load JSON credentials: {e}")

            # Configure regional endpoint
            location_lower = (self.location or "us").lower()
            client_options = None

            if location_lower == "eu" or location_lower.startswith("europe"):
                client_options = ClientOptions(api_endpoint="eu-documentai.googleapis.com")
            elif location_lower not in ("us", "us-central1"):
                client_options = ClientOptions(api_endpoint=f"{location_lower}-documentai.googleapis.com")

            if credentials:
                self._client = documentai.DocumentProcessorServiceClient(
                    credentials=credentials,
                    client_options=client_options
                )
            else:
                self._client = documentai.DocumentProcessorServiceClient(
                    client_options=client_options
                )

            self._processor_path = self._client.processor_path(
                self.project_id, self.location, self.processor_id
            )

        return self._client

    def process_image(
        self,
        image_data: bytes,
        language: str = "heb+eng"
    ) -> ParseResult:
        """Process a single image with Document AI"""
        if not self.is_available:
            raise OCRNotImplementedError("Document AI is not available")

        try:
            from google.cloud import documentai

            client = self._get_client()

            # Determine MIME type
            mime_type = "image/png"
            if image_data[:2] == b'\xff\xd8':
                mime_type = "image/jpeg"
            elif image_data[:4] == b'\x89PNG':
                mime_type = "image/png"

            raw_document = documentai.RawDocument(content=image_data, mime_type=mime_type)
            request = documentai.ProcessRequest(name=self._processor_path, raw_document=raw_document)

            result = client.process_document(request=request)
            document = result.document

            text = normalize_text(document.text or "")

            page = PageContent(
                page_no=1,
                text=text,
                blocks=[],
                char_start=0,
                char_end=len(text)
            )

            return ParseResult(
                full_text=text,
                pages=[page],
                page_count=1,
                language="he" if "heb" in language else "en",
                metadata={
                    "ocr_engine": "document_ai",
                    "ocr_language": language
                }
            )

        except Exception as e:
            raise ParserError(f"Document AI OCR failed: {e}")

    def process_pdf(
        self,
        pdf_data: bytes,
        language: str = "heb+eng"
    ) -> ParseResult:
        """Process a scanned PDF with Document AI"""
        if not self.is_available:
            raise OCRNotImplementedError("Document AI is not available")

        try:
            from google.cloud import documentai

            client = self._get_client()

            raw_document = documentai.RawDocument(content=pdf_data, mime_type="application/pdf")
            request = documentai.ProcessRequest(name=self._processor_path, raw_document=raw_document)

            logger.info(f"📄 Document AI: Processing PDF ({len(pdf_data)} bytes)")
            result = client.process_document(request=request)
            document = result.document

            full_text = normalize_text(document.text or "")

            # Build pages from Document AI response
            pages = []
            char_offset = 0

            for page_idx, page_obj in enumerate(document.pages, start=1):
                # Extract text for this page using text anchors
                page_text = ""
                if page_obj.paragraphs:
                    for para in page_obj.paragraphs:
                        if para.layout.text_anchor.text_segments:
                            for segment in para.layout.text_anchor.text_segments:
                                start = int(segment.start_index) if segment.start_index else 0
                                end = int(segment.end_index) if segment.end_index else len(document.text)
                                page_text += document.text[start:end]

                if not page_text:
                    # Fallback: divide text evenly if text_anchor not available
                    total_pages = len(document.pages) or 1
                    chars_per_page = len(full_text) // total_pages
                    start = (page_idx - 1) * chars_per_page
                    end = page_idx * chars_per_page if page_idx < total_pages else len(full_text)
                    page_text = full_text[start:end]

                page_text = normalize_text(page_text)

                pages.append(PageContent(
                    page_no=page_idx,
                    text=page_text,
                    blocks=[],
                    width=int(page_obj.dimension.width) if page_obj.dimension else None,
                    height=int(page_obj.dimension.height) if page_obj.dimension else None,
                    char_start=char_offset,
                    char_end=char_offset + len(page_text)
                ))

                char_offset += len(page_text) + 1

            if not pages:
                # Single page fallback
                pages = [PageContent(
                    page_no=1,
                    text=full_text,
                    blocks=[],
                    char_start=0,
                    char_end=len(full_text)
                )]

            logger.info(f"✅ Document AI: Extracted {len(full_text)} chars from {len(pages)} pages")

            return ParseResult(
                full_text=full_text,
                pages=pages,
                page_count=len(pages),
                language="he" if "heb" in language else "en",
                metadata={
                    "ocr_engine": "document_ai",
                    "ocr_language": language,
                    "page_count": len(pages)
                }
            )

        except Exception as e:
            logger.error(f"Document AI OCR failed: {e}")
            raise ParserError(f"Document AI OCR failed: {e}")


class TesseractOCR(OCRAdapter):
    """
    Tesseract OCR implementation.

    Requires tesseract-ocr to be installed on the system.
    For Hebrew: apt-get install tesseract-ocr-heb
    """

    def __init__(self):
        self._available = None
        self._pytesseract = None

    @property
    def name(self) -> str:
        return "tesseract"

    @property
    def is_available(self) -> bool:
        if self._available is None:
            try:
                import pytesseract
                # Test if tesseract is installed
                pytesseract.get_tesseract_version()
                self._pytesseract = pytesseract
                self._available = True
            except Exception:
                self._available = False
        return self._available

    def _ensure_available(self):
        if not self.is_available:
            raise OCRNotImplementedError(
                "Tesseract OCR is not available. "
                "Install with: apt-get install tesseract-ocr tesseract-ocr-heb && pip install pytesseract pillow"
            )

    def process_image(
        self,
        image_data: bytes,
        language: str = "heb+eng"
    ) -> ParseResult:
        """Process a single image with Tesseract"""
        self._ensure_available()

        try:
            from PIL import Image
        except ImportError:
            raise ParserError("Pillow is required for OCR. Install with: pip install pillow")

        try:
            # Load image
            image = Image.open(io.BytesIO(image_data))

            # Get image dimensions
            width, height = image.size

            # Run OCR
            text = self._pytesseract.image_to_string(
                image,
                lang=language,
                config='--psm 3'  # Automatic page segmentation
            )

            text = normalize_text(text)

            # Get detailed OCR data for blocks
            ocr_data = self._pytesseract.image_to_data(
                image,
                lang=language,
                output_type=self._pytesseract.Output.DICT
            )

            # Build blocks from OCR data
            blocks = self._build_blocks_from_ocr_data(ocr_data, page_no=1)

            page = PageContent(
                page_no=1,
                text=text,
                blocks=blocks,
                width=width,
                height=height,
                char_start=0,
                char_end=len(text)
            )

            return ParseResult(
                full_text=text,
                pages=[page],
                page_count=1,
                language=language.split('+')[0] if '+' in language else language,
                metadata={
                    "ocr_engine": "tesseract",
                    "ocr_language": language
                }
            )

        except Exception as e:
            raise ParserError(f"OCR failed: {e}")

    def process_pdf(
        self,
        pdf_data: bytes,
        language: str = "heb+eng"
    ) -> ParseResult:
        """Process a scanned PDF with Tesseract"""
        self._ensure_available()

        try:
            from pdf2image import convert_from_bytes
        except ImportError:
            raise ParserError(
                "pdf2image is required for PDF OCR. "
                "Install with: pip install pdf2image"
            )

        try:
            # Convert PDF pages to images
            images = convert_from_bytes(pdf_data, dpi=300)

            pages = []
            full_text_parts = []
            global_char_offset = 0
            global_block_index = 0

            for page_no, image in enumerate(images, start=1):
                # Get dimensions
                width, height = image.size

                # Run OCR
                text = self._pytesseract.image_to_string(
                    image,
                    lang=language,
                    config='--psm 3'
                )

                text = normalize_text(text)

                # Get detailed OCR data
                ocr_data = self._pytesseract.image_to_data(
                    image,
                    lang=language,
                    output_type=self._pytesseract.Output.DICT
                )

                # Build blocks
                blocks = self._build_blocks_from_ocr_data(
                    ocr_data,
                    page_no=page_no,
                    char_offset=global_char_offset,
                    block_offset=global_block_index
                )

                pages.append(PageContent(
                    page_no=page_no,
                    text=text,
                    blocks=blocks,
                    width=width,
                    height=height,
                    char_start=global_char_offset,
                    char_end=global_char_offset + len(text)
                ))

                full_text_parts.append(text)
                global_char_offset += len(text) + 1
                global_block_index += len(blocks)

            full_text = "\n".join(full_text_parts)

            return ParseResult(
                full_text=full_text,
                pages=pages,
                page_count=len(pages),
                language=language.split('+')[0] if '+' in language else language,
                metadata={
                    "ocr_engine": "tesseract",
                    "ocr_language": language,
                    "page_count": len(pages)
                }
            )

        except Exception as e:
            raise ParserError(f"PDF OCR failed: {e}")

    def _build_blocks_from_ocr_data(
        self,
        ocr_data: dict,
        page_no: int,
        char_offset: int = 0,
        block_offset: int = 0
    ) -> List[BlockContent]:
        """Build blocks from Tesseract OCR data"""
        blocks = []
        current_block_num = -1
        current_block_text = []
        current_block_bbox = None
        block_char_start = char_offset

        n_items = len(ocr_data.get('text', []))

        for i in range(n_items):
            text = ocr_data['text'][i].strip()
            block_num = ocr_data['block_num'][i]
            conf = ocr_data['conf'][i]

            # Skip low confidence or empty text
            if conf < 0 or not text:
                continue

            if block_num != current_block_num:
                # Save previous block
                if current_block_text:
                    block_text = ' '.join(current_block_text)
                    blocks.append(BlockContent(
                        text=block_text,
                        block_index=len(blocks) + block_offset,
                        page_no=page_no,
                        paragraph_index=len(blocks),
                        char_start=block_char_start,
                        char_end=block_char_start + len(block_text),
                        bbox=current_block_bbox,
                        confidence=sum(float(c) for c in ocr_data['conf'][i-len(current_block_text):i] if c > 0) / max(len(current_block_text), 1)
                    ))
                    block_char_start += len(block_text) + 1

                # Start new block
                current_block_num = block_num
                current_block_text = [text]
                current_block_bbox = {
                    'x': ocr_data['left'][i],
                    'y': ocr_data['top'][i],
                    'width': ocr_data['width'][i],
                    'height': ocr_data['height'][i]
                }
            else:
                current_block_text.append(text)
                # Expand bbox
                if current_block_bbox:
                    x2 = max(
                        current_block_bbox['x'] + current_block_bbox['width'],
                        ocr_data['left'][i] + ocr_data['width'][i]
                    )
                    y2 = max(
                        current_block_bbox['y'] + current_block_bbox['height'],
                        ocr_data['top'][i] + ocr_data['height'][i]
                    )
                    current_block_bbox['width'] = x2 - current_block_bbox['x']
                    current_block_bbox['height'] = y2 - current_block_bbox['y']

        # Save last block
        if current_block_text:
            block_text = ' '.join(current_block_text)
            blocks.append(BlockContent(
                text=block_text,
                block_index=len(blocks) + block_offset,
                page_no=page_no,
                paragraph_index=len(blocks),
                char_start=block_char_start,
                char_end=block_char_start + len(block_text),
                bbox=current_block_bbox
            ))

        return blocks


class StubOCR(OCRAdapter):
    """
    Stub OCR that returns an error.

    Used when no OCR engine is available.
    """

    @property
    def name(self) -> str:
        return "stub"

    @property
    def is_available(self) -> bool:
        return True  # Always "available" but will error

    def process_image(
        self,
        image_data: bytes,
        language: str = "heb+eng"
    ) -> ParseResult:
        raise OCRNotImplementedError(
            "OCR_NOT_IMPLEMENTED: No OCR engine is configured. "
            "Install Tesseract or configure a cloud OCR provider."
        )

    def process_pdf(
        self,
        pdf_data: bytes,
        language: str = "heb+eng"
    ) -> ParseResult:
        raise OCRNotImplementedError(
            "OCR_NOT_IMPLEMENTED: No OCR engine is configured. "
            "Install Tesseract or configure a cloud OCR provider."
        )


def get_ocr_adapter() -> OCRAdapter:
    """
    Get the best available OCR adapter.

    Priority:
    1. Document AI (cloud, high quality, supports Hebrew)
    2. Tesseract (local, free)
    3. StubOCR (fallback that returns error)
    """
    # Check OCR_MODE env var for explicit preference
    ocr_mode = os.getenv("OCR_MODE", "auto").lower()

    if ocr_mode == "document_ai":
        doc_ai = DocumentAIOCR()
        if doc_ai.is_available:
            logger.info("🔧 OCR Mode: Document AI (explicit)")
            return doc_ai
        logger.warning("⚠️ OCR_MODE=document_ai but Document AI not available, falling back")

    if ocr_mode == "tesseract":
        tesseract = TesseractOCR()
        if tesseract.is_available:
            logger.info("🔧 OCR Mode: Tesseract (explicit)")
            return tesseract
        logger.warning("⚠️ OCR_MODE=tesseract but Tesseract not available, falling back")

    # Auto mode: try Document AI first, then Tesseract
    doc_ai = DocumentAIOCR()
    if doc_ai.is_available:
        logger.info("🔧 OCR Mode: Document AI (auto-detected)")
        return doc_ai

    tesseract = TesseractOCR()
    if tesseract.is_available:
        logger.info("🔧 OCR Mode: Tesseract (auto-detected)")
        return tesseract

    logger.warning("⚠️ No OCR engine available! PDFs with scanned images will fail.")
    return StubOCR()
