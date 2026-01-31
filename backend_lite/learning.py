"""
Learning System — Adaptive Analysis from User Feedback
======================================================

Implements a feedback-driven learning loop that improves contradiction
detection quality over time:

1. **Feedback Collection**: Users mark contradictions as confirmed/rejected
   with optional rationale.

2. **Few-Shot Examples**: Past confirmed contradictions and confirmed false
   positives are injected as few-shot examples into the Analyzer and Verifier
   LLM prompts, teaching the model what counts as a real contradiction in
   this firm's legal context.

3. **Confidence Calibration**: Tracks precision/recall per contradiction type
   and adjusts confidence thresholds accordingly.

4. **Pattern Memory**: Remembers successful detection patterns (entity types,
   claim structures) and false positive patterns for future runs.

Usage:
    from learning import get_learning_context

    ctx = get_learning_context(firm_id, db_session)
    # ctx.few_shot_examples  -> list of example dicts for LLM
    # ctx.confidence_adjustments -> dict of type -> float adjustment
    # ctx.false_positive_patterns -> list of patterns to avoid
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# Feedback labels for contradictions
FEEDBACK_CONFIRMED = "confirmed"       # User confirmed this is a real contradiction
FEEDBACK_FALSE_POSITIVE = "false_positive"  # User says this is NOT a contradiction
FEEDBACK_PARTIALLY_CORRECT = "partial"  # Contradiction exists but details are wrong
FEEDBACK_EXCELLENT = "excellent"        # Outstanding detection

# Map existing FeedbackLabel enum values to our categories
_LABEL_MAP = {
    "worked": FEEDBACK_CONFIRMED,
    "excellent": FEEDBACK_EXCELLENT,
    "not_worked": FEEDBACK_FALSE_POSITIVE,
    "too_risky": FEEDBACK_PARTIALLY_CORRECT,
    # Direct labels (if used with new system)
    "confirmed": FEEDBACK_CONFIRMED,
    "false_positive": FEEDBACK_FALSE_POSITIVE,
    "partial": FEEDBACK_PARTIALLY_CORRECT,
}


@dataclass
class FewShotExample:
    """A few-shot example derived from user feedback."""
    claim_a: str
    claim_b: str
    contradiction_type: str
    is_true_contradiction: bool
    explanation: str
    user_rationale: str = ""


@dataclass
class LearningContext:
    """Context for the current analysis, informed by past feedback."""
    few_shot_positive: List[FewShotExample] = field(default_factory=list)
    few_shot_negative: List[FewShotExample] = field(default_factory=list)
    confidence_adjustments: Dict[str, float] = field(default_factory=dict)
    type_precision: Dict[str, float] = field(default_factory=dict)
    total_feedback_count: int = 0
    confirmed_count: int = 0
    rejected_count: int = 0


def get_learning_context(
    firm_id: str,
    db_session: Any,
    max_examples: int = 3,
    lookback_days: int = 90,
) -> LearningContext:
    """
    Build a LearningContext from past user feedback for a firm.

    Args:
        firm_id: Firm ID to scope feedback
        db_session: SQLAlchemy session
        max_examples: Max few-shot examples per category (positive/negative)
        lookback_days: Only consider feedback from the last N days

    Returns:
        LearningContext with few-shot examples and confidence adjustments
    """
    try:
        from .db.models import Feedback, Contradiction, Claim, Case

        cutoff = datetime.utcnow() - timedelta(days=lookback_days)

        # Query feedback for contradictions in this firm
        feedbacks = (
            db_session.query(Feedback, Contradiction)
            .join(Case, Case.id == Feedback.case_id)
            .join(Contradiction, Contradiction.id == Feedback.entity_id)
            .filter(
                Feedback.entity_type == "contradiction",
                Case.firm_id == firm_id,
                Feedback.created_at >= cutoff,
            )
            .order_by(Feedback.created_at.desc())
            .limit(100)
            .all()
        )

        if not feedbacks:
            return LearningContext()

        ctx = LearningContext()
        type_stats: Dict[str, Dict[str, int]] = {}  # type -> {confirmed: N, rejected: N}

        for fb, contr in feedbacks:
            label_str = fb.label.value if hasattr(fb.label, 'value') else str(fb.label)
            category = _LABEL_MAP.get(label_str, label_str)

            ctx.total_feedback_count += 1

            # Get claim texts for few-shot examples
            claim1_text = ""
            claim2_text = ""
            if contr.claim1_id:
                claim1 = db_session.query(Claim).filter(Claim.id == contr.claim1_id).first()
                if claim1:
                    claim1_text = claim1.text or ""
            if contr.claim2_id:
                claim2 = db_session.query(Claim).filter(Claim.id == contr.claim2_id).first()
                if claim2:
                    claim2_text = claim2.text or ""

            contr_type = contr.contradiction_type or "unknown"

            # Track type-level precision
            if contr_type not in type_stats:
                type_stats[contr_type] = {"confirmed": 0, "rejected": 0}

            if category in (FEEDBACK_CONFIRMED, FEEDBACK_EXCELLENT):
                ctx.confirmed_count += 1
                type_stats[contr_type]["confirmed"] += 1

                # Add as positive few-shot example
                if len(ctx.few_shot_positive) < max_examples and claim1_text and claim2_text:
                    ctx.few_shot_positive.append(FewShotExample(
                        claim_a=claim1_text[:300],
                        claim_b=claim2_text[:300],
                        contradiction_type=contr_type,
                        is_true_contradiction=True,
                        explanation=contr.explanation or "",
                        user_rationale=fb.note or "",
                    ))

            elif category == FEEDBACK_FALSE_POSITIVE:
                ctx.rejected_count += 1
                type_stats[contr_type]["rejected"] += 1

                # Add as negative few-shot example
                if len(ctx.few_shot_negative) < max_examples and claim1_text and claim2_text:
                    ctx.few_shot_negative.append(FewShotExample(
                        claim_a=claim1_text[:300],
                        claim_b=claim2_text[:300],
                        contradiction_type=contr_type,
                        is_true_contradiction=False,
                        explanation=contr.explanation or "",
                        user_rationale=fb.note or "",
                    ))

        # Compute per-type precision and confidence adjustments
        for ctype, stats in type_stats.items():
            total = stats["confirmed"] + stats["rejected"]
            if total >= 3:  # Need minimum data points
                precision = stats["confirmed"] / total
                ctx.type_precision[ctype] = precision

                # Adjust confidence: boost types with high precision, penalize low
                if precision >= 0.8:
                    ctx.confidence_adjustments[ctype] = 0.1  # Boost
                elif precision <= 0.3:
                    ctx.confidence_adjustments[ctype] = -0.15  # Penalize
                elif precision <= 0.5:
                    ctx.confidence_adjustments[ctype] = -0.05  # Slight penalize

        logger.info(
            "Learning context: %d feedbacks, %d confirmed, %d rejected, "
            "%d positive examples, %d negative examples, %d type adjustments",
            ctx.total_feedback_count, ctx.confirmed_count, ctx.rejected_count,
            len(ctx.few_shot_positive), len(ctx.few_shot_negative),
            len(ctx.confidence_adjustments),
        )

        return ctx

    except Exception as e:
        logger.warning("Failed to build learning context: %s", e)
        return LearningContext()


def build_few_shot_prompt(ctx: LearningContext) -> str:
    """
    Build a few-shot examples section for the Analyzer/Verifier prompt.

    Returns empty string if no feedback examples are available.
    """
    if not ctx.few_shot_positive and not ctx.few_shot_negative:
        return ""

    parts = ["\n## דוגמאות מניתוחים קודמים (למדו מהם):"]

    for ex in ctx.few_shot_positive:
        parts.append(f"""
