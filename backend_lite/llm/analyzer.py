"""
Analyzer LLM Client (Claude / Gemini)
======================================

Primary analyzer for contradiction detection.
Uses Claude Sonnet (when LLM_MODE=claude) or Gemini (default).

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

from .openrouter_base import LLMCallResult
from .gemini_client import GeminiBaseClient
from .claude_client import ClaudeBaseClient
from ..llm_client import parse_json_robust

logger = logging.getLogger(__name__)


# System prompt for contradiction analysis (v2 – precision-oriented)
ANALYZER_SYSTEM_PROMPT = """אתה מומחה בזיהוי סתירות **אמיתיות** במסמכים משפטיים בעברית.

## הגדרת סתירה אמיתית
זוג טענות A ו-B הוא סתירה אמיתית **רק** אם מתקיימים **כל** התנאים:
1. **אותו מושא** — אותן ישויות/אירוע/סעיף/תקופה/פעולה (לא דמיון מילולי בלבד).
2. **אותו מישור** — עובדה מול עובדה, או נורמה מול נורמה. אל תערבב עובדה עם הערכה/טיעון משפטי.
3. **אי-יכולת יישוב** — תחת כל פרשנות סבירה, לא ייתכן ששתיהן נכונות יחד.

## מה **אינו** סתירה (אל תדווח כסתירה!):
- **מחלוקת בין צדדים** — "התובע טען X" מול "הנתבע טען Y" היא מחלוקת, לא סתירה פנימית.
- **שינוי נסיבות/זמן** — טענה מתקופה א' מול טענה מתקופה ב' אינה סתירה.
- **הבדל בין עובדה לנורמה** — קביעה עובדתית מול פרשנות/הלכה/דעה.
- **פערי ניסוח/עמימות** — "כ-100" מול "כמאה" אינם סתירה.
- **ציטוט** — "לטענת הנתבע, X" אינו ממצא של הכותב.

## חוקים קריטיים:
1. מספרי תיקים (17682-06-25, ת.א. 12345/20) הם **לא** תאריכים!
2. אל תמציא עובדות — ציטוט מדויק בלבד.
3. בדוק: זמן, כימות, תחולה, מודאליות (חובה/רשות/ייתכן), שלילה.

## סוגי סתירות:
- temporal_conflict: תאריכים/מועדים סותרים **לאותו אירוע**
- quantitative_conflict: סכומים/כמויות סותרים **לאותו עניין**
- presence_conflict: היה/לא היה נוכח **באותו אירוע**
- attribution_conflict: ייחוס פעולה סותר **לאותה פעולה**
- factual_conflict: עובדות סותרות אחרות

## החזר JSON בלבד:
{
  "contradictions": [
    {
      "claim1_id": "claim_X",
      "claim2_id": "claim_Y",
      "type": "temporal_conflict|quantitative_conflict|presence_conflict|attribution_conflict|factual_conflict",
      "severity": "critical|high|medium|low",
      "confidence": 0.5-1.0,
      "explanation": "הסבר קצר: מה מתנגש, למה לא ניתן ליישוב",
      "quote1": "ציטוט מדויק מטענה 1",
      "quote2": "ציטוט מדויק מטענה 2",
      "same_subject": true,
      "same_plane": true,
      "reconciliation_tried": "תיאור קצר של ניסיון היישוב שנכשל"
    }
  ]
}

