"""
C1 Training Session Tests
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
    db_path = tmp_path / "c1_training.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    reset_engine()
    init_db()

    yield

    if old_db_url is not None:
        os.environ["DATABASE_URL"] = old_db_url
    else:
        os.environ.pop("DATABASE_URL", None)
    reset_engine()


def _seed_training_data():
    from backend_lite.db.session import get_db_session
    from backend_lite.db.models import (
        Firm,
        User,
        Case,
        AnalysisRun,
        Organization,
        OrganizationMember,
        OrganizationRole,
        CrossExamPlan,
        Witness,
        SystemRole,
    )

    with get_db_session() as db:
        firm = Firm(name="Training Firm", domain="training.local")
        db.add(firm)
        db.flush()

        user = User(
            firm_id=firm.id,
            email="trainer@orgs.local",
            name="Trainer User",
            system_role=SystemRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        db.flush()

        org = Organization(firm_id=firm.id, name="Org Training")
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
            name="Training Case",
            created_by_user_id=user.id,
            status="active",
        )
        db.add(case)
        db.flush()

        witness = Witness(
            firm_id=firm.id,
            case_id=case.id,
            name="Witness A",
            side="ours",
        )
        db.add(witness)
        db.flush()

        run = AnalysisRun(
            firm_id=firm.id,
            case_id=case.id,
            status="done",
            triggered_by_user_id=user.id,
        )
        db.add(run)
        db.flush()

        plan = CrossExamPlan(
            firm_id=firm.id,
            case_id=case.id,
            run_id=run.id,
            witness_id=witness.id,
            plan_json={
                "stages": [
                    {
                        "stage": "early",
                        "steps": [
                            {
                                "id": "step-1",
                                "step_type": "lock_in",
                                "question": "אתה מאשר את הגרסה?",
                                "branches": [
                                    {"trigger": "לא זוכר", "follow_up_questions": ["אתה בטוח?"]},
                                ],
                            }
                        ],
                    }
                ]
            },
        )
        db.add(plan)
        db.flush()

        return {
            "case_id": case.id,
            "plan_id": plan.id,
            "witness_id": witness.id,
            "email": user.email,
        }


def test_training_session_flow(sqlalchemy_db):
    from fastapi.testclient import TestClient
    from backend_lite.api import app

    seed = _seed_training_data()
    client = TestClient(app)
    client.headers.update({"X-User-Email": seed["email"]})

    start_resp = client.post(f"/api/v1/cases/{seed['case_id']}/training/start", json={
        "plan_id": seed["plan_id"],
        "witness_id": seed["witness_id"],
        "persona": "cooperative",
    })
    assert start_resp.status_code == 200
    session_id = start_resp.json()["session_id"]

    turn_resp = client.post(f"/api/v1/training/{session_id}/turn", json={
        "step_id": "step-1",
        "chosen_branch": "לא זוכר",
    })
    assert turn_resp.status_code == 200
    assert turn_resp.json()["step_id"] == "step-1"

    back_resp = client.post(f"/api/v1/training/{session_id}/back")
    assert back_resp.status_code == 200
    assert back_resp.json()["back_remaining"] == 1

    turn_resp2 = client.post(f"/api/v1/training/{session_id}/turn", json={
        "step_id": "step-1",
    })
    assert turn_resp2.status_code == 200

    finish_resp = client.post(f"/api/v1/training/{session_id}/finish")
    assert finish_resp.status_code == 200
    summary = finish_resp.json()["summary"]
    assert summary["total_turns"] == 1
