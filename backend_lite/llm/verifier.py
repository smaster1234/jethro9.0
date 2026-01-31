"""
Verifier LLM Client (Qwen via OpenRouter)
=========================================

Second opinion verifier for contradiction validation.
Uses Qwen model for high precision verification.

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
from ..llm_client import parse_json_robust

logger = logging.getLogger(__name__)


# Verifier system prompt (v3 – Hebrew, precision-first with 9-category outcome)
VERIFIER_SYSTEM_PROMPT = """אתה שופט אימות לסתירות בטקסטים משפטיים בעברית.

תפקידך: לקבוע את היחס **המדויק** בין שתי טענות.

## כללים קריטיים
1. מספרי תיקים (17682-06-25, ת.א. 12345/20) הם **לא** תאריכים!
2. אל תמציא עובדות — השתמש רק במה שנאמר בטענות.
3. סתירה אמיתית (TRUE_CONTRADICTION) = אותו מושא + אותו מישור + אי-אפשר ששתיהן נכונות.

## מה **אינו** סתירה:
- טענות צדדים שונים ("התובע טען X" מול "הנתבע טען Y") → DISAGREEMENT_BETWEEN_PARTIES
- ציטוט/חוות דעת/הפניה לפסיקה מול ממצא → ROLE_OR_ATTRIBUTION_MISMATCH
- תקופות/שלבים שונים → TIME_OR_STAGE_SHIFT
- עובדה מול הערכה/טיעון משפטי → PLANE_MISMATCH
- ניסוח עמום / מספרים משוערים → AMBIGUITY_OR_VAGUENESS
- חוסר הקשר / שדות חסרים → INSUFFICIENT_CONTEXT
- ניסוח מחדש של אותו רעיון → DUPLICATE_OR_RESTATEMENT
- ניתן ליישוב דרך היקף/תנאי/כימות → APPARENT_TENSION_RESOLVABLE

## דגשים לדיוק:
- בדוק: זמן, כימות, תחולה, מודאליות (חובה/רשות/ייתכן), שלילה.
- "לטענת X" = ציטוט/ייחוס, לא קביעה עובדתית.
- עדיף לפספס מאשר לדווח שגוי. דיוק חשוב מזכרון.

החזר JSON בלבד."""


VERIFIER_USER_TEMPLATE = """סכמה (בדיוק):
{{
  "same_fact": "yes|no|unclear",
  "outcome": "TRUE_CONTRADICTION|APPARENT_TENSION_RESOLVABLE|DISAGREEMENT_BETWEEN_PARTIES|ROLE_OR_ATTRIBUTION_MISMATCH|PLANE_MISMATCH|TIME_OR_STAGE_SHIFT|AMBIGUITY_OR_VAGUENESS|INSUFFICIENT_CONTEXT|DUPLICATE_OR_RESTATEMENT",
  "type": "temporal|quant|presence|actor|document|identity|none",
  "confidence": 0.0-1.0,
  "reason": "הסבר קצר בעברית, עד 30 מילים",
  "reconciliation_tried": "תיאור קצר של ניסיון יישוב"
}}

טענה א: {claim_a}

טענה ב: {claim_b}

סוג מוצע: {suggested_type}

קבע את היחס המדויק בין הטענות."""


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


class VerifierLLM:
    """
    Verifier LLM for contradiction verification.

    Supports OpenAI (GPT-4o), OpenRouter (Qwen), or any OpenAI-compatible API.
    Provides second opinion on contradiction candidates.
    Optimized for precision - filters false positives.
    """

    def __init__(self):
        llm_mode = os.getenv("LLM_MODE", "none").lower()
        enabled_str = os.getenv("VERIFIER_ENABLED", "true").lower()
        max_calls = int(os.getenv("VERIFIER_MAX_CALLS", "30"))

        # Resolve API key, model, and base URL based on LLM_MODE
        if llm_mode == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            model = os.getenv("OPENAI_MODEL", "gpt-4o")
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions"
        else:
            api_key = os.getenv("OPENROUTER_API_KEY")
            model = os.getenv("OPENROUTER_VERIFIER_MODEL", "openai/gpt-4o")
            base_url = None  # Use default OpenRouter URL

        self.enabled = enabled_str == "true" and bool(api_key)
        self.model = model
        self.max_calls = max_calls
        self.stats = VerifierStats()

        if self.enabled:
            self.client = OpenRouterBaseClient(
                api_key=api_key,
                model=model,
                timeout=30,
                app_name="JETHRO Verifier",
                base_url=base_url,
            )
            logger.info(f"Verifier initialized with model: {model} (mode: {llm_mode})")
        else:
            self.client = None
            if not api_key:
                logger.warning(f"Verifier disabled: no API key set for mode '{llm_mode}'")
            else:
                logger.info("Verifier disabled via VERIFIER_ENABLED=false")

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
        suggested_type: str = "unknown"
    ) -> VerifierResult:
        """
        Verify if two claims contradict each other.

        Args:
            claim_a: First claim text
            claim_b: Second claim text
            suggested_type: Suggested contradiction type from analyzer

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

        # Format user prompt
        user_prompt = VERIFIER_USER_TEMPLATE.format(
            claim_a=claim_a[:500],  # Truncate long claims
            claim_b=claim_b[:500],
            suggested_type=suggested_type
        )

        messages = [
            {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        # Call LLM
        result = await self.client.call(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=256
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

        verdict = VerifierResult(
            same_fact=data.get("same_fact", "unclear"),
            contradiction=legacy_contradiction,
            outcome=outcome,
            type=data.get("type", "none"),
            confidence=float(data.get("confidence", 0.5)),
            reason=data.get("reason", ""),
            reconciliation_tried=data.get("reconciliation_tried", ""),
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
