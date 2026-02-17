"""
LLM-Powered Cross-Examination Question Generator
==================================================

Uses Gemini to generate context-aware cross-examination questions
that go beyond templates. Operates as an enhancement layer on top of
the existing template-based system.

Privacy: All calls go directly to Google Gemini — no third-party proxies.

Architecture:
- Takes contradiction context + template questions as input
- Gemini generates tailored, context-aware questions in Hebrew
- Falls back to template questions on any LLM failure (non-blocking)
"""

import os
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from .llm.gemini_client import GeminiBaseClient
from .llm.openrouter_base import LLMCallResult
from .llm_client import parse_json_robust

logger = logging.getLogger(__name__)


# ============================================================================
# System Prompt — Hebrew Legal Cross-Examination Expert
# ============================================================================

CROSS_EXAM_SYSTEM_PROMPT = """אתה מומחה בחקירות נגדיות במשפט הישראלי. תפקידך לייצר שאלות חקירה נגדית חכמות, ממוקדות ואסטרטגיות בעברית משפטית.

## כללים מחייבים:
1. **עברית משפטית** — כל השאלות בעברית תקנית ומשפטית. לא לשלב מונחים באנגלית.
2. **ממוקדות בסתירה** — כל שאלה חייבת להתייחס ישירות לסתירה שזוהתה.
3. **מבנה אסטרטגי** — השאלות בנויות ברצף הגיוני: קיבוע → הנחה → עימות → ניצול.
4. **ציטוטים מדויקים** — השתמש בציטוטים המקוריים מהטענות. לא להמציא עובדות.
5. **שאלות סגורות** — רוב השאלות צריכות להיות סגורות (כן/לא) בהתאם לכלל ויגמור.
6. **אל תשאל שאלה אחת יותר מדי** — דיבר 9 של ירווינג יאנגר.

## 10 הדיברות של ירווינג יאנגר (חקירה נגדית):
1. היה קצר
2. שאל שאלות קצרות, במילים פשוטות
3. שאל רק שאלות מנחות
4. אל תשאל שאלה שאתה לא יודע את תשובתה
5. הקשב לתשובה
6. אל תתווכח עם העד
7. אל תתן לעד להסביר
8. אל תשאל שאלה "למה"
9. אל תשאל שאלה אחת יותר מדי
10. שמור את הנקודה הטובה ביותר לסיכום

## מבנה השאלות:
כל שאלה צריכה לכלול:
- `question`: טקסט השאלה בעברית
- `purpose`: מטרת השאלה (קיבוע/הנחה/עימות/ניצול/מלכודת)
- `question_type`: סוג (yes_no/open/leading/confront/clarify/trap)
- `follow_up_if_yes`: מה לעשות אם העד מאשר
- `follow_up_if_no`: מה לעשות אם העד מכחיש
- `trap_branch`: ענף מלכודת אופציונלי

## החזר JSON בלבד בפורמט:
{
  "questions": [...],
  "strategy_summary": "סיכום אסטרטגי קצר",
  "key_objective": "המטרה המרכזית של שאלון זה",
  "risk_warning": "אזהרה על סיכונים פוטנציאליים"
}"""


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class LLMQuestionResult:
    """Result from LLM question generation"""
    questions: List[Dict[str, Any]] = field(default_factory=list)
    strategy_summary: str = ""
    key_objective: str = ""
    risk_warning: str = ""
    success: bool = True
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    used_llm: bool = False


# ============================================================================
# Question Generator
# ============================================================================

