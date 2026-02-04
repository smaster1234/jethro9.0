"""
LLM Module
==========

Provides separate analyzer and verifier LLM clients.

Architecture:
- Analyzer: Proposes contradiction candidates, optimized for recall
- Verifier: Confirms/rejects candidates, optimized for precision

Supports multiple backends:
- Gemini (primary): Google Gemini API
- OpenRouter (fallback): DeepSeek analyzer + Qwen verifier

Environment Variables:
- LLM_MODE: none|gemini|openrouter|deepseek (default: none)
- GEMINI_API_KEY: API key for Google Gemini (primary)
- GEMINI_MODEL: Gemini model (default: gemini-1.5-flash)
- OPENROUTER_API_KEY: API key for OpenRouter (fallback)
- OPENROUTER_ANALYZER_MODEL: Analyzer model (default: deepseek/deepseek-chat)
- OPENROUTER_VERIFIER_MODEL: Verifier model (default: qwen/qwen-2.5-72b-instruct)
- VERIFIER_ENABLED: Enable verifier (default: true)
- VERIFIER_MAX_CALLS: Max verifier calls per analysis (default: 30)

Usage:
    from backend_lite.llm import get_analyzer, get_verifier

    analyzer = get_analyzer()
    result = await analyzer.analyze(claims)

    verifier = get_verifier()
    if verifier.can_verify():
        verdict = await verifier.verify(claim_a, claim_b)
"""

from .openrouter_base import OpenRouterBaseClient, LLMCallResult
from .gemini_client import GeminiBaseClient
from .analyzer import AnalyzerLLM, AnalyzerResult, AnalyzerStats, get_analyzer
from .verifier import VerifierLLM, VerifierResult, VerifierStats, get_verifier

__all__ = [
    # Base clients
    "OpenRouterBaseClient",
    "GeminiBaseClient",
    "LLMCallResult",
    # Analyzer
    "AnalyzerLLM",
    "AnalyzerResult",
    "AnalyzerStats",
    "get_analyzer",
    # Verifier
    "VerifierLLM",
    "VerifierResult",
    "VerifierStats",
    "get_verifier",
]
