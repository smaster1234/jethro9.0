"""
Witness Simulation
==================

Simulates witness responses based on a cross-examination plan.

Modes:
1. **Template mode** (default): Fast, deterministic persona-based responses
2. **LLM mode** (when available): Dynamic, context-aware responses via Gemini/OpenRouter API

The LLM mode uses the existing OpenRouter infrastructure to generate realistic witness
responses without requiring a fine-tuned model. It considers:
- The witness's testimony (what they said in their documents)
- Their persona type (cooperative, evasive, hostile, etc.)
- The question context and strategic intent
- Previous questions and responses in the session
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Template-Based Persona Replies (Fast Fallback)
# =============================================================================

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
    "nervous": {
        "lock_in": "אני... כן, אני חושב שכן.",
        "timeline_commitment": "אני חושב שזה היה בערך אז, אבל אני לא בטוח.",
        "document_confrontation": "אני... כן, אבל אולי לא הבנתי נכון.",
        "explosion": "אני... אני לא יודע איך זה קרה. אולי טעיתי.",
        "close": "אני מקווה שעניתי נכון.",
        "default": "אני חושב שכן.",
    },
    "confident": {
        "lock_in": "בוודאי. אני זוכר בדיוק.",
        "timeline_commitment": "בהחלט. התאריך הזה חרוט בזיכרון שלי.",
        "document_confrontation": "אני מכיר את המסמך הזה, ואני עומד מאחורי מה שכתוב שם.",
        "explosion": "אין כאן סתירה. אני יכול להסביר.",
        "close": "אני עומד מאחורי כל מילה.",
        "default": "בהחלט.",
    },
    "calculated": {
        "lock_in": "אני מאשר את מה שכתוב בתצהיר שלי.",
        "timeline_commitment": "לפי התיעוד שלי, כן.",
        "document_confrontation": "אני צריך לבדוק את ההקשר המלא של המסמך.",
        "explosion": "אני מציע שנבדוק את שני המסמכים יחד.",
        "close": "אני עומד מאחורי עדותי כפי שנרשמה.",
        "default": "כפי שציינתי בתצהיר.",
    },
}

# Extended behavior patterns per persona for different question intents
PERSONA_BEHAVIORS = {
    "cooperative": {
        "under_pressure": "מנסה לעזור אבל מתחיל להתבלבל",
        "when_caught": "מודה בטעות ומנסה לתקן",
        "verbal_tics": ["אני חושב ש", "כפי שציינתי", "לפי מה שאני זוכר"],
        "hedging_level": 0.2,
    },
    "evasive": {
        "under_pressure": "מתחמק יותר ומתחיל להשתמש ב'לא זוכר'",
        "when_caught": "מנסה לשנות נושא או להסיט את השיחה",
        "verbal_tics": ["לא בדיוק", "זה לא מה שהתכוונתי", "יכול להיות"],
        "hedging_level": 0.7,
    },
    "hostile": {
        "under_pressure": "הופך תוקפני יותר ומערער על השאלות",
        "when_caught": "מכחיש או מאשים את הצד השני",
        "verbal_tics": ["זו פרשנות שלכם", "אני מתנגד לניסוח", "אני לא מקבל את הנחת היסוד"],
        "hedging_level": 0.1,
    },
    "nervous": {
        "under_pressure": "מתבלבל, חוזר על עצמו, מבקש לחזור על השאלה",
        "when_caught": "נלחץ ועלול לשנות גרסה",
        "verbal_tics": ["אני... אה...", "רגע, תן לי לחשוב", "אני לא בטוח"],
        "hedging_level": 0.8,
    },
    "confident": {
        "under_pressure": "נשאר בטוח בעצמו, יכול להיות מתנשא",
        "when_caught": "מחפש הסבר לוגי או מציג פרשנות חלופית",
        "verbal_tics": ["ברור ש", "אין ספק", "כמו שאמרתי"],
        "hedging_level": 0.1,
    },
    "calculated": {
        "under_pressure": "שוקל כל מילה, מבקש לראות מסמכים",
        "when_caught": "מציע הסבר מחושב ומפנה לתיעוד",
        "verbal_tics": ["בהתייחס למסמך", "לפי התיעוד", "אם תרשו לי לעיין"],
        "hedging_level": 0.4,
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
        if persona == "nervous" and ("מתבלבל" in trigger or "לא בטוח" in trigger):
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


def _build_llm_system_prompt(
    persona: str,
    testimony_context: str = "",
    contradictions_context: str = "",
    previous_qa: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Build a system prompt for LLM-based witness simulation."""
    behavior = PERSONA_BEHAVIORS.get(persona, PERSONA_BEHAVIORS["cooperative"])
    verbal_tics = ", ".join(behavior.get("verbal_tics", []))

    prompt = f"""אתה עד בהליך משפטי ישראלי. אתה משיב בחקירה נגדית.

## הפרופיל שלך
- סוג: {persona}
- התנהגות תחת לחץ: {behavior.get('under_pressure', '')}
- כשנתפס בסתירה: {behavior.get('when_caught', '')}
- ביטויים אופייניים: {verbal_tics}

## כללים חשובים
1. ענה בקצרה (1-3 משפטים)
2. השתמש בביטויים אופייניים לפרופיל שלך
3. אל תמציא עובדות חדשות שלא בעדות שלך
4. אם נשאלת על משהו שסותר את העדות שלך, הגב לפי הפרופיל
5. שמור על עקביות עם תשובות קודמות בחקירה זו
"""

    if testimony_context:
        prompt += f"""
## העדות שלך
{testimony_context[:2000]}
"""

    if contradictions_context:
        prompt += f"""
## סתירות שזוהו (אתה לא יודע שיודעים עליהן!)
{contradictions_context[:1000]}
"""

    if previous_qa:
        prompt += "\n## שאלות ותשובות קודמות בחקירה זו:\n"
        for qa in previous_qa[-5:]:  # Last 5 Q&As for context
            prompt += f"ש: {qa.get('question', '')}\n"
            prompt += f"ת: {qa.get('answer', '')}\n"

    return prompt


