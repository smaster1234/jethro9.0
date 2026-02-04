"""
Feedback aggregation utilities (C3).
"""

from typing import Dict, List


def feedback_rank(counts: Dict[str, int]) -> int:
    """
    Rank based on feedback counts.
    excellent>=2 => boost, too_risky>=2 => demote.
    """
    if counts.get("excellent", 0) >= 2:
        return 1
    if counts.get("too_risky", 0) >= 2:
        return -1
    return 0


def sort_feedback_aggregates(aggregates: List[Dict]) -> List[Dict]:
    """
    Deterministic sort: boost > normal > demote, then entity_id.
    """
    return sorted(
        aggregates,
        key=lambda item: (
            -feedback_rank(item.get("counts", {})),
            item.get("entity_type", ""),
            item.get("entity_id", ""),
        ),
    )
