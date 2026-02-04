"""
LLM Gray-zone Adjudicator (Part 4)
====================================

Called **only** for claim pairs where the NLI cross-encoder returned
``decision == "ambiguous"``  (gray zone between contradiction and neutral).

Budget: ≤ 10 % of total pairs per analysis run.

Input:  two Hebrew claims  +  NLI raw scores  +  rule-based metadata
Output: final tri-state decision  +  short Hebrew rationale

The adjudicator uses a structured JSON prompt so the answer is machine-
parseable.  If the LLM is unavailable or the budget is exhausted the
pair stays AMBIGUOUS.
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional, Dict, Any

from .nli.nli_types import NLIResult

logger = logging.getLogger(__name__)

# ── JSON prompt template (mandatory per spec §4) ────────────────────────────
_ADJUDICATOR_SYSTEM_PROMPT = """\
אתה שופט-על למערכת זיהוי סתירות במסמכים משפטיים בעברית.

קיבלת שתי טענות שהמערכת לא הצליחה להכריע לגביהן (אזור אפור).
עליך להחליט: האם יש ביניהן סתירה אמיתית?

כללים:
1. סתירה = שתי טענות על אותו נושא/אירוע שלא יכולות להיות נכונות בו-זמנית.
2. אם הטענות עוסקות באירועים שונים, מועדים שונים, או גורמים שונים — אין סתירה.
3. אם אחת הטענות היא דעה/ציטוט ולא עובדה — אין סתירה.
4. אם חסר מידע להכריע — תשאיר "ambiguous".

החזר JSON בלבד:\
"""

_ADJUDICATOR_USER_TEMPLATE = """\
טענה א: {text_a}
טענה ב: {text_b}

ציון NLI (contradiction_prob): {contradiction_prob:.3f}
סוג שזוהה (rule-based): {detector_type}

החזר JSON:
{{
  "decision": "contradiction" | "not_contradiction" | "ambiguous",
  "confidence": 0.0-1.0,
  "rationale": "הסבר קצר בעברית (משפט אחד)"
}}
"""


async def adjudicate_pair(
    text_a: str,
    text_b: str,
    nli_result: Optional[NLIResult] = None,
    detector_type: str = "",
) -> Dict[str, Any]:
    """
    Send a single ambiguous pair to the LLM for adjudication.

    Returns dict with keys: decision, confidence, rationale.
    On failure returns decision="ambiguous" so the pair is not silently dropped.
    """
    from .llm_client import generate_with_llm, parse_json_robust

    contradiction_prob = 0.0
    if nli_result:
        contradiction_prob = nli_result.contradiction_prob

    user_prompt = _ADJUDICATOR_USER_TEMPLATE.format(
        text_a=text_a,
        text_b=text_b,
        contradiction_prob=contradiction_prob,
        detector_type=detector_type or "unknown",
    )

    try:
        raw = await generate_with_llm(
            prompt=user_prompt,
            system_prompt=_ADJUDICATOR_SYSTEM_PROMPT,
            json_mode=True,
        )
        if not raw:
            logger.warning("Adjudicator: LLM returned empty — keeping ambiguous")
            return _default_result()

        parsed, ok, err = parse_json_robust(raw)
        if not ok or not parsed:
            logger.warning("Adjudicator: JSON parse failed (%s) — keeping ambiguous", err)
            return _default_result()

        decision = parsed.get("decision", "ambiguous")
        if decision not in ("contradiction", "not_contradiction", "ambiguous"):
            decision = "ambiguous"

        return {
            "decision": decision,
            "confidence": float(parsed.get("confidence", 0.5)),
            "rationale": parsed.get("rationale", ""),
        }
    except Exception as exc:
        logger.warning("Adjudicator error: %s — keeping ambiguous", exc)
        return _default_result()


async def adjudicate_batch(
    ambiguous_results: List[Dict[str, Any]],
    max_ratio: float = 0.10,
    total_pairs: int = 0,
) -> List[Dict[str, Any]]:
    """
    Adjudicate a batch of ambiguous pairs, respecting the budget.

    Parameters
    ----------
    ambiguous_results : list of dicts, each with:
        - text_a, text_b: claim texts
        - nli_result: NLIResult (optional)
        - detector_type: str (optional)
        - pair_id: str
    max_ratio : maximum fraction of total_pairs to send to LLM
    total_pairs : total number of pairs in this analysis run

    Returns
    -------
    Same list with ``adjudication`` key added to each dict.
    """
    budget = max(1, int(total_pairs * max_ratio)) if total_pairs > 0 else len(ambiguous_results)
    to_adjudicate = ambiguous_results[:budget]
    skipped = ambiguous_results[budget:]

    logger.info(
        "Adjudicator: %d ambiguous pairs, budget=%d (%.0f%% of %d), skipping=%d",
        len(ambiguous_results), budget, max_ratio * 100, total_pairs, len(skipped),
    )

    for item in to_adjudicate:
        result = await adjudicate_pair(
            text_a=item.get("text_a", ""),
            text_b=item.get("text_b", ""),
            nli_result=item.get("nli_result"),
            detector_type=item.get("detector_type", ""),
        )
        item["adjudication"] = result

    for item in skipped:
        item["adjudication"] = _default_result()

    return ambiguous_results


def _default_result() -> Dict[str, Any]:
    return {
        "decision": "ambiguous",
        "confidence": 0.0,
        "rationale": "לא ניתן להכריע (תקציב LLM / שגיאה)",
    }
