"""
Analyzer LLM Client (DeepSeek via OpenRouter)
=============================================

Primary analyzer for contradiction detection.
Uses DeepSeek model for cost-effective analysis.

Role:
- Propose contradiction candidates
- Broad JSON output
- Optimized for Recall (may over-detect)
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from .openrouter_base import OpenRouterBaseClient, LLMCallResult

logger = logging.getLogger(__name__)


# System prompt for contradiction analysis
ANALYZER_SYSTEM_PROMPT = """אתה מומחה בזיהוי סתירות במסמכים משפטיים בעברית.

המשימה שלך: למצוא את כל הסתירות האפשריות בין הטענות.

סתירה מתרחשת כאשר:
1. שתי טענות מתייחסות לאותו אירוע/עניין
2. הן מכילות מידע שלא יכול להיות נכון בו-זמנית
3. זה כולל גם סתירות פנימיות (אותו צד) וגם מחלוקות בין צדדים שונים

חוקים קריטיים:
1. מספרי תיקים (כמו 17682-06-25 או ת.א. 12345/20) הם לא תאריכים!
2. אל תמציא עובדות שלא כתובות בטענות
3. חפש תאריכים, סכומים, מספרים, שמות, מיקומים שונים

סוגי סתירות למצוא:
- temporal_conflict: תאריכים/זמנים/מועדים שונים לאותו אירוע
- quantitative_conflict: סכומים/כמויות/אחוזים שונים
- presence_conflict: היה/לא היה נוכח במקום או אירוע
- attribution_conflict: מי עשה/אמר/חתם על מה
- factual_conflict: עובדות סותרות אחרות

היה אגרסיבי - עדיף לזהות יותר מדי מאשר לפספס. הverifier יסנן.

החזר JSON בלבד:
{
  "contradictions": [
    {
      "claim1_id": "claim_X",
      "claim2_id": "claim_Y",
      "type": "temporal_conflict|quantitative_conflict|presence_conflict|attribution_conflict|factual_conflict",
      "severity": "critical|high|medium|low",
      "confidence": 0.5-1.0,
      "explanation": "הסבר קצר בעברית מה בדיוק סותר",
      "quote1": "הציטוט הרלוונטי מטענה 1",
      "quote2": "הציטוט הרלוונטי מטענה 2"
    }
  ]
}

אם באמת אין שום סתירה, החזר: {"contradictions": []}"""


@dataclass
class AnalyzerStats:
    """Statistics for analyzer calls"""
    calls: int = 0
    successful: int = 0
    failed: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    contradictions_found: int = 0


@dataclass
class AnalyzerResult:
    """Result from analyzer"""
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
    raw_content: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0


class AnalyzerLLM:
    """
    Analyzer LLM using DeepSeek via OpenRouter.

    Proposes contradiction candidates with broad detection.
    Optimized for recall - may over-detect, verifier filters.
    """

    def __init__(self):
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_ANALYZER_MODEL", "deepseek/deepseek-chat")

        self.enabled = bool(api_key)
        self.model = model
        self.stats = AnalyzerStats()

        if self.enabled:
            self.client = OpenRouterBaseClient(
                api_key=api_key,
                model=model,
                timeout=60,
                app_name="JETHRO Analyzer"
            )
            logger.info(f"Analyzer initialized with model: {model}")
        else:
            self.client = None
            logger.warning("Analyzer disabled: OPENROUTER_API_KEY not set")

    async def close(self):
        """Close the client"""
        if self.client:
            await self.client.close()

    async def analyze(
        self,
        claims: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> AnalyzerResult:
        """
        Analyze claims for contradictions.

        Args:
            claims: List of claim dicts with id and text
            system_prompt: Optional custom system prompt

        Returns:
            AnalyzerResult with contradictions list
        """
        if not self.enabled:
            return AnalyzerResult(
                success=False,
                error="Analyzer not enabled"
            )

        self.stats.calls += 1

        # Format claims for LLM
        claims_text = "\n\n".join([
            f"[{c.get('id', i)}] {c.get('text', '')}"
            for i, c in enumerate(claims, 1)
        ])

        user_prompt = f"נתח את הטענות הבאות ומצא סתירות:\n\n{claims_text}"

        messages = [
            {"role": "system", "content": system_prompt or ANALYZER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        # Call LLM
        result = await self.client.call(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=4096
        )

        if not result.success:
            self.stats.failed += 1
            logger.error(f"Analyzer API call failed: {result.error}")
            return AnalyzerResult(
                success=False,
                error=result.error
            )

        self.stats.successful += 1
        self.stats.total_input_tokens += result.input_tokens
        self.stats.total_output_tokens += result.output_tokens

        # Log raw response for debugging
        content_preview = result.content[:500] if result.content else 'None'
        logger.info(f"Analyzer response ({result.output_tokens} tokens): {content_preview}...")

        # Parse JSON response
        try:
            data = json.loads(result.content) if result.content else {}
            contradictions = data.get("contradictions", [])
            self.stats.contradictions_found += len(contradictions)

            logger.info(f"Analyzer found {len(contradictions)} contradictions")
            for c in contradictions[:3]:  # Log first 3
                logger.info(f"  - {c.get('claim1_id')} vs {c.get('claim2_id')}: {c.get('type')} (conf={c.get('confidence', 0):.2f})")

            return AnalyzerResult(
                contradictions=contradictions,
                success=True,
                raw_content=result.content,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens
            )
        except json.JSONDecodeError as e:
            logger.error(f"Analyzer JSON parse error: {e}")
            return AnalyzerResult(
                success=False,
                error=f"JSON parse error: {e}",
                raw_content=result.content
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get analyzer statistics"""
        return {
            "calls": self.stats.calls,
            "successful": self.stats.successful,
            "failed": self.stats.failed,
            "total_input_tokens": self.stats.total_input_tokens,
            "total_output_tokens": self.stats.total_output_tokens,
            "contradictions_found": self.stats.contradictions_found
        }


# Singleton
_analyzer: Optional[AnalyzerLLM] = None


def get_analyzer() -> AnalyzerLLM:
    """Get singleton analyzer instance"""
    global _analyzer
    if _analyzer is None:
        _analyzer = AnalyzerLLM()
    return _analyzer
