"""
Witness Simulation
==================

Simulates witness responses based on a cross-examination plan.
"""

from typing import Any, Dict, List, Optional, Tuple


PERSONA_REPLIES = {
    "cooperative": {
        "lock_in": "כן, אני מאשר.",
        "timeline_commitment": "כן, זה המועד שאני זוכר.",
        "document_confrontation": "כן, זה מה שכתוב במסמך.",
        "explosion": "אני מבין את הפער ומוכן להסביר.",
        "close": "זו גרסתי הסופית.",
        "default": "כן.",
    },
    "evasive": {
        "lock_in": "לא זוכר במדויק.",
        "timeline_commitment": "קשה לי לקבוע מועד מדויק.",
        "document_confrontation": "אני לא בטוח לגבי המסמך הזה.",
        "explosion": "אני לא מסכים שהייתה סתירה.",
        "close": "אין לי מה להוסיף.",
        "default": "לא זוכר.",
    },
    "hostile": {
        "lock_in": "אני לא מוכן להתחייב.",
        "timeline_commitment": "אני לא זוכר ואתם מפעילים לחץ.",
        "document_confrontation": "אני לא מאשר את המסמך הזה.",
        "explosion": "זו פרשנות שלכם.",
        "close": "אני מסרב לענות.",
        "default": "אני לא משיב.",
    },
}


def _choose_branch(branches: List[Dict[str, Any]], persona: str) -> Tuple[Optional[str], List[str]]:
    if not branches:
        return None, []

    persona = (persona or "cooperative").lower()
    for branch in branches:
        trigger = branch.get("trigger", "")
        if persona == "evasive" and "לא זוכר" in trigger:
            return trigger, branch.get("follow_up_questions", [])
        if persona == "hostile" and ("מתחמק" in trigger or "לא עונה" in trigger or "מסרב" in trigger):
            return trigger, branch.get("follow_up_questions", [])

    first = branches[0]
    return first.get("trigger"), first.get("follow_up_questions", [])


def _warnings_for_step(step: Dict[str, Any]) -> List[str]:
    warnings = []
    if step.get("do_not_ask_flag"):
        warnings.append("DON'T ASK THIS: סיכון גבוה לעומת אחיזה נמוכה בעוגנים.")
    if not step.get("anchors"):
        warnings.append("אין עוגן ראייתי לשאלה זו.")
    if step.get("step_type") == "explosion":
        warnings.append("שלב פיצוץ עשוי להגביר התנגדות העד.")
    return warnings


def simulate_plan(plan: Dict[str, Any], persona: str) -> List[Dict[str, Any]]:
    persona_key = (persona or "cooperative").lower()
    replies = PERSONA_REPLIES.get(persona_key, PERSONA_REPLIES["cooperative"])

    steps_output: List[Dict[str, Any]] = []
    for stage in plan.get("stages", []):
        stage_name = stage.get("stage", "mid")
        for step in stage.get("steps", []):
            step_type = step.get("step_type", "default")
            reply = replies.get(step_type, replies["default"])
            branch_trigger, follow_ups = _choose_branch(step.get("branches", []), persona_key)
            warnings = _warnings_for_step(step)

            steps_output.append({
                "step_id": step.get("id"),
                "stage": stage_name,
                "question": step.get("question", ""),
                "witness_reply": reply,
                "chosen_branch_trigger": branch_trigger,
                "follow_up_questions": follow_ups,
                "warnings": warnings,
            })

    return steps_output


def simulate_step(step: Dict[str, Any], persona: str, chosen_branch: Optional[str] = None) -> Dict[str, Any]:
    persona_key = (persona or "cooperative").lower()
    replies = PERSONA_REPLIES.get(persona_key, PERSONA_REPLIES["cooperative"])
    step_type = step.get("step_type", "default")
    reply = replies.get(step_type, replies["default"])

    branch_trigger = None
    follow_ups: List[str] = []
    branches = step.get("branches", []) or []
    if chosen_branch:
        for branch in branches:
            if branch.get("trigger") == chosen_branch:
                branch_trigger = branch.get("trigger")
                follow_ups = branch.get("follow_up_questions", [])
                break
    if not branch_trigger:
        branch_trigger, follow_ups = _choose_branch(branches, persona_key)

    warnings = _warnings_for_step(step)
    return {
        "witness_reply": reply,
        "chosen_branch_trigger": branch_trigger,
        "follow_up_questions": follow_ups,
        "warnings": warnings,
    }
