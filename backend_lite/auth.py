"""
Authorization Module (RBAC) with JWT Support
=============================================

Role-Based Access Control for the Case Management System.

System Roles (firm-wide):
- super_admin: Full control over firm, all teams, all cases
- admin: Manage teams/users within scope (admin_team_scope)
- member: Regular user - access via team membership or direct assignment
- viewer: Read-only access to assigned content

Team Roles (team-level):
- team_leader: Professional lead - can manage team cases
- team_member: Regular team member

Authorization Flow:
1. Load user from JWT token or X-User-Id header (for backwards compatibility)
2. Determine firm_id from user
3. Check permissions based on role and scope
"""

import os
import logging
from typing import Optional, List, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# JWT configuration
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

def _env_truthy(name: str, default: str = "false") -> bool:
    """Parse boolean environment variable values."""
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "y", "on")

def _auto_provision_enabled() -> bool:
    """
    Allow auto-provisioning of unknown users (dev/demo convenience).

    This is intentionally **off by default**.
    """
    return _env_truthy("BACKEND_LITE_AUTO_PROVISION_USERS", "false")

def _auto_provision_firm_domain() -> str:
    return os.environ.get("BACKEND_LITE_AUTO_PROVISION_FIRM_DOMAIN", "demo.jethro.ai").strip() or "demo.jethro.ai"

def _auto_provision_firm_name() -> str:
    return os.environ.get("BACKEND_LITE_AUTO_PROVISION_FIRM_NAME", "משרד דמו לבדיקות").strip() or "משרד דמו לבדיקות"


# =============================================================================
# PERMISSION TYPES
# =============================================================================

class Permission(str, Enum):
    """Available permissions in the system"""
    # Case permissions
    CASE_CREATE = "case:create"
    CASE_READ = "case:read"
    CASE_UPDATE = "case:update"
    CASE_DELETE = "case:delete"
    CASE_ANALYZE = "case:analyze"

    # Document permissions
    DOC_CREATE = "doc:create"
    DOC_READ = "doc:read"
    DOC_UPDATE = "doc:update"
    DOC_DELETE = "doc:delete"

    # Team permissions
    TEAM_CREATE = "team:create"
    TEAM_READ = "team:read"
    TEAM_UPDATE = "team:update"
    TEAM_DELETE = "team:delete"
    TEAM_MANAGE_MEMBERS = "team:manage_members"

    # User permissions
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DEACTIVATE = "user:deactivate"

    # Firm permissions
    FIRM_READ = "firm:read"
    FIRM_UPDATE = "firm:update"

    # Admin permissions
    ADMIN_SCOPE_MANAGE = "admin:scope_manage"


# Import SystemRole and TeamRole from db.models (SQLAlchemy models)
from .db.models import SystemRole, TeamRole


# Role to base permissions mapping
ROLE_PERMISSIONS = {
    SystemRole.SUPER_ADMIN: {
        Permission.CASE_CREATE, Permission.CASE_READ, Permission.CASE_UPDATE,
        Permission.CASE_DELETE, Permission.CASE_ANALYZE,
        Permission.DOC_CREATE, Permission.DOC_READ, Permission.DOC_UPDATE, Permission.DOC_DELETE,
        Permission.TEAM_CREATE, Permission.TEAM_READ, Permission.TEAM_UPDATE,
        Permission.TEAM_DELETE, Permission.TEAM_MANAGE_MEMBERS,
        Permission.USER_CREATE, Permission.USER_READ, Permission.USER_UPDATE, Permission.USER_DEACTIVATE,
        Permission.FIRM_READ, Permission.FIRM_UPDATE,
        Permission.ADMIN_SCOPE_MANAGE,
    },
    SystemRole.ADMIN: {
        Permission.CASE_CREATE, Permission.CASE_READ, Permission.CASE_UPDATE, Permission.CASE_ANALYZE,
        Permission.DOC_CREATE, Permission.DOC_READ, Permission.DOC_UPDATE, Permission.DOC_DELETE,
        Permission.TEAM_READ, Permission.TEAM_UPDATE, Permission.TEAM_MANAGE_MEMBERS,
        Permission.USER_CREATE, Permission.USER_READ, Permission.USER_UPDATE,
        Permission.FIRM_READ,
    },
    SystemRole.MEMBER: {
        Permission.CASE_CREATE, Permission.CASE_READ, Permission.CASE_UPDATE, Permission.CASE_ANALYZE,
        Permission.DOC_CREATE, Permission.DOC_READ, Permission.DOC_UPDATE,
        Permission.TEAM_READ,
        Permission.USER_READ,
        Permission.FIRM_READ,
    },
    SystemRole.VIEWER: {
        Permission.CASE_READ,
        Permission.DOC_READ,
        Permission.TEAM_READ,
        Permission.USER_READ,
        Permission.FIRM_READ,
    },
}


