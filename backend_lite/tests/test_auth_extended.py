"""
Extended Logical Tests — Auth & RBAC
=====================================

~50 tests covering:
- SystemRole enum and permissions
- Permission enum
- TeamRole enum
- Role-based access control logic
- Role hierarchy
- Password hashing (when available)
- JWT tokens (when available)
"""

import pytest
from backend_lite.auth import (
    SystemRole,
    TeamRole,
    Permission,
    ROLE_PERMISSIONS,
    get_password_hash,
    verify_password,
)


# Check if password hashing is available
_PASSLIB_AVAILABLE = False
try:
    _test_hash = get_password_hash("test")
    _PASSLIB_AVAILABLE = True
except Exception:
    pass

# Check if JWT is available — must handle PanicException from pyo3
_JWT_AVAILABLE = False
try:
    from backend_lite.auth import is_jwt_available
    _JWT_AVAILABLE = is_jwt_available()
except (Exception, SystemExit):
    pass
except BaseException:
    # pyo3 PanicException inherits from BaseException
    pass


# ===================================================================
# 1. SystemRole Enum
# ===================================================================

class TestSystemRole:
    def test_super_admin(self):
        assert SystemRole.SUPER_ADMIN.value == "super_admin"

    def test_admin(self):
        assert SystemRole.ADMIN.value == "admin"

    def test_member(self):
        assert SystemRole.MEMBER.value == "member"

    def test_viewer(self):
        assert SystemRole.VIEWER.value == "viewer"

    def test_all_roles_unique(self):
        values = [r.value for r in SystemRole]
        assert len(values) == len(set(values))

    def test_count(self):
        assert len(list(SystemRole)) == 4

    def test_is_str_enum(self):
        assert isinstance(SystemRole.SUPER_ADMIN.value, str)


# ===================================================================
# 2. TeamRole Enum
# ===================================================================

class TestTeamRole:
    def test_team_leader(self):
        assert TeamRole.TEAM_LEADER.value == "team_leader"

    def test_team_member(self):
        assert TeamRole.TEAM_MEMBER.value == "team_member"

    def test_count(self):
        assert len(list(TeamRole)) == 2

    def test_all_values_unique(self):
        values = [r.value for r in TeamRole]
        assert len(values) == len(set(values))


# ===================================================================
# 3. Permission Enum
# ===================================================================

class TestPermission:
    def test_case_permissions_exist(self):
        assert Permission.CASE_CREATE.value == "case:create"
        assert Permission.CASE_READ.value == "case:read"
        assert Permission.CASE_UPDATE.value == "case:update"
        assert Permission.CASE_DELETE.value == "case:delete"
        assert Permission.CASE_ANALYZE.value == "case:analyze"

    def test_doc_permissions_exist(self):
        assert Permission.DOC_CREATE.value == "doc:create"
        assert Permission.DOC_READ.value == "doc:read"
        assert Permission.DOC_UPDATE.value == "doc:update"
        assert Permission.DOC_DELETE.value == "doc:delete"

    def test_team_permissions_exist(self):
        assert Permission.TEAM_CREATE.value == "team:create"
        assert Permission.TEAM_READ.value == "team:read"
        assert Permission.TEAM_UPDATE.value == "team:update"
        assert Permission.TEAM_DELETE.value == "team:delete"
        assert Permission.TEAM_MANAGE_MEMBERS.value == "team:manage_members"

    def test_user_permissions_exist(self):
        assert Permission.USER_CREATE.value == "user:create"
        assert Permission.USER_READ.value == "user:read"
        assert Permission.USER_UPDATE.value == "user:update"
        assert Permission.USER_DEACTIVATE.value == "user:deactivate"

    def test_firm_permissions_exist(self):
        assert Permission.FIRM_READ.value == "firm:read"
        assert Permission.FIRM_UPDATE.value == "firm:update"

    def test_admin_scope_permission(self):
        assert Permission.ADMIN_SCOPE_MANAGE.value == "admin:scope_manage"

    def test_all_values_unique(self):
        values = [p.value for p in Permission]
        assert len(values) == len(set(values))

    def test_permission_format(self):
        # All permissions follow "resource:action" format
        for p in Permission:
            assert ":" in p.value


# ===================================================================
# 4. ROLE_PERMISSIONS Mapping
# ===================================================================

