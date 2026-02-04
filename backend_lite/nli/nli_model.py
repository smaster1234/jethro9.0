"""
NLI Cross-Encoder wrapper with graceful degradation.

If torch / transformers are unavailable the module exposes a no-op
classifier that always returns NEUTRAL — the pipeline continues with
rule-based detection only.

Memory budget: fits comfortably in 7 GB VRAM with batch_size ≤ 16 and
max_length ≤ 512 for a base-size (~280 M params) cross-encoder.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import List, Optional, Dict, Sequence

from .nli_types import NLIPair, NLIResult, NLILabel

logger = logging.getLogger(__name__)

# ── Soft imports ────────────────────────────────────────────────────────────
_HAS_TORCH = False
_HAS_TRANSFORMERS = False

try:
    import torch  # type: ignore
    _HAS_TORCH = True
except Exception:
    logger.info("torch not available — NLI will use fallback mode")

try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification  # type: ignore
    _HAS_TRANSFORMERS = True
except Exception:
    logger.info("transformers not available — NLI will use fallback mode")


# ── Label mapping ───────────────────────────────────────────────────────────
# Most MNLI / XNLI models use index mapping:  0=contradiction, 1=neutral, 2=entailment
# mDeBERTa-v3-base-mnli-xnli uses the same convention.
_DEFAULT_LABEL_MAP: Dict[int, NLILabel] = {
    0: NLILabel.CONTRADICTION,
    1: NLILabel.NEUTRAL,
    2: NLILabel.ENTAILMENT,
}


class NLICrossEncoder:
    """
    Wraps a HuggingFace NLI cross-encoder with:
    - Lazy model loading (first call triggers download)
    - Batch inference with configurable chunk size
    - CPU / CUDA auto-detection
    - Graceful fallback when torch is missing
    """

    def __init__(
        self,
        model_name: str = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
        max_length: int = 512,
        batch_size: int = 16,
        device: Optional[str] = None,
        label_map: Optional[Dict[int, NLILabel]] = None,
    ):
        self.model_name = model_name
        self.max_length = max_length
        self.batch_size = batch_size
        self.label_map = label_map or _DEFAULT_LABEL_MAP
        self._model = None
        self._tokenizer = None
        self._available = _HAS_TORCH and _HAS_TRANSFORMERS

        # Device selection
        if device:
            self._device_str = device
        elif self._available and torch.cuda.is_available():
            self._device_str = "cuda"
        else:
            self._device_str = "cpu"

    # ── lazy loading ────────────────────────────────────────────────────
    def _ensure_loaded(self) -> bool:
        """Load model + tokenizer on first use. Returns True if ready."""
        if not self._available:
            return False
        if self._model is not None:
            return True
        try:
            logger.info("Loading NLI model %s on %s …", self.model_name, self._device_str)
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self._model.to(self._device_str)
            self._model.eval()

            # Detect label mapping from model config if available
            config = self._model.config
            if hasattr(config, "label2id"):
                detected: Dict[int, NLILabel] = {}
                for lbl_name, idx in config.label2id.items():
                    lbl_lower = lbl_name.lower()
                    if "contradict" in lbl_lower:
                        detected[idx] = NLILabel.CONTRADICTION
                    elif "entail" in lbl_lower:
                        detected[idx] = NLILabel.ENTAILMENT
                    else:
                        detected[idx] = NLILabel.NEUTRAL
                if len(detected) == 3:
                    self.label_map = detected
                    logger.info("NLI label map auto-detected: %s", detected)

            logger.info("NLI model loaded successfully (%d params)",
                        sum(p.numel() for p in self._model.parameters()))
            return True
        except Exception as exc:
            logger.warning("Failed to load NLI model: %s — falling back to neutral", exc)
            self._available = False
            return False

    # ── public API ──────────────────────────────────────────────────────
    @property
    def is_available(self) -> bool:
        return self._available

    def predict_batch(self, pairs: Sequence[NLIPair]) -> List[NLIResult]:
        """
        Run NLI inference on a batch of pairs.

        Returns one NLIResult per input pair (same order).
        Falls back to NEUTRAL with score 0.33 if model is unavailable.
        """
        if not pairs:
            return []

        if not self._ensure_loaded():
            return self._fallback_results(pairs)

        results: List[NLIResult] = []
        for chunk_start in range(0, len(pairs), self.batch_size):
            chunk = pairs[chunk_start: chunk_start + self.batch_size]
            chunk_results = self._predict_chunk(chunk)
            results.extend(chunk_results)
        return results

    def predict_single(self, pair: NLIPair) -> NLIResult:
        """Convenience: single-pair prediction."""
        return self.predict_batch([pair])[0]

    # ── internals ───────────────────────────────────────────────────────
    def _predict_chunk(self, chunk: Sequence[NLIPair]) -> List[NLIResult]:
        """Run a single batch through the model."""
        texts_a = [p.text_a for p in chunk]
        texts_b = [p.text_b for p in chunk]

        encoded = self._tokenizer(
            texts_a,
            texts_b,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        ).to(self._device_str)

        with torch.no_grad():
            logits = self._model(**encoded).logits  # (B, 3)
            probs = torch.softmax(logits, dim=-1).cpu().tolist()

        results: List[NLIResult] = []
        for pair, prob_row in zip(chunk, probs):
            scores: Dict[str, float] = {}
            for idx, label in self.label_map.items():
                scores[label.value] = prob_row[idx]

            argmax_idx = prob_row.index(max(prob_row))
            label = self.label_map.get(argmax_idx, NLILabel.NEUTRAL)

            results.append(NLIResult(
                pair_id=pair.pair_id,
                label=label,
                raw_scores=scores,
                contradiction_prob=scores.get("contradiction", 0.0),
                metadata=dict(pair.metadata),
            ))
        return results

    @staticmethod
    def _fallback_results(pairs: Sequence[NLIPair]) -> List[NLIResult]:
        """Return neutral results when model is unavailable."""
        uniform = {"entailment": 0.333, "contradiction": 0.333, "neutral": 0.334}
        return [
            NLIResult(
                pair_id=p.pair_id,
                label=NLILabel.NEUTRAL,
                raw_scores=dict(uniform),
                contradiction_prob=0.333,
                metadata={**p.metadata, "_fallback": True},
            )
            for p in pairs
        ]


# ── singleton ───────────────────────────────────────────────────────────────
_nli_instance: Optional[NLICrossEncoder] = None


def get_nli_classifier(
    model_name: Optional[str] = None,
    max_length: Optional[int] = None,
    batch_size: Optional[int] = None,
) -> NLICrossEncoder:
    """
    Return (or create) the singleton NLI classifier.

    Parameters fall back to config.py defaults when None.
    """
    global _nli_instance
    if _nli_instance is not None:
        return _nli_instance

    # Late import to avoid circular deps
    try:
        from ..config import get_settings
        settings = get_settings()
        _model = model_name or settings.nli_model_name
        _max_len = max_length or settings.nli_max_length
        _batch = batch_size or settings.nli_batch_size
    except Exception:
        _model = model_name or "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
        _max_len = max_length or 512
        _batch = batch_size or 16

    _nli_instance = NLICrossEncoder(
        model_name=_model,
        max_length=_max_len,
        batch_size=_batch,
    )
    return _nli_instance


def reset_nli_classifier() -> None:
    """Reset the singleton (useful for tests)."""
    global _nli_instance
    _nli_instance = None
