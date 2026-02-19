"""
Claude (Anthropic) Base Client
==============================

Async HTTP client for the Anthropic Messages API.
Supports Claude Sonnet 4.5 for superior Hebrew legal analysis.

Used as primary or fallback LLM for:
- Contradiction analysis (analyzer)
- Contradiction verification (verifier)
- Cross-examination question generation
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
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}

# Default model
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
ANTHROPIC_API_VERSION = "2023-06-01"


class ClaudeBaseClient:
    """
    Base async client for Anthropic's Claude API.

    Supports:
    - Claude Sonnet 4.5 (primary for legal analysis)
    - Extended thinking via extended_thinking parameter
    - System prompts via top-level system parameter
    - JSON mode via prefilled assistant response

    All calls go directly to api.anthropic.com.
    """

    BASE_URL = "https://api.anthropic.com/v1/messages"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout: int = 90,
        app_name: str = "JETHRO Legal Analysis",
        extended_thinking: bool = False,
        thinking_budget: int = 4096,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.app_name = app_name
        self.extended_thinking = extended_thinking
        self.thinking_budget = thinking_budget
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

    async def call(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict] = None,
        temperature: float = 0,
        max_tokens: int = 4096,
        thinking_level: Optional[str] = None,
    ) -> LLMCallResult:
        """
        Make an API call to Anthropic Claude with retry support.

        Args:
            messages: List of message dicts with role and content.
                      'system' role messages are extracted as top-level system param.
            response_format: Optional format spec. {"type": "json_object"} triggers
                           JSON instruction in system prompt.
            temperature: Sampling temperature (0 = deterministic)
            max_tokens: Maximum response tokens
            thinking_level: Unused (kept for API compat with Gemini client)

        Returns:
            LLMCallResult with content or error
        """
        if not self.api_key:
            return LLMCallResult(
                content="",
                model=self.model,
                success=False,
                error="Anthropic API key not configured"
            )

        # Separate system prompt from conversation messages
        system_prompt = None
        conversation = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_prompt = content
            elif role == "user":
                conversation.append({"role": "user", "content": content})
            elif role == "assistant":
                conversation.append({"role": "assistant", "content": content})

        # JSON mode: add instruction to system prompt
        json_mode = response_format and response_format.get("type") == "json_object"
        if json_mode:
            json_instruction = "\n\nIMPORTANT: Return ONLY valid JSON. No prose, no markdown, no explanations outside the JSON."
            if system_prompt:
                system_prompt += json_instruction
            else:
                system_prompt = json_instruction

        # Build payload
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": conversation,
            "max_tokens": max_tokens,
        }

        # temperature 0 is not supported with extended thinking
        if not self.extended_thinking:
            payload["temperature"] = temperature

        if system_prompt:
            payload["system"] = system_prompt

        # Extended thinking support
        if self.extended_thinking:
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            }

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }

        last_error: Optional[str] = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                client = await self._get_client()
                response = await client.post(
                    self.BASE_URL,
                    json=payload,
                    headers=headers,
                )

                # Check for retryable HTTP errors before raising
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_SECONDS[attempt] if attempt < len(RETRY_BACKOFF_SECONDS) else 4
                    logger.warning(
                        "Claude API returned %d, retrying in %ds (attempt %d/%d)",
                        response.status_code, wait, attempt + 1, MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    continue

                response.raise_for_status()
                data = response.json()

                # Extract content from Claude response
                # Claude returns content as array of content blocks
                try:
                    content_blocks = data.get("content", [])
                    content = ""
                    for block in content_blocks:
                        if block.get("type") == "text":
                            content = block.get("text", "")
                            break
                    # If extended thinking, skip thinking blocks
                    if not content:
                        for block in content_blocks:
                            if block.get("type") == "text":
                                content = block.get("text", "")
                                break
                except (KeyError, IndexError, TypeError) as e:
                    logger.error(f"Claude response missing content: {e}")
                    return LLMCallResult(
                        content="",
                        model=self.model,
                        success=False,
                        error=f"Response missing content: {e}",
                        raw_response=data,
                    )

                if content is None:
                    content = ""

                usage = data.get("usage", {})

                return LLMCallResult(
                    content=content,
                    model=self.model,
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    raw_response=data,
                    success=True,
                )

            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                if e.response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_SECONDS[attempt] if attempt < len(RETRY_BACKOFF_SECONDS) else 4
                    logger.warning(
                        "Claude API HTTP error %d, retrying in %ds (attempt %d/%d)",
                        e.response.status_code, wait, attempt + 1, MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"Claude API error: {last_error}")
                return LLMCallResult(
                    content="",
                    model=self.model,
                    success=False,
                    error=last_error,
                )

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as e:
                last_error = str(e)
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_SECONDS[attempt] if attempt < len(RETRY_BACKOFF_SECONDS) else 4
                    logger.warning(
                        "Claude API network error: %s, retrying in %ds (attempt %d/%d)",
                        type(e).__name__, wait, attempt + 1, MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"Claude request failed after {MAX_RETRIES} retries: {e}")
                return LLMCallResult(
                    content="",
                    model=self.model,
                    success=False,
                    error=last_error,
                )

            except Exception as e:
                logger.error(f"Claude request failed: {e}")
                return LLMCallResult(
                    content="",
                    model=self.model,
                    success=False,
                    error=str(e),
                )

        # Safety fallback
        return LLMCallResult(
            content="",
            model=self.model,
            success=False,
            error=last_error or "Max retries exceeded",
        )
