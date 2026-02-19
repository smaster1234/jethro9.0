"""
Extended Logical Tests — Rule-Based Detector
=============================================

~100 tests covering:
- Date extraction & normalization
- Amount extraction & normalization
- Attribution extraction & conflict detection
- Presence/participation polarity
- Document existence polarity
- Identity extraction & conflicts
- Time (hour) extraction & conflicts
- Claims relatedness scoring
- Deduplication logic
- Edge cases & boundary conditions
"""

import pytest
from backend_lite.extractor import Claim
from backend_lite.detector import RuleBasedDetector, DetectedContradiction
from backend_lite.schemas import (
    ContradictionType,
    ContradictionSubtype,
    ContradictionStatus,
    Severity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(text: str, **kwargs) -> Claim:
    """Quick claim factory."""
    defaults = dict(
        id=kwargs.pop("id", f"c_{abs(hash(text)) % 100000}"),
        text=text,
    )
    defaults.update(kwargs)
    return Claim(**defaults)


@pytest.fixture
def detector():
    return RuleBasedDetector()


# ===================================================================
# 1. Date Extraction (_extract_dates)
# ===================================================================

class TestDateExtraction:
    """Test date extraction from Hebrew text."""

    def test_numeric_date_dd_mm_yyyy(self, detector):
        dates = detector._extract_dates("ההסכם נחתם ביום 15/01/2024")
        assert len(dates) >= 1
        _, norm, _ = dates[0]
        assert norm == (2024, 1, 15)

    def test_numeric_date_dd_dash_mm_dash_yyyy(self, detector):
        dates = detector._extract_dates("תאריך: 20-03-2023")
        assert len(dates) >= 1
        _, norm, _ = dates[0]
        assert norm == (2023, 3, 20)

    def test_numeric_date_dd_dot_mm_dot_yyyy(self, detector):
        dates = detector._extract_dates("ביום 05.12.2022 התקיימה הפגישה")
        assert len(dates) >= 1
        _, norm, _ = dates[0]
        assert norm == (2022, 12, 5)

    def test_short_year_below_50(self, detector):
        dates = detector._extract_dates("נחתם ב-01/06/23")
        assert len(dates) >= 1
        _, norm, _ = dates[0]
        assert norm[0] == 2023

    def test_short_year_above_50(self, detector):
        dates = detector._extract_dates("נחתם ב-01/06/95")
        assert len(dates) >= 1
        _, norm, _ = dates[0]
        assert norm[0] == 1995

    def test_hebrew_full_date(self, detector):
        dates = detector._extract_dates("15 בינואר 2024")
        assert len(dates) >= 1
        _, norm, _ = dates[0]
        assert norm == (2024, 1, 15)

    def test_hebrew_month_only(self, detector):
        dates = detector._extract_dates("באפריל 2023 החלה העבודה")
        assert len(dates) >= 1
        _, norm, _ = dates[0]
        assert norm == (2023, 4, 0)

    def test_hebrew_year_only(self, detector):
        dates = detector._extract_dates("בשנת 2020 שונה החוזה")
        assert len(dates) >= 1
        _, norm, _ = dates[0]
        assert norm == (2020, 0, 0)

    def test_no_dates_in_text(self, detector):
        dates = detector._extract_dates("הנתבע טען כי לא חתם על שום מסמך")
        assert len(dates) == 0

    def test_case_number_excluded(self, detector):
        dates = detector._extract_dates('תיק 17682-06-25')
        assert len(dates) == 0

    def test_case_number_with_prefix_excluded(self, detector):
        dates = detector._extract_dates('ת"א 12345-01-22')
        assert len(dates) == 0

    def test_multiple_dates_extracted(self, detector):
        dates = detector._extract_dates("מ-01/01/2020 ועד 31/12/2020")
        assert len(dates) >= 2

    def test_march_alternative_spelling(self, detector):
        dates = detector._extract_dates("5 במרס 2023")
        assert len(dates) >= 1
        _, norm, _ = dates[0]
        assert norm[1] == 3

    def test_all_hebrew_months(self, detector):
        months = {
            'ינואר': 1, 'פברואר': 2, 'מרץ': 3, 'אפריל': 4,
            'מאי': 5, 'יוני': 6, 'יולי': 7, 'אוגוסט': 8,
            'ספטמבר': 9, 'אוקטובר': 10, 'נובמבר': 11, 'דצמבר': 12,
        }
        for name, num in months.items():
            dates = detector._extract_dates(f"1 ב{name} 2024")
            assert len(dates) >= 1, f"Failed for month: {name}"
            _, norm, _ = dates[0]
            assert norm[1] == num, f"Wrong month number for {name}"


# ===================================================================
# 2. Date Conflict Detection (_dates_conflict)
# ===================================================================

class TestDateConflict:
    def test_different_years_conflict(self, detector):
        d1 = [("01/01/2020", (2020, 1, 1), ContradictionSubtype.EXACT_DATE)]
        d2 = [("01/01/2021", (2021, 1, 1), ContradictionSubtype.EXACT_DATE)]
        result = detector._dates_conflict(d1, d2)
        assert result is not None

    def test_different_months_conflict(self, detector):
        d1 = [("01/01/2020", (2020, 1, 1), ContradictionSubtype.EXACT_DATE)]
        d2 = [("01/03/2020", (2020, 3, 1), ContradictionSubtype.EXACT_DATE)]
        result = detector._dates_conflict(d1, d2)
        assert result is not None

    def test_different_days_conflict(self, detector):
        d1 = [("01/01/2020", (2020, 1, 1), ContradictionSubtype.EXACT_DATE)]
        d2 = [("15/01/2020", (2020, 1, 15), ContradictionSubtype.EXACT_DATE)]
        result = detector._dates_conflict(d1, d2)
        assert result is not None

    def test_same_dates_no_conflict(self, detector):
        d1 = [("01/01/2020", (2020, 1, 1), ContradictionSubtype.EXACT_DATE)]
        d2 = [("01/01/2020", (2020, 1, 1), ContradictionSubtype.EXACT_DATE)]
        result = detector._dates_conflict(d1, d2)
        assert result is None

    def test_unknown_day_no_conflict(self, detector):
        d1 = [("ינואר 2020", (2020, 1, 0), ContradictionSubtype.MONTH_ONLY)]
        d2 = [("15/01/2020", (2020, 1, 15), ContradictionSubtype.EXACT_DATE)]
        result = detector._dates_conflict(d1, d2)
        assert result is None

    def test_unknown_month_no_conflict(self, detector):
        d1 = [("שנת 2020", (2020, 0, 0), ContradictionSubtype.MONTH_ONLY)]
        d2 = [("מרץ 2020", (2020, 3, 0), ContradictionSubtype.MONTH_ONLY)]
        result = detector._dates_conflict(d1, d2)
        assert result is None


# ===================================================================
# 3. Date Formatting
# ===================================================================

class TestDateFormatting:
    def test_full_date_format(self, detector):
        assert detector._format_date((2024, 1, 15)) == "2024-01-15"

    def test_month_only_format(self, detector):
        assert detector._format_date((2024, 3, 0)) == "2024-03"

    def test_year_only_format(self, detector):
        assert detector._format_date((2024, 0, 0)) == "2024"


# ===================================================================
# 4. Case Number Detection
# ===================================================================

class TestCaseNumberDetection:
    def test_standard_case_number(self, detector):
        assert detector._is_case_number("תיק 17682-06-25", 4, 16) is True

    def test_five_digit_case_number(self, detector):
        assert detector._is_case_number("12345-01-22", 0, 11) is True

    def test_first_number_over_31(self, detector):
        assert detector._is_case_number("99-01-22", 0, 8) is True

    def test_valid_date_not_case_number(self, detector):
        result = detector._is_case_number("ביום 15-01-2024 נחתם", 4, 14)
        # 15 <= 31 and 01 <= 12, so depends on context
        # Without case context, it should be False
        assert result is False

    def test_context_after_makes_case_number(self, detector):
        text = "מספר 15-01-22 תיק בבית המשפט"
        assert detector._is_case_number(text, 5, 13) is True


# ===================================================================
# 5. Amount Extraction (_extract_amounts)
# ===================================================================

class TestAmountExtraction:
    def test_shekel_symbol(self, detector):
        amounts = detector._extract_amounts("סכום של ₪10,000")
        assert len(amounts) >= 1
        val, typ, _ = amounts[0]
        assert val == 10000
        assert typ == "shekel"

    def test_shekel_text(self, detector):
        amounts = detector._extract_amounts('סכום של 50,000 ש"ח')
        assert len(amounts) >= 1
        val, _, _ = amounts[0]
        assert val == 50000

    def test_dollar_symbol(self, detector):
        amounts = detector._extract_amounts("paid $5,000")
        assert len(amounts) >= 1
        val, typ, _ = amounts[0]
        assert val == 5000
        assert typ == "dollar"

    def test_dollar_text(self, detector):
        amounts = detector._extract_amounts("15,000 דולר")
        assert len(amounts) >= 1
        val, _, _ = amounts[0]
        assert val == 15000

    def test_thousands_multiplier(self, detector):
        amounts = detector._extract_amounts("50 אלף")
        assert len(amounts) >= 1
        val, _, _ = amounts[0]
        assert val == 50000

    def test_millions_multiplier(self, detector):
        amounts = detector._extract_amounts("2 מיליון")
        assert len(amounts) >= 1
        val, _, _ = amounts[0]
        assert val == 2000000

    def test_percentage(self, detector):
        amounts = detector._extract_amounts("ריבית של 5%")
        assert len(amounts) >= 1
        val, typ, sub = amounts[0]
        assert val == 5
        assert typ == "percent"
        assert sub == ContradictionSubtype.PERCENTAGE

    def test_percentage_hebrew(self, detector):
        amounts = detector._extract_amounts("25 אחוז מהסכום")
        assert len(amounts) >= 1
        val, _, _ = amounts[0]
        assert val == 25

    def test_duration_years(self, detector):
        amounts = detector._extract_amounts("תקופה של 3 שנים")
        assert len(amounts) >= 1
        val, _, sub = amounts[0]
        assert val == 3
        assert sub == ContradictionSubtype.DURATION

    def test_duration_months(self, detector):
        amounts = detector._extract_amounts("6 חודשים")
        assert len(amounts) >= 1
        val, _, _ = amounts[0]
        assert val == 6

    def test_duration_days(self, detector):
        amounts = detector._extract_amounts("30 ימים")
        assert len(amounts) >= 1
        val, _, _ = amounts[0]
        assert val == 30

    def test_count_times(self, detector):
        amounts = detector._extract_amounts("3 פעמים")
        assert len(amounts) >= 1
        val, _, sub = amounts[0]
        assert val == 3
        assert sub == ContradictionSubtype.COUNT

    def test_no_amounts_in_text(self, detector):
        amounts = detector._extract_amounts("הנתבע טען כי לא חתם על שום מסמך")
        assert len(amounts) == 0

    def test_decimal_amount(self, detector):
        amounts = detector._extract_amounts("₪10,500.50")
        assert len(amounts) >= 1
        val, _, _ = amounts[0]
        assert val == 10500.50


# ===================================================================
# 6. Amount Conflict Detection
# ===================================================================

class TestAmountConflict:
    def test_same_type_different_values(self, detector):
        a1 = [(10000, "shekel", ContradictionSubtype.CURRENCY)]
        a2 = [(50000, "shekel", ContradictionSubtype.CURRENCY)]
        result = detector._amounts_conflict(a1, a2)
        assert result is not None

    def test_same_values_no_conflict(self, detector):
        a1 = [(10000, "shekel", ContradictionSubtype.CURRENCY)]
        a2 = [(10000, "shekel", ContradictionSubtype.CURRENCY)]
        result = detector._amounts_conflict(a1, a2)
        assert result is None

    def test_different_types_no_conflict(self, detector):
        a1 = [(10000, "shekel", ContradictionSubtype.CURRENCY)]
        a2 = [(10000, "dollar", ContradictionSubtype.CURRENCY)]
        result = detector._amounts_conflict(a1, a2)
        assert result is None

    def test_small_difference_below_threshold(self, detector):
        a1 = [(100, "shekel", ContradictionSubtype.CURRENCY)]
        a2 = [(105, "shekel", ContradictionSubtype.CURRENCY)]
        result = detector._amounts_conflict(a1, a2)
        # 5% difference, threshold for <100 is 20% → no conflict
        assert result is None

    def test_percentage_conflict(self, detector):
        a1 = [(5, "percent", ContradictionSubtype.PERCENTAGE)]
        a2 = [(15, "percent", ContradictionSubtype.PERCENTAGE)]
        result = detector._amounts_conflict(a1, a2)
        assert result is not None


# ===================================================================
# 7. Adaptive Amount Threshold
# ===================================================================

class TestAdaptiveAmountThreshold:
    def test_small_amount_threshold(self):
        threshold = RuleBasedDetector._adaptive_amount_threshold(50, "shekel")
        assert threshold == 0.20

    def test_medium_amount_threshold(self):
        threshold = RuleBasedDetector._adaptive_amount_threshold(5000, "shekel")
        assert threshold == 0.10

    def test_large_amount_threshold(self):
        threshold = RuleBasedDetector._adaptive_amount_threshold(500000, "shekel")
        assert threshold == 0.05

    def test_very_large_amount_threshold(self):
        threshold = RuleBasedDetector._adaptive_amount_threshold(5000000, "shekel")
        assert threshold == 0.03

    def test_percent_threshold(self):
        threshold = RuleBasedDetector._adaptive_amount_threshold(50, "percent")
        assert threshold == 0.10


# ===================================================================
# 8. Amount Formatting
# ===================================================================

class TestAmountFormatting:
    def test_shekel_format(self, detector):
        assert detector._format_amount(10000, "shekel") == "₪10,000"

    def test_dollar_format(self, detector):
        assert detector._format_amount(5000, "dollar") == "$5,000"

    def test_percent_format(self, detector):
        assert detector._format_amount(15.5, "percent") == "15.5%"

    def test_generic_format(self, detector):
        result = detector._format_amount(42, "units")
        assert "42" in result


# ===================================================================
# 9. Attribution Extraction
# ===================================================================

class TestAttributionExtraction:
    def test_signer_pattern(self, detector):
        attrs = detector._extract_attributions("יוסי כהן חתם על ההסכם")
        assert len(attrs) >= 1
        name, subtype = attrs[0]
        assert subtype == ContradictionSubtype.SIGNER

    def test_sender_pattern(self, detector):
        attrs = detector._extract_attributions("דוד לוי שלח את ההודעה")
        assert len(attrs) >= 1
        name, subtype = attrs[0]
        assert subtype == ContradictionSubtype.SENDER

    def test_payer_pattern(self, detector):
        attrs = detector._extract_attributions("משה כהן שילם את הסכום")
        assert len(attrs) >= 1
        name, subtype = attrs[0]
        assert subtype == ContradictionSubtype.PAYER

    def test_decision_maker_pattern(self, detector):
        attrs = detector._extract_attributions("השופט החליט לדחות את הבקשה")
        assert len(attrs) >= 1

    def test_receiver_pattern(self, detector):
        attrs = detector._extract_attributions("רחל ישראלי קיבלה את ההודעה")
        assert len(attrs) >= 1
        name, subtype = attrs[0]
        assert subtype == ContradictionSubtype.RECEIVER

    def test_by_pattern(self, detector):
        attrs = detector._extract_attributions("הוגש על ידי יוסי כהן")
        assert len(attrs) >= 1

    def test_stopword_only_filtered(self, detector):
        # Attributions that are just stopwords should be filtered
        attrs = detector._extract_attributions("את של חתם על")
        # Should be filtered because captured name is stopword
        for name, _ in attrs:
            words = name.split()
            meaningful = [w for w in words if len(w) > 2 and w.lower() not in detector.stopwords]
            assert len(meaningful) > 0

    def test_no_attributions(self, detector):
        attrs = detector._extract_attributions("היום יום יפה")
        assert len(attrs) == 0


# ===================================================================
# 10. Attribution Conflict Detection
# ===================================================================

class TestAttributionConflict:
    def test_different_signers_conflict(self, detector):
        a1 = [("יוסי כהן", ContradictionSubtype.SIGNER)]
        a2 = [("דוד לוי", ContradictionSubtype.SIGNER)]
        result = detector._attributions_conflict(a1, a2)
        assert result is not None

    def test_same_signer_no_conflict(self, detector):
        a1 = [("יוסי כהן", ContradictionSubtype.SIGNER)]
        a2 = [("יוסי כהן", ContradictionSubtype.SIGNER)]
        result = detector._attributions_conflict(a1, a2)
        assert result is None

    def test_different_subtypes_no_conflict(self, detector):
        a1 = [("יוסי כהן", ContradictionSubtype.SIGNER)]
        a2 = [("דוד לוי", ContradictionSubtype.PAYER)]
        result = detector._attributions_conflict(a1, a2)
        assert result is None


# ===================================================================
# 11. Presence Polarity Detection
# ===================================================================

class TestPresencePolarity:
    def test_positive_was_present(self, detector):
        pol = detector._extract_presence_polarity("הוא היה נוכח בפגישה")
        assert pol is True

    def test_positive_attended(self, detector):
        pol = detector._extract_presence_polarity("נכחתי בישיבה")
        assert pol is True

    def test_positive_signed(self, detector):
        pol = detector._extract_presence_polarity("חתמתי על ההסכם")
        assert pol is True

    def test_positive_paid(self, detector):
        pol = detector._extract_presence_polarity("שילמתי את הסכום")
        assert pol is True

    def test_negative_was_not_present(self, detector):
        pol = detector._extract_presence_polarity("לא היה נוכח באותו יום")
        assert pol is False

    def test_negative_did_not_attend(self, detector):
        pol = detector._extract_presence_polarity("לא נכחתי בפגישה")
        assert pol is False

    def test_negative_never(self, detector):
        pol = detector._extract_presence_polarity("מעולם לא חתמתי על מסמך כזה")
        assert pol is False

    def test_negative_never_ever(self, detector):
        pol = detector._extract_presence_polarity("אף פעם לא שילמתי")
        assert pol is False

    def test_neutral_no_presence(self, detector):
        pol = detector._extract_presence_polarity("השמש זרחה היום")
        assert pol is None


# ===================================================================
# 12. Presence Subtype Determination
# ===================================================================

class TestPresenceSubtype:
    def test_signed_subtype(self, detector):
        sub = detector._determine_presence_subtype("חתם על המסמך", "לא חתם")
        assert sub == ContradictionSubtype.SIGNED

    def test_paid_subtype(self, detector):
        sub = detector._determine_presence_subtype("שילם את הכסף", "לא שילם")
        assert sub == ContradictionSubtype.PAID

    def test_attended_subtype(self, detector):
        sub = detector._determine_presence_subtype("היה נוכח", "לא נכח")
        assert sub == ContradictionSubtype.ATTENDED

    def test_received_subtype(self, detector):
        sub = detector._determine_presence_subtype("קיבל הודעה", "לא קיבלה")
        assert sub == ContradictionSubtype.RECEIVED

    def test_delivered_subtype(self, detector):
        sub = detector._determine_presence_subtype("מסר את המסמך", "לא מסרה")
        assert sub == ContradictionSubtype.DELIVERED

    def test_default_attended(self, detector):
        sub = detector._determine_presence_subtype("היה שם", "לא היה")
        assert sub == ContradictionSubtype.ATTENDED


# ===================================================================
# 13. Document Existence Polarity
# ===================================================================

class TestDocExistencePolarity:
    def test_positive_contract_exists(self, detector):
        pol = detector._extract_doc_existence_polarity("קיים הסכם בין הצדדים")
        assert pol is True

    def test_positive_signed_contract(self, detector):
        pol = detector._extract_doc_existence_polarity("נחתם הסכם ביום 1.1.2020")
        assert pol is True

    def test_positive_notice_sent(self, detector):
        pol = detector._extract_doc_existence_polarity("נשלחה הודעה לצד השני")
        assert pol is True

    def test_negative_no_contract(self, detector):
        pol = detector._extract_doc_existence_polarity("אין הסכם בין הצדדים")
        assert pol is False

    def test_negative_not_signed(self, detector):
        pol = detector._extract_doc_existence_polarity("לא נחתם הסכם")
        assert pol is False

    def test_negative_not_sent(self, detector):
        pol = detector._extract_doc_existence_polarity("לא נשלחה הודעה")
        assert pol is False

    def test_neutral_no_doc_mention(self, detector):
        pol = detector._extract_doc_existence_polarity("השמש זרחה היום")
        assert pol is None


# ===================================================================
# 14. Document Subtype Determination
# ===================================================================

class TestDocSubtype:
    def test_contract_subtype(self, detector):
        sub = detector._determine_doc_subtype("הסכם", "חוזה")
        assert sub == ContradictionSubtype.CONTRACT_EXISTS

    def test_notice_subtype(self, detector):
        sub = detector._determine_doc_subtype("הודעה", "מכתב")
        assert sub == ContradictionSubtype.NOTICE_SENT

    def test_email_subtype(self, detector):
        sub = detector._determine_doc_subtype('דוא"ל', "אימייל")
        assert sub == ContradictionSubtype.EMAIL_EXISTS

    def test_signature_subtype(self, detector):
        sub = detector._determine_doc_subtype("חתימה", "חתימה")
        assert sub == ContradictionSubtype.SIGNATURE_EXISTS

    def test_default_contract(self, detector):
        sub = detector._determine_doc_subtype("מסמך כלשהו", "טקסט כלשהו")
        assert sub == ContradictionSubtype.CONTRACT_EXISTS


# ===================================================================
# 15. Identity Extraction
# ===================================================================

class TestIdentityExtraction:
    def test_id_number_with_prefix(self, detector):
        ids = detector._extract_identities("ת.ז. 123456789")
        assert len(ids) >= 1
        id_num, id_type = ids[0]
        assert id_num == "123456789"
        assert id_type == "id_number"

    def test_id_full_text(self, detector):
        ids = detector._extract_identities("תעודת זהות: 987654321")
        assert len(ids) >= 1
        assert ids[0][0] == "987654321"

    def test_company_id(self, detector):
        ids = detector._extract_identities("ח.פ. 512345678")
        assert len(ids) >= 1
        _, id_type = ids[0]
        assert id_type == "company_id"

    def test_no_ids(self, detector):
        ids = detector._extract_identities("אין מספר זיהוי כאן")
        assert len(ids) == 0


# ===================================================================
# 16. Identity Conflict Detection
# ===================================================================

class TestIdentityConflict:
    def test_different_ids_same_type(self, detector):
        ids1 = [("123456789", "id_number")]
        ids2 = [("987654321", "id_number")]
        result = detector._identities_conflict(ids1, ids2)
        assert result is not None

    def test_same_ids_no_conflict(self, detector):
        ids1 = [("123456789", "id_number")]
        ids2 = [("123456789", "id_number")]
        result = detector._identities_conflict(ids1, ids2)
        assert result is None

    def test_different_types_no_conflict(self, detector):
        ids1 = [("123456789", "id_number")]
        ids2 = [("123456789", "company_id")]
        result = detector._identities_conflict(ids1, ids2)
        assert result is None


# ===================================================================
# 17. Time (Hour) Extraction
# ===================================================================

class TestTimeExtraction:
    def test_hhmm_format(self, detector):
        times = detector._extract_times("בשעה 10:30 התקיימה הפגישה")
        assert len(times) >= 1
        _, norm = times[0]
        assert norm == (10, 30)

    def test_24h_format(self, detector):
        times = detector._extract_times("בשעה 14:00 יצא מהמשרד")
        assert len(times) >= 1
        _, norm = times[0]
        assert norm[0] == 14

    def test_hour_only(self, detector):
        times = detector._extract_times("בשעה 9 בבוקר")
        assert len(times) >= 1

    def test_no_times(self, detector):
        times = detector._extract_times("היום יום שני")
        assert len(times) == 0


# ===================================================================
# 18. Time Conflict Detection
# ===================================================================

class TestTimeConflict:
    def test_different_hours_conflict(self, detector):
        t1 = [("10:00", (10, 0))]
        t2 = [("14:00", (14, 0))]
        result = detector._times_conflict(t1, t2)
        assert result is not None

    def test_same_time_no_conflict(self, detector):
        t1 = [("10:00", (10, 0))]
        t2 = [("10:00", (10, 0))]
        result = detector._times_conflict(t1, t2)
        assert result is None

    def test_small_difference_no_conflict(self, detector):
        # 1 hour difference with < 30 min → no conflict
        t1 = [("10:00", (10, 0))]
        t2 = [("11:00", (11, 0))]
        result = detector._times_conflict(t1, t2)
        assert result is None

    def test_same_hour_big_minute_diff(self, detector):
        t1 = [("10:00", (10, 0))]
        t2 = [("10:30", (10, 30))]
        result = detector._times_conflict(t1, t2)
        assert result is not None


# ===================================================================
# 19. Time Formatting
# ===================================================================

class TestTimeFormatting:
    def test_format_time_basic(self, detector):
        assert detector._format_time((10, 30)) == "10:30"

    def test_format_time_midnight(self, detector):
        assert detector._format_time((0, 0)) == "00:00"

    def test_format_time_single_digit(self, detector):
        assert detector._format_time((9, 5)) == "09:05"


# ===================================================================
# 20. Quote Extraction
# ===================================================================

class TestQuoteExtraction:
    def test_target_found(self, detector):
        text = "הנתבע טען כי שילם סכום של 50,000 ש\"ח ביום 1.1.2020"
        quote = detector._extract_quote_around(text, "50,000", context_chars=20)
        assert "50,000" in quote

    def test_target_not_found(self, detector):
        text = "הנתבע טען כי שילם סכום"
        quote = detector._extract_quote_around(text, "999,999", context_chars=20)
        # Should return first 200 chars
        assert len(quote) <= 200

    def test_ellipsis_added(self, detector):
        text = "A" * 300
        quote = detector._extract_quote_around(text, "A" * 10, context_chars=20)
        assert "..." in quote


# ===================================================================
# 21. Deduplication
# ===================================================================

class TestDeduplication:
    def test_same_pair_same_type_deduped(self, detector):
        c1 = _claim("טענה א", id="c1")
        c2 = _claim("טענה ב", id="c2")
        contrs = [
            DetectedContradiction(
                id="d1", claim1=c1, claim2=c2,
                type=ContradictionType.TEMPORAL_DATE,
                subtype=None, status=ContradictionStatus.VERIFIED,
                severity=Severity.HIGH, confidence=0.9,
                same_event_confidence=0.8, explanation="test",
                quote1="q1", quote2="q2",
            ),
            DetectedContradiction(
                id="d2", claim1=c1, claim2=c2,
                type=ContradictionType.TEMPORAL_DATE,
                subtype=None, status=ContradictionStatus.VERIFIED,
                severity=Severity.HIGH, confidence=0.9,
                same_event_confidence=0.8, explanation="test2",
                quote1="q1", quote2="q2",
            ),
        ]
        result = detector._deduplicate(contrs)
        assert len(result) == 1

    def test_same_pair_different_type_kept(self, detector):
        c1 = _claim("טענה א", id="c1")
        c2 = _claim("טענה ב", id="c2")
        contrs = [
            DetectedContradiction(
                id="d1", claim1=c1, claim2=c2,
                type=ContradictionType.TEMPORAL_DATE,
                subtype=None, status=ContradictionStatus.VERIFIED,
                severity=Severity.HIGH, confidence=0.9,
                same_event_confidence=0.8, explanation="test",
                quote1="q1", quote2="q2",
            ),
            DetectedContradiction(
                id="d2", claim1=c1, claim2=c2,
                type=ContradictionType.QUANT_AMOUNT,
                subtype=None, status=ContradictionStatus.VERIFIED,
                severity=Severity.HIGH, confidence=0.9,
                same_event_confidence=0.8, explanation="test2",
                quote1="q1", quote2="q2",
            ),
        ]
        result = detector._deduplicate(contrs)
        assert len(result) == 2

    def test_different_pairs_kept(self, detector):
        c1 = _claim("טענה א", id="c1")
        c2 = _claim("טענה ב", id="c2")
        c3 = _claim("טענה ג", id="c3")
        contrs = [
            DetectedContradiction(
                id="d1", claim1=c1, claim2=c2,
                type=ContradictionType.TEMPORAL_DATE,
                subtype=None, status=ContradictionStatus.VERIFIED,
                severity=Severity.HIGH, confidence=0.9,
                same_event_confidence=0.8, explanation="test",
                quote1="q1", quote2="q2",
            ),
            DetectedContradiction(
                id="d2", claim1=c1, claim2=c3,
                type=ContradictionType.TEMPORAL_DATE,
                subtype=None, status=ContradictionStatus.VERIFIED,
                severity=Severity.HIGH, confidence=0.9,
                same_event_confidence=0.8, explanation="test2",
                quote1="q1", quote2="q2",
            ),
        ]
        result = detector._deduplicate(contrs)
        assert len(result) == 2


# ===================================================================
# 22. Meaningful Words
# ===================================================================

class TestMeaningfulWords:
    def test_filters_stopwords(self, detector):
        words = detector._get_meaningful_words("את של על עם הנתבע חתם")
        assert "את" not in words
        assert "של" not in words

    def test_filters_short_words(self, detector):
        words = detector._get_meaningful_words("א בב גגג דדדד")
        assert "א" not in words
        assert "בב" not in words

    def test_returns_meaningful(self, detector):
        words = detector._get_meaningful_words("ההסכם נחתם בתאריך מוקדם")
        assert len(words) >= 2

    def test_empty_text(self, detector):
        words = detector._get_meaningful_words("")
        assert len(words) == 0


# ===================================================================
# 23. Nearby Context
# ===================================================================

class TestNearbyContext:
    def test_found_context(self):
        text = "The meeting was at 10:00 in the morning"
        ctx = RuleBasedDetector._get_nearby_context(text, "10:00", window=10)
        assert "10:00" in ctx

    def test_not_found(self):
        text = "No time mentioned here"
        ctx = RuleBasedDetector._get_nearby_context(text, "99:99", window=10)
        assert ctx == ""

    def test_window_boundaries(self):
        text = "A" * 5 + "TARGET" + "B" * 5
        ctx = RuleBasedDetector._get_nearby_context(text, "TARGET", window=3)
        assert len(ctx) <= len("TARGET") + 6  # 3 before + 3 after


# ===================================================================
# 24. DetectedContradiction to_claim_evidence
# ===================================================================

class TestToClaimEvidence:
    def test_basic_conversion(self):
        claim = _claim("טענה כלשהי", doc_id="doc1", page=3, block_index=2,
                       paragraph_index=5, char_start=100, char_end=200)
        contr = DetectedContradiction(
            id="test", claim1=claim, claim2=claim,
            type=ContradictionType.TEMPORAL_DATE,
            subtype=ContradictionSubtype.EXACT_DATE,
            status=ContradictionStatus.VERIFIED,
            severity=Severity.HIGH, confidence=0.9,
            same_event_confidence=0.8, explanation="test",
            quote1="quote", quote2="quote2",
            normalized1="2024-01-15", normalized2="2024-03-20",
        )
        evidence = contr.to_claim_evidence(claim, "quote", "2024-01-15")
        assert evidence.claim_id == claim.id
        assert evidence.doc_id == "doc1"
        assert evidence.quote == "quote"
        assert evidence.normalized == "2024-01-15"
        assert evidence.locator is not None
        assert evidence.locator.page == 3

    def test_no_doc_id(self):
        claim = _claim("טענה ללא מסמך")
        contr = DetectedContradiction(
            id="test", claim1=claim, claim2=claim,
            type=ContradictionType.TEMPORAL_DATE,
            subtype=None,
            status=ContradictionStatus.VERIFIED,
            severity=Severity.HIGH, confidence=0.9,
            same_event_confidence=0.8, explanation="test",
            quote1="q", quote2="q2",
        )
        evidence = contr.to_claim_evidence(claim, "q", None)
        assert evidence.locator is None
        assert evidence.anchor is None


# ===================================================================
# 25. DetectionResult creation
# ===================================================================

class TestDetectionResult:
    def test_empty_claims(self, detector):
        result = detector.detect([], enrich=False)
        assert len(result.contradictions) == 0
        assert result.method == "rule_based"
        assert result.detection_time_ms >= 0

    def test_single_claim_no_contradictions(self, detector):
        claims = [_claim("ההסכם נחתם ביום 15/01/2024")]
        result = detector.detect(claims, enrich=False)
        assert len(result.contradictions) == 0

    def test_metadata_populated(self, detector):
        claims = [_claim("claim1"), _claim("claim2")]
        result = detector.detect(claims, enrich=False)
        assert "claims_analyzed" in result.metadata
        assert result.metadata["claims_analyzed"] == 2
