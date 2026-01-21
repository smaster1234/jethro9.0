"""
Tests for Input Sanitizer Module

Tests:
- sanitize_input removes report artifacts
- contains_system_text detects system markers
- is_signature_block filters contact info
- Integration with extractor
"""

import pytest
from backend_lite.sanitize import (
    sanitize_input,
    contains_system_text,
    is_signature_block,
    sanitize_claim_text,
    sanitize_quote,
    SYSTEM_MARKERS
)


class TestSanitizeInput:
    """Tests for sanitize_input function"""

    def test_removes_report_header(self):
        """Report header should be removed"""
        text = """תוכן משפטי חשוב.

תוצאות הניתוח
סה"כ טענות: 10
סתירות: 2

טענה אמיתית נוספת."""

        result = sanitize_input(text)
        assert "תוצאות הניתוח" not in result
        assert "תוכן משפטי חשוב" in result
        assert "טענה אמיתית נוספת" in result

    def test_removes_metadata_section(self):
        """Metadata section should be removed"""
        text = """תצהיר עדות ראשית

מטא-דאטה
analysis_id: abc123
processing_time_ms: 150
duration_ms: 200

סעיף 1: התובע מצהיר."""

        result = sanitize_input(text)
        assert "מטא-דאטה" not in result
        assert "analysis_id" not in result
        assert "duration_ms" not in result
        assert "תצהיר עדות ראשית" in result
        assert "התובע מצהיר" in result

    def test_removes_claims_table(self):
        """Claims table should be removed"""
        text = """מסמך חשוב.

טבלת טענות
ID\tטקסט\tסטטוס
claim_1\tטענה ראשונה\tבעיה
claim_2\tטענה שנייה\tתקין

סעיף נוסף במסמך."""

        result = sanitize_input(text)
        assert "טבלת טענות" not in result
        assert "claim_1" not in result
        assert "claim_2" not in result
        assert "מסמך חשוב" in result
        assert "סעיף נוסף" in result

    def test_removes_cross_exam_section(self):
        """Cross-exam section should be removed"""
        text = """טענה 1.

שאלות לחקירה נגדית
1. שאלה ראשונה?
2. שאלה שנייה?

טענה 2."""

        result = sanitize_input(text)
        assert "שאלות לחקירה נגדית" not in result
        assert "טענה 1" in result
        assert "טענה 2" in result

    def test_removes_llm_markers(self):
        """LLM markers should be removed"""
        text = """טענה אמיתית.

LLM_enhanced: true
LLM_confidence: 0.95
validation_flags: []

טענה נוספת."""

        result = sanitize_input(text)
        assert "LLM_" not in result
        assert "validation_flags" not in result
        assert "טענה אמיתית" in result

    def test_removes_contr_markers(self):
        """Contradiction markers should be removed"""
        text = """תוכן משפטי.

contr_1\tסתירה בתאריך
contr_2\tסתירה בסכום

תוכן נוסף."""

        result = sanitize_input(text)
        assert "contr_1" not in result
        assert "contr_2" not in result
        assert "תוכן משפטי" in result

    def test_preserves_legal_content(self):
        """Legal document content should be preserved"""
        text = """תצהיר עדות ראשית

אני הח"מ, יוסי כהן, ת.ז. 123456789, לאחר שהוזהרתי כי עלי לומר
את האמת וכי אהיה צפוי לעונשים הקבועים בחוק אם לא אעשה כן,
מצהיר בזאת כדלקמן:

1. ביום 15.03.2024 נחתם הסכם בין הצדדים.
2. התמורה עמדה על 50,000 ש"ח.
3. המסמך נמסר לנתבע ביום 20.03.2024.

ולראיה באתי על החתום:
_____________
יוסי כהן"""

        result = sanitize_input(text)
        # Should preserve all content
        assert "תצהיר עדות ראשית" in result
        assert "15.03.2024" in result
        assert "50,000 ש\"ח" in result
        assert "יוסי כהן" in result

    def test_handles_empty_input(self):
        """Empty input should return empty string"""
        assert sanitize_input("") == ""
        assert sanitize_input(None) == ""
        assert sanitize_input("   ") == ""

    def test_full_report_cleanup(self):
        """Full report mixed with content should be cleaned"""
        text = """הסכם מכר

תוצאות הניתוח
===============
Claims Checked: 5
Contradictions Found: 1

טבלת טענות
-----------
claim_1\tנחתם ב-2023
claim_2\tנחתם ב-2024

סתירות קשורות
-------------
contr_1\tתאריכים

הצדדים הסכימו על:
1. מחיר: 100,000 ש"ח
2. מועד: 01.06.2024"""

        result = sanitize_input(text)

        # Report sections removed
        assert "תוצאות הניתוח" not in result
        assert "טבלת טענות" not in result
        assert "claim_1" not in result
        assert "Contradictions Found" not in result
        assert "סתירות קשורות" not in result

        # Legal content preserved
        assert "הסכם מכר" in result
        assert "100,000 ש\"ח" in result


