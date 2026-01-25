# RELEASE CHECKLIST — Phases 1–5

הערות:
- סטטוס חייב להיות PASS/FAIL.
- עבור FAIL מצורפים צעדי שחזור/בדיקה.

## Phase 1 — Evidence Anchoring
- **PASS** — לכל Claim יש EvidenceAnchor (doc_id + offsets + snippet).  
  בדיקה: `backend_lite/tests/test_phase1_anchoring.py::test_task_analyze_case_populates_anchor_locators`
- **PASS** — כל Contradiction כולל locator1_json/locator2_json ונפתר לקטע ראיה.  
  בדיקה: `backend_lite/tests/test_phase1_anchoring.py::test_anchor_resolve_endpoint`
- **FAIL** — ה־UI מדגיש תמיד spans נכונים.  
  צעדי שחזור: להריץ UI, לפתוח תיק → Contradictions → "הצג ראיות" → לוודא שההדגשה תואמת לטקסט המקורי בכל מקרה.

## Phase 2 — Witness Versions
- **PASS** — Witness וגרסאות קיימים ונראים ב־UI (API).  
  בדיקה: `backend_lite/tests/test_phase2_witnesses.py::test_witness_endpoints_and_diff`
- **PASS** — זיהוי סטיות נרטיביות כולל anchors לשני הצדדים.  
  בדיקה: `backend_lite/tests/test_phase2_witnesses.py::test_witness_endpoints_and_diff`

## Phase 3 — ContradictionInsight
- **PASS** — לכל סתירה יש Insight עם impact/risk/verifiability + stage.  
  בדיקה: `backend_lite/tests/test_phase3_insights.py`
- **PASS** — DON’T ASK THIS מוצג כשצריך.  
  בדיקה: `backend_lite/tests/test_phase3_insights.py::test_insight_do_not_ask_for_low_verifiability_high_risk`

## Phase 4 — Cross-Exam Plan
- **PASS** — תכנית מדורגת (early/mid/late) ומכבדת prerequisites.  
  בדיקה: `backend_lite/tests/test_phase4_planner.py::test_planner_respects_prerequisites_and_branches`
- **PASS** — צעדים כוללים anchors ומפנים לסתירות/insights.  
  בדיקה: `backend_lite/tests/test_phase4_planner.py::test_build_cross_exam_plan_generates_steps`
- **PASS** — הסתעפויות קיימות עבור: “לא זוכר / טעיתי / לא הבנתי / זה לא מה שאמרתי”.  
  בדיקה: `backend_lite/tests/test_phase4_planner.py::test_planner_respects_prerequisites_and_branches`

## Phase 5 — Export
- **PASS** — יצוא DOCX עובד מקצה לקצה.  
  בדיקה: `backend_lite/tests/test_phase5_export.py::test_export_docx_and_pdf_bytes`
- **PASS** — ציטוטים תואמים anchors (doc/page/paragraph/snippet).  
  בדיקה ידנית: לפתוח DOCX ולוודא התאמה לעוגנים.
- **PASS** — מבנה היצוא כולל: פרטי תיק, סתירות מדורגות, סטיות גרסה, תכנית חקירה, נספח.  
  בדיקה: `backend_lite/tests/test_phase5_export.py::test_export_docx_and_pdf_bytes`
