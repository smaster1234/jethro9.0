"""
LLM Module — Multi-Backend (Claude / Gemini)
=============================================

Supports Claude Sonnet (via Anthropic API) and Gemini (via Google API).
Set LLM_MODE=claude + ANTHROPIC_API_KEY for Claude-powered analysis.
Set LLM_MODE=gemini + GEMINI_API_KEY for Gemini-powered analysis.

Architecture:
- Analyzer: Proposes contradiction candidates, optimized for recall
- Verifier: Confirms/rejects candidates, optimized for precision

Claude Models:
- Claude Sonnet 4.5 (superior Hebrew legal reasoning)

Gemini Models:
- Primary: Gemini 3 Flash Preview (with thinking support)
- Fallback: Gemini 2.5 Flash (when primary fails)

Environment Variables:
- LLM_MODE: none|gemini|claude (default: none)
- ANTHROPIC_API_KEY: API key for Anthropic Claude
- CLAUDE_ANALYZER_MODEL: Claude analyzer model (default: claude-sonnet-4-5-20250929)
- CLAUDE_VERIFIER_MODEL: Claude verifier model (default: claude-sonnet-4-5-20250929)
- GEMINI_API_KEY: API key for Google Gemini
- GEMINI_ANALYZER_MODEL: Gemini analyzer model (default: gemini-3-flash-preview)
- GEMINI_VERIFIER_MODEL: Gemini verifier model (default: gemini-3-flash-preview)
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
from .claude_client import ClaudeBaseClient
from .analyzer import AnalyzerLLM, AnalyzerResult, AnalyzerStats, get_analyzer
from .verifier import VerifierLLM, VerifierResult, VerifierStats, get_verifier

__all__ = [
    # Base clients
    "OpenRouterBaseClient",
    "GeminiBaseClient",
    "ClaudeBaseClient",
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
