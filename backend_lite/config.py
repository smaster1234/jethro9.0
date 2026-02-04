"""
Configuration for Contradiction Service
=======================================

Environment variables:
- LLM_MODE: none|openrouter|gemini|deepseek (default: none)
- GEMINI_API_KEY: API key for Gemini (primary)
- GEMINI_MODEL: Model to use (default: gemini-1.5-flash)
- OPENROUTER_API_KEY: API key for OpenRouter (fallback)
- OPENROUTER_MODEL: Model to use (default: anthropic/claude-3-haiku)
- DEEPSEEK_API_KEY: API key for DeepSeek (analyzer)
- DEEPSEEK_MODEL: Model to use (default: deepseek-chat)
- VERIFIER_MODEL: Model for verification via OpenRouter (default: qwen/qwen-2.5-72b-instruct)
- VERIFIER_MAX_CALLS: Max verifier calls per analysis (default: 30)
- RAG_MODE: bm25|hebert|hybrid (default: hybrid)
- HEBERT_MODEL: HuggingFace model name (default: avichr/Legal-heBERT)

NLI / Calibration / Adjudicator settings:
- NLI_ENABLED: Enable NLI cross-encoder (default: true)
- NLI_MODEL_NAME: HuggingFace NLI model (default: MoritzLaurer/mDeBERTa-v3-base-mnli-xnli)
- NLI_BATCH_SIZE: Batch size for NLI inference (default: 16)
- NLI_MAX_LENGTH: Max token length for NLI (default: 512)
- CALIBRATION_ENABLED: Enable temperature scaling calibration (default: true)
- LLM_ADJUDICATOR_ENABLED: Enable LLM gray-zone adjudicator (default: true)
- LLM_ADJUDICATOR_MAX_RATIO: Max % of pairs sent to LLM (default: 0.10)
"""

import os
from typing import Optional, List, Dict
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache

from .schemas import LLMMode


# ── NLI threshold presets ────────────────────────────────────────────────────
NLI_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "strict": {"contradiction": 0.75, "ambiguous": 0.45},
    "balanced": {"contradiction": 0.55, "ambiguous": 0.30},
}


class Settings(BaseSettings):
    """Application settings from environment variables"""

    # LLM Configuration
    llm_mode: LLMMode = LLMMode.NONE

    # OpenAI (GPT-4o)
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"

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
    precision_mode: str = "balanced"  # "balanced" | "strict"

    # ── NLI Cross-Encoder ────────────────────────────────────────────────
    nli_enabled: bool = True
    nli_model_name: str = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
    nli_batch_size: int = 16
    nli_max_length: int = 512

    # ── Calibration (temperature scaling) ────────────────────────────────
    calibration_enabled: bool = True

    # ── LLM Gray-zone Adjudicator ────────────────────────────────────────
    llm_adjudicator_enabled: bool = True
    llm_adjudicator_max_ratio: float = 0.10  # ≤10% of pairs go to LLM

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

    # ── Convenience: NLI thresholds for current precision_mode ───────────
    @property
    def nli_thresholds(self) -> Dict[str, float]:
        """Return NLI thresholds for the active precision_mode."""
        return NLI_THRESHOLDS.get(self.precision_mode, NLI_THRESHOLDS["balanced"])

    def validate_llm_config(self) -> List[str]:
        """Validate LLM configuration, return list of warnings"""
        warnings = []

        if self.llm_mode == LLMMode.OPENAI:
            if not self.openai_api_key:
                warnings.append("LLM_MODE=openai but OPENAI_API_KEY not set")

        elif self.llm_mode == LLMMode.OPENROUTER:
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

        # Check NLI + adjudicator config
        if self.llm_adjudicator_enabled and self.llm_mode == LLMMode.NONE:
            warnings.append("LLM_ADJUDICATOR_ENABLED=true but LLM_MODE=none — adjudicator will be skipped")

        return warnings


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience functions
def get_llm_mode() -> LLMMode:
    """Get current LLM mode"""
    return get_settings().llm_mode


def get_nli_thresholds() -> Dict[str, float]:
    """Get NLI thresholds for current precision_mode."""
    return get_settings().nli_thresholds
