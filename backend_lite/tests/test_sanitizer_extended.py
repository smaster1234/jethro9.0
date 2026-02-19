"""
Extended Logical Tests — Sanitizer & Utilities
================================================

~50 tests covering:
- sanitize_input function
- contains_system_text function
- is_signature_block function
- sanitize_claim_text function
- sanitize_quote function
- System markers detection
- Report table pattern detection
- Edge cases
"""

import pytest
from backend_lite.sanitize import (
    sanitize_input,
    contains_system_text,
    is_signature_block,
    sanitize_claim_text,
    sanitize_quote,
    SYSTEM_MARKERS,
    REPORT_TABLE_PATTERNS,
    SIGNATURE_PATTERNS,
)


# ===================================================================
# 1. SYSTEM_MARKERS Constants
# ===================================================================

class TestSystemMarkers:
    def test_markers_is_set(self):
        assert isinstance(SYSTEM_MARKERS, set)

    def test_markers_not_empty(self):
        assert len(SYSTEM_MARKERS) > 0

    def test_hebrew_markers_present(self):
        assert "תוצאות הניתוח" in SYSTEM_MARKERS
        assert "מטא-דאטה" in SYSTEM_MARKERS

    def test_english_markers_present(self):
        assert "LLM_" in SYSTEM_MARKERS
        assert "claim_" in SYSTEM_MARKERS
        assert "contr_" in SYSTEM_MARKERS

    def test_metadata_markers(self):
        assert "analysis_id" in SYSTEM_MARKERS
        assert "processing_time_ms" in SYSTEM_MARKERS


# ===================================================================
# 2. REPORT_TABLE_PATTERNS
# ===================================================================

class TestReportTablePatterns:
    def test_patterns_is_list(self):
        assert isinstance(REPORT_TABLE_PATTERNS, list)

    def test_patterns_not_empty(self):
        assert len(REPORT_TABLE_PATTERNS) > 0

    def test_id_tab_pattern_matches(self):
        assert REPORT_TABLE_PATTERNS[0].match("ID\tsomething")

    def test_claim_row_pattern_matches(self):
        assert REPORT_TABLE_PATTERNS[1].match("claim_001")

    def test_contr_row_pattern_matches(self):
        assert REPORT_TABLE_PATTERNS[2].match("contr_001")

    def test_normal_text_no_match(self):
        for pattern in REPORT_TABLE_PATTERNS:
            assert not pattern.match("הנתבע טען כי שילם")


# ===================================================================
# 3. SIGNATURE_PATTERNS
# ===================================================================

class TestSignaturePatterns:
    def test_patterns_is_list(self):
        assert isinstance(SIGNATURE_PATTERNS, list)

    def test_phone_pattern(self):
        assert any(p.search("טל: 03-1234567") for p in SIGNATURE_PATTERNS)

    def test_email_pattern(self):
        assert any(p.search("test@example.com") for p in SIGNATURE_PATTERNS)

    def test_regards_pattern(self):
        assert any(p.search("בכבוד רב") for p in SIGNATURE_PATTERNS)

    def test_blessing_pattern(self):
        assert any(p.search("בברכה") for p in SIGNATURE_PATTERNS)


# ===================================================================
# 4. sanitize_input
# ===================================================================

class TestSanitizeInput:
    def test_empty_input(self):
        assert sanitize_input("") == ""

    def test_none_like_input(self):
        assert sanitize_input("") == ""

    def test_clean_text_unchanged(self):
        text = "הנתבע טען כי שילם את הסכום"
        result = sanitize_input(text)
        assert result == text

    def test_system_marker_section_removed(self):
        text = "תוכן משפטי\nתוצאות הניתוח\nשורת תוצאה\n\nתוכן נוסף"
        result = sanitize_input(text)
        assert "תוצאות הניתוח" not in result
        assert "שורת תוצאה" not in result
        assert "תוכן נוסף" in result

    def test_report_table_rows_removed(self):
        text = "תוכן משפטי\nclaim_001 some data\nתוכן נוסף"
        result = sanitize_input(text)
        assert "claim_001" not in result

    def test_contr_rows_removed(self):
        text = "תוכן משפטי\ncontr_001 some data\nתוכן נוסף"
        result = sanitize_input(text)
        assert "contr_001" not in result

    def test_section_skip_reset_on_empty_line(self):
        text = "תוכן לפני\nתוצאות הניתוח\nskipped line\n\nתוכן אחרי"
        result = sanitize_input(text)
        assert "תוכן אחרי" in result

    def test_multiple_system_sections(self):
        text = "legal\nתוצאות הניתוח\ndata\n\nlegal2\nמטא-דאטה\ndata2\n\nlegal3"
        result = sanitize_input(text)
        assert "legal" in result
        assert "legal3" in result

    def test_inline_marker_removed(self):
        text = "תוכן עם analysis_id בתוכו"
        result = sanitize_input(text)
        assert "analysis_id" not in result

    def test_preserves_structure(self):
        text = "line 1\n\nline 2\n\nline 3"
        result = sanitize_input(text)
        assert "line 1" in result
        assert "line 3" in result


