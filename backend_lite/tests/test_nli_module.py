"""
Tests for NLI module (Part 2), Calibration (Part 3), and Adjudicator (Part 4).

Verifies:
- NLI types and dataclasses
- NLI model fallback when torch unavailable
- Calibration temperature scaling math
- Batcher threshold logic
- Dataset exporter output format
"""
import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# =============================================================================
# NLI Types
# =============================================================================

class TestNLITypes:
    def test_nli_pair_creation(self):
        from backend_lite.nli.nli_types import NLIPair
        p = NLIPair(text_a="טענה א", text_b="טענה ב", pair_id="p1")
        assert p.text_a == "טענה א"
        assert p.text_b == "טענה ב"
        assert p.pair_id == "p1"

    def test_nli_pair_immutable(self):
        from backend_lite.nli.nli_types import NLIPair
        p = NLIPair(text_a="a", text_b="b", pair_id="p1")
        with pytest.raises(AttributeError):
            p.text_a = "changed"

    def test_nli_result_properties(self):
        from backend_lite.nli.nli_types import NLIResult, NLILabel
        r = NLIResult(
            pair_id="p1",
            label=NLILabel.CONTRADICTION,
            raw_scores={"entailment": 0.1, "contradiction": 0.8, "neutral": 0.1},
            contradiction_prob=0.8,
            decision="contradiction",
        )
        assert r.is_contradiction
        assert not r.is_ambiguous

    def test_nli_result_ambiguous(self):
        from backend_lite.nli.nli_types import NLIResult, NLILabel
        r = NLIResult(
            pair_id="p1",
            label=NLILabel.NEUTRAL,
            raw_scores={"entailment": 0.2, "contradiction": 0.4, "neutral": 0.4},
            contradiction_prob=0.4,
            decision="ambiguous",
        )
        assert r.is_ambiguous
        assert not r.is_contradiction

    def test_nli_label_values(self):
        from backend_lite.nli.nli_types import NLILabel
        assert NLILabel.ENTAILMENT.value == "entailment"
        assert NLILabel.CONTRADICTION.value == "contradiction"
        assert NLILabel.NEUTRAL.value == "neutral"


# =============================================================================
# NLI Model (fallback mode — torch not loadable in this env)
# =============================================================================

class TestNLIModelFallback:
    def test_singleton_creation(self):
        from backend_lite.nli.nli_model import get_nli_classifier, reset_nli_classifier
        reset_nli_classifier()
        clf = get_nli_classifier()
        assert clf is not None

    def test_predict_batch_empty(self):
        from backend_lite.nli.nli_model import get_nli_classifier, reset_nli_classifier
        reset_nli_classifier()
        clf = get_nli_classifier()
        results = clf.predict_batch([])
        assert results == []

    def test_fallback_returns_neutral(self):
        """When torch is unavailable, fallback returns neutral with ~0.33 scores."""
        from backend_lite.nli.nli_model import NLICrossEncoder
        from backend_lite.nli.nli_types import NLIPair, NLILabel

        clf = NLICrossEncoder(model_name="fake_model")
        clf._available = False  # Force fallback

        pairs = [NLIPair(text_a="a", text_b="b", pair_id="p1")]
        results = clf.predict_batch(pairs)
        assert len(results) == 1
        assert results[0].label == NLILabel.NEUTRAL
        assert abs(results[0].contradiction_prob - 0.333) < 0.01
        assert results[0].metadata.get("_fallback") is True

    def test_fallback_multiple_pairs(self):
        from backend_lite.nli.nli_model import NLICrossEncoder
        from backend_lite.nli.nli_types import NLIPair

        clf = NLICrossEncoder()
        clf._available = False

        pairs = [
            NLIPair(text_a=f"a{i}", text_b=f"b{i}", pair_id=f"p{i}")
            for i in range(10)
        ]
        results = clf.predict_batch(pairs)
        assert len(results) == 10
        for i, r in enumerate(results):
            assert r.pair_id == f"p{i}"


# =============================================================================
# NLI Batcher — threshold logic
# =============================================================================

