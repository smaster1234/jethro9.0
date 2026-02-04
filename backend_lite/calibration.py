"""
Temperature-scaling calibration for NLI cross-encoder outputs.

Why:
  Raw softmax probabilities from neural networks are often over-confident.
  Temperature scaling learns a single scalar T on a held-out dev set so that
  softmax(logits / T) is well-calibrated (ECE ≤ 0.05).

Usage:
    from backend_lite.calibration import TemperatureCalibrator

    cal = TemperatureCalibrator()
    cal.fit(dev_logits, dev_labels)   # one-time on dev set
    calibrated = cal.calibrate(raw_scores)  # per-pair at inference

Persistence:
    cal.save("calibration.json")
    cal = TemperatureCalibrator.load("calibration.json")
"""
from __future__ import annotations

import json
import math
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Optional: numpy / scipy for fitting
try:
    import numpy as np  # type: ignore
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

try:
    from scipy.optimize import minimize_scalar  # type: ignore
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


class TemperatureCalibrator:
    """
    Post-hoc temperature scaling for 3-class NLI softmax outputs.

    Attributes:
        temperature: learned T (default 1.0 = uncalibrated)
        ece: Expected Calibration Error on the dev set after fitting
        fitted: whether fit() has been called
    """

    def __init__(self, temperature: float = 1.0):
        self.temperature: float = temperature
        self.ece: float = -1.0
        self.fitted: bool = (temperature != 1.0)

    # ── fitting ─────────────────────────────────────────────────────────

    def fit(
        self,
        logits: Sequence[Sequence[float]],
        labels: Sequence[int],
        n_bins: int = 15,
    ) -> float:
        """
        Fit temperature on a dev set.

        Parameters
        ----------
        logits : (N, 3) raw logits from the NLI model **before** softmax.
        labels : (N,) integer ground-truth labels (0=contradiction, 1=neutral, 2=entailment).
        n_bins : number of bins for ECE computation.

        Returns
        -------
        Optimal temperature T.
        """
        if not _HAS_NUMPY or not _HAS_SCIPY:
            logger.warning("numpy/scipy required for calibration fitting — skipping")
            return self.temperature

        logits_arr = np.array(logits, dtype=np.float64)  # (N, 3)
        labels_arr = np.array(labels, dtype=np.int64)    # (N,)

        def nll(t: float) -> float:
            """Negative log-likelihood with temperature T."""
            if t <= 0:
                return 1e9
            scaled = logits_arr / t
            # log-softmax for numerical stability
            log_probs = scaled - np.log(np.exp(scaled).sum(axis=1, keepdims=True))
            return -log_probs[np.arange(len(labels_arr)), labels_arr].mean()

        result = minimize_scalar(nll, bounds=(0.1, 10.0), method="bounded")
        self.temperature = float(result.x)
        self.fitted = True

        # Compute ECE with the optimal T
        self.ece = self._compute_ece(logits_arr, labels_arr, n_bins)
        logger.info("Calibration fitted: T=%.4f  ECE=%.4f", self.temperature, self.ece)
        return self.temperature

    def _compute_ece(
        self,
        logits: "np.ndarray",
        labels: "np.ndarray",
        n_bins: int = 15,
    ) -> float:
        """Expected Calibration Error after temperature scaling."""
        scaled = logits / self.temperature
        exp_s = np.exp(scaled - scaled.max(axis=1, keepdims=True))
        probs = exp_s / exp_s.sum(axis=1, keepdims=True)

        confidences = probs.max(axis=1)
        predictions = probs.argmax(axis=1)
        accuracies = (predictions == labels).astype(float)

        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        for lo, hi in zip(bin_boundaries[:-1], bin_boundaries[1:]):
            mask = (confidences > lo) & (confidences <= hi)
            if mask.sum() == 0:
                continue
            avg_conf = confidences[mask].mean()
            avg_acc = accuracies[mask].mean()
            ece += mask.sum() / len(labels) * abs(avg_acc - avg_conf)
        return float(ece)

    # ── inference ───────────────────────────────────────────────────────

    def calibrate(self, raw_scores: Dict[str, float]) -> Dict[str, float]:
        """
        Apply temperature scaling to a single set of raw softmax scores.

        Parameters
        ----------
        raw_scores : {"entailment": p_e, "contradiction": p_c, "neutral": p_n}
                     These are already softmax probabilities. We invert softmax,
                     divide by T, then re-apply softmax.

        Returns
        -------
        Calibrated probability dict with same keys.
        """
        if self.temperature == 1.0:
            return dict(raw_scores)

        # Invert softmax → log-space, divide by T, re-softmax
        labels = list(raw_scores.keys())
        vals = [max(raw_scores[k], 1e-12) for k in labels]
        log_vals = [math.log(v) for v in vals]

        scaled = [lv / self.temperature for lv in log_vals]
        max_s = max(scaled)
        exp_s = [math.exp(s - max_s) for s in scaled]
        total = sum(exp_s)

        return {k: e / total for k, e in zip(labels, exp_s)}

    def calibrate_batch(
        self, results: List["NLIResult"],
    ) -> List["NLIResult"]:
        """
        Apply calibration to a list of NLIResult objects, setting `.calibrated`.
        """
        for r in results:
            r.calibrated = self.calibrate(r.raw_scores)
            r.contradiction_prob = r.calibrated.get("contradiction", r.contradiction_prob)
        return results

    # ── persistence ─────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Save calibration parameters to JSON."""
        data = {
            "temperature": self.temperature,
            "ece": self.ece,
            "fitted": self.fitted,
        }
        Path(path).write_text(json.dumps(data, indent=2))
        logger.info("Calibration saved to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "TemperatureCalibrator":
        """Load calibration parameters from JSON."""
        data = json.loads(Path(path).read_text())
        cal = cls(temperature=data.get("temperature", 1.0))
        cal.ece = data.get("ece", -1.0)
        cal.fitted = data.get("fitted", False)
        logger.info("Calibration loaded: T=%.4f  ECE=%.4f", cal.temperature, cal.ece)
        return cal

    def report(self) -> Dict[str, float]:
        """Return calibration metrics for the measurement report."""
        return {
            "temperature": self.temperature,
            "ece": self.ece,
            "fitted": 1.0 if self.fitted else 0.0,
        }


# ── singleton ───────────────────────────────────────────────────────────────
_calibrator: Optional[TemperatureCalibrator] = None
_CALIBRATION_PATH = Path(__file__).parent / "fixtures" / "calibration.json"


def get_calibrator() -> TemperatureCalibrator:
    """
    Return the singleton calibrator.

    Loads from disk if a saved calibration file exists; otherwise returns
    an uncalibrated instance (T=1.0).
    """
    global _calibrator
    if _calibrator is not None:
        return _calibrator

    if _CALIBRATION_PATH.exists():
        try:
            _calibrator = TemperatureCalibrator.load(_CALIBRATION_PATH)
            return _calibrator
        except Exception as exc:
            logger.warning("Failed to load calibration from %s: %s", _CALIBRATION_PATH, exc)

    _calibrator = TemperatureCalibrator()
    return _calibrator


def reset_calibrator() -> None:
    """Reset the singleton (useful for tests)."""
    global _calibrator
    _calibrator = None
