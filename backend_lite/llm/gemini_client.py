"""
Gemini Base Client
==================

Async HTTP client for Google Gemini API (v1beta).
Supports Gemini 3 (thinking_level) and Gemini 2.5 (thinking_budget).

Privacy: All calls go directly to Google's API — no third-party proxies.
"""

import asyncio
import httpx
import logging
from typing import Optional, Dict, Any, List

from .openrouter_base import LLMCallResult

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [1, 2, 4]
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Valid thinking levels for Gemini 3 models
VALID_THINKING_LEVELS = {"minimal", "low", "medium", "high"}


class GeminiBaseClient:
    """
    Base async client for Google Gemini API.

    Supports:
    - Gemini 3 series: thinking_level parameter (minimal/low/medium/high)
    - Gemini 2.5 series: thinking_budget parameter (0-24576 tokens)
    - Gemini 2.0 series: no thinking support (deprecated March 2026)

    All calls go directly to generativelanguage.googleapis.com.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3-flash-preview",
        timeout: int = 60,
        app_name: str = "JETHRO Legal Analysis",
        thinking_level: Optional[str] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.app_name = app_name
        self.thinking_level = thinking_level
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _is_gemini3(self) -> bool:
        """Check if current model is Gemini 3 series."""
        return "gemini-3" in self.model

    async def call(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict] = None,
        temperature: float = 0,
        max_tokens: int = 2048,
        thinking_level: Optional[str] = None,
    ) -> LLMCallResult:
        """
        Make an API call to Google Gemini with retry and thinking support.

        Args:
            messages: List of message dicts with role and content
            response_format: Optional format spec (e.g., {"type": "json_object"})
            temperature: Sampling temperature (0 = deterministic)
            max_tokens: Maximum response tokens
            thinking_level: Override thinking level for this call
                           (minimal/low/medium/high for Gemini 3)

        Returns:
            LLMCallResult with content or error
        """
        if not self.api_key:
            return LLMCallResult(
                content="",
                model=self.model,
                success=False,
                error="Gemini API key not configured"
            )

        # Convert OpenRouter-style messages to Gemini format
        system_instruction = None
        contents = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_instruction = content
            elif role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": content}]
                })
            elif role == "assistant":
                contents.append({
                    "role": "model",
                    "parts": [{"text": content}]
                })

        # Build payload
        generation_config: Dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }

        # Add thinking config for supported models
        effective_thinking = thinking_level or self.thinking_level
        if effective_thinking and self._is_gemini3():
            if effective_thinking in VALID_THINKING_LEVELS:
                generation_config["thinkingConfig"] = {
                    "thinkingLevel": effective_thinking.upper(),
                }
            else:
                logger.warning(
                    "Invalid thinking_level '%s', ignoring. Valid: %s",
                    effective_thinking, VALID_THINKING_LEVELS,
                )

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }

        # Add system instruction if present
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        # JSON mode
        json_mode = response_format and response_format.get("type") == "json_object"
        if json_mode:
            generation_config["responseMimeType"] = "application/json"

        url = f"{self.BASE_URL}/{self.model}:generateContent"

        last_error: Optional[str] = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                client = await self._get_client()
                response = await client.post(
                    url,
                    json=payload,
                    params={"key": self.api_key}
                )

                # Check for retryable HTTP errors before raising
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_SECONDS[attempt] if attempt < len(RETRY_BACKOFF_SECONDS) else 4
                    logger.warning(
                        "Gemini API returned %d, retrying in %ds (attempt %d/%d)",
                        response.status_code, wait, attempt + 1, MAX_RETRIES
                    )
                    await asyncio.sleep(wait)
                    continue

                response.raise_for_status()
                data = response.json()

                # Extract content — Gemini 3 with thinking may have multiple parts
                try:
                    parts = data["candidates"][0]["content"]["parts"]
                    # Find the text part (skip thought parts if present)
                    content = ""
                    for part in parts:
                        if "text" in part and not part.get("thought"):
                            content = part["text"]
                            break
                    if not content and parts:
                        # Fallback: take the last text part
                        for part in reversed(parts):
                            if "text" in part:
                                content = part["text"]
                                break
                except (KeyError, IndexError) as e:
                    # Check for safety filtering
                    block_reason = data.get("promptFeedback", {}).get("blockReason")
                    if block_reason:
                        logger.error(f"Gemini blocked response: {block_reason}")
                        return LLMCallResult(
                            content="",
                            model=self.model,
                            success=False,
                            error=f"Response blocked: {block_reason}",
                            raw_response=data
                        )
                    logger.error(f"Gemini response missing content: {e}")
                    return LLMCallResult(
                        content="",
                        model=self.model,
                        success=False,
                        error=f"Response missing content: {e}",
                        raw_response=data
                    )

                if content is None:
                    content = ""

                usage = data.get("usageMetadata", {})

                return LLMCallResult(
                    content=content,
                    model=self.model,
                    input_tokens=usage.get("promptTokenCount", 0),
                    output_tokens=usage.get("candidatesTokenCount", 0),
                    raw_response=data,
                    success=True
                )

            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                if e.response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_SECONDS[attempt] if attempt < len(RETRY_BACKOFF_SECONDS) else 4
                    logger.warning(
                        "Gemini API HTTP error %d, retrying in %ds (attempt %d/%d)",
                        e.response.status_code, wait, attempt + 1, MAX_RETRIES
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"Gemini API error: {last_error}")
                return LLMCallResult(
                    content="",
                    model=self.model,
                    success=False,
                    error=last_error
                )

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as e:
                last_error = str(e)
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_SECONDS[attempt] if attempt < len(RETRY_BACKOFF_SECONDS) else 4
                    logger.warning(
                        "Gemini API network error: %s, retrying in %ds (attempt %d/%d)",
                        type(e).__name__, wait, attempt + 1, MAX_RETRIES
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"Gemini request failed after {MAX_RETRIES} retries: {e}")
                return LLMCallResult(
                    content="",
                    model=self.model,
                    success=False,
                    error=last_error
                )

            except Exception as e:
                logger.error(f"Gemini request failed: {e}")
                return LLMCallResult(
                    content="",
                    model=self.model,
                    success=False,
                    error=str(e)
                )

        # Safety fallback
        return LLMCallResult(
            content="",
            model=self.model,
            success=False,
            error=last_error or "Max retries exceeded"
        )
