"""
OpenRouter Base Client
======================

Shared async HTTP client for OpenRouter API.
Used by both Analyzer and Verifier.
"""

import httpx
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
    Base async client for OpenRouter API.

    Provides common functionality for all OpenRouter-based LLM calls.
    """

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: int = 60,
        app_name: str = "JETHRO Legal Analysis"
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.app_name = app_name
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
        Make an API call to OpenRouter.

        Args:
            messages: List of message dicts with role and content
            response_format: Optional format spec (e.g., {"type": "json_object"})
            temperature: Sampling temperature (0 = deterministic)
            max_tokens: Maximum response tokens

        Returns:
            LLMCallResult with content or error
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

        try:
            client = await self._get_client()
            response = await client.post(
                self.BASE_URL,
                json=payload,
                headers=headers
            )
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
                content = ""

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
            logger.error(f"OpenRouter API error: {e.response.status_code}")
            return LLMCallResult(
                content="",
                model=self.model,
                success=False,
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            )
        except Exception as e:
            logger.error(f"OpenRouter request failed: {e}")
            return LLMCallResult(
                content="",
                model=self.model,
                success=False,
                error=str(e)
            )