async def simulate_step_llm(
    step: Dict[str, Any],
    persona: str,
    testimony_context: str = "",
    contradictions_context: str = "",
    previous_qa: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Simulate a single step using LLM for dynamic response generation.

    Falls back to template-based responses if LLM is unavailable.
    """
    question = step.get("question", "")
    step_type = step.get("step_type", "default")

    try:
        from .llm.openrouter_base import OpenRouterBaseClient, LLMCallResult

        client = OpenRouterBaseClient()
        system_prompt = _build_llm_system_prompt(
            persona=persona,
            testimony_context=testimony_context,
            contradictions_context=contradictions_context,
            previous_qa=previous_qa,
        )

        result: LLMCallResult = await client.call(
            model="google/gemini-2.0-flash-001",  # Fast, cheap, Hebrew-capable
            system_prompt=system_prompt,
            user_prompt=f"השאלה שנשאלת:\n{question}\n\nענה כעד (1-3 משפטים בלבד):",
            temperature=0.7,
            max_tokens=256,
        )

        if result and result.content:
            reply = result.content.strip()
            # Determine behavior cues from LLM response
            branch_trigger, follow_ups = _choose_branch(
                step.get("branches", []), persona
            )
            warnings = _warnings_for_step(step)

            logger.info("LLM witness simulation: persona=%s, reply_len=%d", persona, len(reply))

            return {
                "witness_reply": reply,
                "chosen_branch_trigger": branch_trigger,
                "follow_up_questions": follow_ups,
                "warnings": warnings,
                "simulation_mode": "llm",
                "behavior_analysis": _analyze_response(reply, persona),
            }

    except ImportError:
        logger.debug("LLM client not available, falling back to template")
    except Exception as e:
        logger.warning("LLM simulation failed, falling back to template: %s", e)

    # Fallback to template
    return simulate_step(step, persona)


def _analyze_response(reply: str, persona: str) -> Dict[str, Any]:
    """Analyze a witness response for behavioral cues."""
    behavior = PERSONA_BEHAVIORS.get(persona, PERSONA_BEHAVIORS["cooperative"])

    analysis = {
        "hedging_detected": False,
        "evasion_detected": False,
        "contradiction_risk": False,
        "emotional_markers": [],
    }

    # Check for hedging markers
    hedging_words = ["אולי", "יכול להיות", "לא בטוח", "כנראה", "אני חושב"]
    for word in hedging_words:
        if word in reply:
            analysis["hedging_detected"] = True
            break

    # Check for evasion
    evasion_words = ["לא זוכר", "לא יודע", "לא שמתי לב", "קשה לי"]
    for word in evasion_words:
        if word in reply:
            analysis["evasion_detected"] = True
            break

    # Check for absolutist statements (contradiction risk)
    absolute_words = ["תמיד", "אף פעם", "בוודאות", "מאה אחוז", "בהחלט"]
    for word in absolute_words:
        if word in reply:
            analysis["contradiction_risk"] = True
            break

    # Check for emotional markers
    emotional_words = {
        "anger": ["מתנגד", "לא הוגן", "מפעילים לחץ"],
        "fear": ["אני מפחד", "אני לא...", "רגע"],
        "confidence": ["בוודאי", "ברור", "אין ספק"],
    }
    for emotion, words in emotional_words.items():
        for word in words:
            if word in reply:
                analysis["emotional_markers"].append(emotion)
                break

    return analysis


def simulate_plan(plan: Dict[str, Any], persona: str) -> List[Dict[str, Any]]:
    """Simulate a full cross-examination plan with template responses."""
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
                "simulation_mode": "template",
                "behavior_analysis": _analyze_response(reply, persona_key),
            })

    return steps_output


def simulate_step(step: Dict[str, Any], persona: str, chosen_branch: Optional[str] = None) -> Dict[str, Any]:
    """Simulate a single step with template responses."""
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
        "simulation_mode": "template",
        "behavior_analysis": _analyze_response(reply, persona_key),
    }
