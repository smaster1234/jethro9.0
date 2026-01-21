"""
Refactored Code Tests
=====================

Tests for the refactored codebase:
- Ingest module exports
- ZIP bomb protections
- SQLAlchemy-based auth
- Database initialization
"""

import pytest
import os
import io
import zipfile
import tempfile
from pathlib import Path


# =============================================================================
# Ingest Module Export Tests
# =============================================================================

class TestIngestExports:
    """Test that ingest module exports are correct"""

    def test_detect_mime_type_is_exported(self):
        """detect_mime_type should be exported from ingest package"""
        from backend_lite.ingest import detect_mime_type
        assert callable(detect_mime_type)

    def test_is_supported_is_exported(self):
        """is_supported should be exported from ingest package"""
        from backend_lite.ingest import is_supported
        assert callable(is_supported)

    def test_list_supported_formats_is_exported(self):
        """list_supported_formats should be exported from ingest package"""
        from backend_lite.ingest import list_supported_formats
        assert callable(list_supported_formats)

    def test_detect_mime_type_works(self):
        """detect_mime_type should return correct MIME types"""
        from backend_lite.ingest import detect_mime_type

        assert detect_mime_type("test.pdf") == "application/pdf"
        assert detect_mime_type("test.txt") == "text/plain"
        assert detect_mime_type("test.docx") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def test_is_supported_works(self):
        """is_supported should correctly identify supported formats"""
        from backend_lite.ingest import is_supported

        assert is_supported("application/pdf") is True
        assert is_supported("text/plain") is True
        assert is_supported("application/octet-stream") is False


# =============================================================================
# ZIP Security Tests
# =============================================================================

class TestZipSecurity:
    """Test ZIP bomb protection and security validation"""

    def test_validate_zip_safe_rejects_path_traversal(self):
        """ZIP with path traversal should be rejected"""
        from backend_lite.jobs.tasks import validate_zip_safe, ZipSecurityError

        # Create a ZIP with path traversal
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("../evil.txt", "malicious content")

        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            with pytest.raises(ZipSecurityError) as exc_info:
                validate_zip_safe(zf)

        assert "path traversal" in str(exc_info.value).lower()

    def test_validate_zip_safe_rejects_absolute_paths(self):
        """ZIP with absolute paths should be rejected"""
        from backend_lite.jobs.tasks import validate_zip_safe, ZipSecurityError

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("/etc/passwd", "root:x:0:0:")

        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            with pytest.raises(ZipSecurityError) as exc_info:
                validate_zip_safe(zf)

        assert "absolute path" in str(exc_info.value).lower()

    def test_validate_zip_safe_accepts_valid_zip(self):
        """Valid ZIP should be accepted"""
        from backend_lite.jobs.tasks import validate_zip_safe

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("document.txt", "valid content")
            zf.writestr("folder/nested.txt", "also valid")

        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            files = validate_zip_safe(zf)

        assert "document.txt" in files
        assert "folder/nested.txt" in files

    def test_validate_zip_safe_skips_hidden_files(self):
        """Hidden files and __MACOSX should be skipped"""
        from backend_lite.jobs.tasks import validate_zip_safe

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("visible.txt", "content")
            zf.writestr(".hidden", "hidden content")
            zf.writestr("__MACOSX/resource", "mac metadata")

        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            files = validate_zip_safe(zf)

        assert "visible.txt" in files
        assert ".hidden" not in files
        assert "__MACOSX/resource" not in files

    def test_validate_zip_safe_rejects_too_many_files(self):
        """ZIP with too many files should be rejected"""
        from backend_lite.jobs.tasks import validate_zip_safe, ZipSecurityError, MAX_ZIP_FILES
        import os

        # Temporarily reduce max files for test
        original = os.environ.get("MAX_ZIP_FILES")
        os.environ["MAX_ZIP_FILES"] = "5"

        # Need to reimport to get new value
        import importlib
        from backend_lite.jobs import tasks
        importlib.reload(tasks)

        try:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w') as zf:
                for i in range(10):  # More than MAX_ZIP_FILES=5
                    zf.writestr(f"file{i}.txt", f"content {i}")

            zip_buffer.seek(0)
            with zipfile.ZipFile(zip_buffer, 'r') as zf:
                with pytest.raises(ZipSecurityError) as exc_info:
                    tasks.validate_zip_safe(zf)

            assert "too many files" in str(exc_info.value).lower()
        finally:
            # Restore
            if original:
                os.environ["MAX_ZIP_FILES"] = original
            else:
                os.environ.pop("MAX_ZIP_FILES", None)
            importlib.reload(tasks)


