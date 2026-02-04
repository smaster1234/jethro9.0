"""
NLI Cross-Encoder module for semantic contradiction detection.

Architecture:
- nli_types: Dataclasses for NLI input/output (NLIPair, NLIResult)
- nli_model: Cross-encoder wrapper with graceful degradation
- nli_batcher: Batch inference with memory-safe chunking (7 GB VRAM)

Usage:
    from backend_lite.nli import get_nli_classifier, NLIPair

    classifier = get_nli_classifier()
    results = classifier.predict_batch([
        NLIPair(text_a="...", text_b="...", pair_id="p1"),
    ])
"""
from .nli_types import NLIPair, NLIResult, NLILabel
from .nli_model import NLICrossEncoder, get_nli_classifier

__all__ = [
    "NLIPair",
    "NLIResult",
    "NLILabel",
    "NLICrossEncoder",
    "get_nli_classifier",
]
