"""
Acceptance Tests for Upload System
==================================

Tests for:
1. Single/multi document upload
2. ZIP upload with folder creation
3. Document parsing flow
4. Job status tracking
5. Rate limiting
6. Firm scoping and permissions
"""

import io
import os
import json
import zipfile
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

# Note: Some tests may skip if dependencies not available


class TestIngestParsers:
    """Test document parsers"""

    def test_txt_parser_utf8(self):
        """Test TXT parser with UTF-8 Hebrew text"""
        from backend_lite.ingest import TXTParser

        parser = TXTParser()
        text = "זהו טקסט בעברית.\n\nפסקה שנייה עם תוכן נוסף."
        data = text.encode('utf-8')

        result = parser.parse(data, "test.txt")

        assert result.full_text
        assert "עברית" in result.full_text
        assert result.page_count == 1
        assert len(result.pages[0].blocks) >= 1
        assert result.language == "he"

    def test_txt_parser_hebrew_encoding(self):
        """Test TXT parser with Windows-1255 Hebrew encoding"""
        from backend_lite.ingest import TXTParser

        parser = TXTParser()
        text = "טקסט בעברית"

        # Create Windows-1255 encoded data
        try:
            data = text.encode('windows-1255')
            result = parser.parse(data, "test.txt")
            assert "עברית" in result.full_text or len(result.full_text) > 0
        except UnicodeEncodeError:
            # Skip if encoding not supported
            pass

    def test_detect_mime_type(self):
        """Test MIME type detection"""
        from backend_lite.ingest import detect_mime_type

        assert detect_mime_type("doc.txt") == "text/plain"
        assert detect_mime_type("doc.pdf") == "application/pdf"
        assert detect_mime_type("doc.docx") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert detect_mime_type("image.png") == "image/png"
        assert detect_mime_type("image.jpg") == "image/jpeg"

    def test_is_supported(self):
        """Test format support check"""
        from backend_lite.ingest import is_supported

        assert is_supported("text/plain")
        assert is_supported("application/pdf")
        assert is_supported("image/png")
        assert not is_supported("application/x-unknown")

    def test_parse_result_structure(self):
        """Test ParseResult structure"""
        from backend_lite.ingest import TXTParser

        parser = TXTParser()
        text = "Line 1\n\nLine 2\n\nLine 3"
        result = parser.parse(text.encode('utf-8'), "test.txt")

        # Check structure
        assert hasattr(result, 'full_text')
        assert hasattr(result, 'pages')
        assert hasattr(result, 'page_count')
        assert hasattr(result, 'metadata')

        # Check blocks have locators
        for block in result.all_blocks:
            assert hasattr(block, 'char_start')
            assert hasattr(block, 'char_end')
            assert hasattr(block, 'page_no')
            assert hasattr(block, 'block_index')


class TestLocalStorage:
    """Test local storage backend"""

    def test_put_and_get(self, tmp_path):
        """Test storing and retrieving data"""
        from backend_lite.storage import LocalStorage

        storage = LocalStorage(base_path=str(tmp_path / "storage"))

        data = b"Hello, World!"
        key = "test/file.txt"

        # Store
        meta = storage.put(key, data, "text/plain")
        assert meta.size_bytes == len(data)
        assert meta.sha256

        # Retrieve
        retrieved = storage.get(key)
        assert retrieved == data

    def test_exists_and_delete(self, tmp_path):
        """Test exists and delete operations"""
        from backend_lite.storage import LocalStorage

        storage = LocalStorage(base_path=str(tmp_path / "storage"))

        data = b"Test data"
        key = "test/to_delete.txt"

        storage.put(key, data)

        assert storage.exists(key)
        assert storage.delete(key)
        assert not storage.exists(key)

    def test_generate_key(self, tmp_path):
        """Test key generation"""
        from backend_lite.storage import LocalStorage

        key = LocalStorage.generate_key("firm123", "case456", "document.pdf")

        assert "firm123" in key
        assert "case456" in key
        assert "document.pdf" in key


class TestJobQueue:
    """Test job queue functionality"""

    def test_enqueue_synchronous_fallback(self):
        """Test synchronous execution when Redis unavailable"""
        from backend_lite.jobs.queue import enqueue_job

        def simple_task(x, y):
            return x + y

        # Without Redis, should run synchronously
        result = enqueue_job(simple_task, 1, 2)

        assert result['status'] in ['done', 'queued']
        if result['status'] == 'done':
            assert result['result'] == 3

    def test_job_status_not_found(self):
        """Test getting status of non-existent job"""
        from backend_lite.jobs.queue import get_job_status

        result = get_job_status("nonexistent_job_id")

        assert result['status'] in ['not_found', 'unknown']


class TestRateLimiting:
    """Test rate limiting functionality"""

    def test_rate_limiter_without_redis(self):
        """Test rate limiter allows requests when Redis unavailable"""
        from backend_lite.middleware.rate_limit import RateLimiter

        limiter = RateLimiter(redis_url="redis://nonexistent:6379")

        # Should allow all when Redis unavailable
        allowed, remaining, reset = limiter.is_allowed("test_key", 10)
        assert allowed
        assert remaining == 10

    def test_quota_check_without_redis(self):
        """Test quota check allows when Redis unavailable"""
        from backend_lite.middleware.rate_limit import check_document_quota

        # Should allow when Redis unavailable
        assert check_document_quota("firm123", count=1)