class TestContainsSystemText:
    """Tests for contains_system_text function"""

    def test_detects_hebrew_markers(self):
        """Should detect Hebrew system markers"""
        assert contains_system_text("תוצאות הניתוח")
        assert contains_system_text("מטא-דאטה")
        assert contains_system_text("טבלת טענות")
        assert contains_system_text("פרטי הטענה")
        assert contains_system_text("סתירות קשורות")
        assert contains_system_text("שאלות לחקירה נגדית")

    def test_detects_english_markers(self):
        """Should detect English system markers"""
        assert contains_system_text("LLM_enhanced")
        assert contains_system_text("claim_123")
        assert contains_system_text("contr_456")
        assert contains_system_text("analysis_id")
        assert contains_system_text("processing_time_ms")
        assert contains_system_text("validation_flags")
        assert contains_system_text("Claims Checked")
        assert contains_system_text("Contradictions Found")

    def test_clean_text_returns_false(self):
        """Clean legal text should return False"""
        assert not contains_system_text("תצהיר עדות ראשית")
        assert not contains_system_text("הסכם נחתם ביום 15.03.2024")
        assert not contains_system_text("סכום העסקה: 50,000 ש\"ח")
        assert not contains_system_text("התובע טוען כי הנתבע הפר את ההסכם")

    def test_empty_returns_false(self):
        """Empty/None should return False"""
        assert not contains_system_text("")
        assert not contains_system_text(None)


class TestIsSignatureBlock:
    """Tests for is_signature_block function"""

    def test_detects_phone_fax(self):
        """Should detect phone/fax numbers"""
        assert is_signature_block("טל: 03-1234567 פקס: 03-7654321")
        assert is_signature_block("נייד: 050-1234567")

    def test_detects_email(self):
        """Should detect email addresses"""
        assert is_signature_block('דוא"ל: lawyer@example.com')
        assert is_signature_block("contact@firm.co.il")

    def test_detects_closing_phrases(self):
        """Should detect closing phrases"""
        text = """בכבוד רב,
עו"ד ישראל כהן"""
        assert is_signature_block(text)

        assert is_signature_block("בברכה")

    def test_detects_electronic_signature(self):
        """Should detect electronic signature markers"""
        assert is_signature_block("[נחתם אלקטרונית]")

    def test_legal_content_not_filtered(self):
        """Legal content should not be flagged as signature"""
        assert not is_signature_block("ביום 15.03.2024 נחתם הסכם בין הצדדים.")
        assert not is_signature_block("התובע שילם לנתבע סך של 50,000 ש\"ח.")
        assert not is_signature_block("הנתבע התחייב למסור את הנכס תוך 30 יום.")


class TestSanitizeClaimText:
    """Tests for sanitize_claim_text function"""

    def test_removes_system_markers(self):
        """Should remove system markers from claim text"""
        text = "טענה claim_1 שהוגשה"
        result = sanitize_claim_text(text)
        assert "claim_" not in result

    def test_truncates_long_text(self):
        """Should truncate text to max_length"""
        long_text = "א" * 600
        result = sanitize_claim_text(long_text, max_length=500)
        assert len(result) <= 503  # +3 for "..."
        assert result.endswith("...")

    def test_preserves_short_text(self):
        """Should preserve text under limit"""
        short_text = "טענה קצרה ופשוטה."
        result = sanitize_claim_text(short_text)
        assert result == short_text

    def test_handles_empty(self):
        """Should handle empty input"""
        assert sanitize_claim_text("") == ""
        assert sanitize_claim_text(None) == ""


class TestSanitizeQuote:
    """Tests for sanitize_quote function"""

    def test_returns_empty_for_system_text(self):
        """Should return empty for quotes with system text"""
        assert sanitize_quote("טבלת טענות - טענה 1") == ""
        assert sanitize_quote("claim_1: טענה") == ""

    def test_truncates_long_quotes(self):
        """Should truncate to 200 chars by default"""
        long_quote = "א" * 300
        result = sanitize_quote(long_quote)
        assert len(result) <= 203

    def test_preserves_clean_quotes(self):
        """Should preserve clean quotes"""
        clean = "ההסכם נחתם ביום 15.03.2024"
        result = sanitize_quote(clean)
        assert "15.03.2024" in result

    def test_handles_empty(self):
        """Should handle empty input"""
        assert sanitize_quote("") == ""
        assert sanitize_quote(None) == ""


class TestIntegration:
    """Integration tests with extractor"""

    def test_extractor_uses_sanitize(self):
        """Extractor should use sanitize_input"""
        from backend_lite.extractor import extract_claims

        text = """תצהיר עדות

תוצאות הניתוח
claim_1\tטענה
claim_2\tטענה

סעיף 1: התובע טוען כי הנתבע הפר את ההסכם ביום 15.03.2024
כאשר לא שילם את הסכום המוסכם בסך 50,000 ש"ח."""

        claims = extract_claims(text)

        # Should have extracted claims
        assert len(claims) > 0

        # No claim should contain system text
        for claim in claims:
            assert not contains_system_text(claim.text), f"Claim contains system text: {claim.text[:50]}"

    def test_full_report_not_extracted(self):
        """Full report output should not produce claims"""
        from backend_lite.extractor import extract_claims

        report_only = """תוצאות הניתוח
Claims Checked: 5
Contradictions Found: 1

טבלת טענות
ID\tטקסט\tסטטוס
claim_1\tטענה ראשונה\tבעיה
claim_2\tטענה שנייה\tתקין

סתירות קשורות
contr_1\tסתירה בתאריך

שאלות לחקירה נגדית
1. שאלה?"""

        claims = extract_claims(report_only)

        # Should produce no claims or all claims should be clean
        for claim in claims:
            assert not contains_system_text(claim.text)
