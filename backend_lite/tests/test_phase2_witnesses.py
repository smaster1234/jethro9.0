"""
Phase 2 Witness Tests
=====================
"""

import os
from pathlib import Path
import pytest

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def sqlalchemy_db(tmp_path):
    """Configure a fresh SQLAlchemy SQLite DB for tests."""
    from backend_lite.db.session import reset_engine, init_db

    old_db_url = os.environ.get("DATABASE_URL")
    db_path = tmp_path / "phase2_witness.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    reset_engine()
    init_db()

    yield

    if old_db_url is not None:
        os.environ["DATABASE_URL"] = old_db_url
    else:
        os.environ.pop("DATABASE_URL", None)
    reset_engine()


def _seed_case_with_docs():
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

    doc1_text = "החוזה נחתם ביום 01.01.2020 ולא הייתי נוכח."
    doc2_text = "החוזה נחתם ביום 02.02.2021 הייתי נוכח."

    with get_db_session() as db:
        firm = Firm(name="Test Firm", domain="test.local")
        db.add(firm)
        db.flush()

        user = User(
            firm_id=firm.id,
            email="witness@test.local",
            name="Test User",
            system_role=SystemRole.SUPER_ADMIN,
            is_active=True,
        )
        db.add(user)
        db.flush()

        case = Case(
            firm_id=firm.id,
            name="תיק עדים",
            created_by_user_id=user.id,
        )
        db.add(case)
        db.flush()

        doc1 = Document(
            firm_id=firm.id,
            case_id=case.id,
            doc_name="גרסה 1",
            original_filename="v1.txt",
            mime_type="text/plain",
            status=DocumentStatus.READY,
            storage_key="local://v1.txt",
            storage_provider="local",
            full_text=doc1_text,
            page_count=1,
            language="he",
        )
        doc2 = Document(
            firm_id=firm.id,
            case_id=case.id,
            doc_name="גרסה 2",
            original_filename="v2.txt",
            mime_type="text/plain",
            status=DocumentStatus.READY,
            storage_key="local://v2.txt",
            storage_provider="local",
            full_text=doc2_text,
            page_count=1,
            language="he",
        )
        db.add_all([doc1, doc2])
        db.flush()

        db.add(DocumentBlock(
            document_id=doc1.id,
            page_no=1,
            block_index=0,
            paragraph_index=0,
            text=doc1_text,
            char_start=0,
            char_end=len(doc1_text),
            locator_json={
                "doc_id": doc1.id,
                "page_no": 1,
                "block_index": 0,
                "paragraph_index": 0,
                "char_start": 0,
                "char_end": len(doc1_text),
            },
        ))
        db.add(DocumentBlock(
            document_id=doc2.id,
            page_no=1,
            block_index=0,
            paragraph_index=0,
            text=doc2_text,
            char_start=0,
            char_end=len(doc2_text),
            locator_json={
                "doc_id": doc2.id,
                "page_no": 1,
                "block_index": 0,
                "paragraph_index": 0,
                "char_start": 0,
                "char_end": len(doc2_text),
            },
        ))

        db.flush()

        return {
            "firm_id": firm.id,
            "user_email": user.email,
            "case_id": case.id,
            "doc1_id": doc1.id,
            "doc2_id": doc2.id,
        }


def test_witness_endpoints_and_diff(sqlalchemy_db):
    from fastapi.testclient import TestClient
    from backend_lite.api import app

    seed = _seed_case_with_docs()
    client = TestClient(app)
    client.headers.update({"X-User-Email": seed["user_email"]})

    # Create witness
    resp = client.post(
        f"/api/v1/cases/{seed['case_id']}/witnesses",
        json={"name": "עד בדיקה", "side": "theirs"},
    )
    assert resp.status_code == 200
    witness = resp.json()

    # Add two versions
    v1 = client.post(
        f"/api/v1/witnesses/{witness['id']}/versions",
        json={"document_id": seed["doc1_id"], "version_type": "statement"},
    )
    assert v1.status_code == 200
    v2 = client.post(
        f"/api/v1/witnesses/{witness['id']}/versions",
        json={"document_id": seed["doc2_id"], "version_type": "testimony"},
    )
    assert v2.status_code == 200

    # List witnesses includes versions
    list_resp = client.get(f"/api/v1/cases/{seed['case_id']}/witnesses")
    assert list_resp.status_code == 200
    witnesses = list_resp.json()
    assert len(witnesses) == 1
    assert len(witnesses[0]["versions"]) == 2

    # Diff versions
    diff_resp = client.post(
        f"/api/v1/witnesses/{witness['id']}/versions/diff",
        json={"version_a_id": v1.json()["id"], "version_b_id": v2.json()["id"]},
    )
    assert diff_resp.status_code == 200
    diff = diff_resp.json()
    assert diff["similarity"] >= 0.0
    assert isinstance(diff["shifts"], list)
    for shift in diff["shifts"]:
        assert shift.get("anchor_a") is not None
        assert shift.get("anchor_b") is not None
        assert shift["anchor_a"].get("doc_id")
        assert shift["anchor_b"].get("doc_id")
