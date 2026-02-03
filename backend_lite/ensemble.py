"""
Ensemble Scoring System
=======================

Combines multiple detection signals into a single confidence score:

1. **Rule-based confidence** — from detector.py (0-1)
2. **LLM analyzer confidence** — from analyzer.py (0-1)
3. **Semantic similarity** — from semantic.py (0-1)
4. **Entity overlap** — from entity_graph.py (0-1)
5. **Temporal evidence** — from temporal_graph.py (0-0.3 boost)
6. **Learning adjustment** — from learning.py (-0.15 to +0.1)
7. **Verification confidence** — from verifier.py (0-1)

Scoring modes:
- DEFAULT: Fixed weights calibrated for legal text
- ADAPTIVE: Weights adjusted from feedback (logistic regression)

Usage:
    from ensemble import EnsembleScorer, ContradictionSignals

    scorer = EnsembleScorer()
    signals = ContradictionSignals(
        rule_confidence=0.85,
        llm_confidence=0.72,
        semantic_similarity=0.65,
        entity_overlap=0.80,
        temporal_boost=0.15,
        learning_adjustment=0.05,
    )
    final = scorer.score(signals)
"""

import math
import logging
from typing import Dict, Optional, List, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ContradictionSignals:
    """All signals for scoring a contradiction candidate."""
    # Detection signals
    rule_confidence: float = 0.0        # Rule-based detector confidence
    llm_confidence: Optional[float] = None  # LLM analyzer confidence (None = not analyzed)
    verifier_confidence: Optional[float] = None  # LLM verifier confidence (None = not verified)

    # Context signals
    semantic_similarity: float = 0.0     # Semantic relatedness between claims
    entity_overlap: float = 0.0          # Entity overlap score
    same_subject_score: float = 0.0      # Same-subject probability
    negation_contrast: float = 0.0       # Negation polarity contrast (0-1)
    contradiction_signal: float = 0.0    # High similarity + opposing polarity (0-1)

    # Temporal signals
    temporal_boost: float = 0.0          # Temporal evidence boost (0-0.3)
    has_temporal_conflict: bool = False   # Direct temporal conflict detected
    has_impossible_sequence: bool = False # Causal ordering violation detected

    # Learning signals
    learning_adjustment: float = 0.0     # From feedback loop (-0.15 to +0.1)
    type_precision: Optional[float] = None  # Historical precision for this type

    # Detection agreement
    both_engines_agree: bool = False      # Both rule-based and LLM found it
    rule_only: bool = False               # Only rule-based found it
    llm_only: bool = False                # Only LLM found it

    # Metadata
    contradiction_type: str = ""
    severity: str = "medium"


@dataclass
class EnsembleResult:
    """Result from ensemble scoring."""
    final_confidence: float              # Combined confidence (0-1)
    final_status: str                    # verified / likely / suspicious
    signals_used: Dict[str, float]       # Which signals contributed
    explanation: str                     # Human-readable explanation
    boosted_by: List[str] = field(default_factory=list)   # What boosted confidence
    penalized_by: List[str] = field(default_factory=list)  # What reduced confidence


