"""
Qwen Verifier - Second Opinion Verification Layer
==================================================

Uses Qwen model (via OpenRouter) to verify contradiction candidates.

This provides a second opinion from a different model family to:
1. Reduce false positives
2. Confirm high-confidence detections
3. Filter out noise

Architecture:
- DeepSeek: Primary analyzer (cost-effective, powerful)
- Qwen: Verifier (different model family, high precision)

Usage:
    verifier = QwenVerifier()
    result = await verifier.verify(claim1, claim2, candidate_type)
"""

import json
import logging
import httpx
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

from .config import get_settings
from .schemas import ContradictionType, ContradictionStatus, Severity
from .llm_client import parse_json_robust, safe_log_content

logger = logging.getLogger(__name__)


@dataclass
class VerifierResult:
    """Result from verifier"""
    same_fact: str  # "yes" | "no" | "unclear"
    contradiction: str  # "yes" | "no" | "unclear"
    type: str  # contradiction type or "none"
    confidence: float  # 0.0-1.0
    reason: str  # Hebrew explanation (<=20 words)
    raw_response: Optional[Dict] = None


@dataclass
class VerifierStats:
    """Statistics from verifier runs"""
    calls: int = 0
    promoted: int = 0  # Contradictions confirmed
    rejected: int = 0  # False positives filtered
    unclear: int = 0   # Uncertain results


# Verifier system prompt - designed to be precise
VERIFIER_SYSTEM_PROMPT = """אתה מאמת סתירות במסמכים משפטיים.

תפקידך: לקבוע אם שתי טענות סותרות זו את זו.

חוקים קריטיים:
1. מספרי תיקים (כמו 17682-06-25) הם לא תאריכים
2. אם הטענות מתייחסות לאירועים/נושאים שונים - אין סתירה
3. אל תמציא עובדות שלא כתובות
4. סתירה = אותו עניין, שתי גרסאות שלא יכולות להיות נכונות ביחד

החזר JSON בלבד:
{
  "same_fact": "yes|no|unclear",
  "contradiction": "yes|no|unclear",
  "type": "temporal|quant|presence|actor|document|identity|none",
  "confidence": 0.0-1.0,
  "reason": "הסבר קצר בעברית (עד 20 מילים)"
}"""


class QwenVerifier:
    """
    Verifier using Qwen model via OpenRouter.

    Provides second opinion on contradiction candidates to:
    - Confirm high-confidence detections
    - Filter out false positives
    - Handle edge cases

    Uses different model family from analyzer for true second opinion.
    """

    def __init__(self):
        self.settings = get_settings()
        self._http_client: Optional[httpx.AsyncClient] = None
        self.stats = VerifierStats()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.settings.llm_timeout)
        return self._http_client

    async def close(self):
        """Close HTTP client"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def verify(
        self,
        claim1_text: str,
        claim2_text: str,
        candidate_type: str,
        context: Optional[str] = None
    ) -> Optional[VerifierResult]:
        """
        Verify a contradiction candidate.

        Args:
            claim1_text: First claim text
            claim2_text: Second claim text
            candidate_type: Suggested contradiction type
            context: Optional additional context

        Returns:
            VerifierResult or None if verification failed
        """
        if not self.settings.openrouter_api_key:
            logger.warning("Verifier called but OPENROUTER_API_KEY not set")
            return None

        if self.stats.calls >= self.settings.verifier_max_calls:
            logger.warning(f"Verifier max calls reached ({self.settings.verifier_max_calls})")
            return None

        self.stats.calls += 1

        # Build verification prompt
        prompt = f"""בדוק אם יש סתירה בין שתי הטענות הבאות:

טענה 1: {claim1_text[:300]}

טענה 2: {claim2_text[:300]}

סוג סתירה מוצע: {candidate_type}
{f"הקשר נוסף: {context}" if context else ""}

