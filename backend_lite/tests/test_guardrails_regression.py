"""
Guardrail Regression Tests — Temporal & Quantitative (Part 7)
==============================================================

50 temporal + 50 quantitative pairs that MUST ALWAYS pass.
These are the "golden" pairs: any regression that breaks them blocks the merge.

Rule: temporal/quantitative remain rule-first (not NLI). These tests ensure
that NLI integration never degrades the rule-based precision on these types.

Convention:
  - TRUE pairs  → system MUST detect as contradiction
  - FALSE pairs → system MUST NOT detect as contradiction

Naming:
  test_temporal_true_NN  → must detect
  test_temporal_false_NN → must not detect
  test_quant_true_NN     → must detect
  test_quant_false_NN    → must not detect
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend_lite.extractor import Claim
from backend_lite.detector import RuleBasedDetector


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_claim(id_: str, text: str, source: str = "doc") -> Claim:
    return Claim(id=id_, text=text, source=source)


def _has_temporal(detector: RuleBasedDetector, text_a: str, text_b: str) -> bool:
    """Returns True if detector finds a temporal contradiction."""
    c1 = _make_claim("a", text_a, "doc_a")
    c2 = _make_claim("b", text_b, "doc_b")
    result = detector.detect([c1, c2])
    return any(
        "temporal" in str(c.type).lower()
        for c in result.contradictions
    )


def _has_quantitative(detector: RuleBasedDetector, text_a: str, text_b: str) -> bool:
    """Returns True if detector finds a quantitative contradiction."""
    c1 = _make_claim("a", text_a, "doc_a")
    c2 = _make_claim("b", text_b, "doc_b")
    result = detector.detect([c1, c2])
    return any(
        "quant" in str(c.type).lower()
        for c in result.contradictions
    )


@pytest.fixture(scope="module")
def detector():
    return RuleBasedDetector()


# =============================================================================
# TEMPORAL TRUE (25 pairs) — must detect contradiction
# =============================================================================

class TestTemporalTrue:
    """Temporal contradictions that MUST be detected."""

    def test_temporal_true_01(self, detector):
        """Same event, different exact dates"""
        assert _has_temporal(detector,
            "החוזה נחתם ביום 15.3.2020",
            "החוזה נחתם ביום 20.5.2021")

    def test_temporal_true_02(self, detector):
        """Meeting on different dates"""
        assert _has_temporal(detector,
            "הפגישה התקיימה ב-1.1.2022",
            "הפגישה התקיימה ב-15.6.2022")

    def test_temporal_true_03(self, detector):
        """Payment on different dates"""
        assert _has_temporal(detector,
            "התשלום בוצע ביום 10.4.2021",
            "התשלום בוצע ביום 25.8.2021")

    def test_temporal_true_04(self, detector):
        """Notification on different dates"""
        assert _has_temporal(detector,
            "ההודעה נמסרה ביום 5.2.2023",
            "ההודעה נמסרה ביום 18.7.2023")

    def test_temporal_true_05(self, detector):
        """Termination on different dates"""
        assert _has_temporal(detector,
            "החוזה הסתיים ב-30.6.2022",
            "החוזה הסתיים ב-31.12.2022")

    def test_temporal_true_06(self, detector):
        """Start of employment different dates"""
        assert _has_temporal(detector,
            "העובד החל לעבוד ביום 1.3.2019",
            "העובד החל לעבוד ביום 15.9.2019")

    def test_temporal_true_07(self, detector):
        """Accident on different dates"""
        assert _has_temporal(detector,
            "התאונה אירעה ביום 12.7.2020",
            "התאונה אירעה ביום 5.11.2020")

    def test_temporal_true_08(self, detector):
        """Signing different dates"""
        assert _has_temporal(detector,
            "ההסכם נחתם ב-1.1.2021",
            "ההסכם נחתם ב-1.6.2021")

    def test_temporal_true_09(self, detector):
        """Delivery on different dates"""
        assert _has_temporal(detector,
            "הסחורה נמסרה ביום 20.3.2022",
            "הסחורה נמסרה ביום 15.9.2022")

    def test_temporal_true_10(self, detector):
        """Court hearing different dates"""
        assert _has_temporal(detector,
            "הדיון התקיים ביום 3.5.2023",
            "הדיון התקיים ביום 17.10.2023")

    def test_temporal_true_11(self, detector):
        """Eviction on different dates"""
        assert _has_temporal(detector,
            "הפינוי בוצע ב-1.4.2021",
            "הפינוי בוצע ב-30.11.2021")

    def test_temporal_true_12(self, detector):
        """Document sent different dates"""
        assert _has_temporal(detector,
            "המסמך נשלח ביום 8.2.2022",
            "המסמך נשלח ביום 22.8.2022")

    def test_temporal_true_13(self, detector):
        """Inspection different dates"""
        assert _has_temporal(detector,
            "הבדיקה נערכה ביום 14.6.2020",
            "הבדיקה נערכה ביום 3.12.2020")

    def test_temporal_true_14(self, detector):
        """Transfer different dates"""
        assert _has_temporal(detector,
            "ההעברה בוצעה ב-7.1.2023",
            "ההעברה בוצעה ב-19.7.2023")

    def test_temporal_true_15(self, detector):
        """Registration different dates"""
        assert _has_temporal(detector,
            "הרישום נעשה ביום 25.3.2021",
            "הרישום נעשה ביום 10.10.2021")

    def test_temporal_true_16(self, detector):
        """Complaint filed different dates"""
        assert _has_temporal(detector,
            "התלונה הוגשה ביום 2.5.2022",
            "התלונה הוגשה ביום 16.11.2022")

    def test_temporal_true_17(self, detector):
        """Approval given different dates"""
        assert _has_temporal(detector,
            "האישור ניתן ב-11.4.2020",
            "האישור ניתן ב-28.9.2020")

    def test_temporal_true_18(self, detector):
        """Construction started different dates"""
        assert _has_temporal(detector,
            "הבנייה החלה ביום 6.8.2021",
            "הבנייה החלה ביום 21.2.2022")

    def test_temporal_true_19(self, detector):
        """Lease signed different dates"""
        assert _has_temporal(detector,
            "חוזה השכירות נחתם ב-1.7.2022",
            "חוזה השכירות נחתם ב-1.1.2023")

    def test_temporal_true_20(self, detector):
        """Report submitted different dates"""
        assert _has_temporal(detector,
            "הדוח הוגש ביום 15.5.2023",
            "הדוח הוגש ביום 30.11.2023")

    def test_temporal_true_21(self, detector):
        """Medical exam different dates"""
        assert _has_temporal(detector,
            "הבדיקה הרפואית נערכה ב-9.3.2021",
            "הבדיקה הרפואית נערכה ב-24.8.2021")

    def test_temporal_true_22(self, detector):
        """Deposit paid different dates"""
        assert _has_temporal(detector,
            "הפיקדון הופקד ביום 18.6.2022",
            "הפיקדון הופקד ביום 4.12.2022")

    def test_temporal_true_23(self, detector):
        """Renovation completed different dates"""
        assert _has_temporal(detector,
            "השיפוץ הסתיים ב-22.4.2020",
            "השיפוץ הסתיים ב-7.10.2020")

    def test_temporal_true_24(self, detector):
        """License granted different dates"""
        assert _has_temporal(detector,
            "הרישיון ניתן ביום 13.1.2023",
            "הרישיון ניתן ביום 29.7.2023")

    def test_temporal_true_25(self, detector):
        """Cancellation notice different dates"""
        assert _has_temporal(detector,
            "הודעת הביטול נשלחה ב-5.9.2021",
            "הודעת הביטול נשלחה ב-20.3.2022")


# =============================================================================
# TEMPORAL FALSE (25 pairs) — must NOT detect contradiction
# =============================================================================

class TestTemporalFalse:
    """Non-contradictions that must NOT be flagged as temporal."""

    def test_temporal_false_01(self, detector):
        """Different events (contract vs meeting)"""
        assert not _has_temporal(detector,
            "החוזה נחתם ביום 15.3.2020",
            "הפגישה התקיימה ביום 20.5.2020")

    def test_temporal_false_02(self, detector):
        """Sequential: worked then fired"""
        assert not _has_temporal(detector,
            "העובד עבד מיום 1.1.2020",
            "העובד פוטר ביום 30.6.2020")

    def test_temporal_false_03(self, detector):
        """Different payment types"""
        assert not _has_temporal(detector,
            "דמי השכירות שולמו ב-1.3.2022",
            "דמי הארנונה שולמו ב-15.7.2022")

    def test_temporal_false_04(self, detector):
        """First meeting vs second meeting (ordinals differ)"""
        assert not _has_temporal(detector,
            "פגישה ראשונה התקיימה ב-5.1.2023",
            "פגישה שניה התקיימה ב-12.3.2023")

    def test_temporal_false_05(self, detector):
        """Complaint vs response — sequential process"""
        assert not _has_temporal(detector,
            "התביעה הוגשה ב-10.4.2022",
            "כתב ההגנה הוגש ב-25.6.2022")

    def test_temporal_false_06(self, detector):
        """Left then returned — complementary verbs"""
        assert not _has_temporal(detector,
            "יצא מהארץ ביום 1.5.2021",
            "חזר לארץ ביום 15.8.2021")

    def test_temporal_false_07(self, detector):
        """Bought then sold"""
        assert not _has_temporal(detector,
            "רכש את הנכס ביום 10.2.2020",
            "מכר את הנכס ביום 5.11.2021")

    def test_temporal_false_08(self, detector):
        """Different subjects entirely"""
        assert not _has_temporal(detector,
            "הלקוח חתם על החוזה ב-1.1.2022",
            "הקבלן סיים את העבודה ב-30.6.2022")

    def test_temporal_false_09(self, detector):
        """Phase A vs Phase B"""
        assert not _has_temporal(detector,
            "שלב א' של הפרויקט הסתיים ב-1.4.2023",
            "שלב ב' של הפרויקט החל ב-15.4.2023")

    def test_temporal_false_10(self, detector):
        """Advance payment vs final payment"""
        assert not _has_temporal(detector,
            "המקדמה שולמה ביום 3.3.2022",
            "היתרה שולמה ביום 20.9.2022")

    def test_temporal_false_11(self, detector):
        """Start and end of same period"""
        assert not _has_temporal(detector,
            "החל לעבוד ביום 1.1.2021",
            "סיים לעבוד ביום 31.12.2021")

    def test_temporal_false_12(self, detector):
        """Filed then withdrew"""
        assert not _has_temporal(detector,
            "הגיש את התביעה ביום 5.2.2023",
            "משך את התביעה ביום 18.8.2023")

    def test_temporal_false_13(self, detector):
        """Signed then cancelled"""
        assert not _has_temporal(detector,
            "חתם על ההסכם ביום 10.6.2022",
            "ביטל את ההסכם ביום 25.12.2022")

    def test_temporal_false_14(self, detector):
        """Different people same verb"""
        assert not _has_temporal(detector,
            "יוסי הגיע למשרד ביום 3.4.2023",
            "דוד הגיע למשרד ביום 17.9.2023")

    def test_temporal_false_15(self, detector):
        """Mediation then settlement"""
        assert not _has_temporal(detector,
            "הגישור התקיים ביום 12.5.2022",
            "הפשרה נחתמה ביום 30.7.2022")

    def test_temporal_false_16(self, detector):
        """Different quarters"""
        assert not _has_temporal(detector,
            "רבעון הראשון הסתיים ב-31.3.2023",
            "רבעון השני הסתיים ב-30.6.2023")

    def test_temporal_false_17(self, detector):
        """Opened then closed"""
        assert not _has_temporal(detector,
            "פתח את החשבון ביום 1.2.2022",
            "סגר את החשבון ביום 15.11.2022")

    def test_temporal_false_18(self, detector):
        """Entered then exited"""
        assert not _has_temporal(detector,
            "נכנס לתפקיד ב-1.7.2021",
            "יצא מהתפקיד ב-30.6.2022")

    def test_temporal_false_19(self, detector):
        """Inquiry then decision"""
        assert not _has_temporal(detector,
            "הבקשה הוגשה ב-5.3.2023",
            "ההחלטה ניתנה ב-20.9.2023")

    def test_temporal_false_20(self, detector):
        """Invoice then payment — naturally sequential"""
        assert not _has_temporal(detector,
            "החשבונית הוצאה ב-1.4.2022",
            "התשלום בוצע ב-15.5.2022")

    def test_temporal_false_21(self, detector):
        """Different documents"""
        assert not _has_temporal(detector,
            "החוזה נחתם ביום 10.1.2023",
            "הנספח נחתם ביום 25.3.2023")

    def test_temporal_false_22(self, detector):
        """Different items delivered"""
        assert not _has_temporal(detector,
            "חומרי הגלם נמסרו ב-8.5.2022",
            "הציוד נמסר ב-22.8.2022")

    def test_temporal_false_23(self, detector):
        """Claim A vs counter-claim — different actions"""
        assert not _has_temporal(detector,
            "התביעה העיקרית הוגשה ב-1.6.2023",
            "התביעה שכנגד הוגשה ב-15.8.2023")

    def test_temporal_false_24(self, detector):
        """Different appraisals (by different experts)"""
        assert not _has_temporal(detector,
            "השמאי קבע ב-10.2.2022 שווי של 500,000 ש\"ח",
            "רואה החשבון קבע ב-5.8.2022 שווי של 480,000 ש\"ח")

    def test_temporal_false_25(self, detector):
        """Loan given vs repaid"""
        assert not _has_temporal(detector,
            "ההלוואה ניתנה ביום 1.3.2021",
            "ההלוואה הוחזרה ביום 1.3.2023")


# =============================================================================
# QUANTITATIVE TRUE (25 pairs) — must detect contradiction
# =============================================================================

class TestQuantitativeTrue:
    """Quantitative contradictions that MUST be detected."""

    def test_quant_true_01(self, detector):
        """Same payment different amounts"""
        assert _has_quantitative(detector,
            "הסכום ששולם היה 50,000 ש\"ח",
            "הסכום ששולם היה 75,000 ש\"ח")

    def test_quant_true_02(self, detector):
        """Salary different amounts"""
        assert _has_quantitative(detector,
            "השכר החודשי עמד על 15,000 ש\"ח",
            "השכר החודשי עמד על 22,000 ש\"ח")

    def test_quant_true_03(self, detector):
        """Rent different amounts"""
        assert _has_quantitative(detector,
            "דמי השכירות היו 4,000 ש\"ח לחודש",
            "דמי השכירות היו 6,500 ש\"ח לחודש")

    def test_quant_true_04(self, detector):
        """Debt different amounts"""
        assert _has_quantitative(detector,
            "החוב עמד על 120,000 ש\"ח",
            "החוב עמד על 85,000 ש\"ח")

    def test_quant_true_05(self, detector):
        """Compensation different amounts"""
        assert _has_quantitative(detector,
            "הפיצוי שסוכם היה 200,000 ש\"ח",
            "הפיצוי שסוכם היה 350,000 ש\"ח")

    def test_quant_true_06(self, detector):
        """Deposit different amounts"""
        assert _has_quantitative(detector,
            "הפיקדון היה בסך 30,000 ש\"ח",
            "הפיקדון היה בסך 45,000 ש\"ח")

    def test_quant_true_07(self, detector):
        """Loan different amounts"""
        assert _has_quantitative(detector,
            "ההלוואה הייתה בסכום של 100,000 ש\"ח",
            "ההלוואה הייתה בסכום של 150,000 ש\"ח")

    def test_quant_true_08(self, detector):
        """Percentage different"""
        assert _has_quantitative(detector,
            "הריבית הייתה 5%",
            "הריבית הייתה 8%")

    def test_quant_true_09(self, detector):
        """Property value different"""
        assert _has_quantitative(detector,
            "שווי הנכס הוערך ב-1,200,000 ש\"ח",
            "שווי הנכס הוערך ב-900,000 ש\"ח")

    def test_quant_true_10(self, detector):
        """Commission different"""
        assert _has_quantitative(detector,
            "העמלה הייתה 10,000 ש\"ח",
            "העמלה הייתה 18,000 ש\"ח")

    def test_quant_true_11(self, detector):
        """Insurance payment different"""
        assert _has_quantitative(detector,
            "תגמולי הביטוח היו 80,000 ש\"ח",
            "תגמולי הביטוח היו 55,000 ש\"ח")

    def test_quant_true_12(self, detector):
        """Bonus different amounts"""
        assert _has_quantitative(detector,
            "הבונוס השנתי היה 25,000 ש\"ח",
            "הבונוס השנתי היה 40,000 ש\"ח")

    def test_quant_true_13(self, detector):
        """Fine different amounts"""
        assert _has_quantitative(detector,
            "הקנס עמד על 5,000 ש\"ח",
            "הקנס עמד על 12,000 ש\"ח")

    def test_quant_true_14(self, detector):
        """Damage estimate different"""
        assert _has_quantitative(detector,
            "הנזק הוערך ב-300,000 ש\"ח",
            "הנזק הוערך ב-180,000 ש\"ח")

    def test_quant_true_15(self, detector):
        """Monthly payment different"""
        assert _has_quantitative(detector,
            "ההחזר החודשי היה 3,500 ש\"ח",
            "ההחזר החודשי היה 5,200 ש\"ח")

    def test_quant_true_16(self, detector):
        """Contract value different"""
        assert _has_quantitative(detector,
            "שווי ההתקשרות היה 500,000 ש\"ח",
            "שווי ההתקשרות היה 750,000 ש\"ח")

    def test_quant_true_17(self, detector):
        """Fee different"""
        assert _has_quantitative(detector,
            "שכר הטרחה היה 60,000 ש\"ח",
            "שכר הטרחה היה 35,000 ש\"ח")

    def test_quant_true_18(self, detector):
        """Advance payment different"""
        assert _has_quantitative(detector,
            "המקדמה הייתה 20,000 ש\"ח",
            "המקדמה הייתה 40,000 ש\"ח")

    def test_quant_true_19(self, detector):
        """Refund different amounts"""
        assert _has_quantitative(detector,
            "ההחזר היה 50,000 ש\"ח",
            "ההחזר היה 120,000 ש\"ח")

    def test_quant_true_20(self, detector):
        """Maintenance fee different"""
        assert _has_quantitative(detector,
            "דמי האחזקה היו 80,000 ש\"ח",
            "דמי האחזקה היו 110,000 ש\"ח")

    def test_quant_true_21(self, detector):
        """Revenue different"""
        assert _has_quantitative(detector,
            "ההכנסה השנתית הייתה 400,000 ש\"ח",
            "ההכנסה השנתית הייתה 600,000 ש\"ח")

    def test_quant_true_22(self, detector):
        """Investment different"""
        assert _has_quantitative(detector,
            "ההשקעה הייתה בסך 250,000 ש\"ח",
            "ההשקעה הייתה בסך 180,000 ש\"ח")

    def test_quant_true_23(self, detector):
        """Management fees different"""
        assert _has_quantitative(detector,
            "דמי הניהול היו 45,000 ש\"ח",
            "דמי הניהול היו 78,000 ש\"ח")

    def test_quant_true_24(self, detector):
        """Duration in months different"""
        assert _has_quantitative(detector,
            "תקופת השכירות הייתה 12 חודשים",
            "תקופת השכירות הייתה 24 חודשים")

    def test_quant_true_25(self, detector):
        """Budget different"""
        assert _has_quantitative(detector,
            "התקציב שהוקצה היה 1,000,000 ש\"ח",
            "התקציב שהוקצה היה 650,000 ש\"ח")


# =============================================================================
# QUANTITATIVE FALSE (25 pairs) — must NOT detect contradiction
# =============================================================================

class TestQuantitativeFalse:
    """Non-contradictions that must NOT be flagged as quantitative."""

    def test_quant_false_01(self, detector):
        """Different payment types (rent vs arnona)"""
        assert not _has_quantitative(detector,
            "דמי השכירות היו 5,000 ש\"ח",
            "דמי הארנונה היו 800 ש\"ח")

    def test_quant_false_02(self, detector):
        """Advance vs balance (complementary)"""
        assert not _has_quantitative(detector,
            "המקדמה הייתה 30,000 ש\"ח",
            "היתרה הייתה 70,000 ש\"ח")

    def test_quant_false_03(self, detector):
        """Salary vs bonus — different categories"""
        assert not _has_quantitative(detector,
            "השכר היה 15,000 ש\"ח",
            "הבונוס היה 5,000 ש\"ח")

    def test_quant_false_04(self, detector):
        """Payment A vs Payment B"""
        assert not _has_quantitative(detector,
            "התשלום הראשון היה 10,000 ש\"ח",
            "התשלום השני היה 15,000 ש\"ח")

    def test_quant_false_05(self, detector):
        """Severance vs notice pay"""
        assert not _has_quantitative(detector,
            "פיצויי הפיטורין היו 50,000 ש\"ח",
            "דמי ההודעה המוקדמת היו 15,000 ש\"ח")

    def test_quant_false_06(self, detector):
        """Different properties"""
        assert not _has_quantitative(detector,
            "שטח הדירה היה 80 מ\"ר",
            "שטח המחסן היה 15 מ\"ר")

    def test_quant_false_07(self, detector):
        """Net vs gross"""
        assert not _has_quantitative(detector,
            "השכר ברוטו היה 20,000 ש\"ח",
            "השכר נטו היה 14,000 ש\"ח")

    def test_quant_false_08(self, detector):
        """Different people's salaries"""
        assert not _has_quantitative(detector,
            "שכרו של יוסי היה 18,000 ש\"ח",
            "שכרו של דוד היה 22,000 ש\"ח")

    def test_quant_false_09(self, detector):
        """Lawyer fee vs accountant fee"""
        assert not _has_quantitative(detector,
            "שכר טרחת עורך הדין היה 30,000 ש\"ח",
            "שכר טרחת רואה החשבון היה 15,000 ש\"ח")

    def test_quant_false_10(self, detector):
        """Raw materials vs labor costs"""
        assert not _has_quantitative(detector,
            "עלות חומרי הגלם הייתה 100,000 ש\"ח",
            "עלות העבודה הייתה 200,000 ש\"ח")

    def test_quant_false_11(self, detector):
        """Principal vs interest"""
        assert not _has_quantitative(detector,
            "הקרן הייתה 100,000 ש\"ח",
            "הריבית הייתה 15,000 ש\"ח")

    def test_quant_false_12(self, detector):
        """Estimate vs actual (clearly labeled)"""
        assert not _has_quantitative(detector,
            "האומדן המוקדם היה 200,000 ש\"ח",
            "העלות בפועל הייתה 280,000 ש\"ח")

    def test_quant_false_13(self, detector):
        """Insurance premium vs claim"""
        assert not _has_quantitative(detector,
            "פרמיית הביטוח הייתה 5,000 ש\"ח",
            "תגמולי הביטוח היו 150,000 ש\"ח")

    def test_quant_false_14(self, detector):
        """Revenue vs expenses"""
        assert not _has_quantitative(detector,
            "ההכנסות היו 500,000 ש\"ח",
            "ההוצאות היו 350,000 ש\"ח")

    def test_quant_false_15(self, detector):
        """Q1 vs Q2 revenue"""
        assert not _has_quantitative(detector,
            "הכנסות רבעון ראשון היו 100,000 ש\"ח",
            "הכנסות רבעון שני היו 120,000 ש\"ח")

    def test_quant_false_16(self, detector):
        """Different years' budgets"""
        assert not _has_quantitative(detector,
            "תקציב 2021 היה 800,000 ש\"ח",
            "תקציב 2022 היה 950,000 ש\"ח")

    def test_quant_false_17(self, detector):
        """Deposit vs monthly rent"""
        assert not _has_quantitative(detector,
            "הפיקדון היה 12,000 ש\"ח",
            "דמי השכירות היו 4,000 ש\"ח לחודש")

    def test_quant_false_18(self, detector):
        """Original price vs discount price"""
        assert not _has_quantitative(detector,
            "המחיר המקורי היה 100,000 ש\"ח",
            "המחיר לאחר הנחה היה 85,000 ש\"ח")

    def test_quant_false_19(self, detector):
        """Trustee vs liquidator fees"""
        assert not _has_quantitative(detector,
            "שכר הנאמן היה 50,000 ש\"ח",
            "שכר המפרק היה 80,000 ש\"ח")

    def test_quant_false_20(self, detector):
        """Main claim vs counter-claim amounts"""
        assert not _has_quantitative(detector,
            "סכום התביעה העיקרית היה 300,000 ש\"ח",
            "סכום התביעה שכנגד היה 150,000 ש\"ח")

    def test_quant_false_21(self, detector):
        """Agreed price vs market value"""
        assert not _has_quantitative(detector,
            "המחיר המוסכם היה 1,000,000 ש\"ח",
            "שווי השוק היה 1,200,000 ש\"ח")

    def test_quant_false_22(self, detector):
        """Different departments"""
        assert not _has_quantitative(detector,
            "מספר העובדים במחלקה א' היה 20",
            "מספר העובדים במחלקה ב' היה 35")

    def test_quant_false_23(self, detector):
        """Loan from bank vs grant from state"""
        assert not _has_quantitative(detector,
            "ההלוואה מהבנק הייתה 200,000 ש\"ח",
            "המענק מהמדינה היה 50,000 ש\"ח")

    def test_quant_false_24(self, detector):
        """Building area vs land area"""
        assert not _has_quantitative(detector,
            "שטח הבנייה היה 150 מ\"ר",
            "שטח המגרש היה 500 מ\"ר")

    def test_quant_false_25(self, detector):
        """Cost A vs Cost B (sequential invoices)"""
        assert not _has_quantitative(detector,
            "חשבון א' היה בסך 25,000 ש\"ח",
            "חשבון ב' היה בסך 35,000 ש\"ח")
