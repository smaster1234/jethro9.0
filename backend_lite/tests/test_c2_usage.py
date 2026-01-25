"""
C2 Entity Usage Tests
"""

import os
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def sqlalchemy_db(tmp_path):
    from backend_lite.db.session import reset_engine, init_db

    old_db_url = os.environ.get("DATABASE_URL")
    db_path = tmp_path / "c2_usage.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    reset_engine()
    init_db()

    yield

    if old_db_url is not None:
        os.environ["DATABASE_URL"] = old_db_url
    else:
        os.environ.pop("DATABASE_URL", None)
    reset_engine()


def _seed_usage_data():
    from backend_lite.db.session import get_db_session
    from backend_lite.db.models import (
        Firm,
        User,
        Case,
        AnalysisRun,
        Organization,
        OrganizationMember,
        OrganizationRole,
        Document,
        Contradiction,
        ContradictionInsight,
        DocumentStatus,
        SystemRole,
    )

    with get_db_session() as db:
        firm = Firm(name="Usage Firm", domain="usage.local")
        db.add(firm)
        db.flush()

        user = User(
            firm_id=firm.id,
            email="usage@orgs.local",
            name="Usage User",
            system_role=SystemRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        db.flush()

        org = Organization(firm_id=firm.id, name="Org Usage")
        db.add(org)
        db.flush()

        db.add(OrganizationMember(
            organization_id=org.id,
            user_id=user.id,
            role=OrganizationRole.OWNER,
            added_by_user_id=user.id,
        ))

        case = Case(
            firm_id=firm.id,
            organization_id=org.id,
            name="Usage Case",
            created_by_user_id=user.id,
            status="active",
        )
        db.add(case)
        db.flush()

        doc = Document(
            firm_id=firm.id,
            case_id=case.id,
            doc_name="Doc1",
            original_filename="doc1.txt",
            mime_type="text/plain",
            status=DocumentStatus.READY,
            storage_key="doc1.txt",
            storage_provider="local",
            size_bytes=100,
            sha256="dummy",
        )
        db.add(doc)
        db.flush()

        run = AnalysisRun(
            firm_id=firm.id,
            case_id=case.id,
            status="done",
            triggered_by_user_id=user.id,
        )
        db.add(run)
        db.flush()

        contr = Contradiction(
            run_id=run.id,
            contradiction_type="TEMPORAL_DATE",
            severity="high",
            quote1="החוזה נחתם ביום 01.01.2020",
            quote2="החוזה נחתם ביום 01.02.2020",
            locator1_json={"doc_id": doc.id, "char_start": 0, "char_end": 10, "snippet": "01.01.2020"},
            locator2_json={"doc_id": doc.id, "char_start": 11, "char_end": 20, "snippet": "01.02.2020"},
        )
        db.add(contr)
        db.flush()

        db.add(ContradictionInsight(
            contradiction_id=contr.id,
            impact_score=0.9,
            risk_score=0.2,
            verifiability_score=0.8,
            stage_recommendation="early",
        ))

        return {
            "case_id": case.id,
            "run_id": run.id,
            "doc_id": doc.id,
            "email": user.email,
        }


def _get_usage_counts(db, case_id: str, usage_type: str):
    from backend_lite.db.models import EntityUsage
    return db.query(EntityUsage).filter(
        EntityUsage.case_id == case_id,
        EntityUsage.usage_type == usage_type,
    ).count()


def test_plan_usage_records(sqlalchemy_db):
    from fastapi.testclient import TestClient
    from backend_lite.api import app
    from backend_lite.db.session import get_db_session
    from backend_lite.db.models import EntityUsage

    seed = _seed_usage_data()
    client = TestClient(app)
    client.headers.update({"X-User-Email": seed["email"]})

    resp = client.post(f"/api/v1/analysis-runs/{seed['run_id']}/cross-exam-plan", json={})
    assert resp.status_code == 200

    with get_db_session() as db:
        rows = db.query(EntityUsage).filter(EntityUsage.case_id == seed["case_id"]).all()
        types = {(r.entity_type, r.usage_type) for r in rows}
        assert ("contradiction", "plan") in types
        assert ("insight", "plan") in types
        assert ("plan_step", "plan") in types
        assert ("question", "plan") in types


def test_training_usage_records_and_idempotency(sqlalchemy_db):
    from fastapi.testclient import TestClient
    from backend_lite.api import app
    from backend_lite.db.session import get_db_session

    seed = _seed_usage_data()
    client = TestClient(app)
    client.headers.update({"X-User-Email": seed["email"]})

    plan_resp = client.post(f"/api/v1/analysis-runs/{seed['run_id']}/cross-exam-plan", json={})
    plan_id = plan_resp.json()["plan_id"]

    session_resp = client.post(f"/api/v1/cases/{seed['case_id']}/training/start", json={
        "plan_id": plan_id,
        "persona": "cooperative",
    })
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    step_id = plan_resp.json()["stages"][0]["steps"][0]["id"]
    turn_resp = client.post(f"/api/v1/training/{session_id}/turn", json={
        "step_id": step_id,
    })
    assert turn_resp.status_code == 200

    with get_db_session() as db:
        count_first = _get_usage_counts(db, seed["case_id"], "training")

    turn_resp2 = client.post(f"/api/v1/training/{session_id}/turn", json={
        "step_id": step_id,
    })
    assert turn_resp2.status_code == 200

    with get_db_session() as db:
        count_second = _get_usage_counts(db, seed["case_id"], "training")

    assert count_first == count_second


def test_export_usage_records_and_idempotency(sqlalchemy_db):
    from fastapi.testclient import TestClient
    from backend_lite.api import app
    from backend_lite.db.session import get_db_session

    seed = _seed_usage_data()
    client = TestClient(app)
    client.headers.update({"X-User-Email": seed["email"]})

    plan_resp = client.post(f"/api/v1/analysis-runs/{seed['run_id']}/cross-exam-plan", json={})
    assert plan_resp.status_code == 200

    export_resp = client.get(f"/api/v1/analysis-runs/{seed['run_id']}/export/cross-exam?format=docx")
    assert export_resp.status_code == 200

    with get_db_session() as db:
        count_first = _get_usage_counts(db, seed["case_id"], "export")

    export_resp2 = client.get(f"/api/v1/analysis-runs/{seed['run_id']}/export/cross-exam?format=docx")
    assert export_resp2.status_code == 200

    with get_db_session() as db:
        count_second = _get_usage_counts(db, seed["case_id"], "export")

    assert count_first == count_second
