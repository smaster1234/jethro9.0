"""
Configuration for Contradiction Service
=======================================

Privacy-first: Only Google Gemini is supported — no third-party proxies.
All LLM data goes directly to generativelanguage.googleapis.com.

Environment variables:
- GEMINI_API_KEY: API key for Google Gemini (required for LLM features)
- GEMINI_ANALYZER_MODEL: Analyzer model (default: gemini-3-flash-preview)
- GEMINI_ANALYZER_FALLBACK: Analyzer fallback model (default: gemini-2.5-flash)
- GEMINI_ANALYZER_THINKING: Thinking level for analyzer (default: low)
- GEMINI_VERIFIER_MODEL: Verifier model (default: gemini-3-flash-preview)
- GEMINI_VERIFIER_FALLBACK: Verifier fallback model (default: gemini-2.5-flash)
- GEMINI_VERIFIER_THINKING: Thinking level for verifier (default: medium)
- VERIFIER_MAX_CALLS: Max verifier calls per analysis (default: 30)
- RAG_MODE: bm25|hebert|hybrid (default: hybrid)
- HEBERT_MODEL: HuggingFace model name (default: avichr/Legal-heBERT)
"""

import os
from typing import Optional, List
from pydantic_settings import BaseSettings
from functools import lru_cache

from .schemas import LLMMode


class Settings(BaseSettings):
    """Application settings from environment variables"""

    # LLM Configuration — Gemini only (privacy-first)
    llm_mode: LLMMode = LLMMode.NONE

    # Gemini (primary and only LLM provider)
    gemini_api_key: Optional[str] = None

    # Analyzer models
    gemini_analyzer_model: str = "gemini-3-flash-preview"
    gemini_analyzer_fallback: str = "gemini-2.5-flash"
    gemini_analyzer_thinking: str = "low"

    # Verifier models
    gemini_verifier_model: str = "gemini-3-flash-preview"
    gemini_verifier_fallback: str = "gemini-2.5-flash"
    gemini_verifier_thinking: str = "medium"

    # Verifier settings
    verifier_max_calls: int = 30
    verifier_enabled: bool = True

    # Legacy compat — kept but unused (all traffic routes to Gemini)
    openai_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None

    # Detection settings
    detection_confidence_threshold: float = 0.6
    max_claims_per_request: int = 500

    # Database
    db_path: str = "./cases.db"

    # RAG / Retrieval settings
    rag_top_k: int = 8
    rag_mode: str = "hybrid"  # bm25 | hebert | hybrid
    hebert_model: str = "avichr/Legal-heBERT"

    # Timeouts (seconds)
    llm_timeout: int = 30
    rule_based_timeout: int = 10

    # Service info
    service_version: str = "1.0.0"

    class Config:
        env_prefix = ""
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"

    def validate_llm_config(self) -> List[str]:
        """Validate LLM configuration, return list of warnings"""
        warnings = []

        if not self.gemini_api_key:
            warnings.append(
                "GEMINI_API_KEY not set — LLM features (analyzer, verifier) will be disabled. "
                "All LLM traffic routes through Google Gemini for privacy."
            )

        if self.verifier_enabled and not self.gemini_api_key:
            warnings.append("VERIFIER_ENABLED=true but GEMINI_API_KEY not set")

        return warnings


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience function
def get_llm_mode() -> LLMMode:
    """Get current LLM mode"""
    return get_settings().llm_mode
