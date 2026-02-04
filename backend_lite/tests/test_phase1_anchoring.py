"""
Phase 1 Anchoring Tests
=======================

Tests for:
- Claim offsets in normalized text
- Anchor propagation into DB locators
- Anchor resolution endpoint
"""

import os
import pytest
from pathlib import Path

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def sqlalchemy_db(tmp_path):
    """Configure a fresh SQLAlchemy SQLite DB for tests."""
    from backend_lite.db.session import reset_engine, init_db

    old_db_url = os.environ.get("DATABASE_URL")
    db_path = tmp_path / "phase1_anchor.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    reset_engine()
    init_db()

    yield

    # Restore env
    if old_db_url is not None:
        os.environ["DATABASE_URL"] = old_db_url
    else:
        os.environ.pop("DATABASE_URL", None)
    reset_engine()


def _seed_case_with_blocks():
    """Create a firm, user, case, document, and blocks for tests."""
    from backend_lite.db.session import get_db_session
    from backend_lite.db.models import (
        Firm,
        User,
        Case,
        Document,
        DocumentBlock,
        DocumentStatus,
        SystemRole,
    )

    block1_text = "החוזה נחתם ביום 01.01.2020."
    block2_text = "החוזה נחתם ביום 02.02.2021."
    full_text = f"{block1_text}\n{block2_text}"

    with get_db_session() as db:
        firm = Firm(name="Test Firm", domain="test.local")
        db.add(firm)
        db.flush()

        user = User(
            firm_id=firm.id,
            email="user@test.local",
            name="Test User",
            system_role=SystemRole.SUPER_ADMIN,
            is_active=True,
        )
        db.add(user)
        db.flush()

        case = Case(
            firm_id=firm.id,
            name="תיק בדיקה",
            created_by_user_id=user.id,
        )
        db.add(case)
        db.flush()

        doc = Document(
            firm_id=firm.id,
            case_id=case.id,
            doc_name="תצהיר בדיקה",
            original_filename="test.txt",
            mime_type="text/plain",
            status=DocumentStatus.READY,
            storage_key="local://test.txt",
            storage_provider="local",
            full_text=full_text,
            page_count=1,
            language="he",
        )
        db.add(doc)
        db.flush()

        # Block 1
        db.add(DocumentBlock(
            document_id=doc.id,
            page_no=1,
            block_index=0,
            paragraph_index=0,
            text=block1_text,
            char_start=0,
            char_end=len(block1_text),
            bbox_json=None,
            locator_json={
                "doc_id": doc.id,
                "page_no": 1,
                "block_index": 0,
                "paragraph_index": 0,
                "char_start": 0,
                "char_end": len(block1_text),
            },
        ))

        # Block 2
        block2_start = len(block1_text) + 1
        db.add(DocumentBlock(
            document_id=doc.id,
            page_no=1,
            block_index=1,
            paragraph_index=1,
            text=block2_text,
            char_start=block2_start,
            char_end=block2_start + len(block2_text),
            bbox_json=None,
            locator_json={
                "doc_id": doc.id,
                "page_no": 1,
                "block_index": 1,
                "paragraph_index": 1,
                "char_start": block2_start,
                "char_end": block2_start + len(block2_text),
            },
        ))

        db.flush()
        return {
            "firm_id": firm.id,
            "user_email": user.email,
            "case_id": case.id,
            "document_id": doc.id,
        }


def test_claim_offsets_match_normalized_text():
    """Claim offsets should align with normalized text."""
    from backend_lite.extractor import ClaimExtractor

    extractor = ClaimExtractor()
    text = "החוזה נחתם ביום 15.3.2020."
    claims = extractor.extract_from_text(text, sanitize=False)
    assert claims

    normalized = extractor._normalize_text(text)
    claim = claims[0]
    assert claim.char_start is not None
    assert claim.char_end is not None
    assert normalized[claim.char_start:claim.char_end] == claim.text


def test_task_analyze_case_populates_anchor_locators(sqlalchemy_db):
    """Analysis should store standardized anchor locators for claims and contradictions."""
    from backend_lite.jobs.tasks import task_analyze_case
    from backend_lite.db.session import get_db_session
    from backend_lite.db.models import Claim as DbClaim, Contradiction

    seed = _seed_case_with_blocks()
    result = task_analyze_case(
        case_id=seed["case_id"],
        firm_id=seed["firm_id"],
        document_ids=[seed["document_id"]],
    )

    run_id = result.get("analysis_run_id")
    assert run_id is not None

    with get_db_session() as db:
        claims = db.query(DbClaim).filter(DbClaim.run_id == run_id).all()
        assert claims
        for cl in claims:
            locator = cl.locator_json or {}
            assert locator.get("doc_id")
            assert locator.get("block_index") is not None
            assert locator.get("char_start") is not None
            assert locator.get("char_end") is not None

        contradictions = db.query(Contradiction).filter(Contradiction.run_id == run_id).all()
        assert contradictions
        c = contradictions[0]
        assert (c.locator1_json or {}).get("doc_id")
        assert (c.locator2_json or {}).get("doc_id")
        assert (c.locator1_json or {}).get("block_index") is not None
        assert (c.locator2_json or {}).get("block_index") is not None


def test_anchor_resolve_endpoint(sqlalchemy_db):
    """Anchor resolution should return highlight offsets and text."""
    from fastapi.testclient import TestClient
    from backend_lite.api import app

    seed = _seed_case_with_blocks()
    client = TestClient(app)
    client.headers.update({"X-User-Email": seed["user_email"]})

    payload = {
        "anchor": {
            "doc_id": seed["document_id"],
            "page_no": 1,
            "block_index": 0,
            "char_start": 0,
            "char_end": 8,
        },
        "context": 1,
    }

    response = client.post("/api/v1/anchors/resolve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == seed["document_id"]
    assert data["text"]
    assert data["highlight_start"] is not None
    assert data["highlight_end"] is not None
