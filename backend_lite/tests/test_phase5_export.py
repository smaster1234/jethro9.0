"""
Phase 5 Export Tests
====================
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend_lite.exporter import build_cross_exam_docx, build_cross_exam_pdf


class DummyDoc:
    def __init__(self, doc_name: str):
        self.doc_name = doc_name


def _sample_plan():
    return {
        "stages": [
            {
                "stage": "early",
                "steps": [
                    {
                        "id": "step_1",
                        "step_type": "lock_in",
                        "title": "קיבוע",
                        "question": "אתה עומד מאחורי הגרסה הזו?",
                        "anchors": [
                            {
                                "doc_id": "doc_1",
                                "page_no": 1,
                                "paragraph_index": 2,
                                "snippet": "החוזה נחתם ביום 01.01.2020",
                            }
                        ],
                        "branches": [],
                        "do_not_ask_flag": False,
                    }
                ],
            }
        ]
    }


def test_export_docx_and_pdf_bytes():
    plan = _sample_plan()
    doc_lookup = {"doc_1": DummyDoc("מסמך א'")}

    docx_bytes = build_cross_exam_docx(plan, "תיק בדיקה", "run_1", doc_lookup)
    pdf_bytes = build_cross_exam_pdf(plan, "תיק בדיקה", "run_1", doc_lookup)

    assert docx_bytes[:2] == b"PK"
    assert pdf_bytes[:4] == b"%PDF"
