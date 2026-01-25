"""
Cross-Examination Planner
=========================

Builds a staged plan with branching based on ContradictionInsights and playbooks.
"""

import uuid
import logging
from typing import Any, Dict, List, Optional, Tuple

from .cross_exam import PlaybookLoader
from .db.models import Contradiction, ContradictionInsight

logger = logging.getLogger(__name__)


STEP_TYPES = [
    "lock_in",
    "timeline_commitment",
    "document_confrontation",
    "explosion",
    "close",
]


def _playbook_key_for_type(contradiction_type: str) -> str:
    lowered = (contradiction_type or "").lower()
    if "temporal" in lowered:
        return "temporal"
    if "version" in lowered:
        return "version"
    if "witness" in lowered:
        return "witness"
    if "expert" in lowered:
        return "expert"
    if "document" in lowered:
        return "document_integrity"
    return "factual"


def _safe_quote(text: Optional[str], limit: int = 120) -> str:
    if not text:
        return ""
    return text[:limit].strip()


def _fill_template(template: str, variables: Dict[str, str]) -> str:
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{key}}}", value)
    # clean up missing placeholders
    import re
    result = re.sub(r"\{[^}]+\}", "לא זמין", result)
    return result


def _build_variables(contr: Contradiction) -> Dict[str, str]:
    quote_a = _safe_quote(contr.quote1)
    quote_b = _safe_quote(contr.quote2)
    return {
        "quote_a": quote_a,
        "quote_b": quote_b,
        "fact_a": quote_a[:80],
        "fact_b": quote_b[:80],
        "date_a": quote_a[:30],
        "date_b": quote_b[:30],
        "event_a": quote_a[:40],
        "event_b": quote_b[:40],
    }


def _anchors_from_contradiction(contr: Contradiction) -> List[Dict[str, Any]]:
    anchors = []
    if contr.locator1_json and contr.locator1_json.get("doc_id"):
        anchors.append(contr.locator1_json)
    if contr.locator2_json and contr.locator2_json.get("doc_id"):
        anchors.append(contr.locator2_json)
    return anchors


def _build_branches(trap_branches: List[str], evasions: List[str], counters: List[str]) -> List[Dict[str, Any]]:
    branches: List[Dict[str, Any]] = []
    seen_triggers = set()

    for branch in trap_branches:
        if branch and branch not in seen_triggers:
            branches.append({"trigger": branch, "follow_up_questions": []})
            seen_triggers.add(branch)

    default_evasions = ["לא זוכר", "טעיתי", "לא הבנתי", "זה לא מה שאמרתי"]
    combined_evasions = list(dict.fromkeys((evasions or []) + default_evasions))
    counter_question = counters[0] if counters else "אתה עומד מאחורי הגרסה הזו?"
    for evasion in combined_evasions:
        trigger = f"אם העד אומר: '{evasion}'"
        if trigger in seen_triggers:
            continue
        branches.append({
            "trigger": trigger,
            "follow_up_questions": [counter_question],
        })
        seen_triggers.add(trigger)

    return branches


def build_cross_exam_plan(
    contradictions: List[Tuple[Contradiction, Optional[ContradictionInsight]]]
) -> List[Dict[str, Any]]:
    playbooks = PlaybookLoader.load()
    stages: Dict[str, List[Dict[str, Any]]] = {"early": [], "mid": [], "late": []}

    for contr, insight in contradictions:
        stage = (insight.stage_recommendation if insight else None) or "mid"
        if insight and insight.prerequisites_json and stage == "early":
            stage = "mid"
        if stage not in stages:
            stage = "mid"

        playbook_key = _playbook_key_for_type(contr.contradiction_type)
        playbook = playbooks.get(playbook_key, playbooks.get("factual", {}))
        cross_exam = playbook.get("cross_examination", {})
        question_set = cross_exam.get("question_set", [])
        trap_branches = cross_exam.get("trap_branches", [])

        variables = _build_variables(contr)
        anchors = _anchors_from_contradiction(contr)
        if not anchors:
            logger.debug("Skipping contradiction %s due to missing anchors", contr.id)
            continue

        do_not_ask = bool(insight.do_not_ask) if insight else False
        if do_not_ask:
            alternative = None
            if insight and insight.counters_json:
                alternative = insight.counters_json[0]
            steps = [{
                "id": f"step_{uuid.uuid4().hex[:8]}",
                "contradiction_id": contr.id,
                "stage": stage,
                "step_type": "do_not_ask",
                "title": "DON'T ASK THIS",
                "question": alternative or "מומלץ להימנע משאלה זו בשלב זה.",
                "purpose": "אזהרה מפני סיכון גבוה",
                "anchors": anchors,
                "branches": [],
                "do_not_ask_flag": True,
                "do_not_ask_reason": insight.do_not_ask_reason if insight else None,
            }]
            stages[stage].extend(steps)
            continue

        branches = _build_branches(
            trap_branches=trap_branches,
            evasions=(insight.evasions_json if insight else []) or [],
            counters=(insight.counters_json if insight else []) or [],
        )

        sequence = cross_exam.get("sequence", []) or []
        for idx, template in enumerate(question_set[: len(STEP_TYPES)]):
            question = _fill_template(template, variables)
            step_type = STEP_TYPES[idx] if idx < len(STEP_TYPES) else "follow_up"
            title = sequence[idx] if idx < len(sequence) else step_type
            stages[stage].append({
                "id": f"step_{uuid.uuid4().hex[:8]}",
                "contradiction_id": contr.id,
                "stage": stage,
                "step_type": step_type,
                "title": title,
                "question": question,
                "purpose": None,
                "anchors": anchors,
                "branches": branches if idx == 2 else [],
                "do_not_ask_flag": False,
                "do_not_ask_reason": None,
            })

    return [
        {"stage": "early", "steps": stages["early"]},
        {"stage": "mid", "steps": stages["mid"]},
        {"stage": "late", "steps": stages["late"]},
    ]
