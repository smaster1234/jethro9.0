"""
Authorization Tests
===================

Tests for RBAC authorization logic, multi-tenancy isolation, and access control.
"""

import pytest
from httpx import AsyncClient, ASGITransport

from backend_lite.api import app
from backend_lite.models import (
    CaseDatabase, SystemRole, TeamRole, CaseStatus,
    get_database
)
from backend_lite.auth import AuthService, Permission


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def test_db(tmp_path):
    """Create a fresh test database"""
    db_path = str(tmp_path / "test_auth.db")
    db = CaseDatabase(db_path)
    return db


@pytest.fixture
def seeded_db(test_db):
    """Database with seeded test data"""
    db = test_db

    # Create two firms
    firm_a = db.create_firm(name="Firm A", domain="firma.co.il")
    firm_b = db.create_firm(name="Firm B", domain="firmb.co.il")

    # Create users for Firm A
    super_admin_a = db.create_user(
        firm_id=firm_a.id,
        email="super@firma.co.il",
        name="Super Admin A",
        system_role=SystemRole.SUPER_ADMIN
    )
    admin_a = db.create_user(
        firm_id=firm_a.id,
        email="admin@firma.co.il",
        name="Admin A",
        system_role=SystemRole.ADMIN
    )
    member_a = db.create_user(
        firm_id=firm_a.id,
        email="member@firma.co.il",
        name="Member A",
        system_role=SystemRole.MEMBER
    )
    viewer_a = db.create_user(
        firm_id=firm_a.id,
        email="viewer@firma.co.il",
        name="Viewer A",
        system_role=SystemRole.VIEWER
    )

    # Create users for Firm B
    member_b = db.create_user(
        firm_id=firm_b.id,
        email="member@firmb.co.il",
        name="Member B",
        system_role=SystemRole.MEMBER
    )

    # Create teams for Firm A
    team1_a = db.create_team(
        firm_id=firm_a.id,
        name="Team 1",
        created_by_user_id=super_admin_a.id
    )
    team2_a = db.create_team(
        firm_id=firm_a.id,
        name="Team 2",
        created_by_user_id=super_admin_a.id
    )

    # Add members to teams
    db.add_team_member(team1_a.id, member_a.id, TeamRole.TEAM_LEADER)
    db.add_team_member(team1_a.id, viewer_a.id, TeamRole.TEAM_MEMBER)
    db.add_team_member(team2_a.id, admin_a.id, TeamRole.TEAM_LEADER)

    # Set admin scope (admin_a can manage team1_a only)
    db.set_admin_team_scope(admin_a.id, team1_a.id, granted_by_user_id=super_admin_a.id)

    # Create cases for Firm A
    case1_a = db.create_case(name="Case 1 - Team 1")
    db.update_case_firm(case1_a.id, firm_a.id)
    db.assign_case_to_team(case1_a.id, team1_a.id, assigned_by_user_id=super_admin_a.id)

    case2_a = db.create_case(name="Case 2 - Team 2")
    db.update_case_firm(case2_a.id, firm_a.id)
    db.assign_case_to_team(case2_a.id, team2_a.id, assigned_by_user_id=super_admin_a.id)

    # Create a case for Firm B
    case_b = db.create_case(name="Case B")
    db.update_case_firm(case_b.id, firm_b.id)

    return {
        "db": db,
        "firm_a": firm_a,
        "firm_b": firm_b,
        "super_admin_a": super_admin_a,
        "admin_a": admin_a,
        "member_a": member_a,
        "viewer_a": viewer_a,
        "member_b": member_b,
        "team1_a": team1_a,
        "team2_a": team2_a,
        "case1_a": case1_a,
        "case2_a": case2_a,
        "case_b": case_b,
    }


# =============================================================================
# AuthContext Tests
# =============================================================================