# =============================================================================
# PASSWORD HASHING
# =============================================================================

# bcrypt truncates passwords at 72 bytes; enforce to avoid 500s.
MAX_PASSWORD_BYTES = 72

def is_password_too_long(password: str) -> bool:
    """Return True if password exceeds bcrypt 72-byte limit."""
    try:
        return len(password.encode("utf-8")) > MAX_PASSWORD_BYTES
    except Exception:
        return len(password) > MAX_PASSWORD_BYTES

try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash"""
        if is_password_too_long(plain_password):
            logger.warning("Auth failed: password exceeds bcrypt 72-byte limit")
            return False
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except ValueError as e:
            logger.warning(f"Auth failed: invalid password format ({e})")
            return False

    def get_password_hash(password: str) -> str:
        """Hash a password"""
        if is_password_too_long(password):
            raise ValueError("Password exceeds bcrypt 72-byte limit")
        return pwd_context.hash(password)

    PASSWORD_HASHING_AVAILABLE = True
except ImportError:
    logger.warning("passlib not installed - password hashing disabled")
    PASSWORD_HASHING_AVAILABLE = False

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return False

    def get_password_hash(password: str) -> str:
        raise NotImplementedError("passlib required for password hashing")


# =============================================================================
# JWT TOKEN HANDLING
# =============================================================================

JWT_AVAILABLE = False
_jwt_module = None

def _load_jwt():
    """Lazy load JWT module to handle import errors gracefully"""
    global _jwt_module, JWT_AVAILABLE
    if _jwt_module is not None:
        return _jwt_module if JWT_AVAILABLE else None

    try:
        import jwt as jwt_mod
        _jwt_module = jwt_mod
        JWT_AVAILABLE = True
        return jwt_mod
    except Exception as e:
        logger.warning(f"JWT module not available: {e}")
        _jwt_module = None
        JWT_AVAILABLE = False
        return None

def is_jwt_available() -> bool:
    """Return True if PyJWT is available (lazy-loaded)."""
    return _load_jwt() is not None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    jwt_mod = _load_jwt()
    if not jwt_mod:
        raise NotImplementedError("PyJWT required for token creation")

    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt_mod.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token"""
    jwt_mod = _load_jwt()
    if not jwt_mod:
        raise NotImplementedError("PyJWT required for token creation")

    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt_mod.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token"""
    jwt_mod = _load_jwt()
    if not jwt_mod:
        return None

    try:
        payload = jwt_mod.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except Exception as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None


# =============================================================================
# AUTH CONTEXT
# =============================================================================

@dataclass
class AuthContext:
    """Authorization context for a request"""
    user_id: str
    firm_id: str
    email: str
    name: str
    system_role: SystemRole
    professional_role: Optional[str]
    team_ids: List[str]  # Teams user belongs to
    team_leader_of: List[str]  # Teams where user is team_leader
    admin_scope_teams: List[str]  # Teams admin can manage (for admin role)

    @property
    def is_super_admin(self) -> bool:
        return self.system_role == SystemRole.SUPER_ADMIN

    @property
    def is_admin(self) -> bool:
        return self.system_role in (SystemRole.SUPER_ADMIN, SystemRole.ADMIN)

    @property
    def is_viewer(self) -> bool:
        return self.system_role == SystemRole.VIEWER

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission"""
        return permission in ROLE_PERMISSIONS.get(self.system_role, set())

    def can_manage_team(self, team_id: str) -> bool:
        """Check if user can manage a specific team"""
        if self.is_super_admin:
            return True
        if self.system_role == SystemRole.ADMIN:
            return team_id in self.admin_scope_teams
        return team_id in self.team_leader_of

    def can_access_case(self, case_id: str, db: Session) -> bool:
        """Check if user can access a specific case"""
        # Support both SQLAlchemy session (current) and legacy CaseDatabase (tests/back-compat).
        if not hasattr(db, "query") and hasattr(db, "get_case"):
            # Legacy CaseDatabase path
            try:
                case = db.get_case(case_id)
                if not case or case.firm_id != self.firm_id:
                    return False

                if self.is_super_admin:
                    return True

                if self.system_role == SystemRole.ADMIN:
                    # Admin can access cases belonging to teams in their scope
                    for team_id in self.admin_scope_teams:
                        if case_id in (db.get_team_cases(team_id) or []):
                            return True
                    return False

                # Member/Viewer: responsible attorney OR team membership OR direct participation
                if getattr(case, "responsible_user_id", None) == self.user_id:
                    return True

                case_teams = db.get_case_teams(case_id) or []
                case_team_ids = [t.id for t in case_teams if getattr(t, "id", None)]
                if set(case_team_ids) & set(self.team_ids):
                    return True

                direct_cases = set(db.get_user_cases(self.user_id) or [])
                return case_id in direct_cases
            except Exception:
                return False

        from .db.models import Case, CaseTeam, CaseParticipant

        # Super admin can access all cases in firm
        if self.is_super_admin:
            case = db.query(Case).filter(Case.id == case_id).first()
            return case and case.firm_id == self.firm_id

        # Admin can access cases of teams in their scope
        if self.system_role == SystemRole.ADMIN:
            case = db.query(Case).filter(Case.id == case_id).first()
            if not case or case.firm_id != self.firm_id:
                return False
            case_team_ids = [ct.team_id for ct in db.query(CaseTeam).filter(CaseTeam.case_id == case_id).all()]
            return bool(set(case_team_ids) & set(self.admin_scope_teams))

        # Member/Viewer can access cases via team membership or direct participation
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case or case.firm_id != self.firm_id:
            return False

        # Check if user is the responsible attorney
        if case.responsible_user_id == self.user_id:
            return True

        # Check team membership
        case_team_ids = [ct.team_id for ct in db.query(CaseTeam).filter(CaseTeam.case_id == case_id).all()]
        if set(case_team_ids) & set(self.team_ids):
            return True

        # Check direct participation
        participation = db.query(CaseParticipant).filter(
            CaseParticipant.case_id == case_id,
            CaseParticipant.user_id == self.user_id
        ).first()
        return participation is not None


