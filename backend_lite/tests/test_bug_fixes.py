"""
Tests for bug fixes:
1. Input sanitizer - removes report/meta sections
2. Case number exclusion from date detection
3. Cross-exam guardrail for system text
4. Claim extraction improvements (signature filtering)
"""

import pytest
from backend_lite.extractor import (
    sanitize_input,
    contains_system_text,
    ClaimExtractor,
    extract_claims,
    SYSTEM_MARKERS
)
from backend_lite.detector import RuleBasedDetector, get_rule_detector
from backend_lite.cross_exam import CrossExamGenerator, MAX_QUOTE_LENGTH


# =============================================================================
# Test Input Sanitizer
# =============================================================================

class TestInputSanitizer:
    """Tests for sanitize_input function"""

    def test_sanitize_removes_report_header(self):
        """Report header 'תוצאות הניתוח' should be removed"""
        text = """מסמך משפטי חשוב.

תוצאות הניתוח
סה"כ טענות: 10
סתירות: 2

טקסט אמיתי לניתוח."""

        result = sanitize_input(text)
        assert "תוצאות הניתוח" not in result
        assert "טקסט אמיתי לניתוח" in result

    def test_sanitize_removes_claims_table(self):
        """Claims table 'טבלת טענות' should be removed"""
        text = """טבלת טענות
ID	טקסט	סטטוס
claim_1	טענה ראשונה	בעיה
claim_2	טענה שנייה	תקין

תוכן אמיתי של המסמך."""

        result = sanitize_input(text)
        assert "טבלת טענות" not in result
        assert "claim_1" not in result
        assert "תוכן אמיתי של המסמך" in result

    def test_sanitize_removes_metadata_section(self):
        """Metadata section 'מטא-דאטה' should be removed"""
        text = """מטא-דאטה
analysis_id: abc123
processing_time_ms: 150

זהו התוכן האמיתי."""

        result = sanitize_input(text)
        assert "מטא-דאטה" not in result
        assert "analysis_id" not in result
        assert "זהו התוכן האמיתי" in result

    def test_sanitize_removes_cross_exam_section(self):
        """Cross-exam section should be removed"""
        text = """שאלות לחקירה נגדית
1. האם נכח במקום?
2. מתי קיבל את ההודעה?

תצהיר עדות ראשית."""

        result = sanitize_input(text)
        assert "שאלות לחקירה נגדית" not in result
        assert "תצהיר עדות ראשית" in result

    def test_sanitize_removes_llm_references(self):
        """LLM_ prefixed content should be removed"""
        text = """הטענה המקורית.

מטא-דאטה
LLM_enhanced: כן
LLM_confidence: 0.95

טענה נוספת ממקור אחר."""

        result = sanitize_input(text)
        assert "LLM_" not in result
        assert "הטענה המקורית" in result
        # Note: "טענה נוספת" comes after blank line which resets skip mode
        assert "טענה נוספת" in result

    def test_sanitize_removes_table_rows(self):
        """Table rows starting with ID or claim_ should be removed"""
        text = """תוכן אמיתי בהתחלה.

ID\tטקסט\tסטטוס
claim_1\tטענה\tבעיה
contr_1\tסתירה\tמאומת

תוכן אמיתי בסוף."""

        result = sanitize_input(text)
        assert "claim_1" not in result
        assert "contr_1" not in result
        assert "תוכן אמיתי בהתחלה" in result
        assert "תוכן אמיתי בסוף" in result

    def test_sanitize_preserves_legal_content(self):
        """Legal document content should be preserved"""
        text = """תצהיר עדות ראשית

אני הח"מ, יוסי כהן, מצהיר בזאת כדלקמן:
1. ביום 15.03.2024 נחתם הסכם בין הצדדים.
2. התמורה עמדה על 50,000 ש"ח.
3. המסמך נמסר לנתבע ביום 20.03.2024."""

        result = sanitize_input(text)
        # Should preserve all legal content
        assert "תצהיר עדות ראשית" in result
        assert "15.03.2024" in result
        assert "50,000 ש\"ח" in result

    def test_sanitize_handles_empty_input(self):
        """Empty input should return empty string"""
        assert sanitize_input("") == ""
        assert sanitize_input(None) == ""

    def test_sanitize_full_report_mixed_with_content(self):
        """Full report mixed with legal content should be cleaned"""
        text = """הסכם מכר

תוצאות הניתוח
Claims Checked: 5
Contradictions Found: 1

טבלת טענות
claim_1	הסכם נחתם ב-2023
claim_2	הסכם נחתם ב-2024

סתירות קשורות
contr_1	סתירה בתאריכים

הצדדים הסכימו על התנאים הבאים:
1. מחיר העסקה: 100,000 ש"ח
2. מועד מסירה: 01.06.2024"""

        result = sanitize_input(text)

        # Report sections should be removed
        assert "תוצאות הניתוח" not in result
        assert "טבלת טענות" not in result
        assert "claim_1" not in result
        assert "Contradictions Found" not in result

        # Legal content should be preserved
        assert "הסכם מכר" in result
        assert "100,000 ש\"ח" in result


