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

logger = logging.getLogger(__name__)


# Verifier system prompt (v2 – precision-first with 9-category outcome)
VERIFIER_SYSTEM_PROMPT = """You are a verification judge for Hebrew legal contradictions.

Your job: determine the PRECISE relationship between two claims.

## Key rules
1. Case numbers (17682-06-25) are NOT dates.
2. Never invent facts; only use what is stated.
3. A TRUE contradiction means: same subject, same plane, irreconcilable.

## What is NOT a contradiction
- Two party claims from different sides → DISAGREEMENT_BETWEEN_PARTIES
- Quote/opinion/law-citation vs finding, or attribution mismatch → ROLE_OR_ATTRIBUTION_MISMATCH
- Different time periods / stages → TIME_OR_STAGE_SHIFT
- Fact vs law/opinion/assessment → PLANE_MISMATCH
- Vague wording / approximate numbers → AMBIGUITY_OR_VAGUENESS
- Missing speaker mode / plane / insufficient context → INSUFFICIENT_CONTEXT
- Rephrasing of the same idea → DUPLICATE_OR_RESTATEMENT
- Resolvable via scope/condition/quantifier → APPARENT_TENSION_RESOLVABLE

Return ONLY valid JSON."""


VERIFIER_USER_TEMPLATE = """Schema (strict):
{{
  "same_fact": "yes|no|unclear",
  "outcome": "TRUE_CONTRADICTION|APPARENT_TENSION_RESOLVABLE|DISAGREEMENT_BETWEEN_PARTIES|ROLE_OR_ATTRIBUTION_MISMATCH|PLANE_MISMATCH|TIME_OR_STAGE_SHIFT|AMBIGUITY_OR_VAGUENESS|INSUFFICIENT_CONTEXT|DUPLICATE_OR_RESTATEMENT",
  "type": "temporal|quant|presence|actor|document|identity|none",
  "confidence": 0.0-1.0,
  "reason": "Hebrew, max 30 words",
  "reconciliation_tried": "short description of reconciliation attempt"
}}

Claim A: {claim_a}

Claim B: {claim_b}

Suggested type: {suggested_type}

Determine the precise relationship."""


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
            model = os.getenv("OPENROUTER_VERIFIER_MODEL", "qwen/qwen-2.5-72b-instruct")
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

        # Parse JSON response
        try:
            data = json.loads(result.content) if result.content else {}

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

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Verifier JSON parse error: {e}")
            self.stats.unclear += 1
            return VerifierResult(
                success=False,
                error=f"JSON parse error: {e}"
            )

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