class TestRolePermissions:
    def test_all_roles_have_permissions(self):
        for role in SystemRole:
            assert role in ROLE_PERMISSIONS

    def test_super_admin_has_all(self):
        perms = ROLE_PERMISSIONS[SystemRole.SUPER_ADMIN]
        assert Permission.CASE_CREATE in perms
        assert Permission.CASE_DELETE in perms
        assert Permission.USER_CREATE in perms
        assert Permission.FIRM_UPDATE in perms
        assert Permission.ADMIN_SCOPE_MANAGE in perms

    def test_admin_has_case_permissions(self):
        perms = ROLE_PERMISSIONS[SystemRole.ADMIN]
        assert Permission.CASE_CREATE in perms
        assert Permission.CASE_READ in perms

    def test_member_has_basic_permissions(self):
        perms = ROLE_PERMISSIONS[SystemRole.MEMBER]
        assert Permission.CASE_READ in perms
        assert Permission.DOC_READ in perms

    def test_viewer_has_read_only(self):
        perms = ROLE_PERMISSIONS[SystemRole.VIEWER]
        assert Permission.CASE_READ in perms
        # Viewer should not have write permissions
        assert Permission.CASE_CREATE not in perms
        assert Permission.CASE_DELETE not in perms

    def test_role_hierarchy_viewer_subset_of_member(self):
        viewer_perms = ROLE_PERMISSIONS[SystemRole.VIEWER]
        member_perms = ROLE_PERMISSIONS[SystemRole.MEMBER]
        assert viewer_perms.issubset(member_perms)

    def test_role_hierarchy_member_subset_of_admin(self):
        member_perms = ROLE_PERMISSIONS[SystemRole.MEMBER]
        admin_perms = ROLE_PERMISSIONS[SystemRole.ADMIN]
        assert member_perms.issubset(admin_perms)

    def test_role_hierarchy_admin_subset_of_super_admin(self):
        admin_perms = ROLE_PERMISSIONS[SystemRole.ADMIN]
        super_admin_perms = ROLE_PERMISSIONS[SystemRole.SUPER_ADMIN]
        assert admin_perms.issubset(super_admin_perms)

    def test_permissions_are_sets(self):
        for role, perms in ROLE_PERMISSIONS.items():
            assert isinstance(perms, (set, frozenset))

    def test_viewer_no_delete(self):
        perms = ROLE_PERMISSIONS[SystemRole.VIEWER]
        assert Permission.CASE_DELETE not in perms
        assert Permission.DOC_DELETE not in perms

    def test_viewer_no_create(self):
        perms = ROLE_PERMISSIONS[SystemRole.VIEWER]
        assert Permission.CASE_CREATE not in perms
        assert Permission.DOC_CREATE not in perms

    def test_admin_has_team_read(self):
        perms = ROLE_PERMISSIONS[SystemRole.ADMIN]
        assert Permission.TEAM_READ in perms

    def test_super_admin_has_admin_scope(self):
        perms = ROLE_PERMISSIONS[SystemRole.SUPER_ADMIN]
        assert Permission.ADMIN_SCOPE_MANAGE in perms

    def test_viewer_no_admin_scope(self):
        perms = ROLE_PERMISSIONS[SystemRole.VIEWER]
        assert Permission.ADMIN_SCOPE_MANAGE not in perms


# ===================================================================
# 5. Password Hashing (when available)
# ===================================================================

@pytest.mark.skipif(not _PASSLIB_AVAILABLE, reason="passlib/bcrypt not available")
class TestPasswordHashing:
    def test_hash_returns_string(self):
        hashed = get_password_hash("test_password")
        assert isinstance(hashed, str)

    def test_hash_not_plain_text(self):
        hashed = get_password_hash("test_password")
        assert hashed != "test_password"

    def test_verify_correct_password(self):
        hashed = get_password_hash("test_password")
        assert verify_password("test_password", hashed) is True

    def test_verify_wrong_password(self):
        hashed = get_password_hash("test_password")
        assert verify_password("wrong_password", hashed) is False

    def test_different_hashes_for_same_password(self):
        h1 = get_password_hash("test_password")
        h2 = get_password_hash("test_password")
        assert h1 != h2


# ===================================================================
# 6. JWT Tokens (when available)
# ===================================================================

@pytest.mark.skipif(not _JWT_AVAILABLE, reason="JWT not available")
class TestJWTTokens:
    def test_create_access_token(self):
        from backend_lite.auth import create_access_token
        token = create_access_token(data={"sub": "user123"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_token(self):
        from backend_lite.auth import create_access_token, decode_token
        token = create_access_token(data={"sub": "user123"})
        payload = decode_token(token)
        assert payload is not None
        assert payload.get("sub") == "user123"

    def test_decode_invalid_token(self):
        from backend_lite.auth import decode_token
        payload = decode_token("invalid.token.string")
        assert payload is None