class TestAuthContext:
    """Test AuthContext construction and properties"""

    def test_super_admin_context(self, seeded_db):
        """Super admin should have full access flags"""
        db = seeded_db["db"]
        auth_service = AuthService(db)

        auth = auth_service.get_auth_context(seeded_db["super_admin_a"].id)

        assert auth is not None
        assert auth.is_super_admin is True
        assert auth.is_admin is True
        assert auth.is_viewer is False
        assert auth.firm_id == seeded_db["firm_a"].id

    def test_admin_context(self, seeded_db):
        """Admin should have admin flag but not super_admin"""
        db = seeded_db["db"]
        auth_service = AuthService(db)

        auth = auth_service.get_auth_context(seeded_db["admin_a"].id)

        assert auth is not None
        assert auth.is_super_admin is False
        assert auth.is_admin is True
        assert auth.is_viewer is False
        assert len(auth.admin_scope_teams) == 1
        assert seeded_db["team1_a"].id in auth.admin_scope_teams

    def test_member_context(self, seeded_db):
        """Member should have team memberships loaded"""
        db = seeded_db["db"]
        auth_service = AuthService(db)

        auth = auth_service.get_auth_context(seeded_db["member_a"].id)

        assert auth is not None
        assert auth.is_super_admin is False
        assert auth.is_admin is False
        assert auth.is_viewer is False
        assert seeded_db["team1_a"].id in auth.team_ids
        assert seeded_db["team1_a"].id in auth.team_leader_of

    def test_viewer_context(self, seeded_db):
        """Viewer should have viewer flag"""
        db = seeded_db["db"]
        auth_service = AuthService(db)

        auth = auth_service.get_auth_context(seeded_db["viewer_a"].id)

        assert auth is not None
        assert auth.is_viewer is True

    def test_inactive_user_returns_none(self, seeded_db):
        """Inactive user should not get auth context"""
        db = seeded_db["db"]

        # Deactivate user (direct DB update)
        import sqlite3
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_active = 0 WHERE id = ?",
            (seeded_db["member_a"].id,)
        )
        conn.commit()
        conn.close()

        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["member_a"].id)

        assert auth is None

    def test_nonexistent_user_returns_none(self, seeded_db):
        """Nonexistent user should not get auth context"""
        db = seeded_db["db"]
        auth_service = AuthService(db)

        auth = auth_service.get_auth_context("nonexistent-user-id")

        assert auth is None


# =============================================================================
# Permission Tests
# =============================================================================

class TestPermissions:
    """Test role-based permissions"""

    def test_super_admin_has_all_permissions(self, seeded_db):
        """Super admin should have all permissions"""
        db = seeded_db["db"]
        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["super_admin_a"].id)

        assert auth.has_permission(Permission.CASE_CREATE)
        assert auth.has_permission(Permission.CASE_DELETE)
        assert auth.has_permission(Permission.USER_CREATE)
        assert auth.has_permission(Permission.USER_DEACTIVATE)
        assert auth.has_permission(Permission.TEAM_CREATE)
        assert auth.has_permission(Permission.TEAM_DELETE)
        assert auth.has_permission(Permission.FIRM_UPDATE)
        assert auth.has_permission(Permission.ADMIN_SCOPE_MANAGE)

    def test_admin_cannot_delete_cases(self, seeded_db):
        """Admin should not have case delete permission"""
        db = seeded_db["db"]
        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["admin_a"].id)

        assert auth.has_permission(Permission.CASE_CREATE)
        assert not auth.has_permission(Permission.CASE_DELETE)
        assert auth.has_permission(Permission.USER_CREATE)
        assert not auth.has_permission(Permission.USER_DEACTIVATE)

    def test_member_permissions(self, seeded_db):
        """Member should have limited permissions"""
        db = seeded_db["db"]
        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["member_a"].id)

        assert auth.has_permission(Permission.CASE_CREATE)
        assert auth.has_permission(Permission.CASE_READ)
        assert not auth.has_permission(Permission.CASE_DELETE)
        assert not auth.has_permission(Permission.TEAM_CREATE)
        assert not auth.has_permission(Permission.TEAM_DELETE)

    def test_viewer_has_read_only(self, seeded_db):
        """Viewer should only have read permissions"""
        db = seeded_db["db"]
        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["viewer_a"].id)

        assert auth.has_permission(Permission.CASE_READ)
        assert auth.has_permission(Permission.DOC_READ)
        assert not auth.has_permission(Permission.CASE_CREATE)
        assert not auth.has_permission(Permission.CASE_UPDATE)
        assert not auth.has_permission(Permission.DOC_CREATE)


