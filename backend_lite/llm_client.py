"""
LLM Client for Optional Enhancement
===================================

Supports:
- OpenRouter (Claude, GPT, Mistral, etc.)
- Google Gemini

Used for:
- Enhanced contradiction detection (semantic)
- Question refinement

NOT required for basic operation.
"""

import json
import logging
import httpx
import hashlib
import re
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
import asyncio

from .config import get_settings
from .schemas import LLMMode

logger = logging.getLogger(__name__)


# =============================================================================
# Robust JSON Parser
# =============================================================================

def parse_json_robust(content: str) -> Tuple[Optional[Dict], bool, str]:
    """
    Parse JSON content robustly, handling common LLM output issues.

    Handles:
    - Empty content
    - Markdown code blocks (```json...```)
    - Prefix text before JSON
    - Multiple JSON objects (takes largest)
    - Trailing text after JSON

    Args:
        content: Raw content from LLM

    Returns:
        Tuple of (parsed_dict, success, error_message)
    """
    if not content:
        return None, False, "Empty content"

    content = content.strip()

    # Step 1: Remove markdown code blocks
    if "```json" in content:
        start = content.find("```json") + 7
        end = content.find("```", start)
        if end > start:
            content = content[start:end].strip()
    elif "```" in content:
        start = content.find("```") + 3
        end = content.find("```", start)
        if end > start:
            content = content[start:end].strip()

    # Step 2: Try direct parsing
    if content:
        try:
            data = json.loads(content)
            return data, True, ""
        except json.JSONDecodeError:
            pass

    # Step 3: Find largest {...} block
    brace_blocks = []
    depth = 0
    start_idx = None

    for i, char in enumerate(content):
        if char == '{':
            if depth == 0:
                start_idx = i
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0 and start_idx is not None:
                brace_blocks.append(content[start_idx:i + 1])
                start_idx = None

    # Try to parse each block, keep the largest successful one
    for block in sorted(brace_blocks, key=len, reverse=True):
        try:
            data = json.loads(block)
            return data, True, ""
        except json.JSONDecodeError:
            continue

    # Step 4: Clean up common issues and retry
    # Remove common prefixes
    for prefix in ["Here is the JSON:", "Response:", "JSON:"]:
        if content.lower().startswith(prefix.lower()):
            content = content[len(prefix):].strip()

    try:
        data = json.loads(content)
        return data, True, ""
    except json.JSONDecodeError as e:
        return None, False, str(e)


def safe_log_content(content: str, max_chars: int = 120) -> str:
    """
    Create a safe log representation of content.

    Args:
        content: Content to log
        max_chars: Maximum characters to show

    Returns:
        Safe log string with length and hash
    """
    if not content:
        return "(empty)"

    content_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
    preview = content[:max_chars].replace('\n', ' ')

    return f"len={len(content)} hash={content_hash} preview='{preview}...'"


@dataclass
class LLMResponse:
    """Response from LLM"""
    content: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    raw_response: Optional[Dict] = None


