"""
Dataset Exporter & Hard-Negative Generator (Part 5)
=====================================================

Active-learning infrastructure for Hebrew NLI fine-tuning.

Responsibilities:
1. Export labeled pairs (FP / FN / TP / TN) to CSV / JSONL
2. Generate hard negatives from false-positive pairs
3. Maintain a growing dataset for fine-tuning iterations

File formats:
- JSONL: one JSON object per line (for HuggingFace datasets)
  {"text_a": "...", "text_b": "...", "label": 0|1|2, "source": "...", "pair_id": "..."}
- CSV: text_a, text_b, label, source, pair_id

Label mapping (NLI convention):
  0 = contradiction
  1 = neutral (not_contradiction)
  2 = entailment (not used in our pipeline — but kept for compatibility)
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Sequence

logger = logging.getLogger(__name__)

_DEFAULT_EXPORT_DIR = Path(__file__).parent / "data" / "nli_training"

# Label mapping
LABEL_MAP = {
    "contradiction": 0,
    "not_contradiction": 1,
    "neutral": 1,
    "entailment": 2,
    "ambiguous": 1,  # treat ambiguous as neutral for training
}


def export_pairs_jsonl(
    pairs: Sequence[Dict[str, Any]],
    output_path: Optional[str | Path] = None,
    append: bool = True,
) -> Path:
    """
    Export labeled pairs to JSONL format.

    Each pair dict should have:
        text_a, text_b, label (str or int), pair_id, source (optional)

    Returns the output path.
    """
    if output_path is None:
        _DEFAULT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = _DEFAULT_EXPORT_DIR / f"pairs_{datetime.now():%Y%m%d}.jsonl"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if append else "w"
    count = 0
    with open(output_path, mode, encoding="utf-8") as f:
        for p in pairs:
            label = p.get("label", "neutral")
            if isinstance(label, str):
                label = LABEL_MAP.get(label, 1)
            row = {
                "text_a": p.get("text_a", ""),
                "text_b": p.get("text_b", ""),
                "label": label,
                "source": p.get("source", "pipeline"),
                "pair_id": p.get("pair_id", ""),
                "exported_at": datetime.now().isoformat(),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1

    logger.info("Exported %d pairs to %s", count, output_path)
    return output_path


def export_pairs_csv(
    pairs: Sequence[Dict[str, Any]],
    output_path: Optional[str | Path] = None,
    append: bool = True,
) -> Path:
    """
    Export labeled pairs to CSV format.

    Returns the output path.
    """
    if output_path is None:
        _DEFAULT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = _DEFAULT_EXPORT_DIR / f"pairs_{datetime.now():%Y%m%d}.csv"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = output_path.exists() and output_path.stat().st_size > 0
    mode = "a" if append else "w"
    count = 0

    with open(output_path, mode, encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not file_exists or not append:
            writer.writerow(["text_a", "text_b", "label", "source", "pair_id"])
        for p in pairs:
            label = p.get("label", "neutral")
            if isinstance(label, str):
                label = LABEL_MAP.get(label, 1)
            writer.writerow([
                p.get("text_a", ""),
                p.get("text_b", ""),
                label,
                p.get("source", "pipeline"),
                p.get("pair_id", ""),
            ])
            count += 1

    logger.info("Exported %d pairs to %s", count, output_path)
    return output_path


def generate_hard_negatives(
    false_positives: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Generate hard-negative training examples from false-positive pairs.

    False positives are pairs that the system flagged as contradictions
    but are actually non-contradictions. These are the most valuable
    training examples because they sit near the decision boundary.

    Each FP pair becomes a training example with label=1 (not_contradiction).
    We also create a lightly augmented variant (swap order) for robustness.

    Parameters
    ----------
    false_positives : list of dicts with text_a, text_b, pair_id

    Returns
    -------
    List of training-ready dicts with label set to "not_contradiction".
    """
    hard_negatives: List[Dict[str, Any]] = []

    for fp in false_positives:
        text_a = fp.get("text_a", "")
        text_b = fp.get("text_b", "")
        pair_id = fp.get("pair_id", "")

        # Original order as hard negative
        hard_negatives.append({
            "text_a": text_a,
            "text_b": text_b,
            "label": "not_contradiction",
            "source": "hard_negative_fp",
            "pair_id": f"{pair_id}_hn",
        })

        # Swapped order (NLI is not always symmetric)
        hard_negatives.append({
            "text_a": text_b,
            "text_b": text_a,
            "label": "not_contradiction",
            "source": "hard_negative_fp_swap",
            "pair_id": f"{pair_id}_hn_swap",
        })

    logger.info("Generated %d hard negatives from %d FPs", len(hard_negatives), len(false_positives))
    return hard_negatives


def collect_training_pairs_from_results(
    results: List[Dict[str, Any]],
    ground_truth: Optional[Dict[str, str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Collect training pairs from pipeline results, categorized by outcome.

    Parameters
    ----------
    results : list of result dicts from the pipeline, each with:
        - pair_id, text_a, text_b
        - decision: system's decision ("contradiction" / "not_contradiction" / "ambiguous")
    ground_truth : optional dict mapping pair_id → true label

    Returns
    -------
    Dict with keys: "tp", "fp", "tn", "fn", "unlabeled"
    Each value is a list of training-pair dicts.
    """
    categorized: Dict[str, List[Dict[str, Any]]] = {
        "tp": [], "fp": [], "tn": [], "fn": [], "unlabeled": [],
    }

    for r in results:
        pair_id = r.get("pair_id", "")
        decision = r.get("decision", "not_contradiction")
        pred_positive = (decision == "contradiction")

        if ground_truth and pair_id in ground_truth:
            true_label = ground_truth[pair_id]
            true_positive = (true_label == "contradiction")

            if pred_positive and true_positive:
                categorized["tp"].append(r)
            elif pred_positive and not true_positive:
                categorized["fp"].append(r)
            elif not pred_positive and true_positive:
                categorized["fn"].append(r)
            else:
                categorized["tn"].append(r)
        else:
            categorized["unlabeled"].append(r)

    for cat, items in categorized.items():
        if items:
            logger.info("Training pairs — %s: %d", cat, len(items))

    return categorized


def active_learning_export(
    results: List[Dict[str, Any]],
    ground_truth: Optional[Dict[str, str]] = None,
    output_dir: Optional[str | Path] = None,
    export_format: str = "jsonl",
) -> Dict[str, Path]:
    """
    Full active-learning export pipeline:
    1. Categorize results into TP/FP/TN/FN
    2. Generate hard negatives from FPs
    3. Export all categories to files

    Returns dict of category → file path.
    """
    if output_dir is None:
        output_dir = _DEFAULT_EXPORT_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    categorized = collect_training_pairs_from_results(results, ground_truth)
    export_fn = export_pairs_jsonl if export_format == "jsonl" else export_pairs_csv
    ext = ".jsonl" if export_format == "jsonl" else ".csv"

    paths: Dict[str, Path] = {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Export each category
    for cat, items in categorized.items():
        if not items:
            continue
        path = output_dir / f"{cat}_{timestamp}{ext}"
        export_fn(items, output_path=path, append=False)
        paths[cat] = path

    # Generate and export hard negatives
    if categorized["fp"]:
        hard_negs = generate_hard_negatives(categorized["fp"])
        hn_path = output_dir / f"hard_negatives_{timestamp}{ext}"
        export_fn(hard_negs, output_path=hn_path, append=False)
        paths["hard_negatives"] = hn_path

    return paths
