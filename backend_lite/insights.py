"""
Contradiction Insights
======================

Deterministic scoring for contradiction insights.
"""

from typing import Any, Dict, List, Optional, Tuple

from .db.models import Contradiction, ContradictionInsight


SEVERITY_IMPACT = {
    "critical": 0.95,
    "high": 0.8,
    "medium": 0.55,
    "low": 0.3,
}

TYPE_IMPACT_BONUS = {
    "temporal_date_conflict": 0.15,
    "quant_amount_conflict": 0.15,
    "identity_basic_conflict": 0.15,
    "presence_participation_conflict": 0.05,
    "actor_attribution_conflict": 0.05,
    "document_existence_conflict": 0.05,
}

STATUS_VERIFIABILITY = {
    "verified": 0.9,
    "likely": 0.7,
    "suspicious": 0.4,
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _locator_quality(locator: Optional[dict]) -> float:
    if not locator:
        return 0.2
    if locator.get("doc_id") and locator.get("char_start") is not None and locator.get("char_end") is not None:
        return 1.0
    if locator.get("doc_id") and (
        locator.get("block_index") is not None or locator.get("paragraph_index") is not None
    ):
        return 0.7
    if locator.get("doc_id"):
        return 0.5
    return 0.2


def _risk_score(status: str, category: Optional[str], verifiability: float, anchor_quality: float) -> float:
    score = 0.3
    if category in ("narrative_ambiguity", "rhetorical_shift"):
        score += 0.35
    if status == "suspicious":
        score += 0.2
    if verifiability < 0.45:
        score += 0.1
    if anchor_quality < 0.5:
        score += 0.05
    if status == "verified":
        score -= 0.1
    return _clamp(score)


def _stage_recommendation(impact: float, risk: float, verifiability: float) -> str:
    if verifiability >= 0.75 and impact >= 0.7 and risk <= 0.5:
        return "early"
    if risk >= 0.7 or verifiability < 0.45:
        return "late"
    return "mid"


def _expected_evasions(contradiction_type: str, risk: float) -> List[str]:
    base = ["לא זוכר", "טעות סופר"]
    if contradiction_type == "document_existence_conflict":
        base.append("לא קיבלתי את המסמך")
    if contradiction_type == "presence_participation_conflict":
        base.append("הייתי שם חלקית")
    if risk >= 0.7:
        base.append("הבלבול נבע מהזמן שחלף")
    return list(dict.fromkeys(base))


def _best_counters(contradiction_type: str) -> List[str]:
    templates = {
        "temporal_date_conflict": "אני מפנה אותך למועד המדויק במסמך.",
        "quant_amount_conflict": "המספר המדויק מופיע במסמך — האם אתה עומד מאחוריו?",
        "identity_basic_conflict": "פרטי הזיהוי במסמך שונים — תענה כן או לא.",
        "presence_participation_conflict": "האם אתה מאשר שנכחת במעמד?",
        "actor_attribution_conflict": "מי בדיוק ביצע את הפעולה לפי המסמך?",
        "document_existence_conflict": "האם אתה מאשר שהמסמך קיים ונמסר?",
    }
    return [templates.get(contradiction_type, "אתה עומד מאחורי הגרסה הזו?")]


def compute_insight(contr: Contradiction) -> Dict[str, Any]:
    """
    Compute deterministic insight scores for a contradiction.
    """
    contradiction_type = (contr.contradiction_type or "").strip()
    severity = (contr.severity or "medium").strip().lower()
    status = (contr.status.value if hasattr(contr.status, "value") else str(contr.status or "suspicious")).lower()
    category = contr.category

    impact = SEVERITY_IMPACT.get(severity, 0.5) + TYPE_IMPACT_BONUS.get(contradiction_type, 0.0)
    impact = _clamp(impact)

    locator1 = contr.locator1_json or {}
    locator2 = contr.locator2_json or {}
    anchor_quality = (_locator_quality(locator1) + _locator_quality(locator2)) / 2.0

    verifiability = STATUS_VERIFIABILITY.get(status, 0.5) * anchor_quality
    verifiability = _clamp(verifiability)

    risk = _risk_score(status, category, verifiability, anchor_quality)
    stage = _stage_recommendation(impact, risk, verifiability)

    prerequisites = []
    if verifiability < 0.5:
        prerequisites.append("אימות מסמך ומועד")
    if stage == "early":
        prerequisites.append("נעילה על גרסת העד")

    expected_evasions = _expected_evasions(contradiction_type, risk)
    counters = _best_counters(contradiction_type)

    do_not_ask = risk >= 0.7 and verifiability < 0.4
    do_not_ask_reason = None
    if do_not_ask:
        do_not_ask_reason = "סיכון גבוה מול אחיזה נמוכה בעוגנים. מומלץ להימנע בשלב זה."

    return {
        "impact_score": impact,
        "risk_score": risk,
        "verifiability_score": verifiability,
        "stage_recommendation": stage,
        "prerequisites": prerequisites,
        "expected_evasions": expected_evasions,
        "best_counter_questions": counters,
        "do_not_ask": do_not_ask,
        "do_not_ask_reason": do_not_ask_reason,
    }


def compute_insights_for_run(db: Any, run_id: str) -> List[ContradictionInsight]:
    """
    Compute and persist insights for a given analysis run.
    """
    contradictions = (
        db.query(Contradiction)
        .filter(Contradiction.run_id == run_id)
        .order_by(Contradiction.created_at.asc())
        .all()
    )
    if not contradictions:
        return []

    contr_ids = [c.id for c in contradictions]
    db.query(ContradictionInsight).filter(
        ContradictionInsight.contradiction_id.in_(contr_ids)
    ).delete(synchronize_session=False)

    insights = []
    for contr in contradictions:
        data = compute_insight(contr)
        insight = ContradictionInsight(
            contradiction_id=contr.id,
            impact_score=data["impact_score"],
            risk_score=data["risk_score"],
            verifiability_score=data["verifiability_score"],
            stage_recommendation=data["stage_recommendation"],
            prerequisites_json=data["prerequisites"],
            evasions_json=data["expected_evasions"],
            counters_json=data["best_counter_questions"],
            do_not_ask=data["do_not_ask"],
            do_not_ask_reason=data["do_not_ask_reason"],
        )
        db.add(insight)
        insights.append(insight)

    return insights