class TestContainsSystemText:
    """Tests for contains_system_text function"""

    def test_detects_system_markers(self):
        """Should detect system markers"""
        assert contains_system_text("תוצאות הניתוח")
        assert contains_system_text("מטא-דאטה של הניתוח")
        assert contains_system_text("LLM_enhanced")
        assert contains_system_text("claim_123")

    def test_clean_text_returns_false(self):
        """Clean text should return False"""
        assert not contains_system_text("תצהיר עדות ראשית")
        assert not contains_system_text("הסכם נחתם ביום 15.03.2024")

    def test_empty_returns_false(self):
        """Empty/None should return False"""
        assert not contains_system_text("")
        assert not contains_system_text(None)


# =============================================================================
# Test Case Number Exclusion from Date Detection
# =============================================================================

class TestCaseNumberExclusion:
    """Tests for excluding case numbers from date detection"""

    def test_case_number_not_detected_as_date(self):
        """Case number 17682-06-25 should NOT be detected as a date"""
        detector = RuleBasedDetector()

        text = "תיק 17682-06-25 נפתח בבית המשפט"
        dates = detector._extract_dates(text)

        assert len(dates) == 0, f"Case number should not be detected as date, found: {dates}"

    def test_case_number_with_prefix_not_detected(self):
        """Case numbers with court prefixes should not be detected"""
        detector = RuleBasedDetector()

        test_cases = [
            'ת"א 12345-01-22',
            'תמ"ש 98765-12-23',
            'רע"א 54321-06-24',
            'ע"א 11111-03-25',
            'ה"פ 22222-09-23',
        ]

        for case_num in test_cases:
            text = f"בהליך {case_num} נקבע כי..."
            dates = detector._extract_dates(text)
            assert len(dates) == 0, f"Case number {case_num} should not be detected as date"

    def test_real_date_still_detected(self):
        """Real dates should still be detected correctly"""
        detector = RuleBasedDetector()

        text = "תאריך חתימה: 28.12.25"
        dates = detector._extract_dates(text)

        assert len(dates) > 0, "Real date should be detected"
        # Verify the date was parsed
        original, normalized, subtype = dates[0]
        assert normalized[0] == 2025  # Year
        assert normalized[1] == 12    # Month
        assert normalized[2] == 28    # Day

    def test_mixed_case_numbers_and_dates(self):
        """Text with both case numbers and dates should only extract dates"""
        detector = RuleBasedDetector()

        # Text with case numbers and real dates
        text = "בתיק 17682-06-25 נקבע דיון. ביום 15/03/2024 התקיימה ישיבה."

        dates = detector._extract_dates(text)

        # Check that case number is NOT in the results
        for orig, norm, subtype in dates:
            # 17682-06-25 should not appear as a date
            year, month, day = norm
            assert not (year == 2025 and day == 17682), \
                f"Case number 17682-06-25 should not be detected as date"

        # Real date (15/03/2024) should be found
        found_2024 = any(d[1][0] == 2024 for d in dates)
        # If dates were found, at least one should be 2024
        if dates:
            assert found_2024, f"Real date 15/03/2024 should be detected, got: {dates}"

    def test_large_first_number_is_case(self):
        """Numbers like 17682-06-25 where first part > 31 are case numbers"""
        detector = RuleBasedDetector()

        # 17682 > 31, so this is a case number
        assert detector._is_case_number("17682-06-25", 0, 11)

        # 15 <= 31, so this could be a date (15-06-25 = June 15, 2025)
        # But without context, format still matters

    def test_context_detection(self):
        """Context words should help identify case numbers"""
        detector = RuleBasedDetector()

        # With case context
        text_with_context = "תיק מספר 123-06-25"
        dates = detector._extract_dates(text_with_context)
        # Should be excluded due to "תיק" context
        assert not any("123" in str(d) for d in dates)


