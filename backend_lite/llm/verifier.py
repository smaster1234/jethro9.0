"""
Verifier LLM Client (Gemini / Qwen via OpenRouter)
===================================================

Second opinion verifier for contradiction validation.
Uses Gemini (primary) or Qwen via OpenRouter (fallback).

Role:
- Binary decision only (yes/no/unclear)
- Minimal JSON output
- Optimized for Precision (filter false positives)
"""

import os
import json
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

from .openrouter_base import OpenRouterBaseClient
from .gemini_client import GeminiBaseClient
from ..llm_client import parse_json_robust

logger = logging.getLogger(__name__)


# Verifier system prompt — Chain-of-Thought with few-shot examples
VERIFIER_SYSTEM_PROMPT = """אתה שופט אימות לסתירות במסמכים משפטיים בעברית.

## התפקיד שלך
בחן שתי טענות ובצע ניתוח מובנה בשלבים לפני שתגיע למסקנה.

## חוקים קריטיים
1. מספרי תיקים (כגון 17682-06-25, ת"א 12345-01-22) אינם תאריכים — לעולם אל תסווג כסתירה זמנית.
2. אם הטענות מתייחסות לאירועים, נושאים או ישויות שונים — אין סתירה.
3. לעולם אל תמציא עובדות שלא נאמרו בטענות.
4. סתירה אמיתית = אותו נושא, אותה ישות, אותה תקופה — שתי גרסאות שלא יכולות להיות נכונות שתיהן בו-זמנית.
5. "לטענת X" / "נטען כי" / "לגרסת" = טענת צד, לא קביעה עובדתית — אין סתירה אמיתית עם ממצא שיפוטי.
6. אם ניתן למצוא פרשנות סבירה שמיישבת בין שתי הטענות — אין סתירה אמיתית.

## דוגמאות (few-shot)

### דוגמה 1 — TRUE_CONTRADICTION (סתירה אמיתית):
טענה א: "החוזה נחתם ביום 15.3.2020 במשרדי החברה בתל אביב"
טענה ב: "החוזה נחתם ביום 20.5.2021 בנוכחות עורך דין"
ניתוח:
- שלב 1 (מושא): שתי הטענות עוסקות באותו חוזה.
- שלב 2 (מישור): שתיהן קביעות עובדתיות (FACT).
- שלב 3 (זמן): 15.3.2020 לעומת 20.5.2021 — תאריכים שונים לאותו אירוע.
- שלב 4 (ישויות): אותה חברה, אותו חוזה.
- שלב 5 (יישוב): לא ניתן לחתום על אותו חוזה בשני תאריכים שונים.
→ outcome: TRUE_CONTRADICTION, type: temporal, confidence: 0.95

### דוגמה 2 — TRUE_CONTRADICTION (סתירה כמותית):
טענה א: "סכום התמורה בחוזה עמד על 500,000 ש״ח"
טענה ב: "סכום התמורה בחוזה היה 350,000 שקלים בלבד"
ניתוח:
- שלב 1 (מושא): אותה תמורה באותו חוזה.
- שלב 2 (מישור): שתיהן עובדתיות.
- שלב 3 (זמן): אותה תקופה.
- שלב 4 (ישויות): אותו חוזה.
- שלב 5 (יישוב): הסכום לא יכול להיות 500,000 וגם 350,000 בו-זמנית.
→ outcome: TRUE_CONTRADICTION, type: quant, confidence: 0.92

### דוגמה 3 — TRUE_CONTRADICTION (נוכחות):
טענה א: "הנתבע נכח בפגישה ושמע את כל הדברים"
טענה ב: "הנתבע לא נכח בפגישה כלל"
ניתוח:
- שלב 1 (מושא): אותה פגישה.
- שלב 2 (מישור): שתיהן עובדתיות.
- שלב 4 (ישויות): אותו נתבע, אותה פגישה.
- שלב 5 (יישוב): אי אפשר להיות נוכח ולא נוכח בו-זמנית.
→ outcome: TRUE_CONTRADICTION, type: presence, confidence: 0.95

### דוגמה 4 — APPARENT_TENSION_RESOLVABLE (לא סתירה):
טענה א: "התובע דרש פיצוי בסך 500,000 ש״ח"
טענה ב: "הנתבע שילם רק 200,000 ש״ח"
ניתוח:
- שלב 1 (מושא): סכומי כסף שונים.
- שלב 5 (יישוב): דרישה אינה תשלום — ניתן לדרוש 500K ולקבל 200K. אין סתירה.
→ outcome: APPARENT_TENSION_RESOLVABLE, type: none, confidence: 0.85

### דוגמה 5 — DISAGREEMENT_BETWEEN_PARTIES (מחלוקת):
טענה א: "לטענת התובע, החוזה בוטל ללא הודעה מראש"
טענה ב: "לטענת הנתבע, ניתנה הודעה 30 יום מראש כנדרש"
ניתוח:
- שלב 1 (מושא): אותו ביטול חוזה.
- שלב 5 (יישוב): שני צדדים שונים מציגים גרסאות שונות — מחלוקת בין צדדים, לא סתירה פנימית.
→ outcome: DISAGREEMENT_BETWEEN_PARTIES, type: none, confidence: 0.88

### דוגמה 6 — ROLE_OR_ATTRIBUTION_MISMATCH:
טענה א: "בית המשפט קבע כי הנתבע הפר את ההסכם"
טענה ב: "לגרסת הנתבע, ההסכם הופר על ידי התובע"
ניתוח:
- שלב 2 (מישור): ממצא שיפוטי מול טענת צד.
- שלב 5 (יישוב): ייחוסים שונים — ממצא של ביהמ״ש לעומת טענת צד.
→ outcome: ROLE_OR_ATTRIBUTION_MISMATCH, type: none, confidence: 0.82

### דוגמה 7 — TIME_OR_STAGE_SHIFT (לא סתירה):
טענה א: "ההסכם נחתם בינואר 2020"
טענה ב: "ההסכם בוטל באוגוסט 2022"
ניתוח:
- שלב 3 (זמן): אירועים בתקופות שונות (חתימה לעומת ביטול).
- שלב 5 (יישוב): הסכם יכול להיחתם בזמן אחד ולהתבטל בזמן אחר.
→ outcome: TIME_OR_STAGE_SHIFT, type: none, confidence: 0.90

### דוגמה 8 — FALSE_POSITIVE (לא סתירה):
טענה א: "מדובר בתיק אזרחי מספר 17682-06-25 בבית משפט השלום"
טענה ב: "נפתח תיק נוסף במספר 23456-01-24 בעניין אותו סכסוך"
ניתוח:
- שלב 1 (מושא): מספרי תיקים שונים — לא תאריכים.
- שלב 5 (יישוב): שני תיקים שונים באותו סכסוך — אין סתירה.
→ outcome: APPARENT_TENSION_RESOLVABLE, type: none, confidence: 0.90

### דוגמה 9 — DUPLICATE_OR_RESTATEMENT:
טענה א: "ההסכם נחתם ביום 15.1.2024"
טענה ב: "החוזה נחתם ב-15 בינואר 2024"
ניתוח:
- שלב 1 (מושא): אותו אירוע.
- שלב 5 (יישוב): אותו תוכן בניסוח שונה — חזרה, לא סתירה.
→ outcome: DUPLICATE_OR_RESTATEMENT, type: none, confidence: 0.95

### דוגמה 10 — PLANE_MISMATCH:
טענה א: "הנתבע שילם 50,000 ₪ ביום 1.1.2020"
טענה ב: "ייתכן שהתשלום אינו מספיק לכיסוי הנזק"
ניתוח:
- שלב 2 (מישור): עובדה לעומת הערכה/דעה.
- שלב 5 (יישוב): מישורים שונים — לא ניתן להשוות.
→ outcome: PLANE_MISMATCH, type: none, confidence: 0.85

החזר JSON בלבד. בלי הסבר מחוץ ל-JSON."""


