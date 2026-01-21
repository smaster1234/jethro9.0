"""
LLM Module
==========

Provides separate analyzer and verifier LLM clients.

Architecture:
- Analyzer (DeepSeek): Proposes contradiction candidates, optimized for recall
- Verifier (Qwen): Confirms/rejects candidates, optimized for precision

Both use OpenRouter API with different models.

Environment Variables:
- OPENROUTER_API_KEY: Required for both
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
from .analyzer import AnalyzerLLM, AnalyzerResult, AnalyzerStats, get_analyzer
from .verifier import VerifierLLM, VerifierResult, VerifierStats, get_verifier

__all__ = [
    # Base
    "OpenRouterBaseClient",
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
