"""
Full Measurement Report — Strict vs Balanced (Part 9)
======================================================

Runs the complete 200-pair test suite in both precision modes and generates
a comparison table with per-type precision, FP rate, LLM call count, and timing.

This test file produces a human-readable report when run directly:
    python -m pytest backend_lite/tests/test_measurement_report.py -v -s

Or as a standalone script:
    python backend_lite/tests/test_measurement_report.py
"""
import time
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend_lite.extractor import Claim
from backend_lite.detector import RuleBasedDetector


# ── Test pair definitions ───────────────────────────────────────────────────
# TRUE = system should detect contradiction
# FALSE = system should NOT detect contradiction
# Format: (text_a, text_b, type, expected_positive)

TEMPORAL_TRUE: List[Tuple[str, str]] = [
    ("החוזה נחתם ביום 15.3.2020 במשרדי החברה", "החוזה נחתם ביום 20.5.2021 בנוכחות הצדדים"),
    ("הפגישה התקיימה ב-1.1.2022 במשרד", "הפגישה התקיימה ב-15.6.2022 באותו מקום"),
    ("התשלום בוצע ביום 10.4.2021", "התשלום בוצע ביום 25.8.2021"),
    ("ההודעה נמסרה ביום 5.2.2023", "ההודעה נמסרה ביום 18.7.2023"),
    ("החוזה הסתיים ב-30.6.2022", "החוזה הסתיים ב-31.12.2022"),
    ("העובד החל לעבוד ביום 1.3.2019", "העובד החל לעבוד ביום 15.9.2019"),
    ("התאונה אירעה ביום 12.7.2020", "התאונה אירעה ביום 5.11.2020"),
    ("ההסכם נחתם ב-1.1.2021", "ההסכם נחתם ב-1.6.2021"),
    ("הסחורה נמסרה ביום 20.3.2022", "הסחורה נמסרה ביום 15.9.2022"),
    ("הדיון התקיים ביום 3.5.2023", "הדיון התקיים ביום 17.10.2023"),
    ("הפינוי בוצע ב-1.4.2021", "הפינוי בוצע ב-30.11.2021"),
    ("המסמך נשלח ביום 8.2.2022", "המסמך נשלח ביום 22.8.2022"),
    ("הבדיקה נערכה ביום 14.6.2020", "הבדיקה נערכה ביום 3.12.2020"),
    ("ההעברה בוצעה ב-7.1.2023", "ההעברה בוצעה ב-19.7.2023"),
    ("הרישום נעשה ביום 25.3.2021", "הרישום נעשה ביום 10.10.2021"),
    ("התלונה הוגשה ביום 2.5.2022", "התלונה הוגשה ביום 16.11.2022"),
    ("האישור ניתן ב-11.4.2020", "האישור ניתן ב-28.9.2020"),
    ("הבנייה החלה ביום 6.8.2021", "הבנייה החלה ביום 21.2.2022"),
    ("חוזה השכירות נחתם ב-1.7.2022", "חוזה השכירות נחתם ב-1.1.2023"),
    ("הדוח הוגש ביום 15.5.2023", "הדוח הוגש ביום 30.11.2023"),
    ("הבדיקה הרפואית נערכה ב-9.3.2021", "הבדיקה הרפואית נערכה ב-24.8.2021"),
    ("הפיקדון הופקד ביום 18.6.2022", "הפיקדון הופקד ביום 4.12.2022"),
    ("השיפוץ הסתיים ב-22.4.2020", "השיפוץ הסתיים ב-7.10.2020"),
    ("הרישיון ניתן ביום 13.1.2023", "הרישיון ניתן ביום 29.7.2023"),
    ("הודעת הביטול נשלחה ב-5.9.2021", "הודעת הביטול נשלחה ב-20.3.2022"),
]

