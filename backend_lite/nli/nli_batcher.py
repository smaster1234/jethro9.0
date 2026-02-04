"""
NLI Batcher — converts pipeline claim-pairs into NLIPair objects,
runs batch inference, and applies threshold logic to produce tri-state
decisions (CONTRADICTION / NOT_CONTRADICTION / AMBIGUOUS).

This module is the glue between the rule-based detector pipeline and
the NLI cross-encoder.  It is called from `analyze_claims_internal`
for factual / attribution pairs that rules cannot resolve deterministically.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional, Sequence, Tuple

from .nli_types import NLIPair, NLIResult, NLILabel
from .nli_model import NLICrossEncoder, get_nli_classifier

logger = logging.getLogger(__name__)


def build_nli_pairs(
    claim_pairs: Sequence[Tuple[Dict, Dict, str]],
) -> List[NLIPair]:
    """
    Convert pipeline claim pairs into NLIPair objects for the cross-encoder.

    Each element in *claim_pairs* is a tuple:
        (claim_a_dict, claim_b_dict, pair_id)

    claim_a_dict / claim_b_dict must have at least a ``"text"`` key.
    Optional keys (``context_before``, ``context_after``) are prepended /
    appended to the text to give the model more context.
    """
    nli_pairs: List[NLIPair] = []
    for claim_a, claim_b, pair_id in claim_pairs:
        text_a = _build_nli_text(claim_a)
        text_b = _build_nli_text(claim_b)
        nli_pairs.append(NLIPair(
            text_a=text_a,
            text_b=text_b,
            pair_id=pair_id,
            metadata={
                "claim_a_id": claim_a.get("id", ""),
                "claim_b_id": claim_b.get("id", ""),
            },
        ))
    return nli_pairs


def apply_thresholds(
    results: List[NLIResult],
    thresholds: Optional[Dict[str, float]] = None,
) -> List[NLIResult]:
    """
    Apply threshold logic to NLI results, setting the ``decision`` field.

    Threshold dict keys:
        ``contradiction`` — minimum prob to declare CONTRADICTION
        ``ambiguous``     — minimum prob to declare AMBIGUOUS (gray zone)

    Logic:
        if contradiction_prob ≥ contradiction_threshold  → "contradiction"
        elif contradiction_prob ≥ ambiguous_threshold     → "ambiguous"
        else                                              → "not_contradiction"
    """
    if thresholds is None:
        try:
            from ..config import get_nli_thresholds
            thresholds = get_nli_thresholds()
        except Exception:
            thresholds = {"contradiction": 0.55, "ambiguous": 0.30}

    c_thresh = thresholds.get("contradiction", 0.55)
    a_thresh = thresholds.get("ambiguous", 0.30)

    for r in results:
        prob = r.calibrated["contradiction"] if r.calibrated else r.contradiction_prob
        if prob >= c_thresh:
            r.decision = "contradiction"
        elif prob >= a_thresh:
            r.decision = "ambiguous"
        else:
            r.decision = "not_contradiction"
    return results


def classify_pairs(
    claim_pairs: Sequence[Tuple[Dict, Dict, str]],
    classifier: Optional[NLICrossEncoder] = None,
    thresholds: Optional[Dict[str, float]] = None,
) -> List[NLIResult]:
    """
    End-to-end convenience: build pairs → predict → threshold → return.

    Parameters
    ----------
    claim_pairs : sequence of (claim_a_dict, claim_b_dict, pair_id)
    classifier  : optional pre-built NLICrossEncoder (defaults to singleton)
    thresholds  : optional threshold dict (defaults to config)

    Returns
    -------
    List of NLIResult with ``decision`` set.
    """
    if not claim_pairs:
        return []

    clf = classifier or get_nli_classifier()
    nli_pairs = build_nli_pairs(claim_pairs)
    raw_results = clf.predict_batch(nli_pairs)
    return apply_thresholds(raw_results, thresholds=thresholds)


# ── helpers ─────────────────────────────────────────────────────────────────

def _build_nli_text(claim: Dict) -> str:
    """
    Build a single NLI input string from a claim dict.

    Format: ``[context_before] <text> [context_after]``
    Keeps total length reasonable — the tokenizer will truncate if needed.
    """
    parts: List[str] = []
    ctx_before = claim.get("context_before", "")
    if ctx_before:
        parts.append(ctx_before.strip())
    parts.append(claim.get("text", "").strip())
    ctx_after = claim.get("context_after", "")
    if ctx_after:
        parts.append(ctx_after.strip())
    return " ".join(parts)
