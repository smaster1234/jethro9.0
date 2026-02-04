"""
B1 Organization Tests
"""

import os
from pathlib import Path
from datetime import datetime, timedelta

import pytest

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def sqlalchemy_db(tmp_path):
    """Configure a fresh SQLAlchemy SQLite DB for tests."""
    from backend_lite.db.session import reset_engine, init_db

    old_db_url = os.environ.get("DATABASE_URL")
    db_path = tmp_path / "b1_orgs.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    reset_engine()
    init_db()

    yield

    if old_db_url is not None:
        os.environ["DATABASE_URL"] = old_db_url
    else:
        os.environ.pop("DATABASE_URL", None)
    reset_engine()


def _seed_org_data():
    from backend_lite.db.session import get_db_session
    from backend_lite.db.models import (
        Firm,
        User,
        Case,
        AnalysisRun,
        Organization,
        OrganizationMember,
        OrganizationRole,
        InviteStatus,
        OrganizationInvite,
        SystemRole,
    )

    with get_db_session() as db:
        firm = Firm(name="Test Firm", domain="orgs.local")
        db.add(firm)
        db.flush()

        owner = User(
            firm_id=firm.id,
            email="owner@orgs.local",
            name="Owner User",
            system_role=SystemRole.ADMIN,
            is_active=True,
        )
        intern = User(
            firm_id=firm.id,
            email="intern@orgs.local",
            name="Intern User",
            system_role=SystemRole.MEMBER,
            is_active=True,
        )
        outsider = User(
            firm_id=firm.id,
            email="outsider@orgs.local",
            name="Outsider User",
            system_role=SystemRole.MEMBER,
            is_active=True,
        )
        db.add_all([owner, intern, outsider])
        db.flush()

        org_a = Organization(firm_id=firm.id, name="Org A")
        org_b = Organization(firm_id=firm.id, name="Org B")
        db.add_all([org_a, org_b])
        db.flush()

        db.add_all([
            OrganizationMember(
                organization_id=org_a.id,
                user_id=owner.id,
                role=OrganizationRole.OWNER,
                added_by_user_id=owner.id,
            ),
            OrganizationMember(
                organization_id=org_a.id,
                user_id=intern.id,
                role=OrganizationRole.INTERN,
                added_by_user_id=owner.id,
            ),
            OrganizationMember(
                organization_id=org_b.id,
                user_id=outsider.id,
                role=OrganizationRole.VIEWER,
                added_by_user_id=owner.id,
            ),
        ])

        case = Case(
            firm_id=firm.id,
            organization_id=org_a.id,
            name="Org Case",
            created_by_user_id=owner.id,
            status="active",
        )
        db.add(case)
        db.flush()

        run = AnalysisRun(
            firm_id=firm.id,
            case_id=case.id,
            status="done",
            triggered_by_user_id=owner.id,
        )
        db.add(run)
        db.flush()

        expired_invite = OrganizationInvite(
            organization_id=org_a.id,
            email=intern.email,
            token="expired_token",
            status=InviteStatus.PENDING,
            role=OrganizationRole.VIEWER,
            expires_at=datetime.utcnow() - timedelta(days=1),
            created_by_user_id=owner.id,
        )
        db.add(expired_invite)

        return {
            "firm_id": firm.id,
            "org_a": org_a.id,
            "org_b": org_b.id,
            "case_id": case.id,
            "run_id": run.id,
            "owner_email": owner.email,
            "intern_email": intern.email,
            "outsider_email": outsider.email,
            "expired_token": expired_invite.token,
        }


def test_tenant_scoping_blocks_case_access(sqlalchemy_db):
    from fastapi.testclient import TestClient
    from backend_lite.api import app

    seed = _seed_org_data()
    client = TestClient(app)
    client.headers.update({"X-User-Email": seed["outsider_email"]})

    resp = client.get(f"/api/v1/cases/{seed['case_id']}/witnesses")
    assert resp.status_code == 403


def test_invite_accept_expired_token(sqlalchemy_db):
    from fastapi.testclient import TestClient
    from backend_lite.api import app
    from backend_lite.db.session import get_db_session
    from backend_lite.db.models import OrganizationInvite, InviteStatus

    seed = _seed_org_data()
    client = TestClient(app)
    client.headers.update({"X-User-Email": seed["intern_email"]})

    resp = client.post(f"/api/v1/invites/{seed['expired_token']}/accept")
    assert resp.status_code == 400

    with get_db_session() as db:
        invite = db.query(OrganizationInvite).filter(OrganizationInvite.token == seed["expired_token"]).first()
        assert invite.status == InviteStatus.EXPIRED


def test_export_requires_lawyer_or_owner(sqlalchemy_db):
    from fastapi.testclient import TestClient
    from backend_lite.api import app

    seed = _seed_org_data()
    client = TestClient(app)
    client.headers.update({"X-User-Email": seed["intern_email"]})

    resp = client.get(f"/api/v1/analysis-runs/{seed['run_id']}/export/cross-exam?format=docx")
    assert resp.status_code == 403