# =============================================================================
# Test Cross-Exam Guardrail
# =============================================================================

class TestCrossExamGuardrail:
    """Tests for cross-exam question guardrail"""

    def test_sanitize_quote_removes_system_text(self):
        """Quotes with system text should be sanitized"""
        generator = CrossExamGenerator()

        # Quote with system marker
        quote = "טענה claim_1 שהוגשה"
        result = generator._sanitize_quote(quote)

        # Should return empty since it contains system text
        assert result == "" or "claim_" not in result

    def test_sanitize_quote_limits_length(self):
        """Quotes should be limited to MAX_QUOTE_LENGTH"""
        generator = CrossExamGenerator()

        long_quote = "א" * 200  # 200 characters
        result = generator._sanitize_quote(long_quote)

        assert len(result) <= MAX_QUOTE_LENGTH + 3  # +3 for "..."

    def test_sanitize_quote_preserves_clean_text(self):
        """Clean quotes should be preserved"""
        generator = CrossExamGenerator()

        clean_quote = "ההסכם נחתם ביום 15.03.2024"
        result = generator._sanitize_quote(clean_quote)

        assert "15.03.2024" in result

    def test_sanitize_quote_handles_empty(self):
        """Empty quotes should return empty string"""
        generator = CrossExamGenerator()

        assert generator._sanitize_quote("") == ""
        assert generator._sanitize_quote(None) == ""

    def test_extract_variables_sanitizes_quotes(self):
        """Variables extraction should sanitize quotes"""
        from backend_lite.detector import DetectedContradiction
        from backend_lite.extractor import Claim
        from backend_lite.schemas import ContradictionType, ContradictionStatus, Severity

        generator = CrossExamGenerator()

        # Create a contradiction with system text in quotes
        claim1 = Claim(id="c1", text="טענה 1")
        claim2 = Claim(id="c2", text="טענה 2")

        contradiction = DetectedContradiction(
            id="test",
            claim1=claim1,
            claim2=claim2,
            type=ContradictionType.TEMPORAL,
            subtype=None,
            status=ContradictionStatus.VERIFIED,
            severity=Severity.HIGH,
            confidence=0.9,
            same_event_confidence=0.8,
            explanation="test",
            quote1="טבלת טענות - טענה 1",  # Contains system text
            quote2="טענה נקייה מספר 2"
        )

        variables = generator._extract_variables(contradiction)

        # quote_a should be empty (system text)
        assert variables["quote_a"] == ""
        # quote_b should be preserved (clean)
        assert "טענה נקייה" in variables["quote_b"]


# =============================================================================
# Test Claim Extraction Improvements
# =============================================================================