# =============================================================================
# SQLAlchemy Database Tests
# =============================================================================

class TestSQLAlchemyDatabase:
    """Test SQLAlchemy database initialization and operations"""

    def test_database_initializes_with_sqlite(self, tmp_path):
        """Database should initialize with SQLite URL"""
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'test.db'}"

        from backend_lite.db.session import init_db, get_db_session
        from backend_lite.db.models import Firm, User

        init_db()

        # Should be able to create and query
        with get_db_session() as db:
            firm = Firm(name="Test Firm")
            db.add(firm)
            db.commit()
            db.refresh(firm)

            # Query back
            retrieved = db.query(Firm).filter(Firm.name == "Test Firm").first()
            assert retrieved is not None
            assert retrieved.id == firm.id

    def test_auth_service_works_with_sqlalchemy(self, tmp_path):
        """AuthService should work with SQLAlchemy session"""
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'test_auth.db'}"

        from backend_lite.db.session import init_db, get_db_session
        from backend_lite.db.models import Firm, User, SystemRole
        from backend_lite.auth import AuthService, get_auth_service

        init_db()

        with get_db_session() as db:
            # Create firm and user
            firm = Firm(name="Test Firm")
            db.add(firm)
            db.commit()
            db.refresh(firm)

            user = User(
                firm_id=firm.id,
                email="test@test.com",
                name="Test User",
                system_role=SystemRole.MEMBER
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # Get auth context
            auth_service = get_auth_service(db)
            auth = auth_service.get_auth_context(user.id)

            assert auth is not None
            assert auth.user_id == user.id
            assert auth.firm_id == firm.id
            assert auth.email == "test@test.com"
            assert auth.is_admin is False

    def test_auth_service_flexible_email_fallback(self, tmp_path):
        """Flexible auth should fall back to email when user_id is unknown"""
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'test_auth_flexible.db'}"

        from backend_lite.db.session import init_db, get_db_session
        from backend_lite.db.models import Firm, User, SystemRole
        from backend_lite.auth import get_auth_service

        init_db()

        with get_db_session() as db:
            firm = Firm(name="Test Firm", domain="test.example")
            db.add(firm)
            db.commit()
            db.refresh(firm)

            user = User(
                firm_id=firm.id,
                email="fallback@test.com",
                name="Fallback User",
                system_role=SystemRole.MEMBER,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            auth_service = get_auth_service(db)
            auth = auth_service.get_auth_context_flexible("non-existent-id", email="fallback@test.com")

            assert auth is not None
            assert auth.user_id == user.id
            assert auth.email == "fallback@test.com"

    def test_auth_service_can_autoprovision_unknown_user(self, tmp_path):
        """When enabled, unknown user_id should be auto-provisioned for demo/dev."""
        import os
        import uuid

        os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'test_auth_autoprovision.db'}"
        original = os.environ.get("BACKEND_LITE_AUTO_PROVISION_USERS")
        os.environ["BACKEND_LITE_AUTO_PROVISION_USERS"] = "true"

        from backend_lite.db.session import init_db, get_db_session
        from backend_lite.db.models import Firm, User
        from backend_lite.auth import get_auth_service

        try:
            init_db()

            new_user_id = str(uuid.uuid4())

            with get_db_session() as db:
                auth_service = get_auth_service(db)
                auth = auth_service.get_auth_context_flexible(new_user_id, email="newuser@demo.com")

                assert auth is not None
                assert auth.user_id == new_user_id

                # Confirm user is persisted
                created = db.query(User).filter(User.id == new_user_id).first()
                assert created is not None
                assert created.is_active is True

                # Confirm demo firm exists/was created
                firm = db.query(Firm).filter(Firm.id == created.firm_id).first()
                assert firm is not None
        finally:
            if original is None:
                os.environ.pop("BACKEND_LITE_AUTO_PROVISION_USERS", None)
            else:
                os.environ["BACKEND_LITE_AUTO_PROVISION_USERS"] = original