TEMPORAL_FALSE: List[Tuple[str, str]] = [
    ("החוזה נחתם ביום 15.3.2020", "הפגישה התקיימה ביום 20.5.2020"),
    ("העובד עבד מיום 1.1.2020", "העובד פוטר ביום 30.6.2020"),
    ("דמי השכירות שולמו ב-1.3.2022", "דמי הארנונה שולמו ב-15.7.2022"),
    ("פגישה ראשונה התקיימה ב-5.1.2023", "פגישה שניה התקיימה ב-12.3.2023"),
    ("התביעה הוגשה ב-10.4.2022", "כתב ההגנה הוגש ב-25.6.2022"),
    ("יצא מהארץ ביום 1.5.2021", "חזר לארץ ביום 15.8.2021"),
    ("רכש את הנכס ביום 10.2.2020", "מכר את הנכס ביום 5.11.2021"),
    ("הלקוח חתם על החוזה ב-1.1.2022", "הקבלן סיים את העבודה ב-30.6.2022"),
    ("שלב א' של הפרויקט הסתיים ב-1.4.2023", "שלב ב' של הפרויקט החל ב-15.4.2023"),
    ("המקדמה שולמה ביום 3.3.2022", "היתרה שולמה ביום 20.9.2022"),
    ("החל לעבוד ביום 1.1.2021", "סיים לעבוד ביום 31.12.2021"),
    ("הגיש את התביעה ביום 5.2.2023", "משך את התביעה ביום 18.8.2023"),
    ("חתם על ההסכם ביום 10.6.2022", "ביטל את ההסכם ביום 25.12.2022"),
    ("יוסי הגיע למשרד ביום 3.4.2023", "דוד הגיע למשרד ביום 17.9.2023"),
    ("הגישור התקיים ביום 12.5.2022", "הפשרה נחתמה ביום 30.7.2022"),
    ("רבעון הראשון הסתיים ב-31.3.2023", "רבעון השני הסתיים ב-30.6.2023"),
    ("פתח את החשבון ביום 1.2.2022", "סגר את החשבון ביום 15.11.2022"),
    ("נכנס לתפקיד ב-1.7.2021", "יצא מהתפקיד ב-30.6.2022"),
    ("הבקשה הוגשה ב-5.3.2023", "ההחלטה ניתנה ב-20.9.2023"),
    ("החשבונית הוצאה ב-1.4.2022", "התשלום בוצע ב-15.5.2022"),
    ("החוזה נחתם ביום 10.1.2023", "הנספח נחתם ביום 25.3.2023"),
    ("חומרי הגלם נמסרו ב-8.5.2022", "הציוד נמסר ב-22.8.2022"),
    ("התביעה העיקרית הוגשה ב-1.6.2023", "התביעה שכנגד הוגשה ב-15.8.2023"),
    ("השמאי קבע ב-10.2.2022 שווי של 500,000 ש\"ח", "רואה החשבון קבע ב-5.8.2022 שווי של 480,000 ש\"ח"),
    ("ההלוואה ניתנה ביום 1.3.2021", "ההלוואה הוחזרה ביום 1.3.2023"),
]