VERIFIER_USER_TEMPLATE = """בחן את שתי הטענות לפי 5 שלבים:

שלב 1 — זיהוי מושא: מה המושא של כל טענה? האם עוסקות באותו נושא/אירוע?
שלב 2 — מישור: עובדה/דעה/נורמה? האם באותו מישור?
שלב 3 — זמן: מתי כל טענה? האם באותה תקופה?
שלב 4 — ישויות: מי מעורב? האם אותם אנשים/ארגונים?
שלב 5 — ניסיון יישוב: האם יש פרשנות סבירה שמיישבת?

טענה א: {claim_a}

טענה ב: {claim_b}

סכמה (מחייבת):
{{
  "analysis": {{
    "subject_match": "same|different|partial",
    "plane_a": "fact|opinion|law|procedural",
    "plane_b": "fact|opinion|law|procedural",
    "same_timeframe": true|false|"unknown",
    "shared_entities": ["..."],
    "reconciliation_possible": true|false,
    "reconciliation_explanation": "..."
  }},
  "same_fact": "yes|no|unclear",
  "outcome": "TRUE_CONTRADICTION|APPARENT_TENSION_RESOLVABLE|DISAGREEMENT_BETWEEN_PARTIES|ROLE_OR_ATTRIBUTION_MISMATCH|PLANE_MISMATCH|TIME_OR_STAGE_SHIFT|AMBIGUITY_OR_VAGUENESS|INSUFFICIENT_CONTEXT|DUPLICATE_OR_RESTATEMENT",
  "type": "temporal|quant|presence|actor|document|identity|none",
  "confidence": 0.0-1.0,
  "reason": "בעברית, עד 30 מילים"
}}"""