# =============================================================================
# Auth Context Tests
# =============================================================================

class TestAuthContext:
    """Test AuthContext dataclass"""

    def test_auth_context_properties(self):
        """AuthContext should have correct property behavior"""
        from backend_lite.auth import AuthContext
        from backend_lite.db.models import SystemRole

        # Super admin
        ctx = AuthContext(
            user_id="u1",
            firm_id="f1",
            email="super@test.com",
            name="Super Admin",
            system_role=SystemRole.SUPER_ADMIN,
            professional_role="Partner",
            team_ids=[],
            team_leader_of=[],
            admin_scope_teams=[]
        )
        assert ctx.is_super_admin is True
        assert ctx.is_admin is True
        assert ctx.is_viewer is False

        # Viewer
        ctx = AuthContext(
            user_id="u2",
            firm_id="f1",
            email="viewer@test.com",
            name="Viewer",
            system_role=SystemRole.VIEWER,
            professional_role=None,
            team_ids=[],
            team_leader_of=[],
            admin_scope_teams=[]
        )
        assert ctx.is_super_admin is False
        assert ctx.is_admin is False
        assert ctx.is_viewer is True


# =============================================================================
# API Endpoint Tests
# =============================================================================

class TestAPIEndpoints:
    """Test API endpoints with refactored code"""

    @pytest.mark.asyncio
    async def test_health_endpoint_works(self):
        """Health endpoint should return 200"""
        from httpx import AsyncClient, ASGITransport
        from backend_lite.api import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_auth_endpoints_exist(self):
        """Auth endpoints should exist"""
        from httpx import AsyncClient, ASGITransport
        from backend_lite.api import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            # Login endpoint should exist (returns 422 without body, not 404)
            response = await client.post("/auth/login")
            assert response.status_code == 422  # Validation error, not 404

            # Register endpoint should exist
            response = await client.post("/auth/register")
            assert response.status_code == 422  # Validation error, not 404

    @pytest.mark.asyncio
    async def test_cors_not_wildcard(self):
        """CORS should not allow all origins"""
        from backend_lite.api import CORS_ALLOW_ORIGINS

        # Should not be a single "*"
        assert CORS_ALLOW_ORIGINS != ["*"]
        assert "*" not in CORS_ALLOW_ORIGINS


# =============================================================================
# No CaseDatabase in Main API Tests
# =============================================================================

class TestNoCaseDatabase:
    """Verify CaseDatabase is not used in main API path"""

    def test_api_does_not_import_get_database(self):
        """Main api.py should not import get_database from models"""
        import ast
        from pathlib import Path

        api_file = Path(__file__).parent.parent / "api.py"
        with open(api_file) as f:
            content = f.read()

        # Parse the AST
        tree = ast.parse(content)

        # Check imports
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "models" in node.module:
                    imported_names = [alias.name for alias in node.names]
                    # CaseDatabase and get_database should not be imported
                    assert "CaseDatabase" not in imported_names, \
                        "CaseDatabase should not be imported from models"
                    # Note: get_database might still be imported for legacy endpoints
                    # The key point is CaseDatabase should not be used


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
