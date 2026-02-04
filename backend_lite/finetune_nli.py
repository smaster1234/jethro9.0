#!/usr/bin/env python3
"""
Fine-tune script for Hebrew NLI Cross-Encoder (Part 6)
=======================================================

Trains a 3-class NLI cross-encoder on Hebrew legal contradiction data.
Designed for 7 GB VRAM budget (mixed precision + gradient accumulation).

Usage:
    python -m backend_lite.finetune_nli \
        --train_file data/nli_training/train.jsonl \
        --dev_file   data/nli_training/dev.jsonl \
        --output_dir models/hebrew_nli_v1 \
        --epochs 5 \
        --batch_size 8 \
        --grad_accum 4

Data format (JSONL, one per line):
    {"text_a": "...", "text_b": "...", "label": 0|1|2}
    Labels: 0=contradiction, 1=neutral, 2=entailment

Memory budget (7 GB VRAM):
    - base model ~280M params → ~1.1 GB fp16
    - batch_size=8, grad_accum=4 → effective batch 32
    - max_length=512 → ~2.5 GB activation memory
    - Optimizer states → ~2.2 GB
    - Total ≈ 5.8 GB → fits in 7 GB with margin
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ── Soft imports ────────────────────────────────────────────────────────────
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

try:
    from transformers import (
        AutoTokenizer,
        AutoModelForSequenceClassification,
        get_linear_schedule_with_warmup,
    )
    _HAS_TRANSFORMERS = True
except ImportError:
    _HAS_TRANSFORMERS = False

try:
    import numpy as np
    from sklearn.metrics import classification_report, confusion_matrix
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False


# ── Dataset ─────────────────────────────────────────────────────────────────

class NLIPairDataset:
    """Lazy-tokenized NLI pair dataset from JSONL."""

    def __init__(self, path: str | Path, tokenizer, max_length: int = 512):
        self.samples: List[Dict] = []
        self.tokenizer = tokenizer
        self.max_length = max_length

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                self.samples.append(obj)

        logger.info("Loaded %d samples from %s", len(self.samples), path)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        s = self.samples[idx]
        encoded = self.tokenizer(
            s["text_a"],
            s["text_b"],
            padding="max_length",
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        return {
            "input_ids": encoded["input_ids"].squeeze(0),
            "attention_mask": encoded["attention_mask"].squeeze(0),
            "labels": torch.tensor(int(s["label"]), dtype=torch.long),
        }


# ── Training loop ───────────────────────────────────────────────────────────

def train(
    model_name: str = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
    train_file: str = "data/nli_training/train.jsonl",
    dev_file: Optional[str] = None,
    output_dir: str = "models/hebrew_nli_v1",
    epochs: int = 5,
    batch_size: int = 8,
    grad_accum: int = 4,
    lr: float = 2e-5,
    max_length: int = 512,
    warmup_ratio: float = 0.1,
    fp16: bool = True,
    seed: int = 42,
):
    """
    Fine-tune the NLI cross-encoder.

    Parameters match the 7 GB VRAM budget defaults.
    """
    if not _HAS_TORCH or not _HAS_TRANSFORMERS:
        logger.error("torch and transformers required for fine-tuning")
        sys.exit(1)

    torch.manual_seed(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Device: %s | FP16: %s", device, fp16 and device == "cuda")

    # Load tokenizer + model
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=3)
    model.to(device)

    # Datasets
    train_ds = NLIPairDataset(train_file, tokenizer, max_length)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

    dev_loader = None
    if dev_file and Path(dev_file).exists():
        dev_ds = NLIPairDataset(dev_file, tokenizer, max_length)
        dev_loader = DataLoader(dev_ds, batch_size=batch_size * 2, shuffle=False)

    # Optimizer + scheduler
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    total_steps = (len(train_loader) // grad_accum) * epochs
    warmup_steps = int(total_steps * warmup_ratio)
    scheduler = get_linear_schedule_with_warmup(optimizer, warmup_steps, total_steps)

    # Mixed precision
    scaler = None
    if fp16 and device == "cuda":
        scaler = torch.amp.GradScaler("cuda")

    # Training
    best_dev_f1 = 0.0
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        optimizer.zero_grad()

        for step, batch in enumerate(train_loader):
            batch = {k: v.to(device) for k, v in batch.items()}

            if scaler:
                with torch.amp.autocast("cuda"):
                    outputs = model(**batch)
                    loss = outputs.loss / grad_accum
                scaler.scale(loss).backward()
            else:
                outputs = model(**batch)
                loss = outputs.loss / grad_accum
                loss.backward()

            total_loss += loss.item() * grad_accum

            if (step + 1) % grad_accum == 0:
                if scaler:
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    optimizer.step()
                scheduler.step()
                optimizer.zero_grad()

        avg_loss = total_loss / len(train_loader)
        logger.info("Epoch %d/%d — avg loss: %.4f", epoch + 1, epochs, avg_loss)

        # Evaluation
        if dev_loader:
            metrics = evaluate(model, dev_loader, device)
            dev_f1 = metrics.get("macro_f1", 0.0)
            logger.info("  Dev — F1: %.4f | Acc: %.4f", dev_f1, metrics.get("accuracy", 0.0))

            if dev_f1 > best_dev_f1:
                best_dev_f1 = dev_f1
                model.save_pretrained(output_path / "best")
                tokenizer.save_pretrained(output_path / "best")
                logger.info("  New best model saved (F1=%.4f)", dev_f1)

    # Save final model
    model.save_pretrained(output_path / "final")
    tokenizer.save_pretrained(output_path / "final")
    logger.info("Training complete. Models saved to %s", output_path)

    return {"best_dev_f1": best_dev_f1, "final_loss": avg_loss}


def evaluate(model, dataloader, device: str) -> Dict[str, float]:
    """Evaluate model on a dataloader, return metrics dict."""
    model.eval()
    all_preds = []
    all_labels = []

    with torch.no_grad():
        for batch in dataloader:
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)
            preds = outputs.logits.argmax(dim=-1).cpu().tolist()
            labels = batch["labels"].cpu().tolist()
            all_preds.extend(preds)
            all_labels.extend(labels)

    if not _HAS_SKLEARN:
        # Basic accuracy only
        correct = sum(p == l for p, l in zip(all_preds, all_labels))
        return {"accuracy": correct / len(all_labels) if all_labels else 0.0}

    labels_arr = np.array(all_labels)
    preds_arr = np.array(all_preds)

    accuracy = (preds_arr == labels_arr).mean()

    # Per-class metrics
    report = classification_report(
        labels_arr, preds_arr,
        target_names=["contradiction", "neutral", "entailment"],
        output_dict=True,
        zero_division=0,
    )

    return {
        "accuracy": float(accuracy),
        "macro_f1": report["macro avg"]["f1-score"],
        "contradiction_f1": report["contradiction"]["f1-score"],
        "contradiction_precision": report["contradiction"]["precision"],
        "contradiction_recall": report["contradiction"]["recall"],
        "neutral_f1": report["neutral"]["f1-score"],
        "report": report,
    }


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Fine-tune Hebrew NLI cross-encoder")
    parser.add_argument("--model_name", default="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli")
    parser.add_argument("--train_file", required=True, help="Path to train JSONL")
    parser.add_argument("--dev_file", default=None, help="Path to dev JSONL")
    parser.add_argument("--output_dir", default="models/hebrew_nli_v1")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument("--grad_accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max_length", type=int, default=512)
    parser.add_argument("--warmup_ratio", type=float, default=0.1)
    parser.add_argument("--no_fp16", action="store_true")
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    train(
        model_name=args.model_name,
        train_file=args.train_file,
        dev_file=args.dev_file,
        output_dir=args.output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        grad_accum=args.grad_accum,
        lr=args.lr,
        max_length=args.max_length,
        warmup_ratio=args.warmup_ratio,
        fp16=not args.no_fp16,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