@dataclass
class VerifierStats:
    """Statistics for verifier calls"""
    calls: int = 0
    promoted: int = 0    # Confirmed contradictions
    rejected: int = 0    # False positives filtered
    unclear: int = 0     # Uncertain results
    total_input_tokens: int = 0
    total_output_tokens: int = 0


@dataclass
class VerifierResult:
    """Result from verifier"""
    same_fact: str = "unclear"      # yes|no|unclear
    contradiction: str = "unclear"  # yes|no|unclear  (legacy compat)
    outcome: str = ""               # 7-category outcome (v2)
    type: str = "none"              # temporal|quant|presence|actor|document|identity|none
    confidence: float = 0.5
    reason: str = ""
    reconciliation_tried: str = ""  # v2: reconciliation attempt summary
    success: bool = True
    error: Optional[str] = None
    raw_response: Optional[Dict] = None


def _detect_verifier_backend() -> str:
    """
    Detect which LLM backend to use for the verifier.

    Priority:
    1. LLM_MODE=gemini + GEMINI_API_KEY -> use Gemini
    2. OPENROUTER_API_KEY set -> use OpenRouter (Qwen)
    3. GEMINI_API_KEY set -> use Gemini
    4. None -> disabled
    """
    llm_mode = os.getenv("LLM_MODE", "none").lower()

    if llm_mode == "gemini" and os.getenv("GEMINI_API_KEY"):
        return "gemini"
    elif llm_mode in ("openrouter", "deepseek") and os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    elif os.getenv("GEMINI_API_KEY"):
        return "gemini"
    elif os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    return "none"