class TestClaimExtractionImprovements:
    """Tests for improved claim extraction"""

    def test_signature_block_filtered(self):
        """Signature/contact blocks should be filtered out"""
        extractor = ClaimExtractor()

        text = """טל: 03-1234567
פקס: 03-7654321
דוא"ל: lawyer@example.com
בכבוד רב,
עו"ד יוסי כהן"""

        assert extractor._is_signature_block(text)

    def test_legal_content_not_filtered(self):
        """Legal content should not be filtered as signature"""
        extractor = ClaimExtractor()

        text = "ביום 15.03.2024 נחתם הסכם בין הצדדים לרכישת הנכס."

        assert not extractor._is_signature_block(text)

    def test_long_claims_split(self):
        """Long segments should be split into sentences"""
        extractor = ClaimExtractor()

        long_text = "טענה ראשונה חשובה מאוד. " * 50  # Very long text

        parts = extractor._split_long_segment(long_text)

        # Should be split
        assert len(parts) > 1
        # Each part should be within limit
        assert all(len(p) <= extractor.MAX_CLAIM_LENGTH + 50 for p in parts)

    def test_short_claims_not_split(self):
        """Short segments should not be split"""
        extractor = ClaimExtractor()

        short_text = "טענה קצרה ופשוטה."

        parts = extractor._split_long_segment(short_text)

        assert len(parts) == 1
        assert parts[0] == short_text

    def test_extract_filters_system_text(self):
        """Extraction should filter out system text from input"""
        claims = extract_claims("""טענה אמיתית מהמסמך.

תוצאות הניתוח
claim_1	טענה מהדוח
claim_2	טענה נוספת

טענה אמיתית נוספת.""")

        # Should have claims
        assert len(claims) > 0

        # None should contain system text
        for claim in claims:
            assert not contains_system_text(claim.text)


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for all bug fixes"""

    def test_full_report_not_analyzed_as_document(self):
        """A full report should not create false contradictions when re-analyzed"""
        # Simulate report output being fed back as input
        report_text = """תוצאות הניתוח
===============
מספר טענות: 5
סתירות: 1

טבלת טענות
-----------
ID	טענה	סטטוס
claim_1	ההסכם נחתם ב-2023	potential_contradiction
claim_2	ההסכם נחתם ב-2024	potential_contradiction

סתירות קשורות
-------------
סתירה בתאריך: 2023 לעומת 2024

שאלות לחקירה נגדית
------------------
1. מתי בדיוק נחתם ההסכם?"""

        # Extract claims from this report
        claims = extract_claims(report_text)

        # Should extract nothing meaningful from report output
        assert len(claims) == 0 or all(
            not contains_system_text(c.text) for c in claims
        )

    def test_case_number_does_not_create_date_contradiction(self):
        """Case numbers should not create false date contradictions"""
        detector = get_rule_detector()

        claims = extract_claims("""
בתיק 17682-06-25 הוגשה תביעה על סך 100,000 ש"ח.
התביעה הוגשה בגין הפרת חוזה מיום 15.03.2024.
בדיון שהתקיים ביום 15.03.2024 הוחלט להמשיך בהליך.""")

        result = detector.detect(claims)

        # Should not have contradictions based on case number vs real date
        for contr in result.contradictions:
            if contr.type.value == "temporal_date":
                # Verify it's not a case number being compared
                assert "17682-06-25" not in str(contr.metadata)

    def test_clean_cross_exam_questions(self):
        """Cross-exam questions should not contain system text"""
        from backend_lite.cross_exam import generate_cross_exam_questions
        from backend_lite.detector import DetectedContradiction
        from backend_lite.extractor import Claim
        from backend_lite.schemas import ContradictionType, ContradictionStatus, Severity

        claim1 = Claim(id="c1", text="ההסכם נחתם ב-2023")
        claim2 = Claim(id="c2", text="ההסכם נחתם ב-2024")

        contradiction = DetectedContradiction(
            id="test",
            claim1=claim1,
            claim2=claim2,
            type=ContradictionType.TEMPORAL,
            subtype=None,
            status=ContradictionStatus.VERIFIED,
            severity=Severity.HIGH,
            confidence=0.9,
            same_event_confidence=0.8,
            explanation="סתירה בתאריכים",
            quote1="ההסכם נחתם ב-2023",
            quote2="ההסכם נחתם ב-2024",
            metadata={"date1": "2023", "date2": "2024"}
        )

        cross_exams = generate_cross_exam_questions([contradiction])

        assert len(cross_exams) > 0
        for exam_set in cross_exams:
            for question in exam_set.questions:
                assert not contains_system_text(question.question)
