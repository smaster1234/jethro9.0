"""
C3 Feedback API Tests
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
    db_path = tmp_path / "c3_feedback.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    reset_engine()
    init_db()

    yield

    if old_db_url is not None:
        os.environ["DATABASE_URL"] = old_db_url
    else:
        os.environ.pop("DATABASE_URL", None)
    reset_engine()


def _seed_case():
    from backend_lite.db.session import get_db_session
    from backend_lite.db.models import (
        Firm,
        User,
        Case,
        Organization,
        OrganizationMember,
        OrganizationRole,
        SystemRole,
    )

    with get_db_session() as db:
        firm = Firm(name="Feedback Firm", domain="feedback.local")
        db.add(firm)
        db.flush()

        user = User(
            firm_id=firm.id,
            email="feedback@orgs.local",
            name="Feedback User",
            system_role=SystemRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        db.flush()

        org = Organization(firm_id=firm.id, name="Org Feedback")
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
            name="Feedback Case",
            created_by_user_id=user.id,
            status="active",
        )
        db.add(case)
        db.flush()

        return {"case_id": case.id, "email": user.email}


def test_create_feedback_and_aggregate(sqlalchemy_db):
    from fastapi.testclient import TestClient
    from backend_lite.api import app

    seed = _seed_case()
    client = TestClient(app)
    client.headers.update({"X-User-Email": seed["email"]})

    payload = {
        "case_id": seed["case_id"],
        "entity_type": "insight",
        "entity_id": "contr-1",
        "label": "excellent",
        "note": "מעולה",
    }
    resp = client.post("/api/v1/feedback", json=payload)
    assert resp.status_code == 200

    resp2 = client.post("/api/v1/feedback", json={
        "case_id": seed["case_id"],
        "entity_type": "insight",
        "entity_id": "contr-1",
        "label": "excellent",
    })
    assert resp2.status_code == 200

    list_resp = client.get("/api/v1/feedback", params={"case_id": seed["case_id"], "entity_type": "insight"})
    assert list_resp.status_code == 200
    data = list_resp.json()
    aggregates = {a["entity_id"]: a for a in data["aggregates"]}
    assert aggregates["contr-1"]["counts"]["excellent"] == 2


def test_sort_feedback_aggregates_deterministic():
    from backend_lite.feedback_utils import sort_feedback_aggregates

    items = [
        {"entity_type": "insight", "entity_id": "b", "counts": {"excellent": 2, "too_risky": 0}},
        {"entity_type": "insight", "entity_id": "a", "counts": {"excellent": 0, "too_risky": 2}},
        {"entity_type": "insight", "entity_id": "c", "counts": {"excellent": 0, "too_risky": 0}},
    ]
    sorted_items = sort_feedback_aggregates(items)
    ids = [i["entity_id"] for i in sorted_items]
    assert ids == ["b", "c", "a"]
