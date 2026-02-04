"""
Gemini Base Client
==================

Async HTTP client for Google Gemini API.
Same interface as OpenRouterBaseClient for drop-in replacement.
"""

import os
import httpx
import logging
from typing import Optional, Dict, Any, List

from .openrouter_base import LLMCallResult

logger = logging.getLogger(__name__)


class GeminiBaseClient:
    """
    Base async client for Google Gemini API.

    Provides the same interface as OpenRouterBaseClient
    so analyzer and verifier can use either backend.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
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
        Make an API call to Google Gemini.

        Accepts the same message format as OpenRouter (system/user/assistant roles)
        and converts to Gemini's format.

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
        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }

        # Add system instruction if present
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        # JSON mode
        json_mode = response_format and response_format.get("type") == "json_object"
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        url = f"{self.BASE_URL}/{self.model}:generateContent"

        try:
            client = await self._get_client()
            response = await client.post(
                url,
                json=payload,
                params={"key": self.api_key}
            )
            response.raise_for_status()
            data = response.json()

            # Extract content
            try:
                content = data["candidates"][0]["content"]["parts"][0]["text"]
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
            logger.error(f"Gemini API error: {e.response.status_code} - {e.response.text[:200]}")
            return LLMCallResult(
                content="",
                model=self.model,
                success=False,
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            )
        except Exception as e:
            logger.error(f"Gemini request failed: {e}")
            return LLMCallResult(
                content="",
                model=self.model,
                success=False,
                error=str(e)
            )