# ===================================================================
# 5. contains_system_text
# ===================================================================

class TestContainsSystemText:
    def test_empty_text(self):
        assert contains_system_text("") is False

    def test_clean_text(self):
        assert contains_system_text("הנתבע טען כי שילם") is False

    def test_with_hebrew_marker(self):
        assert contains_system_text("תוצאות הניתוח: 5 סתירות") is True

    def test_with_english_marker(self):
        assert contains_system_text("LLM_mode: none") is True

    def test_with_claim_marker(self):
        assert contains_system_text("claim_001 detected") is True

    def test_with_contr_marker(self):
        assert contains_system_text("contr_001") is True

    def test_partial_match(self):
        # Markers use substring matching
        assert contains_system_text("some processing_time_ms data") is True


# ===================================================================
# 6. is_signature_block
# ===================================================================

class TestIsSignatureBlock:
    def test_empty_text(self):
        assert is_signature_block("") is False

    def test_phone_and_email(self):
        assert is_signature_block("טל: 03-1234567\ntest@test.com") is True

    def test_regards_short(self):
        assert is_signature_block("בכבוד רב") is True

    def test_normal_legal_text(self):
        assert is_signature_block("הנתבע טען כי שילם את הסכום המלא כפי שנקבע בהסכם") is False

    def test_lawyer_signature(self):
        text = 'עו"ד יוסי כהן'
        assert is_signature_block(text) is True

    def test_electronic_signature(self):
        assert is_signature_block("[נחתם אלקטרונית]") is True

    def test_po_box(self):
        assert is_signature_block("ת.ד. 12345") is True

    def test_postal_code(self):
        assert is_signature_block("מיקוד 12345") is True

    def test_long_text_with_one_pattern(self):
        text = "הנתבע טען כי שילם את הסכום המלא כפי שנקבע בהסכם " * 10 + "טל: 03-1234567"
        # Long text with only 1 signature pattern → not a signature block
        assert is_signature_block(text) is False


# ===================================================================
# 7. sanitize_claim_text
# ===================================================================

class TestSanitizeClaimText:
    def test_empty_text(self):
        assert sanitize_claim_text("") == ""

    def test_clean_text(self):
        result = sanitize_claim_text("הנתבע טען כי שילם")
        assert result == "הנתבע טען כי שילם"

    def test_markers_removed(self):
        result = sanitize_claim_text("text with LLM_ marker")
        assert "LLM_" not in result

    def test_whitespace_cleaned(self):
        result = sanitize_claim_text("text   with    extra   spaces")
        assert "   " not in result

    def test_truncation_at_word_boundary(self):
        long_text = "word " * 200  # ~1000 chars
        result = sanitize_claim_text(long_text, max_length=50)
        assert len(result) <= 53  # max_length + "..."
        assert result.endswith("...")

    def test_truncation_default(self):
        long_text = "word " * 200
        result = sanitize_claim_text(long_text)
        assert len(result) <= 503

    def test_short_text_not_truncated(self):
        text = "short text"
        result = sanitize_claim_text(text, max_length=500)
        assert result == text


# ===================================================================
# 8. sanitize_quote
# ===================================================================

class TestSanitizeQuote:
    def test_empty_quote(self):
        assert sanitize_quote("") == ""

    def test_clean_quote(self):
        result = sanitize_quote("הנתבע טען כי שילם")
        assert result == "הנתבע טען כי שילם"

    def test_system_text_returns_empty(self):
        result = sanitize_quote("תוצאות הניתוח: 5 סתירות")
        assert result == ""

    def test_truncation(self):
        long_text = "word " * 100
        result = sanitize_quote(long_text)
        assert len(result) <= 203

    def test_custom_max_length(self):
        long_text = "word " * 100
        result = sanitize_quote(long_text, max_length=50)
        assert len(result) <= 53
