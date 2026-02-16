"""
LLM Module — Privacy-First (Gemini Only)
=========================================

All LLM calls go directly to Google's Gemini API.
No third-party proxies (OpenRouter, DeepSeek, etc.) are used.

Architecture:
- Analyzer: Proposes contradiction candidates, optimized for recall
- Verifier: Confirms/rejects candidates, optimized for precision

Models:
- Primary: Gemini 3 Flash Preview (with thinking support)
- Fallback: Gemini 2.5 Flash (when primary fails)

Environment Variables:
- GEMINI_API_KEY: API key for Google Gemini (required)
- GEMINI_ANALYZER_MODEL: Analyzer model (default: gemini-3-flash-preview)
- GEMINI_ANALYZER_FALLBACK: Analyzer fallback (default: gemini-2.5-flash)
- GEMINI_ANALYZER_THINKING: Thinking level for analyzer (default: low)
- GEMINI_VERIFIER_MODEL: Verifier model (default: gemini-3-flash-preview)
- GEMINI_VERIFIER_FALLBACK: Verifier fallback (default: gemini-2.5-flash)
- GEMINI_VERIFIER_THINKING: Thinking level for verifier (default: medium)
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