**אם אין סתירה אמיתית, החזר: {"contradictions": []}**
**עדיף לפספס מאשר לדווח שגוי. דיוק חשוב מזכרון.**"""


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


def _detect_llm_backend() -> str:
    """
    Detect which LLM backend to use for the analyzer.

    Priority:
    1. LLM_MODE=claude + ANTHROPIC_API_KEY -> Claude Sonnet
    2. LLM_MODE=gemini + GEMINI_API_KEY -> Gemini
    3. ANTHROPIC_API_KEY set -> Claude (auto-detect)
    4. GEMINI_API_KEY set -> Gemini (auto-detect)
    5. None -> disabled
    """
    llm_mode = os.getenv("LLM_MODE", "").lower()
    if llm_mode == "claude" and os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    if llm_mode == "gemini" and os.getenv("GEMINI_API_KEY"):
        return "gemini"
    # Auto-detect
    if os.getenv("ANTHROPIC_API_KEY") and llm_mode == "claude":
        return "claude"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    return "none"


class AnalyzerLLM:
    """
    Analyzer LLM — Claude Sonnet or Gemini.

    When LLM_MODE=claude:
    - Primary: Claude Sonnet 4.5 (superior Hebrew legal reasoning)
    - Fallback: Gemini 2.5 Flash (if Claude unavailable)

    When LLM_MODE=gemini:
    - Primary: Gemini 3 Flash Preview (with thinking_level=low)
    - Fallback: Gemini 2.5 Flash

    Proposes contradiction candidates with broad detection.
    Optimized for recall — may over-detect, verifier filters.
    """

    # Default models
    GEMINI_PRIMARY = "gemini-3-flash-preview"
    GEMINI_FALLBACK = "gemini-2.5-flash"
    CLAUDE_PRIMARY = "claude-sonnet-4-5-20250929"
    THINKING_LEVEL = "low"

    def __init__(self):
        backend = _detect_llm_backend()
        self.backend = backend
        self.stats = AnalyzerStats()

        if backend == "claude":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            model = os.getenv("CLAUDE_ANALYZER_MODEL", self.CLAUDE_PRIMARY)
            self.model = model
            self.enabled = True
            self.client = ClaudeBaseClient(
                api_key=api_key,
                model=model,
                timeout=90,
                app_name="JETHRO Analyzer",
            )

            # Fallback: Gemini if available, else None
            gemini_key = os.getenv("GEMINI_API_KEY")
            if gemini_key:
                fallback_model = os.getenv("GEMINI_ANALYZER_FALLBACK", self.GEMINI_FALLBACK)
                self.fallback_model = fallback_model
                self.fallback_client = GeminiBaseClient(
                    api_key=gemini_key,
                    model=fallback_model,
                    timeout=60,
                    app_name="JETHRO Analyzer Fallback",
                )
            else:
                self.fallback_model = "none"
                self.fallback_client = None

            logger.info(
                "Analyzer initialized: primary=Claude %s, fallback=%s",
                model, self.fallback_model,
            )

        elif backend == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            model = os.getenv("GEMINI_ANALYZER_MODEL", self.GEMINI_PRIMARY)
            thinking = os.getenv("GEMINI_ANALYZER_THINKING", self.THINKING_LEVEL)
            self.model = model
            self.enabled = True
            self.client = GeminiBaseClient(
                api_key=api_key,
                model=model,
                timeout=60,
                app_name="JETHRO Analyzer",
                thinking_level=thinking,
            )

            # Fallback: Gemini 2.5 Flash (no thinking, faster)
            fallback_model = os.getenv("GEMINI_ANALYZER_FALLBACK", self.GEMINI_FALLBACK)
            self.fallback_model = fallback_model
            self.fallback_client = GeminiBaseClient(
                api_key=api_key,
                model=fallback_model,
                timeout=60,
                app_name="JETHRO Analyzer Fallback",
            )
            logger.info(
                "Analyzer initialized: primary=Gemini %s (thinking=%s), fallback=%s",
                model, thinking, fallback_model,
            )

        else:
            self.model = "none"
            self.fallback_model = "none"
            self.enabled = False
            self.client = None
            self.fallback_client = None
            logger.warning("Analyzer disabled: no LLM API key configured")

    async def close(self):
        """Close primary and fallback clients"""
        if self.client:
            await self.client.close()
        if self.fallback_client:
            await self.fallback_client.close()

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

        # Call primary LLM (Gemini 3 Flash with thinking)
        result = await self.client.call(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=4096,
        )

        # If primary fails, try fallback (Gemini 2.5 Flash)
        if not result.success and self.fallback_client:
            logger.warning(
                "Analyzer primary (%s) failed: %s — trying fallback (%s)",
                self.model, result.error, self.fallback_model,
            )
            result = await self.fallback_client.call(
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=4096,
            )

        if not result.success:
            self.stats.failed += 1
            logger.error(f"Analyzer API call failed ({self.backend}): {result.error}")
            return AnalyzerResult(
                success=False,
                error=result.error
            )

        self.stats.successful += 1
        self.stats.total_input_tokens += result.input_tokens
        self.stats.total_output_tokens += result.output_tokens

        # Log raw response for debugging
        content_preview = result.content[:500] if result.content else 'None'
        logger.info(f"Analyzer response ({self.backend}, {result.output_tokens} tokens): {content_preview}...")

        # Parse JSON response using robust parser
        if not result.content or not result.content.strip():
            logger.warning("Analyzer response content is empty")
            data = {}
        else:
            data, ok, error = parse_json_robust(result.content)
            if not ok or data is None:
                raw_preview = result.content[:200].replace('\n', '\\n')
                logger.error(
                    f"Analyzer JSON parse failed: {error} | "
                    f"raw_len={len(result.content)} raw_preview='{raw_preview}'"
                )
                return AnalyzerResult(
                    success=False,
                    error=f"JSON parse error: {error}",
                    raw_content=result.content
                )

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

    def get_stats(self) -> Dict[str, Any]:
        """Get analyzer statistics"""
        return {
            "backend": self.backend,
            "model": self.model,
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