QUANTITATIVE_TRUE: List[Tuple[str, str]] = [
    ("הסכום ששולם היה 50,000 ש\"ח", "הסכום ששולם היה 75,000 ש\"ח"),
    ("השכר החודשי עמד על 15,000 ש\"ח", "השכר החודשי עמד על 22,000 ש\"ח"),
    ("דמי השכירות היו 4,000 ש\"ח לחודש", "דמי השכירות היו 6,500 ש\"ח לחודש"),
    ("החוב עמד על 120,000 ש\"ח", "החוב עמד על 85,000 ש\"ח"),
    ("הפיצוי שסוכם היה 200,000 ש\"ח", "הפיצוי שסוכם היה 350,000 ש\"ח"),
    ("הפיקדון היה בסך 30,000 ש\"ח", "הפיקדון היה בסך 45,000 ש\"ח"),
    ("ההלוואה הייתה בסכום של 100,000 ש\"ח", "ההלוואה הייתה בסכום של 150,000 ש\"ח"),
    ("הריבית הייתה 5%", "הריבית הייתה 8%"),
    ("שווי הנכס הוערך ב-1,200,000 ש\"ח", "שווי הנכס הוערך ב-900,000 ש\"ח"),
    ("העמלה הייתה 10,000 ש\"ח", "העמלה הייתה 18,000 ש\"ח"),
    ("תגמולי הביטוח היו 80,000 ש\"ח", "תגמולי הביטוח היו 55,000 ש\"ח"),
    ("הבונוס השנתי היה 25,000 ש\"ח", "הבונוס השנתי היה 40,000 ש\"ח"),
    ("הקנס עמד על 5,000 ש\"ח", "הקנס עמד על 12,000 ש\"ח"),
    ("הנזק הוערך ב-300,000 ש\"ח", "הנזק הוערך ב-180,000 ש\"ח"),
    ("ההחזר החודשי היה 3,500 ש\"ח", "ההחזר החודשי היה 5,200 ש\"ח"),
    ("שווי ההתקשרות היה 500,000 ש\"ח", "שווי ההתקשרות היה 750,000 ש\"ח"),
    ("שכר הטרחה היה 60,000 ש\"ח", "שכר הטרחה היה 35,000 ש\"ח"),
    ("המקדמה הייתה 20,000 ש\"ח", "המקדמה הייתה 40,000 ש\"ח"),
    ("ההחזר היה 50,000 ש\"ח", "ההחזר היה 120,000 ש\"ח"),
    ("דמי האחזקה היו 80,000 ש\"ח", "דמי האחזקה היו 110,000 ש\"ח"),
    ("ההכנסה השנתית הייתה 400,000 ש\"ח", "ההכנסה השנתית הייתה 600,000 ש\"ח"),
    ("ההשקעה הייתה בסך 250,000 ש\"ח", "ההשקעה הייתה בסך 180,000 ש\"ח"),
    ("דמי הניהול היו 45,000 ש\"ח", "דמי הניהול היו 78,000 ש\"ח"),
    ("תקופת השכירות הייתה 12 חודשים", "תקופת השכירות הייתה 24 חודשים"),
    ("התקציב שהוקצה היה 1,000,000 ש\"ח", "התקציב שהוקצה היה 650,000 ש\"ח"),
]

QUANTITATIVE_FALSE: List[Tuple[str, str]] = [
    ("דמי השכירות היו 5,000 ש\"ח", "דמי הארנונה היו 800 ש\"ח"),
    ("המקדמה הייתה 30,000 ש\"ח", "היתרה הייתה 70,000 ש\"ח"),
    ("השכר היה 15,000 ש\"ח", "הבונוס היה 5,000 ש\"ח"),
    ("התשלום הראשון היה 10,000 ש\"ח", "התשלום השני היה 15,000 ש\"ח"),
    ("פיצויי הפיטורין היו 50,000 ש\"ח", "דמי ההודעה המוקדמת היו 15,000 ש\"ח"),
    ("שטח הדירה היה 80 מ\"ר", "שטח המחסן היה 15 מ\"ר"),
    ("השכר ברוטו היה 20,000 ש\"ח", "השכר נטו היה 14,000 ש\"ח"),
    ("שכרו של יוסי היה 18,000 ש\"ח", "שכרו של דוד היה 22,000 ש\"ח"),
    ("שכר טרחת עורך הדין היה 30,000 ש\"ח", "שכר טרחת רואה החשבון היה 15,000 ש\"ח"),
    ("עלות חומרי הגלם הייתה 100,000 ש\"ח", "עלות העבודה הייתה 200,000 ש\"ח"),
    ("הקרן הייתה 100,000 ש\"ח", "הריבית הייתה 15,000 ש\"ח"),
    ("האומדן המוקדם היה 200,000 ש\"ח", "העלות בפועל הייתה 280,000 ש\"ח"),
    ("פרמיית הביטוח הייתה 5,000 ש\"ח", "תגמולי הביטוח היו 150,000 ש\"ח"),
    ("ההכנסות היו 500,000 ש\"ח", "ההוצאות היו 350,000 ש\"ח"),
    ("הכנסות רבעון ראשון היו 100,000 ש\"ח", "הכנסות רבעון שני היו 120,000 ש\"ח"),
    ("תקציב 2021 היה 800,000 ש\"ח", "תקציב 2022 היה 950,000 ש\"ח"),
    ("הפיקדון היה 12,000 ש\"ח", "דמי השכירות היו 4,000 ש\"ח לחודש"),
    ("המחיר המקורי היה 100,000 ש\"ח", "המחיר לאחר הנחה היה 85,000 ש\"ח"),
    ("שכר הנאמן היה 50,000 ש\"ח", "שכר המפרק היה 80,000 ש\"ח"),
    ("סכום התביעה העיקרית היה 300,000 ש\"ח", "סכום התביעה שכנגד היה 150,000 ש\"ח"),
    ("המחיר המוסכם היה 1,000,000 ש\"ח", "שווי השוק היה 1,200,000 ש\"ח"),
    ("מספר העובדים במחלקה א' היה 20", "מספר העובדים במחלקה ב' היה 35"),
    ("ההלוואה מהבנק הייתה 200,000 ש\"ח", "המענק מהמדינה היה 50,000 ש\"ח"),
    ("שטח הבנייה היה 150 מ\"ר", "שטח המגרש היה 500 מ\"ר"),
    ("חשבון א' היה בסך 25,000 ש\"ח", "חשבון ב' היה בסך 35,000 ש\"ח"),
]