# =============================================================================
# Case Access Tests
# =============================================================================

class TestCaseAccess:
    """Test case-level access control"""

    def test_super_admin_can_access_all_firm_cases(self, seeded_db):
        """Super admin can access all cases in their firm"""
        db = seeded_db["db"]
        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["super_admin_a"].id)

        assert auth.can_access_case(seeded_db["case1_a"].id, db)
        assert auth.can_access_case(seeded_db["case2_a"].id, db)

    def test_super_admin_cannot_access_other_firm_cases(self, seeded_db):
        """Super admin cannot access cases from other firms"""
        db = seeded_db["db"]
        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["super_admin_a"].id)

        # Super admin A cannot access Firm B's case
        assert not auth.can_access_case(seeded_db["case_b"].id, db)

    def test_admin_can_access_scoped_team_cases(self, seeded_db):
        """Admin can access cases from teams in their scope"""
        db = seeded_db["db"]
        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["admin_a"].id)

        # Admin A has scope over team1, which has case1
        assert auth.can_access_case(seeded_db["case1_a"].id, db)
        # Admin A does NOT have scope over team2
        assert not auth.can_access_case(seeded_db["case2_a"].id, db)

    def test_member_can_access_team_cases(self, seeded_db):
        """Member can access cases from their teams"""
        db = seeded_db["db"]
        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["member_a"].id)

        # Member A is in team1, which has case1
        assert auth.can_access_case(seeded_db["case1_a"].id, db)
        # Member A is NOT in team2
        assert not auth.can_access_case(seeded_db["case2_a"].id, db)

    def test_member_cannot_access_other_firm_cases(self, seeded_db):
        """Member cannot access cases from other firms"""
        db = seeded_db["db"]
        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["member_a"].id)

        assert not auth.can_access_case(seeded_db["case_b"].id, db)

    def test_accessible_cases_list(self, seeded_db):
        """Test getting list of accessible cases"""
        db = seeded_db["db"]
        auth_service = AuthService(db)

        # Super admin sees all firm cases
        super_auth = auth_service.get_auth_context(seeded_db["super_admin_a"].id)
        super_cases = auth_service.get_accessible_cases(super_auth)
        assert len(super_cases) == 2
        assert seeded_db["case1_a"].id in super_cases
        assert seeded_db["case2_a"].id in super_cases

        # Member sees only team cases
        member_auth = auth_service.get_auth_context(seeded_db["member_a"].id)
        member_cases = auth_service.get_accessible_cases(member_auth)
        assert len(member_cases) == 1
        assert seeded_db["case1_a"].id in member_cases


# =============================================================================
# Team Management Tests
# =============================================================================

