"""
Database Package - PostgreSQL with SQLAlchemy
==============================================

Production-grade database layer for legal case management.
"""

from .models import (
    Base,
    Firm, User, Team, TeamMember, AdminTeamScope,
    Organization, OrganizationMember, OrganizationInvite,
    Case, CaseParticipant, CaseTeam,
    Witness, WitnessVersion,
    Folder,
    Document, DocumentPage, DocumentBlock, DocumentVersion,
    Job, Event,
    AnalysisRun, Claim, Issue, IssueLink, Contradiction, Finding,
    ContradictionInsight, CrossExamPlan, TrainingSession, TrainingTurn,
    SystemRole, TeamRole, OrganizationRole, InviteStatus, TrainingSessionStatus, CaseStatus, DocumentParty, DocumentRole,
    JobType, JobStatus, EventType, IssueStatus, ContradictionStatus
)
from .session import get_db, init_db, get_engine

__all__ = [
    # Base
    "Base",
    # Organization
    "Firm", "User", "Team", "TeamMember", "AdminTeamScope",
    "Organization", "OrganizationMember", "OrganizationInvite",
    # Case Management
    "Case", "CaseParticipant", "CaseTeam",
    "Witness", "WitnessVersion",
    # Folders
    "Folder",
    # Documents
    "Document", "DocumentPage", "DocumentBlock", "DocumentVersion",
    # Jobs & Events
    "Job", "Event",
    # Analysis
    "AnalysisRun", "Claim", "Issue", "IssueLink", "Contradiction", "ContradictionInsight", "CrossExamPlan", "TrainingSession", "TrainingTurn", "Finding",
    # Enums
    "SystemRole", "TeamRole", "OrganizationRole", "InviteStatus", "TrainingSessionStatus", "CaseStatus", "DocumentParty", "DocumentRole",
    "JobType", "JobStatus", "EventType", "IssueStatus", "ContradictionStatus",
    # Session
    "get_db", "init_db", "get_engine",
]
