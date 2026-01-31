"""
LLM Base Client (OpenAI-compatible)
====================================

Shared async HTTP client for OpenAI-compatible APIs.
Used by both Analyzer and Verifier.
Supports: OpenAI, OpenRouter, DeepSeek, and any OpenAI-compatible endpoint.
Includes automatic retry with exponential backoff for transient errors.
"""

import asyncio
import httpx
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [1, 2, 4]
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass
class LLMCallResult:
    """Result from an LLM API call"""
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw_response: Optional[Dict] = None
    success: bool = True
    error: Optional[str] = None


class OpenRouterBaseClient:
    """
    Base async client for OpenAI-compatible APIs.

    Provides common functionality for all LLM calls via OpenAI-compatible
    endpoints (OpenAI, OpenRouter, DeepSeek, etc.).
    Includes automatic retry with exponential backoff for rate limits and server errors.
    """

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: int = 60,
        app_name: str = "JETHRO Legal Analysis",
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.app_name = app_name
        self.base_url = base_url or self.DEFAULT_BASE_URL
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
        max_tokens: int = 2048
    ) -> LLMCallResult:
        """
        Make an API call with automatic retry and exponential backoff.

        Retries on: 429 (rate limit), 500, 502, 503, 504, and network errors.
        """
        if not self.api_key:
            return LLMCallResult(
                content="",
                model=self.model,
                success=False,
                error="API key not configured"
            )

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://jethro-legal.com",
            "X-Title": self.app_name
        }

        last_error: Optional[str] = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                client = await self._get_client()
                response = await client.post(
                    self.base_url,
                    json=payload,
                    headers=headers
                )

                # Check for retryable HTTP errors before raising
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_SECONDS[attempt] if attempt < len(RETRY_BACKOFF_SECONDS) else 4
                    logger.warning(
                        "LLM API returned %d, retrying in %ds (attempt %d/%d)",
                        response.status_code, wait, attempt + 1, MAX_RETRIES
                    )
                    await asyncio.sleep(wait)
                    continue

                response.raise_for_status()
                data = response.json()

                # Extract content
                try:
                    content = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError) as e:
                    logger.error(f"OpenRouter response missing content: {e}")
                    return LLMCallResult(
                        content="",
                        model=self.model,
                        success=False,
                        error=f"Response missing content: {e}",
                        raw_response=data
                    )

                if content is None:
                    logger.warning(f"OpenRouter returned null content for model {self.model}")
                    content = ""
                elif not content.strip():
                    logger.warning(
                        f"OpenRouter returned empty content for model {self.model} | "
                        f"finish_reason={data.get('choices', [{}])[0].get('finish_reason', 'unknown')}"
                    )

                usage = data.get("usage", {})

                return LLMCallResult(
                    content=content,
                    model=self.model,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    raw_response=data,
                    success=True
                )

            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                if e.response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_SECONDS[attempt] if attempt < len(RETRY_BACKOFF_SECONDS) else 4
                    logger.warning(
                        "LLM API HTTP error %d, retrying in %ds (attempt %d/%d)",
                        e.response.status_code, wait, attempt + 1, MAX_RETRIES
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"OpenRouter API error: {e.response.status_code}")
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
                        "LLM API network error: %s, retrying in %ds (attempt %d/%d)",
                        type(e).__name__, wait, attempt + 1, MAX_RETRIES
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"OpenRouter request failed after {MAX_RETRIES} retries: {e}")
                return LLMCallResult(
                    content="",
                    model=self.model,
                    success=False,
                    error=last_error
                )

            except Exception as e:
                logger.error(f"OpenRouter request failed: {e}")
                return LLMCallResult(
                    content="",
                    model=self.model,
                    success=False,
                    error=str(e)
                )

        # Should not reach here, but safety fallback
        return LLMCallResult(
            content="",
            model=self.model,
            success=False,
            error=last_error or "Max retries exceeded"
        )