class TestTeamManagement:
    """Test team management permissions"""

    def test_super_admin_can_manage_all_teams(self, seeded_db):
        """Super admin can manage all teams in their firm"""
        db = seeded_db["db"]
        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["super_admin_a"].id)

        assert auth.can_manage_team(seeded_db["team1_a"].id)
        assert auth.can_manage_team(seeded_db["team2_a"].id)

    def test_admin_can_manage_scoped_teams(self, seeded_db):
        """Admin can only manage teams in their scope"""
        db = seeded_db["db"]
        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["admin_a"].id)

        assert auth.can_manage_team(seeded_db["team1_a"].id)  # In scope
        assert not auth.can_manage_team(seeded_db["team2_a"].id)  # Not in scope

    def test_team_leader_can_manage_own_team(self, seeded_db):
        """Team leader can manage their own team"""
        db = seeded_db["db"]
        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["member_a"].id)

        # Member A is team leader of team1
        assert auth.can_manage_team(seeded_db["team1_a"].id)
        assert not auth.can_manage_team(seeded_db["team2_a"].id)

    def test_regular_member_cannot_manage_teams(self, seeded_db):
        """Regular team member cannot manage teams"""
        db = seeded_db["db"]
        auth_service = AuthService(db)
        auth = auth_service.get_auth_context(seeded_db["viewer_a"].id)

        # Viewer is in team1 but not as leader
        assert not auth.can_manage_team(seeded_db["team1_a"].id)
        assert not auth.can_manage_team(seeded_db["team2_a"].id)


# =============================================================================
# Cross-Firm Isolation Tests
# =============================================================================

class TestFirmIsolation:
    """Test that firms are properly isolated"""

    def test_user_cannot_see_other_firm_users(self, seeded_db):
        """Users cannot see users from other firms"""
        db = seeded_db["db"]

        # Get users for Firm A
        users_a = db.list_users_by_firm(seeded_db["firm_a"].id)
        user_ids_a = [u.id for u in users_a]

        # Get users for Firm B
        users_b = db.list_users_by_firm(seeded_db["firm_b"].id)
        user_ids_b = [u.id for u in users_b]

        # No overlap
        assert not set(user_ids_a) & set(user_ids_b)

        # Member B not in Firm A list
        assert seeded_db["member_b"].id not in user_ids_a

    def test_user_cannot_see_other_firm_teams(self, seeded_db):
        """Users cannot see teams from other firms"""
        db = seeded_db["db"]

        teams_a = db.list_teams_by_firm(seeded_db["firm_a"].id)
        teams_b = db.list_teams_by_firm(seeded_db["firm_b"].id)

        team_ids_a = [t.id for t in teams_a]

        # Team1 and Team2 are in Firm A
        assert seeded_db["team1_a"].id in team_ids_a
        assert seeded_db["team2_a"].id in team_ids_a

        # No teams in Firm B (we didn't create any)
        assert len(teams_b) == 0

    def test_case_firm_assignment_enforced(self, seeded_db):
        """Cases are properly filtered by firm"""
        db = seeded_db["db"]

        cases_a = db.list_cases_by_firm(seeded_db["firm_a"].id)
        cases_b = db.list_cases_by_firm(seeded_db["firm_b"].id)

        case_ids_a = [c.id for c in cases_a]
        case_ids_b = [c.id for c in cases_b]

        # Case 1 and 2 in Firm A
        assert seeded_db["case1_a"].id in case_ids_a
        assert seeded_db["case2_a"].id in case_ids_a

        # Case B in Firm B
        assert seeded_db["case_b"].id in case_ids_b

        # No cross-firm contamination
        assert seeded_db["case_b"].id not in case_ids_a
        assert seeded_db["case1_a"].id not in case_ids_b


# =============================================================================
# Integration Tests (API Level)
# =============================================================================

class TestAPIAuth:
    """Test API-level authentication and authorization"""

    @pytest.mark.asyncio
    async def test_unauthenticated_request_to_protected_endpoint(self):
        """Request without X-User-Id to protected endpoint should fail"""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get("/users/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_user_id_returns_401(self):
        """Request with invalid user ID should fail"""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get(
                "/users/me",
                headers={"X-User-Id": "invalid-user-id"}
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_public_endpoints_work_without_auth(self):
        """Public endpoints should work without authentication"""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            # Health check is public
            response = await client.get("/health")
            assert response.status_code == 200

            # Analysis endpoints are public for backwards compat
            response = await client.post(
                "/analyze",
                json={"text": "Test text"}
            )
            assert response.status_code == 200