class EnsembleScorer:
    """
    Ensemble scoring combining multiple detection signals.

    Default weights calibrated for Hebrew legal text:
    - Rule-based detection: reliable for structured contradictions (dates, amounts)
    - LLM analyzer: better for semantic/open-ended contradictions
    - Entity overlap: strong signal for same-subject filtering
    - Temporal evidence: confirms date-related contradictions
    """

    # Default weights — derived from signal reliability characteristics:
    # - Rule-based: High precision for structured data (dates/amounts), lower for semantics
    # - LLM: Broad understanding but can hallucinate
    # - Negation: Direct polarity evidence — high precision when present
    # - Semantic: Only measures topical relatedness, not contradiction
    # - Entity/subject: Context filters, not contradiction indicators
    # - Temporal: Rare but very reliable when present
    # - Agreement: Cross-validation between independent detectors
    DEFAULT_WEIGHTS = {
        'rule_confidence': 0.25,
        'llm_confidence': 0.20,
        'negation_contrast': 0.12,    # NEW: opposing polarity is strong evidence
        'semantic_similarity': 0.10,
        'entity_overlap': 0.08,
        'same_subject': 0.10,
        'temporal': 0.05,
        'agreement_bonus': 0.10,
    }

    # Status thresholds
    VERIFIED_THRESHOLD = 0.78   # Lowered: system is now more selective upstream
    LIKELY_THRESHOLD = 0.55
    # Below LIKELY_THRESHOLD = suspicious

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        # Track scoring statistics for self-calibration
        self._score_history: List[float] = []
        self._signal_correlations: Dict[str, List[float]] = defaultdict(list)

    def score(self, signals: ContradictionSignals) -> EnsembleResult:
        """
        Compute final confidence score from all signals.

        Returns EnsembleResult with final score, status, and explanation.
        """
        weighted_sum = 0.0
        total_weight = 0.0
        signals_used = {}
        boosted_by = []
        penalized_by = []

        # 1. Rule-based confidence
        if signals.rule_confidence > 0:
            w = self.weights['rule_confidence']
            weighted_sum += signals.rule_confidence * w
            total_weight += w
            signals_used['rule_confidence'] = signals.rule_confidence

        # 2. LLM analyzer confidence
        if signals.llm_confidence is not None:
            w = self.weights['llm_confidence']
            weighted_sum += signals.llm_confidence * w
            total_weight += w
            signals_used['llm_confidence'] = signals.llm_confidence

        # 3. Negation contrast — opposing polarity is DIRECT contradiction evidence
        if signals.negation_contrast > 0:
            w = self.weights['negation_contrast']
            weighted_sum += signals.negation_contrast * w
            total_weight += w
            signals_used['negation_contrast'] = signals.negation_contrast
            if signals.negation_contrast >= 0.5:
                boosted_by.append("קוטביות מנוגדת (שלילה/היפוך)")

        # 4. Contradiction signal (combined high-similarity + negation)
        if signals.contradiction_signal > 0.3:
            # Strong signal: claims are similar AND have opposing polarity
            boost = signals.contradiction_signal * 0.15
            weighted_sum += boost
            signals_used['contradiction_signal'] = signals.contradiction_signal
            boosted_by.append(f"אות סתירה חזק ({signals.contradiction_signal:.0%})")

        # 5. Semantic similarity — acts as a GATE
        if signals.semantic_similarity > 0:
            w = self.weights['semantic_similarity']
            if signals.semantic_similarity < 0.12:
                # Very low similarity - these claims are likely unrelated
                penalized_by.append("סמנטיקה: טענות לא קשורות")
                weighted_sum -= 0.12
            else:
                weighted_sum += signals.semantic_similarity * w
                total_weight += w
                signals_used['semantic_similarity'] = signals.semantic_similarity

        # 6. Entity overlap
        if signals.entity_overlap > 0:
            w = self.weights['entity_overlap']
            weighted_sum += signals.entity_overlap * w
            total_weight += w
            signals_used['entity_overlap'] = signals.entity_overlap
            if signals.entity_overlap >= 0.5:
                boosted_by.append("ישויות משותפות")

        # 7. Same subject score
        if signals.same_subject_score > 0:
            w = self.weights['same_subject']
            weighted_sum += signals.same_subject_score * w
            total_weight += w
            signals_used['same_subject'] = signals.same_subject_score

        # 8. Temporal evidence (additive boost)
        if signals.temporal_boost > 0:
            weighted_sum += signals.temporal_boost
            signals_used['temporal_boost'] = signals.temporal_boost
            boosted_by.append("עדות זמנית תומכת")

        if signals.has_temporal_conflict:
            weighted_sum += 0.1
            boosted_by.append("סתירה זמנית ישירה")

        if signals.has_impossible_sequence:
            weighted_sum += 0.15
            boosted_by.append("רצף סיבתי בלתי אפשרי")

        # 9. Agreement bonus (both engines found it)
        if signals.both_engines_agree:
            w = self.weights['agreement_bonus']
            weighted_sum += w  # Full weight as bonus (cross-validation)
            total_weight += w
            signals_used['agreement_bonus'] = 1.0
            boosted_by.append("שני מנועי זיהוי מסכימים")

        # Normalize
        if total_weight > 0:
            base_score = weighted_sum / total_weight
        else:
            base_score = signals.rule_confidence  # Fallback to rule only

        # 10. Learning adjustment (additive)
        base_score += signals.learning_adjustment
        if signals.learning_adjustment > 0:
            boosted_by.append(f"למידה: +{signals.learning_adjustment:.2f}")
        elif signals.learning_adjustment < 0:
            penalized_by.append(f"למידה: {signals.learning_adjustment:.2f}")

        # 11. Historical precision — smooth penalty instead of hard threshold
        if signals.type_precision is not None and signals.type_precision < 0.6:
            # Smooth sigmoid penalty: precision 0.0 → multiply by 0.7, precision 0.6 → multiply by 1.0
            penalty = 0.7 + 0.3 * (signals.type_precision / 0.6)
            base_score *= penalty
            penalized_by.append(f"precision היסטורי: {signals.type_precision:.0%}")

        # 12. Self-calibration: track score distribution for threshold adjustment
        self._score_history.append(base_score)

        # Clamp to [0, 1]
        final = max(0.0, min(1.0, base_score))

        # Determine status
        if final >= self.VERIFIED_THRESHOLD:
            status = "verified"
        elif final >= self.LIKELY_THRESHOLD:
            status = "likely"
        else:
            status = "suspicious"

        # Build explanation
        explanation = self._build_explanation(signals, final, status, boosted_by, penalized_by)

        return EnsembleResult(
            final_confidence=round(final, 3),
            final_status=status,
            signals_used=signals_used,
            explanation=explanation,
            boosted_by=boosted_by,
            penalized_by=penalized_by,
        )

    def score_batch(
        self, candidates: List[Tuple[Any, ContradictionSignals]]
    ) -> List[Tuple[Any, EnsembleResult]]:
        """Score a batch of candidates."""
        return [(candidate, self.score(signals)) for candidate, signals in candidates]

    def update_weights_from_feedback(
        self, feedback_data: List[Dict[str, Any]]
    ) -> None:
        """
        Update weights using feedback data (simple gradient-free optimization).

        Each feedback item should have:
        - signals: ContradictionSignals
        - is_true_contradiction: bool
        """
        if len(feedback_data) < 10:
            logger.info("Not enough feedback to update weights (%d < 10)", len(feedback_data))
            return

        # Simple approach: compute correlation between each signal and correctness
        signal_names = ['rule_confidence', 'semantic_similarity', 'entity_overlap', 'same_subject']
        for name in signal_names:
            correct_values = []
            incorrect_values = []
            for item in feedback_data:
                sig = item.get('signals')
                if sig is None:
                    continue
                val = getattr(sig, name, 0.0) if hasattr(sig, name) else 0.0
                if item.get('is_true_contradiction'):
                    correct_values.append(val)
                else:
                    incorrect_values.append(val)

            if correct_values and incorrect_values:
                avg_correct = sum(correct_values) / len(correct_values)
                avg_incorrect = sum(incorrect_values) / len(incorrect_values)
                discriminability = avg_correct - avg_incorrect

                # Adjust weight proportional to discriminability
                current_weight = self.weights.get(name, 0.1)
                if discriminability > 0.1:
                    self.weights[name] = min(0.5, current_weight * 1.1)
                elif discriminability < -0.05:
                    self.weights[name] = max(0.05, current_weight * 0.9)

        # Normalize weights to sum to 1
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}

        logger.info("Updated ensemble weights from %d feedbacks: %s", len(feedback_data), self.weights)

    def _build_explanation(
        self,
        signals: ContradictionSignals,
        final: float,
        status: str,
        boosted_by: List[str],
        penalized_by: List[str],
    ) -> str:
        """Build a Hebrew explanation of the scoring."""
        parts = []

        if signals.both_engines_agree:
            parts.append("סתירה זוהתה בשני מנועים (כללים + LLM)")
        elif signals.rule_only:
            parts.append("סתירה זוהתה במנוע כללים")
        elif signals.llm_only:
            parts.append("סתירה זוהתה במנוע LLM")

        if boosted_by:
            parts.append("חיזוקים: " + ", ".join(boosted_by))

        if penalized_by:
            parts.append("הפחתות: " + ", ".join(penalized_by))

        status_labels = {
            "verified": "מאומת",
            "likely": "סביר",
            "suspicious": "חשוד",
        }
        parts.append(f"ציון סופי: {final:.0%} ({status_labels.get(status, status)})")

        return " | ".join(parts)


# =============================================================================
# Singleton
# =============================================================================

_scorer: Optional[EnsembleScorer] = None


def get_ensemble_scorer() -> EnsembleScorer:
    """Get singleton ensemble scorer."""
    global _scorer
    if _scorer is None:
        _scorer = EnsembleScorer()
    return _scorer
