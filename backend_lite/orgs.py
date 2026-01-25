"""
Organization helpers (B1).
"""

from typing import List, Optional

from sqlalchemy.orm import Session

from .db.models import Organization, OrganizationMember, OrganizationRole


def ensure_default_org(db: Session, firm_id: str, user_id: Optional[str] = None) -> Organization:
    org = (
        db.query(Organization)
        .filter(Organization.firm_id == firm_id)
        .order_by(Organization.created_at.asc())
        .first()
    )
    if not org:
        org = Organization(
            firm_id=firm_id,
            name="משרד ראשי",
            extra_data={"auto_default": True},
        )
        db.add(org)
        db.flush()

    if user_id:
        member = (
            db.query(OrganizationMember)
            .filter(
                OrganizationMember.organization_id == org.id,
                OrganizationMember.user_id == user_id,
            )
            .first()
        )
        if not member:
            db.add(OrganizationMember(
                organization_id=org.id,
                user_id=user_id,
                role=OrganizationRole.OWNER,
                added_by_user_id=user_id,
            ))

    return org


def list_user_org_ids(db: Session, firm_id: str, user_id: str) -> List[str]:
    return [
        m.organization_id
        for m in db.query(OrganizationMember)
        .filter(OrganizationMember.user_id == user_id)
        .all()
    ]


def get_org_member(db: Session, org_id: str, user_id: str) -> Optional[OrganizationMember]:
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
        .first()
    )
