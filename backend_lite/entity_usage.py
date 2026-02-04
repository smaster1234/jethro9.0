"""
Entity usage tracking helpers (C2).
"""

from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from .db.models import EntityUsage


def _key(entity_type: str, entity_id: str, usage_type: str) -> Tuple[str, str, str]:
    return (entity_type, entity_id, usage_type)


def record_entity_usages(
    db: Session,
    case_id: str,
    org_id: Optional[str],
    usage_type: str,
    entries: Iterable[Tuple[str, str, Optional[Dict]]],
    meta_base: Optional[Dict] = None,
) -> int:
    """
    Insert entity usage rows if they do not already exist.

    entries: list of (entity_type, entity_id, meta_json)
    meta_base: shared meta_json additions (no raw text)
    """
    meta_base = meta_base or {}
    seen = set()
    created = 0

    for entity_type, entity_id, meta_json in entries:
        if not entity_id:
            continue
        key = _key(entity_type, entity_id, usage_type)
        if key in seen:
            continue
        seen.add(key)

        exists = db.query(EntityUsage.id).filter(
            EntityUsage.case_id == case_id,
            EntityUsage.entity_type == entity_type,
            EntityUsage.entity_id == entity_id,
            EntityUsage.usage_type == usage_type,
        ).first()
        if exists:
            continue

        payload = {**meta_base, **(meta_json or {})}
        db.add(EntityUsage(
            case_id=case_id,
            org_id=org_id,
            entity_type=entity_type,
            entity_id=entity_id,
            usage_type=usage_type,
            meta_json=payload,
        ))
        created += 1

    return created
