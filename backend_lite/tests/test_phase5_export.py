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
        "case_settings": {
            "case_number": "123-45-67890",
            "court": "שלום תל אביב",
            "our_side": "plaintiff",
            "client_name": "לקוח בדיקה",
            "opponent_name": "צד שכנגד",
            "case_type": "civil",
            "court_level": "magistrate",
            "language": "he",
        },
        "ranked_contradictions": [
            {
                "contradiction_id": "c1",
                "type": "temporal_date_conflict",
                "severity": "high",
                "category": "hard_contradiction",
                "quote1": "החוזה נחתם ביום 01.01.2020",
                "quote2": "החוזה נחתם ביום 02.02.2021",
                "anchors": [
                    {
                        "doc_id": "doc_1",
                        "page_no": 1,
                        "paragraph_index": 2,
                        "snippet": "החוזה נחתם ביום 01.01.2020",
                    }
                ],
                "scores": {"impact": 0.8, "risk": 0.4, "verifiability": 0.9, "composite": 0.288},
                "stage": "early",
            }
        ],
        "version_shifts": [
            {
                "witness_id": "w1",
                "witness_name": "עד בדיקה",
                "shifts": [
                    {
                        "shift_type": "time_change",
                        "description": "שינוי במועדים בין הגרסאות.",
                        "anchor_a": {
                            "doc_id": "doc_1",
                            "page_no": 1,
                            "paragraph_index": 1,
                            "snippet": "01.01.2020",
                        },
                        "anchor_b": {
                            "doc_id": "doc_2",
                            "page_no": 1,
                            "paragraph_index": 1,
                            "snippet": "02.02.2021",
                        },
                    }
                ],
            }
        ],
        "appendix_anchors": [
            {
                "doc_id": "doc_1",
                "page_no": 1,
                "paragraph_index": 2,
                "snippet": "החוזה נחתם ביום 01.01.2020",
            }
        ],
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

    from io import BytesIO
    from docx import Document

    doc = Document(BytesIO(docx_bytes))
    text = "\n".join([p.text for p in doc.paragraphs])
    assert "פרטי תיק" in text
    assert "סתירות מדורגות" in text
    assert "סטיות גרסה בעדויות" in text
    assert "תכנית חקירה" in text
    assert "נספח: קטעי ראיות" in text
