"""
NLI type definitions — dataclasses for cross-encoder input/output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any


class NLILabel(str, Enum):
    """Three-class NLI labels (output of cross-encoder)."""
    ENTAILMENT = "entailment"
    CONTRADICTION = "contradiction"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class NLIPair:
    """
    Single pair sent to the NLI cross-encoder.

    text_a / text_b: Hebrew claim texts (premise / hypothesis).
    pair_id: opaque identifier used to join results back to pipeline data.
    metadata: arbitrary bag carried through (e.g. detector_type, claim IDs).
    """
    text_a: str
    text_b: str
    pair_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NLIResult:
    """
    Result for a single NLI pair after inference + optional calibration.

    Fields:
        pair_id:        matches NLIPair.pair_id
        label:          argmax label (entailment / contradiction / neutral)
        raw_scores:     dict  {"entailment": float, "contradiction": float, "neutral": float}
        calibrated:     same keys but after temperature-scaling (None if calibration off)
        contradiction_prob:  shortcut → calibrated["contradiction"] or raw_scores["contradiction"]
        decision:       tri-state from ContradictionDecision (set by threshold logic)
    """
    pair_id: str
    label: NLILabel
    raw_scores: Dict[str, float]
    calibrated: Optional[Dict[str, float]] = None
    contradiction_prob: float = 0.0
    decision: Optional[str] = None  # "contradiction" | "not_contradiction" | "ambiguous"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_contradiction(self) -> bool:
        return self.decision == "contradiction"

    @property
    def is_ambiguous(self) -> bool:
        return self.decision == "ambiguous"