האם הטענות סותרות?"""

        try:
            client = await self._get_client()

            payload = {
                "model": self.settings.verifier_model,
                "messages": [
                    {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 512,
                "temperature": 0,
                "response_format": {"type": "json_object"}
            }

            headers = {
                "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://contradiction-service.local",
                "X-Title": "Contradiction Verifier"
            }

            response = await client.post(
                f"{self.settings.openrouter_base_url}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            # Extract content
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as e:
                logger.error(f"Verifier response missing content: {e}")
                return None

            if not content:
                logger.warning("Verifier returned empty content")
                return None

            logger.debug(f"Verifier response: {safe_log_content(content)}")

            # Parse response
            parsed, ok, error = parse_json_robust(content)
            if not ok or not parsed:
                logger.error(f"Verifier JSON parse failed: {error}")
                return None

            result = VerifierResult(
                same_fact=parsed.get("same_fact", "unclear"),
                contradiction=parsed.get("contradiction", "unclear"),
                type=parsed.get("type", "none"),
                confidence=float(parsed.get("confidence", 0.5)),
                reason=parsed.get("reason", ""),
                raw_response=parsed
            )

            # Update stats
            if result.contradiction == "yes" and result.confidence >= 0.7:
                self.stats.promoted += 1
            elif result.contradiction == "no":
                self.stats.rejected += 1
            else:
                self.stats.unclear += 1

            return result

        except httpx.HTTPError as e:
            logger.error(f"Verifier HTTP error: {e}")
            return None
        except Exception as e:
            logger.error(f"Verifier error: {e}")
            return None

    def should_verify(
        self,
        status: ContradictionStatus,
        confidence: float
    ) -> bool:
        """
        Determine if a candidate should be verified.

        Rules:
        - Don't verify deterministically verified contradictions
        - Verify suspicious/likely with moderate confidence
        - Skip very low confidence (likely noise)

        Args:
            status: Current contradiction status
            confidence: Current confidence score

        Returns:
            True if should call verifier
        """
        # Don't verify if we've hit the limit
        if self.stats.calls >= self.settings.verifier_max_calls:
            return False

        # Don't verify deterministically verified
        if status == ContradictionStatus.VERIFIED:
            return False

        # Skip very low confidence (likely noise)
        if confidence < 0.3:
            return False

        # Verify likely and suspicious
        return status in (ContradictionStatus.LIKELY, ContradictionStatus.SUSPICIOUS)

    def map_result_to_status(
        self,
        result: VerifierResult,
        current_status: ContradictionStatus
    ) -> Tuple[ContradictionStatus, bool]:
        """
        Map verifier result to contradiction status.

        Args:
            result: Verifier result
            current_status: Current status before verification

        Returns:
            Tuple of (new_status, should_keep)
        """
        # If verifier says "no contradiction" - filter out
        if result.contradiction == "no":
            return current_status, False

        # If verifier confirms with high confidence
        if result.contradiction == "yes" and result.confidence >= 0.7:
            # If same_fact is also yes/unclear, promote to LIKELY
            if result.same_fact != "no":
                return ContradictionStatus.LIKELY, True

        # If unclear - keep as suspicious
        if result.contradiction == "unclear":
            return ContradictionStatus.SUSPICIOUS, True

        # Keep with current status
        return current_status, True


# Singleton
_verifier: Optional[QwenVerifier] = None


def get_verifier() -> QwenVerifier:
    """Get singleton verifier instance"""
    global _verifier
    if _verifier is None:
        _verifier = QwenVerifier()
    return _verifier


async def verify_contradiction(
    claim1_text: str,
    claim2_text: str,
    candidate_type: str,
    context: Optional[str] = None
) -> Optional[VerifierResult]:
    """
    Convenience function to verify a contradiction.

    Args:
        claim1_text: First claim text
        claim2_text: Second claim text
        candidate_type: Suggested contradiction type
        context: Optional additional context

    Returns:
        VerifierResult or None if verification failed
    """
    verifier = get_verifier()
    return await verifier.verify(claim1_text, claim2_text, candidate_type, context)