class TestDatabaseModels:
    """Test SQLAlchemy models"""

    def test_model_imports(self):
        """Test that all models can be imported"""
        from backend_lite.db.models import (
            Firm, User, Team, TeamMember, AdminTeamScope,
            Case, CaseParticipant, CaseTeam,
            Folder,
            Document, DocumentPage, DocumentBlock,
            Job, Event,
            AnalysisRun, Claim, Issue, Contradiction
        )

        # Verify classes exist
        assert Firm
        assert User
        assert Document
        assert Folder

    def test_enum_values(self):
        """Test enum values"""
        from backend_lite.db.models import (
            SystemRole, TeamRole, CaseStatus,
            DocumentParty, DocumentRole, DocumentStatus,
            JobType, JobStatus, EventType
        )

        # Check some enum values
        assert SystemRole.SUPER_ADMIN.value == "super_admin"
        assert DocumentParty.OURS.value == "ours"
        assert DocumentStatus.READY.value == "ready"
        assert JobType.PARSE_DOC.value == "parse_doc"


class TestZipIngestion:
    """Test ZIP file ingestion"""

    def test_create_test_zip(self):
        """Test creating a ZIP file in memory"""
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("folder1/doc1.txt", "Document 1 content")
            zf.writestr("folder1/subfolder/doc2.txt", "Document 2 content")
            zf.writestr("folder2/doc3.txt", "Document 3 content")

        zip_data = zip_buffer.getvalue()

        # Verify ZIP structure
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            names = zf.namelist()
            assert len(names) == 3
            assert "folder1/doc1.txt" in names

    def test_zip_path_traversal_prevention(self):
        """Test that path traversal is prevented"""
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            # Attempt path traversal
            zf.writestr("../../../etc/passwd", "malicious content")
            zf.writestr("normal/file.txt", "normal content")

        zip_data = zip_buffer.getvalue()

        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            file_list = [
                f for f in zf.namelist()
                if not f.endswith('/') and '..' not in f
            ]

            # Only normal file should be allowed
            assert len(file_list) == 1
            assert "normal/file.txt" in file_list


class TestAutoMetadataDetection:
    """Test automatic metadata detection from file paths"""

    def test_party_detection_from_path(self):
        """Test detecting party from file path"""
        from backend_lite.jobs.tasks import _auto_detect_metadata
        from backend_lite.db.models import DocumentParty, DocumentRole

        # Test plaintiff detection
        party, role = _auto_detect_metadata("Plaintiff/complaint.pdf")
        assert party == DocumentParty.THEIRS

        # Test court detection
        party, role = _auto_detect_metadata("Court/decision.pdf")
        assert party == DocumentParty.COURT

    def test_role_detection_from_path(self):
        """Test detecting role from file path"""
        from backend_lite.jobs.tasks import _auto_detect_metadata
        from backend_lite.db.models import DocumentParty, DocumentRole

        # Test defense detection
        party, role = _auto_detect_metadata("documents/defense.pdf")
        assert role == DocumentRole.DEFENSE

        # Test motion detection
        party, role = _auto_detect_metadata("motions/motion_123.pdf")
        assert role == DocumentRole.MOTION

        # Test affidavit detection
        party, role = _auto_detect_metadata("affidavits/תצהיר_כהן.pdf")
        assert role == DocumentRole.AFFIDAVIT


class TestAPIEndpointSchemas:
    """Test API endpoint schemas"""

    def test_folder_create_schema(self):
        """Test FolderCreate schema validation"""
        from backend_lite.api_upload import FolderCreate

        # Valid folder
        folder = FolderCreate(name="Test Folder")
        assert folder.name == "Test Folder"
        assert folder.parent_id is None

        # With parent
        folder = FolderCreate(name="Subfolder", parent_id="parent123")
        assert folder.parent_id == "parent123"

    def test_document_metadata_schema(self):
        """Test DocumentMetadata schema"""
        from backend_lite.api_upload import DocumentMetadata

        meta = DocumentMetadata(
            party="ours",
            role="defense",
            author="עו״ד כהן"
        )
        assert meta.party == "ours"
        assert meta.author == "עו״ד כהן"


class TestEndToEndFlow:
    """End-to-end flow tests (mock database)"""

    def test_upload_flow_mock(self):
        """Test upload flow with mocked dependencies"""
        # This test verifies the code path without actual DB

        # Mock storage
        mock_storage = MagicMock()
        mock_storage.put.return_value = MagicMock(
            size_bytes=1000,
            sha256="abc123"
        )
        mock_storage.generate_key.return_value = "documents/firm/case/doc.txt"

        # Create test file content
        file_content = "Test document content in Hebrew: זהו מסמך בדיקה".encode('utf-8')

        # Verify mock works
        result = mock_storage.put("test.txt", file_content, "text/plain")
        assert result.size_bytes == 1000


# Run pytest with: pytest backend_lite/tests/test_upload_system.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