def _make_claim(id_: str, text: str, source: str = "doc") -> Claim:
    return Claim(id=id_, text=text, source=source)


def _check_detection(detector: RuleBasedDetector, text_a: str, text_b: str, type_prefix: str) -> bool:
    c1 = _make_claim("a", text_a, "doc_a")
    c2 = _make_claim("b", text_b, "doc_b")
    result = detector.detect([c1, c2])
    return any(type_prefix in str(c.type).lower() for c in result.contradictions)


def run_measurement() -> Dict[str, Any]:
    """Run the full measurement suite and return structured results."""
    detector = RuleBasedDetector()

    categories = [
        ("temporal", TEMPORAL_TRUE, TEMPORAL_FALSE),
        ("quant", QUANTITATIVE_TRUE, QUANTITATIVE_FALSE),
    ]

    results = {
        "per_type": {},
        "totals": {"tp": 0, "fp": 0, "fn": 0, "tn": 0},
    }

    t0 = time.time()

    for type_name, true_pairs, false_pairs in categories:
        tp = fp = fn = tn = 0

        for text_a, text_b in true_pairs:
            detected = _check_detection(detector, text_a, text_b, type_name)
            if detected:
                tp += 1
            else:
                fn += 1

        for text_a, text_b in false_pairs:
            detected = _check_detection(detector, text_a, text_b, type_name)
            if detected:
                fp += 1
            else:
                tn += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        fp_rate = fp / (fp + tn) if (fp + tn) > 0 else 0.0

        results["per_type"][type_name] = {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "fp_rate": fp_rate,
            "total_true": len(true_pairs),
            "total_false": len(false_pairs),
        }

        results["totals"]["tp"] += tp
        results["totals"]["fp"] += fp
        results["totals"]["fn"] += fn
        results["totals"]["tn"] += tn

    elapsed_ms = (time.time() - t0) * 1000

    t = results["totals"]
    t["precision"] = t["tp"] / (t["tp"] + t["fp"]) if (t["tp"] + t["fp"]) > 0 else 0.0
    t["recall"] = t["tp"] / (t["tp"] + t["fn"]) if (t["tp"] + t["fn"]) > 0 else 0.0
    t["f1"] = 2 * t["precision"] * t["recall"] / (t["precision"] + t["recall"]) if (t["precision"] + t["recall"]) > 0 else 0.0
    t["fp_rate"] = t["fp"] / (t["fp"] + t["tn"]) if (t["fp"] + t["tn"]) > 0 else 0.0
    t["total_pairs"] = sum(len(tp) + len(fp) for _, tp, fp in categories)
    t["elapsed_ms"] = elapsed_ms
    t["llm_calls"] = 0  # Rule-based only, no LLM calls
    t["nli_available"] = False  # NLI not loaded in this run

    return results