class LLMClient:
    """
    Unified LLM client for OpenRouter and Gemini.

    Usage:
        client = LLMClient()
        response = await client.generate("Analyze this text...")
    """

    def __init__(self):
        self.settings = get_settings()
        self._http_client: Optional[httpx.AsyncClient] = None

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

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
        max_tokens: int = 1024,
        temperature: float = 0.3
    ) -> Optional[LLMResponse]:
        """
        Generate response from LLM.

        Args:
            prompt: User prompt
            system_prompt: System prompt (optional)
            json_mode: Request JSON response
            max_tokens: Maximum tokens
            temperature: Sampling temperature

        Returns:
            LLMResponse or None if failed
        """
        mode = self.settings.llm_mode

        if mode == LLMMode.NONE:
            logger.debug("LLM mode is NONE, skipping")
            return None

        try:
            if mode == LLMMode.OPENROUTER:
                return await self._generate_openrouter(
                    prompt, system_prompt, json_mode, max_tokens, temperature
                )
            elif mode == LLMMode.GEMINI:
                return await self._generate_gemini(
                    prompt, system_prompt, json_mode, max_tokens, temperature
                )
            elif mode == LLMMode.DEEPSEEK:
                return await self._generate_deepseek(
                    prompt, system_prompt, json_mode, max_tokens, temperature
                )
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return None

        return None

    async def _generate_openrouter(
        self,
        prompt: str,
        system_prompt: Optional[str],
        json_mode: bool,
        max_tokens: int,
        temperature: float
    ) -> Optional[LLMResponse]:
        """Generate via OpenRouter API"""
        if not self.settings.openrouter_api_key:
            logger.warning("OpenRouter API key not set")
            return None

        client = await self._get_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.settings.openrouter_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://jethro-legal.com",
            "X-Title": "JETHRO Legal Analysis"
        }

        try:
            response = await client.post(
                f"{self.settings.openrouter_base_url}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            # Extract content - may be None or empty for some model responses
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as e:
                logger.error(f"OpenRouter response missing content: {e}, response: {data}")
                return None

            if content is None:
                logger.warning("OpenRouter returned null content")
                content = ""

            usage = data.get("usage", {})

            return LLMResponse(
                content=content,
                model=self.settings.openrouter_model,
                usage={
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0)
                },
                raw_response=data
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter API error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"OpenRouter request failed: {e}")
            return None

    async def _generate_gemini(
        self,
        prompt: str,
        system_prompt: Optional[str],
        json_mode: bool,
        max_tokens: int,
        temperature: float
    ) -> Optional[LLMResponse]:
        """Generate via Google Gemini API"""
        if not self.settings.gemini_api_key:
            logger.warning("Gemini API key not set")
            return None

        client = await self._get_client()

        # Build content
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        payload = {
            "contents": [
                {
                    "parts": [{"text": full_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }

        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.gemini_model}:generateContent"

        try:
            response = await client.post(
                url,
                json=payload,
                params={"key": self.settings.gemini_api_key}
            )
            response.raise_for_status()
            data = response.json()

            # Extract content - may fail for blocked/filtered responses
            try:
                content = data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError) as e:
                logger.error(f"Gemini response missing content: {e}, response: {data}")
                return None

            if content is None:
                logger.warning("Gemini returned null content")
                content = ""

            usage_metadata = data.get("usageMetadata", {})

            return LLMResponse(
                content=content,
                model=self.settings.gemini_model,
                usage={
                    "input_tokens": usage_metadata.get("promptTokenCount", 0),
                    "output_tokens": usage_metadata.get("candidatesTokenCount", 0)
                },
                raw_response=data
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Gemini API error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Gemini request failed: {e}")
            return None

    async def _generate_deepseek(
        self,
        prompt: str,
        system_prompt: Optional[str],
        json_mode: bool,
        max_tokens: int,
        temperature: float
    ) -> Optional[LLMResponse]:
        """
        Generate via DeepSeek API.

        DeepSeek uses OpenAI-compatible API format.
        """
        if not self.settings.deepseek_api_key:
            logger.warning("DeepSeek API key not set")
            return None

        client = await self._get_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.settings.deepseek_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = await client.post(
                f"{self.settings.deepseek_base_url}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            # Extract content
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as e:
                logger.error(f"DeepSeek response missing content: {e}, response: {data}")
                return None

            if content is None:
                logger.warning("DeepSeek returned null content")
                content = ""

            usage = data.get("usage", {})

            return LLMResponse(
                content=content,
                model=self.settings.deepseek_model,
                usage={
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0)
                },
                raw_response=data
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"DeepSeek API error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"DeepSeek request failed: {e}")
            return None


# Singleton
_llm_client: Optional[LLMClient] = None

def get_llm_client() -> LLMClient:
    """Get singleton LLM client"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


async def generate_with_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    json_mode: bool = False
) -> Optional[str]:
    """
    Convenience function for LLM generation.

    Returns content string or None.
    """
    client = get_llm_client()
    response = await client.generate(prompt, system_prompt, json_mode)
    return response.content if response else None


# ============================================================================
# LLM-Enhanced Contradiction Detection
# ============================================================================

CONTRADICTION_SYSTEM_PROMPT = """אתה מומחה בזיהוי סתירות במסמכים משפטיים בעברית.

המשימה שלך: לזהות סתירות פנימיות בין טענות.

סתירה = כשאותו צד/עד אומר דברים שלא יכולים להיות נכונים ביחד.

סוגי סתירות:
- temporal_conflict: תאריכים/זמנים שונים
- quantitative_conflict: סכומים/מספרים שונים
- attribution_conflict: מי עשה/אמר מה
- factual_conflict: עובדות סותרות

החזר JSON בלבד עם המבנה:
{
  "contradictions": [
    {
      "claim1_id": "...",
      "claim2_id": "...",
      "type": "temporal_conflict|quantitative_conflict|attribution_conflict|factual_conflict",
      "severity": "critical|high|medium|low",
      "confidence": 0.0-1.0,
      "explanation": "הסבר קצר בעברית",
      "quote1": "ציטוט רלוונטי מטענה 1",
      "quote2": "ציטוט רלוונטי מטענה 2"
    }
  ]
}

אם אין סתירות, החזר: {"contradictions": []}"""


@dataclass
class LLMDetectionResult:
    """Result from LLM detection with metadata"""
    contradictions: List[Dict[str, Any]]
    parse_ok: bool = True
    empty_response: bool = False
    retried: bool = False


# Retry prompt for JSON correction
RETRY_PROMPT = """Return ONLY valid JSON object with key "contradictions". No prose, no markdown, no explanations.
Example: {"contradictions": []}"""


async def detect_with_llm(
    claims: List[Dict[str, Any]],
    return_metadata: bool = False
) -> Optional[List[Dict[str, Any]]]:
    """
    Detect contradictions using LLM.

    Args:
        claims: List of claim dicts with id and text
        return_metadata: If True, return LLMDetectionResult instead of list

    Returns:
        List of contradiction dicts, LLMDetectionResult if return_metadata=True, or None if LLM unavailable
    """
    if get_settings().llm_mode == LLMMode.NONE:
        return None

    # Format claims for LLM
    claims_text = "\n\n".join([
        f"[{c.get('id', i)}] {c.get('text', '')}"
        for i, c in enumerate(claims, 1)
    ])

    prompt = f"נתח את הטענות הבאות ומצא סתירות:\n\n{claims_text}"

    client = get_llm_client()

    # First attempt
    response = await client.generate(
        prompt=prompt,
        system_prompt=CONTRADICTION_SYSTEM_PROMPT,
        json_mode=True,
        max_tokens=2048,
        temperature=0  # Use 0 for deterministic output
    )

    result = LLMDetectionResult(contradictions=[], parse_ok=True, empty_response=False)

    if not response:
        result.parse_ok = False
        if return_metadata:
            return result
        return None

    content = response.content

    # Check for None or empty content
    if content is None or not content.strip():
        logger.warning("LLM returned empty or null content")
        result.empty_response = True
        result.contradictions = []
        if return_metadata:
            return result
        return []

    # Log safely
    logger.debug(f"LLM response: {safe_log_content(content)}")

    # Use robust parser
    data, parse_ok, error_msg = parse_json_robust(content)

    if parse_ok and data:
        result.contradictions = data.get("contradictions", [])
        result.parse_ok = True
        if return_metadata:
            return result
        return result.contradictions

    # Parse failed - attempt retry with correction prompt
    logger.warning(f"First LLM parse failed: {error_msg}, attempting retry")

    retry_response = await client.generate(
        prompt=RETRY_PROMPT,
        system_prompt=CONTRADICTION_SYSTEM_PROMPT,
        json_mode=True,
        max_tokens=2048,
        temperature=0
    )

    result.retried = True

    if not retry_response or not retry_response.content:
        logger.error("LLM retry returned empty")
        result.parse_ok = False
        if return_metadata:
            return result
        return None

    retry_data, retry_ok, retry_error = parse_json_robust(retry_response.content)

    if retry_ok and retry_data:
        result.contradictions = retry_data.get("contradictions", [])
        result.parse_ok = True
        logger.info("LLM retry successful")
        if return_metadata:
            return result
        return result.contradictions

    # Both attempts failed
    logger.error(f"LLM JSON parse failed after retry: {retry_error}")
    result.parse_ok = False
    if return_metadata:
        return result
    return None
