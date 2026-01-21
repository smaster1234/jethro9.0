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


# Verifier system prompt - strict and focused
VERIFIER_SYSTEM_PROMPT = """You are a verification judge for legal contradictions.

Your job: Determine if two claims contradict each other.

Critical Rules:
1. Case numbers like 17682-06-25 are NOT dates - never flag as temporal contradiction
2. If claims refer to different events/subjects - no contradiction
3. Never invent facts not stated in the claims
4. Contradiction = same subject, two versions that cannot both be true

Return ONLY valid JSON. No explanation outside JSON."""


VERIFIER_USER_TEMPLATE = """Schema (strict):
{{
  "same_fact": "yes|no|unclear",
  "contradiction": "yes|no|unclear",
  "type": "temporal|quant|presence|actor|document|identity|none",
  "confidence": 0.0-1.0,
  "reason": "Hebrew, max 20 words"
}}

Claim A: {claim_a}

Claim B: {claim_b}

Suggested type: {suggested_type}

Are these claims contradictory?"""


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
    contradiction: str = "unclear"  # yes|no|unclear
    type: str = "none"              # temporal|quant|presence|actor|document|identity|none
    confidence: float = 0.5
    reason: str = ""
    success: bool = True
    error: Optional[str] = None
    raw_response: Optional[Dict] = None


class VerifierLLM:
    """
    Verifier LLM using Qwen via OpenRouter.

    Provides second opinion on contradiction candidates.
    Optimized for precision - filters false positives.
    """

    def __init__(self):
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_VERIFIER_MODEL", "qwen/qwen-2.5-72b-instruct")
        enabled_str = os.getenv("VERIFIER_ENABLED", "true").lower()
        max_calls = int(os.getenv("VERIFIER_MAX_CALLS", "30"))

        self.enabled = enabled_str == "true" and bool(api_key)
        self.model = model
        self.max_calls = max_calls
        self.stats = VerifierStats()

        if self.enabled:
            self.client = OpenRouterBaseClient(
                api_key=api_key,
                model=model,
                timeout=30,
                app_name="JETHRO Verifier"
            )
            logger.info(f"Verifier initialized with model: {model}")
        else:
            self.client = None
            if not api_key:
                logger.warning("Verifier disabled: OPENROUTER_API_KEY not set")
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

            verdict = VerifierResult(
                same_fact=data.get("same_fact", "unclear"),
                contradiction=data.get("contradiction", "unclear"),
                type=data.get("type", "none"),
                confidence=float(data.get("confidence", 0.5)),
                reason=data.get("reason", ""),
                success=True,
                raw_response=data
            )

            # Update stats
            if verdict.contradiction == "yes" and verdict.confidence >= 0.7:
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
