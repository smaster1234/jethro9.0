"""
Configuration for Contradiction Service
=======================================

Multi-LLM support: Gemini (default) or Claude Sonnet (superior legal analysis).
Set LLM_MODE=claude + ANTHROPIC_API_KEY for Claude-powered analysis.

Environment variables:
- LLM_MODE: none|gemini|claude (default: none)
- GEMINI_API_KEY: API key for Google Gemini
- GEMINI_ANALYZER_MODEL: Analyzer model (default: gemini-3-flash-preview)
- GEMINI_ANALYZER_FALLBACK: Analyzer fallback model (default: gemini-2.5-flash)
- GEMINI_ANALYZER_THINKING: Thinking level for analyzer (default: low)
- GEMINI_VERIFIER_MODEL: Verifier model (default: gemini-3-flash-preview)
- GEMINI_VERIFIER_FALLBACK: Verifier fallback model (default: gemini-2.5-flash)
- GEMINI_VERIFIER_THINKING: Thinking level for verifier (default: medium)
- ANTHROPIC_API_KEY: API key for Anthropic Claude
- CLAUDE_ANALYZER_MODEL: Claude analyzer model (default: claude-sonnet-4-5-20250929)
- CLAUDE_VERIFIER_MODEL: Claude verifier model (default: claude-sonnet-4-5-20250929)
- CLAUDE_EXTENDED_THINKING: Enable extended thinking (default: false)
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

    # Claude / Anthropic (superior legal analysis)
    anthropic_api_key: Optional[str] = None
    claude_analyzer_model: str = "claude-sonnet-4-5-20250929"
    claude_verifier_model: str = "claude-sonnet-4-5-20250929"
    claude_extended_thinking: bool = False
    claude_thinking_budget: int = 4096

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

        if self.llm_mode == LLMMode.GEMINI and not self.gemini_api_key:
            warnings.append(
                "LLM_MODE=gemini but GEMINI_API_KEY not set — LLM features will be disabled."
            )

        if self.llm_mode == LLMMode.CLAUDE and not self.anthropic_api_key:
            warnings.append(
                "LLM_MODE=claude but ANTHROPIC_API_KEY not set — LLM features will be disabled."
            )

        if not self.gemini_api_key and not self.anthropic_api_key:
            warnings.append(
                "No LLM API key set — analyzer and verifier will be disabled. "
                "Set GEMINI_API_KEY or ANTHROPIC_API_KEY to enable."
            )

        if self.verifier_enabled and not self.gemini_api_key and not self.anthropic_api_key:
            warnings.append("VERIFIER_ENABLED=true but no LLM API key set")

        return warnings


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience function
def get_llm_mode() -> LLMMode:
    """Get current LLM mode"""
    return get_settings().llm_mode
