"""
Progress Tracker
================

Structured progress tracking for long-running analysis jobs.
Stores rich stage-by-stage data with intermediate results,
enabling the frontend to show real-time feedback.
"""

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StageInfo:
    """One completed or in-progress pipeline stage."""
    key: str                    # machine-readable stage name
    label_he: str               # Hebrew UI label
    started_at: float = 0.0     # epoch seconds
    finished_at: float = 0.0    # epoch seconds (0 = still running)
    progress_pct: int = 0       # 0-100 within this stage
    detail: str = ""            # e.g. "3/8 מסמכים"
    counts: Dict[str, int] = field(default_factory=dict)  # e.g. {"claims": 42}

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.finished_at > 0:
            d["elapsed_sec"] = round(self.finished_at - self.started_at, 1)
        elif self.started_at > 0:
            d["elapsed_sec"] = round(time.time() - self.started_at, 1)
        return d


# Ordered pipeline stages for case analysis
ANALYSIS_STAGES = [
    ("load_docs",       "טוען מסמכים"),
    ("extract_claims",  "מחלץ טענות"),
    ("build_graphs",    "בונה גרפים (סמנטי, ישויות, זמני)"),
    ("learn_context",   "טוען הקשר למידה"),
    ("detect_rules",    "מזהה סתירות (חוקים)"),
    ("detect_llm",      "מזהה סתירות (AI)"),
    ("verify",          "מאמת ממצאים"),
    ("score_save",      "מדרג ושומר תוצאות"),
    ("insights",        "מפיק תובנות"),
    ("complete",        "הושלם"),
]


class ProgressTracker:
    """
    Tracks structured progress through an analysis pipeline.

    Usage:
        tracker = ProgressTracker(job_id="abc")
        tracker.start_stage("load_docs", detail="4 מסמכים")
        tracker.finish_stage("load_docs", counts={"documents": 4})
        tracker.start_stage("extract_claims")
        tracker.update_stage("extract_claims", progress_pct=50, detail="2/4 מסמכים", counts={"claims": 28})
        ...
    """

    def __init__(self, job_id: Optional[str] = None):
        self.job_id = job_id
        self.stages: Dict[str, StageInfo] = {}
        self.stage_order: List[str] = [s[0] for s in ANALYSIS_STAGES]
        self.current_stage: Optional[str] = None
        self.started_at: float = time.time()
        self.overall_pct: int = 0
        self.error: Optional[str] = None

        # Intermediate results shown live to user
        self.preview: Dict[str, Any] = {
            "documents_total": 0,
            "documents_processed": 0,
            "claims_extracted": 0,
            "contradictions_found": 0,
            "contradictions_verified": 0,
            "contradictions_rejected": 0,
            "first_contradictions": [],  # up to 3 preview items
        }

    def start_stage(self, key: str, detail: str = "") -> None:
        """Begin a pipeline stage."""
        label_he = dict(ANALYSIS_STAGES).get(key, key)
        self.stages[key] = StageInfo(
            key=key,
            label_he=label_he,
            started_at=time.time(),
            detail=detail,
        )
        self.current_stage = key
        self._recalc_overall()
        self._persist()

    def update_stage(
        self,
        key: str,
        progress_pct: int = 0,
        detail: str = "",
        counts: Optional[Dict[str, int]] = None,
    ) -> None:
        """Update an in-progress stage."""
        if key not in self.stages:
            self.start_stage(key, detail)
            return
        stage = self.stages[key]
        stage.progress_pct = progress_pct
        if detail:
            stage.detail = detail
        if counts:
            stage.counts.update(counts)
        self._recalc_overall()
        self._persist()

    def finish_stage(
        self,
        key: str,
        counts: Optional[Dict[str, int]] = None,
        detail: str = "",
    ) -> None:
        """Complete a pipeline stage."""
        if key not in self.stages:
            self.start_stage(key, detail)
        stage = self.stages[key]
        stage.finished_at = time.time()
        stage.progress_pct = 100
        if detail:
            stage.detail = detail
        if counts:
            stage.counts.update(counts)
        self._recalc_overall()
        self._persist()

    def set_preview(self, **kwargs: Any) -> None:
        """Update live preview counters."""
        for k, v in kwargs.items():
            if k in self.preview:
                self.preview[k] = v
        self._persist()

    def add_preview_contradiction(
        self,
        claim_a: str,
        claim_b: str,
        contradiction_type: str,
        severity: str,
        confidence: float,
    ) -> None:
        """Add a contradiction to the live preview (max 5)."""
        if len(self.preview["first_contradictions"]) >= 5:
            return
        self.preview["first_contradictions"].append({
            "claim_a": claim_a[:120],
            "claim_b": claim_b[:120],
            "type": contradiction_type,
            "severity": severity,
            "confidence": round(confidence, 2),
        })
        self._persist()

    def set_error(self, error: str) -> None:
        """Mark tracker with error."""
        self.error = error
        self._persist()

    def to_dict(self) -> Dict[str, Any]:
        """Full snapshot for API response."""
        stages_list = []
        for key in self.stage_order:
            if key in self.stages:
                stages_list.append(self.stages[key].to_dict())

        return {
            "overall_pct": self.overall_pct,
            "current_stage": self.current_stage,
            "current_stage_label": dict(ANALYSIS_STAGES).get(
                self.current_stage or "", ""
            ),
            "elapsed_sec": round(time.time() - self.started_at, 1),
            "stages": stages_list,
            "preview": self.preview,
            "error": self.error,
        }

    # ── internal ──

    def _recalc_overall(self) -> None:
        """Calculate overall progress % from stages."""
        total_stages = len(self.stage_order)
        if total_stages == 0:
            return
        completed = sum(
            1 for k in self.stage_order
            if k in self.stages and self.stages[k].finished_at > 0
        )
        # Current in-progress stage contributes partial credit
        current_partial = 0.0
        if self.current_stage and self.current_stage in self.stages:
            s = self.stages[self.current_stage]
            if s.finished_at == 0:
                current_partial = s.progress_pct / 100.0

        self.overall_pct = int(
            ((completed + current_partial) / total_stages) * 100
        )
        self.overall_pct = min(self.overall_pct, 100)

    def _persist(self) -> None:
        """Save structured progress to RQ job meta (if running inside RQ)."""
        try:
            from rq import get_current_job
            job = get_current_job()
            if job:
                job.meta["progress"] = self.overall_pct
                job.meta["message"] = dict(ANALYSIS_STAGES).get(
                    self.current_stage or "", ""
                )
                job.meta["structured_progress"] = self.to_dict()
                job.save_meta()
        except Exception:
            pass  # Not running in RQ or RQ unavailable

        # Also update legacy progress for backwards compatibility
        try:
            from .jobs.tasks import update_job_progress
            update_job_progress(
                self.overall_pct,
                dict(ANALYSIS_STAGES).get(self.current_stage or "", ""),
            )
        except Exception:
            pass
