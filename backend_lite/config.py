"""
Configuration for Contradiction Service
=======================================

Environment variables:
- LLM_MODE: none|openrouter|gemini|deepseek (default: none)
- OPENROUTER_API_KEY: API key for OpenRouter
- OPENROUTER_MODEL: Model to use (default: anthropic/claude-3-haiku)
- DEEPSEEK_API_KEY: API key for DeepSeek (analyzer)
- DEEPSEEK_MODEL: Model to use (default: deepseek-chat)
- VERIFIER_MODEL: Model for verification via OpenRouter (default: qwen/qwen-2.5-72b-instruct)
- VERIFIER_MAX_CALLS: Max verifier calls per analysis (default: 30)
- GEMINI_API_KEY: API key for Gemini
- GEMINI_MODEL: Model to use (default: gemini-1.5-flash)
"""

import os
from typing import Optional, List
from pydantic_settings import BaseSettings
from functools import lru_cache

from .schemas import LLMMode


class Settings(BaseSettings):
    """Application settings from environment variables"""

    # LLM Configuration
    llm_mode: LLMMode = LLMMode.NONE

    # OpenRouter (for verifier and general use)
    openrouter_api_key: Optional[str] = None
    openrouter_model: str = "anthropic/claude-3-haiku"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # DeepSeek (primary analyzer)
    deepseek_api_key: Optional[str] = None
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # Verifier (Qwen via OpenRouter)
    verifier_model: str = "qwen/qwen-2.5-72b-instruct"
    verifier_max_calls: int = 30
    verifier_enabled: bool = True

    # Gemini
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-1.5-flash"

    # Detection settings
    detection_confidence_threshold: float = 0.6
    max_claims_per_request: int = 500

    # Database
    db_path: str = "./cases.db"

    # RAG / Retrieval settings
    rag_top_k: int = 8
    rag_mode: str = "bm25"  # bm25 | embeddings (future)

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

        if self.llm_mode == LLMMode.OPENROUTER:
            if not self.openrouter_api_key:
                warnings.append("LLM_MODE=openrouter but OPENROUTER_API_KEY not set")

        elif self.llm_mode == LLMMode.GEMINI:
            if not self.gemini_api_key:
                warnings.append("LLM_MODE=gemini but GEMINI_API_KEY not set")

        elif self.llm_mode == LLMMode.DEEPSEEK:
            if not self.deepseek_api_key:
                warnings.append("LLM_MODE=deepseek but DEEPSEEK_API_KEY not set")

        # Check verifier config
        if self.verifier_enabled and not self.openrouter_api_key:
            warnings.append("VERIFIER_ENABLED=true but OPENROUTER_API_KEY not set (verifier uses OpenRouter)")

        return warnings


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience function
def get_llm_mode() -> LLMMode:
    """Get current LLM mode"""
    return get_settings().llm_mode