class VerifierLLM:
    """
    Verifier LLM - supports Gemini (primary) and Qwen via OpenRouter (fallback).

    Supports OpenAI (GPT-4o), OpenRouter (Qwen), or any OpenAI-compatible API.
    Provides second opinion on contradiction candidates.
    Optimized for precision - filters false positives.
    """

    # Gemini OpenAI-compatible endpoint (direct, no proxy)
    GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    def __init__(self):
        backend = _detect_verifier_backend()
        self.backend = backend
        enabled_str = os.getenv("VERIFIER_ENABLED", "true").lower()
        max_calls = int(os.getenv("VERIFIER_MAX_CALLS", "30"))
        self.max_calls = max_calls
        self.stats = VerifierStats()

        if enabled_str != "true":
            self.enabled = False
            self.client = None
            self.model = "none"
            logger.info("Verifier disabled via VERIFIER_ENABLED=false")
            return

        if backend == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            self.model = model
            self.enabled = True
            self.client = GeminiBaseClient(
                api_key=api_key,
                model=model,
                timeout=30,
                app_name="JETHRO Verifier"
            )
            logger.info(f"Verifier initialized with Gemini: {model}")

        elif backend == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY")
            model = os.getenv("OPENROUTER_VERIFIER_MODEL", "qwen/qwen-2.5-72b-instruct")
            self.model = model
            self.enabled = True
            self.client = OpenRouterBaseClient(
                api_key=api_key,
                model=model,
                timeout=30,
                app_name="JETHRO Verifier",
                base_url=os.getenv("OPENROUTER_BASE_URL"),
            )
            logger.info(f"Verifier initialized with OpenRouter: {model}")

        else:
            self.model = "none"
            self.enabled = False
            self.client = None
            logger.warning("Verifier disabled: no LLM API key configured")

    async def close(self):
        """Close the client"""
        if self.client:
            await self.client.close()

    def can_verify(self) -> bool:
        """Check if verifier can make more calls"""
        return self.enabled and self.stats.calls < self.max_calls

    def _parse_verifier_response(self, content: str) -> Optional[Dict]:
        """Parse verifier response using robust JSON parser with logging."""
        if not content or not content.strip():
            logger.warning("Verifier response content is empty")
            return None

        data, ok, error = parse_json_robust(content)
        if ok and data is not None:
            return data

        # Log the raw content for debugging (truncated)
        raw_preview = content[:200].replace('\n', '\\n')
        logger.error(
            f"Verifier JSON parse failed: {error} | "
            f"raw_len={len(content)} raw_preview='{raw_preview}'"
        )
        return None

    async def verify(
        self,
        claim_a: str,
        claim_b: str,
        suggested_type: str = "unknown",
        extra_system_context: str = "",
    ) -> VerifierResult:
        """
        Verify if two claims contradict each other.

        Uses Chain-of-Thought prompting with Hebrew few-shot examples.
        The suggested_type parameter is accepted for API compatibility
        but intentionally NOT passed to the LLM to avoid anchoring bias.

        Args:
            claim_a: First claim text
            claim_b: Second claim text
            suggested_type: Ignored (kept for API compat) — prevents anchoring bias
            extra_system_context: Optional extra context (e.g. learned few-shot examples)
                                  appended to the system prompt

        Returns:
            VerifierResult with decision
        """
        if not self.enabled:
            return VerifierResult(
                success=False,
                error="Verifier not enabled"
            )

        if self.stats.calls >= self.max_calls:
            logger.warning(f"Verifier max calls reached ({self.max_calls})")
            return VerifierResult(
                success=False,
                error=f"Max calls reached ({self.max_calls})"
            )

        self.stats.calls += 1

        # Format user prompt — intentionally omit suggested_type to prevent
        # anchoring bias (the LLM should determine the type independently)
        user_prompt = VERIFIER_USER_TEMPLATE.format(
            claim_a=claim_a[:800],  # Increased from 500 to preserve legal context
            claim_b=claim_b[:800],
        )

        # Build system prompt with optional learned few-shot examples
        system_prompt = VERIFIER_SYSTEM_PROMPT
        if extra_system_context:
            system_prompt = system_prompt + "\n\n" + extra_system_context

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # Call LLM — increased max_tokens for Chain-of-Thought analysis field
        result = await self.client.call(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=512
        )

        self.stats.total_input_tokens += result.input_tokens
        self.stats.total_output_tokens += result.output_tokens

        if not result.success:
            return VerifierResult(
                success=False,
                error=result.error
            )

        # Parse JSON response using robust parser
        data = self._parse_verifier_response(result.content)

        # If robust parse failed and content was empty/whitespace, retry once
        if data is None and (not result.content or not result.content.strip()):
            logger.warning(
                f"Verifier got empty content from {self.model}, retrying once"
            )
            retry_result = await self.client.call(
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,  # Slight temperature nudge on retry
                max_tokens=256
            )
            self.stats.total_input_tokens += retry_result.input_tokens
            self.stats.total_output_tokens += retry_result.output_tokens

            if retry_result.success and retry_result.content:
                data = self._parse_verifier_response(retry_result.content)

        if data is None:
            self.stats.unclear += 1
            return VerifierResult(
                success=False,
                error="Failed to parse verifier response"
            )

        # v2: parse outcome field; fall back to legacy contradiction field
        outcome = data.get("outcome", "")
        legacy_contradiction = data.get("contradiction", "unclear")
        # Derive legacy field from outcome for backward compat
        if outcome == "TRUE_CONTRADICTION":
            legacy_contradiction = "yes"
        elif outcome and outcome != "TRUE_CONTRADICTION":
            legacy_contradiction = "no"

        # Extract CoT analysis if present — use reconciliation explanation as extra info
        analysis = data.get("analysis", {})
        reconciliation_tried = data.get("reconciliation_tried", "")
        if isinstance(analysis, dict):
            recon_expl = analysis.get("reconciliation_explanation", "")
            if recon_expl and not reconciliation_tried:
                reconciliation_tried = recon_expl

        verdict = VerifierResult(
            same_fact=data.get("same_fact", "unclear"),
            contradiction=legacy_contradiction,
            outcome=outcome,
            type=data.get("type", "none"),
            confidence=float(data.get("confidence", 0.5)),
            reason=data.get("reason", ""),
            reconciliation_tried=reconciliation_tried,
            success=True,
            raw_response=data,
        )

        # Update stats
        if verdict.outcome == "TRUE_CONTRADICTION" or (
            verdict.contradiction == "yes" and verdict.confidence >= 0.7
        ):
            self.stats.promoted += 1
        elif verdict.contradiction == "no":
            self.stats.rejected += 1
        else:
            self.stats.unclear += 1

        return verdict

    def get_stats(self) -> Dict[str, Any]:
        """Get verifier statistics"""
        return {
            "backend": self.backend,
            "model": self.model,
            "calls": self.stats.calls,
            "promoted": self.stats.promoted,
            "rejected": self.stats.rejected,
            "unclear": self.stats.unclear,
            "remaining_calls": self.max_calls - self.stats.calls,
            "total_input_tokens": self.stats.total_input_tokens,
            "total_output_tokens": self.stats.total_output_tokens
        }

    def reset_stats(self):
        """Reset statistics (for new analysis)"""
        self.stats = VerifierStats()


# Singleton
_verifier: Optional[VerifierLLM] = None


def get_verifier() -> VerifierLLM:
    """Get singleton verifier instance"""
    global _verifier
    if _verifier is None:
        _verifier = VerifierLLM()
    return _verifier
