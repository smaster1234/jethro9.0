"""
Phase 4 Planner Tests
=====================
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend_lite.db.models import Contradiction, ContradictionInsight
from backend_lite.cross_exam_planner import build_cross_exam_plan


def test_build_cross_exam_plan_includes_do_not_ask():
    contr = Contradiction(
        id="c1",
        contradiction_type="temporal_date_conflict",
        quote1="ביום 01.01.2020",
        quote2="ביום 02.02.2021",
        locator1_json={"doc_id": "d1", "char_start": 1, "char_end": 10},
        locator2_json={"doc_id": "d2", "char_start": 11, "char_end": 20},
    )
    insight = ContradictionInsight(
        contradiction_id="c1",
        stage_recommendation="late",
        do_not_ask=True,
        do_not_ask_reason="סיכון גבוה לעומת אחיזה נמוכה",
        counters_json=["תענה כן או לא"],
    )

    stages = build_cross_exam_plan([(contr, insight)])
    late = next(stage for stage in stages if stage["stage"] == "late")
    assert late["steps"]
    assert late["steps"][0]["do_not_ask_flag"]
    assert late["steps"][0]["do_not_ask_reason"]


def test_build_cross_exam_plan_generates_steps():
    contr = Contradiction(
        id="c2",
        contradiction_type="factual_conflict",
        quote1="טענה ראשונה",
        quote2="טענה שנייה",
        locator1_json={"doc_id": "d1", "char_start": 1, "char_end": 10},
        locator2_json={"doc_id": "d2", "char_start": 11, "char_end": 20},
    )
    insight = ContradictionInsight(
        contradiction_id="c2",
        stage_recommendation="early",
        do_not_ask=False,
        evasions_json=["לא זוכר"],
        counters_json=["אני מפנה אותך לסעיף..."],
    )

    stages = build_cross_exam_plan([(contr, insight)])
    early = next(stage for stage in stages if stage["stage"] == "early")
    assert len(early["steps"]) > 0
    assert early["steps"][0]["anchors"]
