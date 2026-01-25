"""
Phase 5 Simulation Tests
========================
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend_lite.witness_simulation import simulate_plan


def test_simulation_includes_warnings_and_branch():
    plan = {
        "stages": [
            {
                "stage": "early",
                "steps": [
                    {
                        "id": "s1",
                        "step_type": "lock_in",
                        "question": "תענה כן או לא",
                        "anchors": [],
                        "branches": [
                            {"trigger": "אם העד אומר: 'לא זוכר'", "follow_up_questions": ["אני מפנה אותך למסמך."]},
                        ],
                        "do_not_ask_flag": True,
                        "do_not_ask_reason": "סיכון גבוה",
                    }
                ],
            }
        ]
    }

    steps = simulate_plan(plan, "evasive")
    assert len(steps) == 1
    assert steps[0]["chosen_branch_trigger"] is not None
    assert steps[0]["warnings"]