# =============================================================================
# AUTH SERVICE (SQLAlchemy-based)
# =============================================================================

class AuthService:
    """Authorization service using SQLAlchemy"""

    def __init__(self, db: Session):
        self.db = db

    def _is_legacy_db(self) -> bool:
        # Legacy CaseDatabase used in some unit tests/back-compat paths
        return (not hasattr(self.db, "query")) and hasattr(self.db, "get_user") and hasattr(self.db, "get_user_by_email")

    def _legacy_auth_context_from_user(self, user) -> Optional[AuthContext]:
        # Map legacy enums -> current enums by value
        try:
            system_role = SystemRole(getattr(user.system_role, "value", user.system_role))
        except Exception:
            system_role = SystemRole.MEMBER

        # Teams + roles
        teams = self.db.get_user_teams(user.id) or []
        team_ids = [t.id for t in teams if getattr(t, "id", None)]
        team_leader_of = []
        for tid in team_ids:
            try:
                role = self.db.get_user_team_role(tid, user.id)
                role_val = getattr(role, "value", role)
                if role_val == TeamRole.TEAM_LEADER.value:
                    team_leader_of.append(tid)
            except Exception:
                continue

        admin_scope_teams = []
        if system_role == SystemRole.ADMIN:
            try:
                admin_scope_teams = list(self.db.get_admin_team_scope(user.id) or [])
            except Exception:
                admin_scope_teams = []

        try:
            self.db.update_user_last_login(user.id)
        except Exception:
            pass

        return AuthContext(
            user_id=user.id,
            firm_id=user.firm_id,
            email=user.email,
            name=user.name,
            system_role=system_role,
            professional_role=getattr(user, "professional_role", None),
            team_ids=team_ids,
            team_leader_of=team_leader_of,
            admin_scope_teams=admin_scope_teams,
        )

    def _ensure_autoprovision_firm(self):
        """Get or create the firm used for auto-provisioned users."""
        from .db.models import Firm

        domain = _auto_provision_firm_domain()
        firm = self.db.query(Firm).filter(Firm.domain == domain).first()
        if firm:
            return firm

        firm = Firm(name=_auto_provision_firm_name(), domain=domain)
        self.db.add(firm)
        self.db.commit()
        self.db.refresh(firm)
        return firm

    def _generate_autoprovision_email(self, firm_id: str, user_id: str, preferred_email: Optional[str]) -> str:
        """Generate a unique email for a firm."""
        from .db.models import User

        domain = _auto_provision_firm_domain()
        base_local = (preferred_email.split("@", 1)[0] if preferred_email and "@" in preferred_email else f"autoprovision+{user_id}")
        base_email = f"{base_local}@{domain}"

        candidate = base_email
        i = 1
        while self.db.query(User).filter(User.firm_id == firm_id, User.email == candidate).first():
            candidate = f"{base_local}+{i}@{domain}"
            i += 1
        return candidate

    def _auto_provision_user(self, user_id: str, email: Optional[str] = None):
        """Create a minimal active user record so auth can proceed (demo/dev only)."""
        from .db.models import User, SystemRole

        firm = self._ensure_autoprovision_firm()

        user = User(
            id=user_id,
            firm_id=firm.id,
            email=self._generate_autoprovision_email(firm.id, user_id, email),
            name=email or f"Auto Provisioned ({user_id[:8]})",
            system_role=SystemRole.MEMBER,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        logger.warning(f"Auto-provisioned user {user.id} in firm {firm.id}")
        return user

    def get_auth_context_flexible(self, user_id: Optional[str], email: Optional[str] = None) -> Optional[AuthContext]:
        """
        Build auth context from either user_id or email, with optional auto-provision.

        - If user_id exists and active: use it.
        - Else if email exists and matches an active user: use it.
        - Else (optional) auto-provision a placeholder user (dev/demo only).
        """
        if self._is_legacy_db():
            user = None
            if user_id:
                user = self.db.get_user(user_id)
            if (not user or not getattr(user, "is_active", False)) and email:
                user = self.db.get_user_by_email(email)
            if not user or not getattr(user, "is_active", False):
                if user_id:
                    logger.warning(f"Auth failed: user {user_id} not found or inactive")
                else:
                    logger.warning("Auth failed: missing user identity (no user_id/email)")
                return None
            return self._legacy_auth_context_from_user(user)

        from .db.models import User, TeamMember, AdminTeamScope

        user: Optional[User] = None
        if user_id:
            user = self.db.query(User).filter(User.id == user_id).first()

        if (not user or not user.is_active) and email:
            user = self.db.query(User).filter(User.email == email, User.is_active == True).first()

        if user and not user.is_active and _auto_provision_enabled():
            user.is_active = True
            self.db.commit()

        if not user and user_id and _auto_provision_enabled():
            user = self._auto_provision_user(user_id=user_id, email=email)

        if not user or not user.is_active:
            # Keep old log shape for easier ops debugging
            if user_id:
                logger.warning(f"Auth failed: user {user_id} not found or inactive")
            else:
                logger.warning("Auth failed: missing user identity (no user_id/email)")
            return None

        # Get user's teams
        team_memberships = self.db.query(TeamMember).filter(TeamMember.user_id == user.id).all()
        team_ids = [tm.team_id for tm in team_memberships]

        # Get teams where user is team_leader
        team_leader_of = [tm.team_id for tm in team_memberships if tm.team_role == TeamRole.TEAM_LEADER]

        # Get admin scope if admin
        admin_scope_teams = []
        if user.system_role == SystemRole.ADMIN:
            scopes = self.db.query(AdminTeamScope).filter(AdminTeamScope.admin_user_id == user.id).all()
            admin_scope_teams = [s.team_id for s in scopes]

        # Update last login
        user.last_login = datetime.utcnow()
        self.db.commit()

        return AuthContext(
            user_id=user.id,
            firm_id=user.firm_id,
            email=user.email,
            name=user.name,
            system_role=user.system_role,
            professional_role=user.professional_role,
            team_ids=team_ids,
            team_leader_of=team_leader_of,
            admin_scope_teams=admin_scope_teams,
        )

    def get_auth_context(self, user_id: str) -> Optional[AuthContext]:
        """
        Build auth context for a user.

        Args:
            user_id: User ID from JWT token or X-User-Id header

        Returns:
            AuthContext if user exists and is active, None otherwise
        """
        if self._is_legacy_db():
            user = self.db.get_user(user_id)
            if not user or not getattr(user, "is_active", False):
                logger.warning(f"Auth failed: user {user_id} not found or inactive")
                return None
            return self._legacy_auth_context_from_user(user)

        from .db.models import User, TeamMember, AdminTeamScope

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            logger.warning(f"Auth failed: user {user_id} not found or inactive")
            return None

        # Get user's teams
        team_memberships = self.db.query(TeamMember).filter(TeamMember.user_id == user_id).all()
        team_ids = [tm.team_id for tm in team_memberships]

        # Get teams where user is team_leader
        team_leader_of = [tm.team_id for tm in team_memberships if tm.team_role == TeamRole.TEAM_LEADER]

        # Get admin scope if admin
        admin_scope_teams = []
        if user.system_role == SystemRole.ADMIN:
            scopes = self.db.query(AdminTeamScope).filter(AdminTeamScope.admin_user_id == user_id).all()
            admin_scope_teams = [s.team_id for s in scopes]

        # Update last login
        user.last_login = datetime.utcnow()
        self.db.commit()

        return AuthContext(
            user_id=user.id,
            firm_id=user.firm_id,
            email=user.email,
            name=user.name,
            system_role=user.system_role,
            professional_role=user.professional_role,
            team_ids=team_ids,
            team_leader_of=team_leader_of,
            admin_scope_teams=admin_scope_teams
        )

    def authenticate_user(self, email: str, password: str) -> Optional[AuthContext]:
        """
        Authenticate a user by email and password.

        Args:
            email: User email
            password: Plain text password

        Returns:
            AuthContext if authentication succeeds, None otherwise
        """
        if not PASSWORD_HASHING_AVAILABLE:
            logger.error("Password hashing not available")
            return None

        from .db.models import User

        user = self.db.query(User).filter(User.email == email, User.is_active == True).first()
        if not user:
            logger.warning(f"Auth failed: email {email} not found")
            return None

        if not user.password_hash:
            logger.warning(f"Auth failed: user {user.id} has no password set")
            return None

        if not verify_password(password, user.password_hash):
            logger.warning(f"Auth failed: invalid password for user {user.id}")
            return None

        return self.get_auth_context(user.id)

    def require_permission(
        self, auth: AuthContext, permission: Permission,
        resource_id: Optional[str] = None
    ) -> bool:
        """
        Check if user has permission, with optional resource-level check.

        Args:
            auth: AuthContext for the request
            permission: Required permission
            resource_id: Optional resource ID for resource-level checks

        Returns:
            True if authorized, False otherwise
        """
        # First check role-based permission
        if not auth.has_permission(permission):
            logger.warning(
                f"Permission denied: {auth.user_id} lacks {permission.value}"
            )
            return False

        # If resource_id provided, do resource-level check
        if resource_id:
            if permission in (Permission.CASE_READ, Permission.CASE_UPDATE,
                            Permission.CASE_DELETE, Permission.CASE_ANALYZE):
                if not auth.can_access_case(resource_id, self.db):
                    logger.warning(
                        f"Resource access denied: {auth.user_id} cannot access case {resource_id}"
                    )
                    return False

            elif permission in (Permission.TEAM_UPDATE, Permission.TEAM_DELETE,
                              Permission.TEAM_MANAGE_MEMBERS):
                if not auth.can_manage_team(resource_id):
                    logger.warning(
                        f"Resource access denied: {auth.user_id} cannot manage team {resource_id}"
                    )
                    return False

        return True

    def get_accessible_cases(self, auth: AuthContext, status=None) -> List[str]:
        """
        Get list of case IDs user can access.

        Args:
            auth: AuthContext for the request
            status: Optional status filter

        Returns:
            List of accessible case IDs
        """
        if self._is_legacy_db():
            # Legacy CaseDatabase path
            try:
                if auth.is_super_admin:
                    cases = self.db.list_cases_by_firm(auth.firm_id, status=status) if status else self.db.list_cases_by_firm(auth.firm_id)
                    return [c.id for c in cases if c]

                if auth.system_role == SystemRole.ADMIN:
                    case_ids = set()
                    for team_id in auth.admin_scope_teams:
                        case_ids.update(self.db.get_team_cases(team_id) or [])
                    if status:
                        filtered = set()
                        for cid in case_ids:
                            c = self.db.get_case(cid)
                            if c and getattr(c, "status", None) == status:
                                filtered.add(cid)
                        case_ids = filtered
                    return list(case_ids)

                case_ids = set()
                for team_id in auth.team_ids:
                    case_ids.update(self.db.get_team_cases(team_id) or [])

                case_ids.update(self.db.get_user_cases(auth.user_id) or [])

                # Responsible attorney
                # (Legacy DB exposes list_cases_by_firm; filter by responsible_user_id)
                try:
                    firm_cases = self.db.list_cases_by_firm(auth.firm_id, status=status) if status else self.db.list_cases_by_firm(auth.firm_id)
                    for c in firm_cases:
                        if c and getattr(c, "responsible_user_id", None) == auth.user_id:
                            case_ids.add(c.id)
                except Exception:
                    pass

                if status:
                    filtered = set()
                    for cid in case_ids:
                        c = self.db.get_case(cid)
                        if c and getattr(c, "status", None) == status:
                            filtered.add(cid)
                    case_ids = filtered

                return list(case_ids)
            except Exception:
                return []

        from .db.models import Case, CaseTeam, CaseParticipant

        if auth.is_super_admin:
            # Super admin sees all firm cases
            query = self.db.query(Case.id).filter(Case.firm_id == auth.firm_id)
            if status:
                query = query.filter(Case.status == status)
            return [c[0] for c in query.all()]

        if auth.system_role == SystemRole.ADMIN:
            # Admin sees cases from teams in their scope
            case_ids = set()
            for team_id in auth.admin_scope_teams:
                team_case_ids = [ct.case_id for ct in self.db.query(CaseTeam).filter(CaseTeam.team_id == team_id).all()]
                case_ids.update(team_case_ids)

            # Filter by status if needed
            if status:
                case_ids = {
                    cid for cid in case_ids
                    if self.db.query(Case).filter(Case.id == cid, Case.status == status).first()
                }
            return list(case_ids)

        # Member/Viewer - cases from their teams + direct participation + responsible
        case_ids = set()

        # Cases from team membership
        for team_id in auth.team_ids:
            team_case_ids = [ct.case_id for ct in self.db.query(CaseTeam).filter(CaseTeam.team_id == team_id).all()]
            case_ids.update(team_case_ids)

        # Direct participation
        participations = self.db.query(CaseParticipant.case_id).filter(CaseParticipant.user_id == auth.user_id).all()
        case_ids.update([p[0] for p in participations])

        # Cases where user is responsible attorney
        responsible_cases = self.db.query(Case.id).filter(
            Case.firm_id == auth.firm_id,
            Case.responsible_user_id == auth.user_id
        ).all()
        case_ids.update([c[0] for c in responsible_cases])

        # Filter by status if needed
        if status:
            case_ids = {
                cid for cid in case_ids
                if self.db.query(Case).filter(Case.id == cid, Case.status == status).first()
            }

        return list(case_ids)

    def get_manageable_teams(self, auth: AuthContext) -> List[str]:
        """
        Get list of team IDs user can manage.

        Args:
            auth: AuthContext for the request

        Returns:
            List of manageable team IDs
        """
        from .db.models import Team

        if auth.is_super_admin:
            # Super admin can manage all teams in firm
            teams = self.db.query(Team.id).filter(Team.firm_id == auth.firm_id).all()
            return [t[0] for t in teams]

        if auth.system_role == SystemRole.ADMIN:
            # Admin can manage teams in their scope
            return auth.admin_scope_teams

        # Team leaders can manage their teams
        return auth.team_leader_of

    def can_assign_case_to_team(self, auth: AuthContext, case_id: str, team_id: str) -> bool:
        """Check if user can assign a case to a team"""
        from .db.models import Team

        # Must be able to manage the team
        if not auth.can_manage_team(team_id):
            return False

        # Must be able to access the case
        if not auth.can_access_case(case_id, self.db):
            return False

        # Team must be in same firm
        team = self.db.query(Team).filter(Team.id == team_id).first()
        if not team or team.firm_id != auth.firm_id:
            return False

        return True

    def can_add_user_to_team(self, auth: AuthContext, team_id: str, user_id: str) -> bool:
        """Check if user can add another user to a team"""
        from .db.models import User

        # Must be able to manage the team
        if not auth.can_manage_team(team_id):
            return False

        # Target user must be in same firm
        target_user = self.db.query(User).filter(User.id == user_id).first()
        if not target_user or target_user.firm_id != auth.firm_id:
            return False

        return True


# =============================================================================
# FASTAPI DEPENDENCY HELPERS
# =============================================================================

def get_auth_service(db: Session) -> AuthService:
    """Get AuthService instance for a database session"""
    return AuthService(db)