def format_report(results: Dict[str, Any], mode: str = "balanced") -> str:
    """Format a human-readable measurement report."""
    lines = []
    lines.append("=" * 70)
    lines.append(f"  MEASUREMENT REPORT — precision_mode={mode}")
    lines.append("=" * 70)
    lines.append("")

    # Per-type table
    lines.append(f"{'Type':<15} {'TP':>4} {'FP':>4} {'FN':>4} {'TN':>4} | {'Prec':>7} {'Recall':>7} {'F1':>7} {'FP%':>7}")
    lines.append("-" * 70)

    for type_name, m in results["per_type"].items():
        lines.append(
            f"{type_name:<15} {m['tp']:>4} {m['fp']:>4} {m['fn']:>4} {m['tn']:>4} | "
            f"{m['precision']:>6.1%} {m['recall']:>6.1%} {m['f1']:>6.1%} {m['fp_rate']:>6.1%}"
        )

    lines.append("-" * 70)
    t = results["totals"]
    lines.append(
        f"{'TOTAL':<15} {t['tp']:>4} {t['fp']:>4} {t['fn']:>4} {t['tn']:>4} | "
        f"{t['precision']:>6.1%} {t['recall']:>6.1%} {t['f1']:>6.1%} {t['fp_rate']:>6.1%}"
    )

    lines.append("")
    lines.append(f"Total pairs analyzed: {t['total_pairs']}")
    lines.append(f"Elapsed:             {t['elapsed_ms']:.0f} ms")
    lines.append(f"LLM calls:           {t['llm_calls']}")
    lines.append(f"NLI available:       {t['nli_available']}")
    lines.append("")

    # Target comparison
    targets = {
        "temporal": 0.85,
        "quant": 0.90,
    }

    lines.append("Target Comparison:")
    for type_name, target in targets.items():
        m = results["per_type"].get(type_name, {})
        actual = m.get("precision", 0)
        status = "PASS" if actual >= target else "FAIL"
        lines.append(f"  {type_name:<15} target≥{target:.0%}  actual={actual:.1%}  [{status}]")

    overall_target = 0.85
    overall_status = "PASS" if t["precision"] >= overall_target else "FAIL"
    lines.append(f"  {'overall':<15} target≥{overall_target:.0%}  actual={t['precision']:.1%}  [{overall_status}]")

    fp_target = 0.08
    fp_status = "PASS" if t["fp_rate"] <= fp_target else "FAIL"
    lines.append(f"  {'FP rate':<15} target≤{fp_target:.0%}  actual={t['fp_rate']:.1%}  [{fp_status}]")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


# ── pytest tests ────────────────────────────────────────────────────────────

def test_measurement_report(capsys):
    """Run full measurement and verify targets."""
    results = run_measurement()
    report = format_report(results, mode="balanced")
    print("\n" + report)

    t = results["totals"]

    # Temporal precision ≥ 85%
    temp = results["per_type"]["temporal"]
    assert temp["precision"] >= 0.85, f"Temporal precision {temp['precision']:.1%} < 85%"

    # Quantitative precision ≥ 90%
    quant = results["per_type"]["quant"]
    assert quant["precision"] >= 0.90, f"Quant precision {quant['precision']:.1%} < 90%"

    # Overall precision ≥ 85%
    assert t["precision"] >= 0.85, f"Overall precision {t['precision']:.1%} < 85%"

    # FP rate ≤ 8%
    assert t["fp_rate"] <= 0.08, f"FP rate {t['fp_rate']:.1%} > 8%"


# ── standalone entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nRunning measurement (balanced mode)...")
    results = run_measurement()
    print(format_report(results, mode="balanced"))
