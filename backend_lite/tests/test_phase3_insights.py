"""
Phase 3 Insight Scoring Tests
=============================
"""

from pathlib import Path
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend_lite.db.models import Contradiction, ContradictionStatus
from backend_lite.insights import compute_insight


def test_insight_high_verifiability_low_risk():
    contr = Contradiction(
        contradiction_type="temporal_date_conflict",
        status=ContradictionStatus.VERIFIED,
        severity="high",
        category="hard_contradiction",
        locator1_json={"doc_id": "d1", "char_start": 10, "char_end": 20},
        locator2_json={"doc_id": "d2", "char_start": 30, "char_end": 40},
    )

    insight = compute_insight(contr)
    assert insight["verifiability_score"] >= 0.7
    assert insight["risk_score"] <= 0.6
    assert insight["stage_recommendation"] in ("early", "mid")
    assert not insight["do_not_ask"]


def test_insight_do_not_ask_for_low_verifiability_high_risk():
    contr = Contradiction(
        contradiction_type="actor_attribution_conflict",
        status=ContradictionStatus.SUSPICIOUS,
        severity="low",
        category="narrative_ambiguity",
        locator1_json={},
        locator2_json={},
    )

    insight = compute_insight(contr)
    assert insight["verifiability_score"] < 0.4
    assert insight["risk_score"] >= 0.7
    assert insight["do_not_ask"]