class LLMQuestionGenerator:
    """
    Generates cross-examination questions using Gemini.

    Privacy: All calls go directly to Google Gemini API.
    Non-blocking: Falls back to template questions on any failure.
    """

    # Model configuration
    PRIMARY_MODEL = "gemini-3-flash-preview"
    FALLBACK_MODEL = "gemini-2.5-flash"
    THINKING_LEVEL = "medium"  # Medium thinking for quality questions

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        self.enabled = bool(api_key)

        if self.enabled:
            model = os.getenv("GEMINI_CROSSEXAM_MODEL", self.PRIMARY_MODEL)
            thinking = os.getenv("GEMINI_CROSSEXAM_THINKING", self.THINKING_LEVEL)
            self.model = model

            self.client = GeminiBaseClient(
                api_key=api_key,
                model=model,
                timeout=45,
                app_name="JETHRO Cross-Exam Generator",
                thinking_level=thinking,
            )

            fallback_model = os.getenv("GEMINI_CROSSEXAM_FALLBACK", self.FALLBACK_MODEL)
            self.fallback_client = GeminiBaseClient(
                api_key=api_key,
                model=fallback_model,
                timeout=45,
                app_name="JETHRO Cross-Exam Fallback",
            )

            logger.info(
                "LLM Question Generator initialized: primary=%s (thinking=%s), fallback=%s",
                model, thinking, fallback_model,
            )
        else:
            self.model = "none"
            self.client = None
            self.fallback_client = None
            logger.info("LLM Question Generator disabled: GEMINI_API_KEY not set")

    async def close(self):
        """Close HTTP clients"""
        if self.client:
            await self.client.close()
        if self.fallback_client:
            await self.fallback_client.close()

    async def generate(
        self,
        contradiction_context: Dict[str, Any],
        template_questions: List[Dict[str, str]],
        max_questions: int = 5,
    ) -> LLMQuestionResult:
        """
        Generate cross-examination questions using Gemini.

        Args:
            contradiction_context: Dict with contradiction details
                - type: Contradiction type (temporal, quantitative, etc.)
                - severity: Severity level
                - confidence: Detection confidence
                - quote_a: First claim quote
                - quote_b: Second claim quote
                - source_a: Source of first claim (optional)
                - source_b: Source of second claim (optional)
                - speaker_a: Speaker of first claim (optional)
                - speaker_b: Speaker of second claim (optional)
                - date_a, date_b: Relevant dates (optional)
                - amount_a, amount_b: Relevant amounts (optional)
                - person_a, person_b: Attributed persons (optional)
                - strategic_approach: Source-aware strategy (optional)
                - witness_profile: Inferred witness profile (optional)
            template_questions: Existing template-generated questions as baseline
            max_questions: Maximum questions to generate

        Returns:
            LLMQuestionResult with generated questions
        """
        if not self.enabled:
            return LLMQuestionResult(
                success=False,
                error="LLM not enabled",
                used_llm=False,
            )

        # Build the user prompt
        user_prompt = self._build_prompt(
            contradiction_context, template_questions, max_questions
        )

        messages = [
            {"role": "system", "content": CROSS_EXAM_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # Try primary model
        result = await self.client.call(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.3,  # Slight creativity for question variety
            max_tokens=3072,
        )

        # Fallback if primary fails
        if not result.success and self.fallback_client:
            logger.warning(
                "Cross-exam LLM primary (%s) failed: %s — trying fallback",
                self.model, result.error,
            )
            result = await self.fallback_client.call(
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=3072,
            )

        if not result.success:
            logger.warning("Cross-exam LLM failed: %s", result.error)
            return LLMQuestionResult(
                success=False,
                error=result.error,
                used_llm=False,
            )

        # Parse response
        return self._parse_response(result)

    def _build_prompt(
        self,
        ctx: Dict[str, Any],
        template_questions: List[Dict[str, str]],
        max_questions: int,
    ) -> str:
        """Build the user prompt with contradiction context"""
        parts = []

        # Contradiction details
        parts.append("## סתירה שזוהתה:")
        parts.append(f"**סוג**: {ctx.get('type', 'לא ידוע')}")
        parts.append(f"**חומרה**: {ctx.get('severity', 'בינונית')}")
        parts.append(f"**ביטחון**: {ctx.get('confidence', 0.0):.0%}")

        # Quotes
        quote_a = ctx.get('quote_a', '')
        quote_b = ctx.get('quote_b', '')
        if quote_a:
            parts.append(f"\n**טענה א'**: \"{quote_a}\"")
        if quote_b:
            parts.append(f"**טענה ב'**: \"{quote_b}\"")

        # Sources
        source_a = ctx.get('source_a', '')
        source_b = ctx.get('source_b', '')
        if source_a:
            parts.append(f"\n**מקור טענה א'**: {source_a}")
        if source_b:
            parts.append(f"**מקור טענה ב'**: {source_b}")

        # Speakers
        speaker_a = ctx.get('speaker_a', '')
        speaker_b = ctx.get('speaker_b', '')
        if speaker_a:
            parts.append(f"**דובר א'**: {speaker_a}")
        if speaker_b:
            parts.append(f"**דובר ב'**: {speaker_b}")

        # Type-specific data
        if ctx.get('date_a'):
            parts.append(f"\n**תאריך א'**: {ctx['date_a']}")
        if ctx.get('date_b'):
            parts.append(f"**תאריך ב'**: {ctx['date_b']}")
        if ctx.get('amount_a'):
            parts.append(f"\n**סכום א'**: {ctx['amount_a']}")
        if ctx.get('amount_b'):
            parts.append(f"**סכום ב'**: {ctx['amount_b']}")
        if ctx.get('person_a'):
            parts.append(f"\n**אדם א'**: {ctx['person_a']}")
        if ctx.get('person_b'):
            parts.append(f"**אדם ב'**: {ctx['person_b']}")

        # Strategic context
        approach = ctx.get('strategic_approach', '')
        if approach:
            approach_labels = {
                "internal_contradiction": "סתירה פנימית (אותו עד/מקור)",
                "cross_party_conflict": "עימות בין צדדים",
                "supporting_witness_conflict": "עימות עם עד תומך",
                "contradict_court_finding": "סתירה לקביעת בית משפט",
                "contradict_document": "סתירה למסמך",
            }
            parts.append(f"\n**גישה אסטרטגית**: {approach_labels.get(approach, approach)}")

        witness = ctx.get('witness_profile', '')
        if witness:
            profile_labels = {
                "cooperative": "שיתופי",
                "hostile": "עוין",
                "evasive": "מתחמק",
                "confident": "בטוח",
                "nervous": "עצבני",
                "defensive": "מתגונן",
            }
            parts.append(f"**פרופיל עד**: {profile_labels.get(witness, witness)}")

        # Template questions as reference
        if template_questions:
            parts.append(f"\n## שאלות תבנית (לייחוס):")
            for i, tq in enumerate(template_questions[:max_questions], 1):
                q_text = tq.get('question', tq) if isinstance(tq, dict) else str(tq)
                parts.append(f"{i}. {q_text}")

        # Instructions
        parts.append(f"\n## הנחיות:")
        parts.append(f"ייצר בדיוק {max_questions} שאלות חקירה נגדית.")
        parts.append("השאלות חייבות להיות ספציפיות לסתירה הזו, לא גנריות.")
        parts.append("השתמש בציטוטים המדויקים מהטענות.")
        parts.append("בנה את השאלות ברצף אסטרטגי: קיבוע → הנחה → עימות → ניצול.")
        parts.append("שפר את שאלות התבנית אם ניתנו — הפוך אותן לממוקדות וחכמות יותר.")

        return "\n".join(parts)

    def _parse_response(self, result: LLMCallResult) -> LLMQuestionResult:
        """Parse LLM response into structured result"""
        if not result.content or not result.content.strip():
            return LLMQuestionResult(
                success=False,
                error="Empty response from LLM",
                used_llm=True,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )

        data, ok, error = parse_json_robust(result.content)
        if not ok or data is None:
            logger.warning("Cross-exam LLM JSON parse failed: %s", error)
            return LLMQuestionResult(
                success=False,
                error=f"JSON parse error: {error}",
                used_llm=True,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )

        questions = data.get("questions", [])

        # Validate questions
        valid_questions = []
        for q in questions:
            if isinstance(q, dict) and q.get("question"):
                valid_questions.append({
                    "question": q["question"],
                    "purpose": q.get("purpose", "שאלת חקירה"),
                    "question_type": q.get("question_type", "leading"),
                    "follow_up_if_yes": q.get("follow_up_if_yes", ""),
                    "follow_up_if_no": q.get("follow_up_if_no", ""),
                    "trap_branch": q.get("trap_branch"),
                })

        if not valid_questions:
            return LLMQuestionResult(
                success=False,
                error="No valid questions in LLM response",
                used_llm=True,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )

        return LLMQuestionResult(
            questions=valid_questions,
            strategy_summary=data.get("strategy_summary", ""),
            key_objective=data.get("key_objective", ""),
            risk_warning=data.get("risk_warning", ""),
            success=True,
            used_llm=True,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )


# ============================================================================
# Singleton & helpers
# ============================================================================

_generator: Optional[LLMQuestionGenerator] = None


def get_llm_question_generator() -> LLMQuestionGenerator:
    """Get singleton LLM question generator"""
    global _generator
    if _generator is None:
        _generator = LLMQuestionGenerator()
    return _generator


def build_contradiction_context(contradiction) -> Dict[str, Any]:
    """
    Build contradiction context dict from a DetectedContradiction.

    Extracts all relevant fields for the LLM prompt.
    """
    metadata = contradiction.metadata or {}

    ctx = {
        "type": _type_label(contradiction.type),
        "severity": _severity_label(contradiction.severity),
        "confidence": getattr(contradiction, 'confidence', 0.8),
        "quote_a": contradiction.quote1 or "",
        "quote_b": contradiction.quote2 or "",
    }

    # Sources
    if contradiction.claim1.source:
        ctx["source_a"] = contradiction.claim1.source
    if contradiction.claim2.source:
        ctx["source_b"] = contradiction.claim2.source

    # Speakers
    if contradiction.claim1.speaker:
        ctx["speaker_a"] = contradiction.claim1.speaker
    if contradiction.claim2.speaker:
        ctx["speaker_b"] = contradiction.claim2.speaker

    # Type-specific from metadata
    if "date1" in metadata:
        ctx["date_a"] = str(metadata["date1"])
    if "date2" in metadata:
        ctx["date_b"] = str(metadata["date2"])
    if "amount1" in metadata:
        ctx["amount_a"] = str(metadata["amount1"])
    if "amount2" in metadata:
        ctx["amount_b"] = str(metadata["amount2"])
    if "attr1" in metadata:
        ctx["person_a"] = ", ".join(metadata["attr1"]) if isinstance(metadata["attr1"], list) else str(metadata["attr1"])
    if "attr2" in metadata:
        ctx["person_b"] = ", ".join(metadata["attr2"]) if isinstance(metadata["attr2"], list) else str(metadata["attr2"])

    return ctx


def _type_label(ctype) -> str:
    """Hebrew label for contradiction type"""
    labels = {
        "TEMPORAL": "סתירה זמנית",
        "TEMPORAL_DATE": "סתירה בתאריכים",
        "TEMPORAL_SEQUENCE": "סתירה ברצף אירועים",
        "QUANTITATIVE": "סתירה כמותית",
        "QUANT_AMOUNT": "סתירה בסכומים",
        "QUANT_MEASUREMENT": "סתירה במדידות",
        "ATTRIBUTION": "סתירה בייחוס",
        "ACTOR_ATTRIBUTION": "סתירה בייחוס שחקנים",
        "FACTUAL": "סתירה עובדתית",
        "VERSION": "שינוי גרסה",
        "WITNESS": "סתירה בין עדים",
        "DOCUMENT": "סתירה במסמכים",
        "PRESENCE": "סתירת נוכחות",
        "IDENTITY": "סתירת זהות",
        "DOC_EXISTENCE": "סתירת קיום מסמך",
    }
    type_str = str(ctype.value) if hasattr(ctype, 'value') else str(ctype)
    return labels.get(type_str, type_str)


def _severity_label(severity) -> str:
    """Hebrew label for severity"""
    labels = {
        "CRITICAL": "קריטית",
        "HIGH": "גבוהה",
        "MEDIUM": "בינונית",
        "LOW": "נמוכה",
    }
    sev_str = str(severity.value) if hasattr(severity, 'value') else str(severity)
    return labels.get(sev_str, sev_str)