class TestNLIBatcher:
    def test_apply_thresholds_contradiction(self):
        from backend_lite.nli.nli_batcher import apply_thresholds
        from backend_lite.nli.nli_types import NLIResult, NLILabel

        results = [NLIResult(
            pair_id="p1",
            label=NLILabel.CONTRADICTION,
            raw_scores={"entailment": 0.05, "contradiction": 0.85, "neutral": 0.10},
            contradiction_prob=0.85,
        )]
        thresholds = {"contradiction": 0.75, "ambiguous": 0.45}
        apply_thresholds(results, thresholds)
        assert results[0].decision == "contradiction"

    def test_apply_thresholds_ambiguous(self):
        from backend_lite.nli.nli_batcher import apply_thresholds
        from backend_lite.nli.nli_types import NLIResult, NLILabel

        results = [NLIResult(
            pair_id="p1",
            label=NLILabel.NEUTRAL,
            raw_scores={"entailment": 0.2, "contradiction": 0.50, "neutral": 0.30},
            contradiction_prob=0.50,
        )]
        thresholds = {"contradiction": 0.75, "ambiguous": 0.45}
        apply_thresholds(results, thresholds)
        assert results[0].decision == "ambiguous"

    def test_apply_thresholds_not_contradiction(self):
        from backend_lite.nli.nli_batcher import apply_thresholds
        from backend_lite.nli.nli_types import NLIResult, NLILabel

        results = [NLIResult(
            pair_id="p1",
            label=NLILabel.ENTAILMENT,
            raw_scores={"entailment": 0.70, "contradiction": 0.15, "neutral": 0.15},
            contradiction_prob=0.15,
        )]
        thresholds = {"contradiction": 0.75, "ambiguous": 0.45}
        apply_thresholds(results, thresholds)
        assert results[0].decision == "not_contradiction"

    def test_build_nli_pairs(self):
        from backend_lite.nli.nli_batcher import build_nli_pairs

        pairs = build_nli_pairs([
            ({"id": "c1", "text": "טענה א"}, {"id": "c2", "text": "טענה ב"}, "pair_1"),
        ])
        assert len(pairs) == 1
        assert pairs[0].pair_id == "pair_1"
        assert "טענה א" in pairs[0].text_a
        assert "טענה ב" in pairs[0].text_b

    def test_build_nli_pairs_with_context(self):
        from backend_lite.nli.nli_batcher import build_nli_pairs

        pairs = build_nli_pairs([
            (
                {"id": "c1", "text": "טענה א", "context_before": "לפני", "context_after": "אחרי"},
                {"id": "c2", "text": "טענה ב"},
                "pair_1",
            ),
        ])
        assert "לפני" in pairs[0].text_a
        assert "אחרי" in pairs[0].text_a


# =============================================================================
# Calibration
# =============================================================================

class TestCalibration:
    def test_uncalibrated_passthrough(self):
        from backend_lite.calibration import TemperatureCalibrator

        cal = TemperatureCalibrator(temperature=1.0)
        scores = {"entailment": 0.2, "contradiction": 0.6, "neutral": 0.2}
        result = cal.calibrate(scores)
        # T=1.0 should be approximately identity
        for k in scores:
            assert abs(result[k] - scores[k]) < 0.01

    def test_higher_temperature_softens(self):
        from backend_lite.calibration import TemperatureCalibrator

        cal = TemperatureCalibrator(temperature=2.0)
        scores = {"entailment": 0.1, "contradiction": 0.8, "neutral": 0.1}
        result = cal.calibrate(scores)
        # Higher T → flatter distribution → contradiction should decrease
        assert result["contradiction"] < scores["contradiction"]
        assert result["neutral"] > scores["neutral"]

    def test_lower_temperature_sharpens(self):
        from backend_lite.calibration import TemperatureCalibrator

        cal = TemperatureCalibrator(temperature=0.5)
        scores = {"entailment": 0.1, "contradiction": 0.8, "neutral": 0.1}
        result = cal.calibrate(scores)
        # Lower T → sharper distribution → contradiction should increase
        assert result["contradiction"] > scores["contradiction"]

    def test_calibrate_sums_to_one(self):
        from backend_lite.calibration import TemperatureCalibrator

        for t in [0.3, 0.5, 1.0, 1.5, 2.0, 5.0]:
            cal = TemperatureCalibrator(temperature=t)
            scores = {"entailment": 0.3, "contradiction": 0.5, "neutral": 0.2}
            result = cal.calibrate(scores)
            assert abs(sum(result.values()) - 1.0) < 1e-6, f"T={t}: sum={sum(result.values())}"

    def test_save_load_roundtrip(self, tmp_path):
        from backend_lite.calibration import TemperatureCalibrator

        cal = TemperatureCalibrator(temperature=1.73)
        cal.ece = 0.042
        cal.fitted = True

        path = tmp_path / "cal.json"
        cal.save(path)

        loaded = TemperatureCalibrator.load(path)
        assert abs(loaded.temperature - 1.73) < 1e-6
        assert abs(loaded.ece - 0.042) < 1e-6
        assert loaded.fitted is True

    def test_calibrate_batch(self):
        from backend_lite.calibration import TemperatureCalibrator
        from backend_lite.nli.nli_types import NLIResult, NLILabel

        cal = TemperatureCalibrator(temperature=1.5)
        results = [
            NLIResult(
                pair_id="p1",
                label=NLILabel.CONTRADICTION,
                raw_scores={"entailment": 0.1, "contradiction": 0.8, "neutral": 0.1},
                contradiction_prob=0.8,
            ),
            NLIResult(
                pair_id="p2",
                label=NLILabel.NEUTRAL,
                raw_scores={"entailment": 0.3, "contradiction": 0.3, "neutral": 0.4},
                contradiction_prob=0.3,
            ),
        ]
        cal.calibrate_batch(results)
        assert results[0].calibrated is not None
        assert results[1].calibrated is not None
        # After calibration, prob should be updated
        assert results[0].contradiction_prob == results[0].calibrated["contradiction"]

    def test_report(self):
        from backend_lite.calibration import TemperatureCalibrator

        cal = TemperatureCalibrator(temperature=1.5)
        cal.ece = 0.03
        cal.fitted = True
        report = cal.report()
        assert report["temperature"] == 1.5
        assert report["ece"] == 0.03