### דוגמה — סתירה אמיתית ({ex.contradiction_type}):
טענה א: "{ex.claim_a}"
טענה ב: "{ex.claim_b}"
→ תוצאה: TRUE_CONTRADICTION
→ הסבר: {ex.explanation}""")
        if ex.user_rationale:
            parts.append(f"→ משוב המשתמש: {ex.user_rationale}")

    for ex in ctx.few_shot_negative:
        parts.append(f"""
### דוגמה — לא סתירה ({ex.contradiction_type}):
טענה א: "{ex.claim_a}"
טענה ב: "{ex.claim_b}"
→ תוצאה: לא סתירה אמיתית
→ הסבר: {ex.explanation}""")
        if ex.user_rationale:
            parts.append(f"→ משוב המשתמש: {ex.user_rationale}")

    return "\n".join(parts)


def apply_confidence_adjustment(
    confidence: float,
    contradiction_type: str,
    ctx: LearningContext,
) -> float:
    """
    Adjust a contradiction's confidence score based on historical feedback.
    """
    adjustment = ctx.confidence_adjustments.get(contradiction_type, 0.0)
    adjusted = max(0.0, min(1.0, confidence + adjustment))
    if adjustment != 0:
        logger.debug(
            "Confidence adjustment for %s: %.2f -> %.2f (adj=%.2f)",
            contradiction_type, confidence, adjusted, adjustment,
        )
    return adjusted


def get_learning_stats(firm_id: str, db_session: Any) -> Dict[str, Any]:
    """
    Return learning system statistics for a firm.
    """
    try:
        from .db.models import Feedback, Case
        from sqlalchemy import func

        total = (
            db_session.query(func.count(Feedback.id))
            .join(Case, Case.id == Feedback.case_id)
            .filter(
                Feedback.entity_type == "contradiction",
                Case.firm_id == firm_id,
            )
            .scalar() or 0
        )

        confirmed = (
            db_session.query(func.count(Feedback.id))
            .join(Case, Case.id == Feedback.case_id)
            .filter(
                Feedback.entity_type == "contradiction",
                Case.firm_id == firm_id,
                Feedback.label.in_(["worked", "excellent", "confirmed"]),
            )
            .scalar() or 0
        )

        rejected = (
            db_session.query(func.count(Feedback.id))
            .join(Case, Case.id == Feedback.case_id)
            .filter(
                Feedback.entity_type == "contradiction",
                Case.firm_id == firm_id,
                Feedback.label.in_(["not_worked", "false_positive"]),
            )
            .scalar() or 0
        )

        precision = confirmed / (confirmed + rejected) if (confirmed + rejected) > 0 else None

        return {
            "total_feedback": total,
            "confirmed": confirmed,
            "rejected": rejected,
            "precision": round(precision, 3) if precision is not None else None,
            "learning_active": total >= 5,
        }

    except Exception as e:
        logger.warning("Failed to get learning stats: %s", e)
        return {"total_feedback": 0, "learning_active": False}