# =============================================================================
# Dataset Exporter
# =============================================================================

class TestDatasetExporter:
    def test_export_jsonl(self, tmp_path):
        from backend_lite.dataset_exporter import export_pairs_jsonl

        pairs = [
            {"text_a": "a1", "text_b": "b1", "label": "contradiction", "pair_id": "p1"},
            {"text_a": "a2", "text_b": "b2", "label": "not_contradiction", "pair_id": "p2"},
        ]
        path = export_pairs_jsonl(pairs, output_path=tmp_path / "test.jsonl", append=False)

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2

        row1 = json.loads(lines[0])
        assert row1["label"] == 0  # contradiction → 0
        assert row1["text_a"] == "a1"

        row2 = json.loads(lines[1])
        assert row2["label"] == 1  # not_contradiction → 1

    def test_export_csv(self, tmp_path):
        from backend_lite.dataset_exporter import export_pairs_csv

        pairs = [
            {"text_a": "a1", "text_b": "b1", "label": "contradiction", "pair_id": "p1"},
        ]
        path = export_pairs_csv(pairs, output_path=tmp_path / "test.csv", append=False)
        content = path.read_text()
        assert "text_a" in content  # header
        assert "a1" in content

    def test_generate_hard_negatives(self):
        from backend_lite.dataset_exporter import generate_hard_negatives

        fps = [
            {"text_a": "a", "text_b": "b", "pair_id": "fp1"},
            {"text_a": "c", "text_b": "d", "pair_id": "fp2"},
        ]
        hn = generate_hard_negatives(fps)
        assert len(hn) == 4  # 2 originals + 2 swapped
        assert all(h["label"] == "not_contradiction" for h in hn)
        # Check swap exists
        swap_ids = [h["pair_id"] for h in hn]
        assert "fp1_hn" in swap_ids
        assert "fp1_hn_swap" in swap_ids

    def test_collect_training_pairs(self):
        from backend_lite.dataset_exporter import collect_training_pairs_from_results

        results = [
            {"pair_id": "p1", "decision": "contradiction"},
            {"pair_id": "p2", "decision": "contradiction"},
            {"pair_id": "p3", "decision": "not_contradiction"},
            {"pair_id": "p4", "decision": "not_contradiction"},
        ]
        gt = {"p1": "contradiction", "p2": "not_contradiction", "p3": "contradiction", "p4": "not_contradiction"}

        cats = collect_training_pairs_from_results(results, gt)
        assert len(cats["tp"]) == 1  # p1
        assert len(cats["fp"]) == 1  # p2
        assert len(cats["fn"]) == 1  # p3
        assert len(cats["tn"]) == 1  # p4


# =============================================================================
# ContradictionDecision enum
# =============================================================================

class TestTriStateEnum:
    def test_enum_values(self):
        from backend_lite.schemas import ContradictionDecision

        assert ContradictionDecision.CONTRADICTION.value == "contradiction"
        assert ContradictionDecision.NOT_CONTRADICTION.value == "not_contradiction"
        assert ContradictionDecision.AMBIGUOUS.value == "ambiguous"

    def test_enum_is_string(self):
        from backend_lite.schemas import ContradictionDecision

        assert isinstance(ContradictionDecision.CONTRADICTION, str)
        assert ContradictionDecision.CONTRADICTION == "contradiction"


# =============================================================================
# Config NLI settings
# =============================================================================

class TestConfigNLI:
    def test_nli_defaults(self):
        from backend_lite.config import Settings

        s = Settings()
        assert s.nli_enabled is True
        assert "mDeBERTa" in s.nli_model_name
        assert s.nli_batch_size == 16
        assert s.nli_max_length == 512
        assert s.calibration_enabled is True
        assert s.llm_adjudicator_enabled is True
        assert s.llm_adjudicator_max_ratio == 0.10

    def test_nli_thresholds_balanced(self):
        from backend_lite.config import Settings

        s = Settings(precision_mode="balanced")
        t = s.nli_thresholds
        assert t["contradiction"] == 0.55
        assert t["ambiguous"] == 0.30

    def test_nli_thresholds_strict(self):
        from backend_lite.config import Settings

        s = Settings(precision_mode="strict")
        t = s.nli_thresholds
        assert t["contradiction"] == 0.75
        assert t["ambiguous"] == 0.45

    def test_adjudicator_warning(self):
        from backend_lite.config import Settings

        s = Settings(llm_adjudicator_enabled=True, llm_mode="none")
        warnings = s.validate_llm_config()
        assert any("ADJUDICATOR" in w.upper() for w in warnings)
