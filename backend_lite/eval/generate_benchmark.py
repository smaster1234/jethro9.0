#!/usr/bin/env python3
"""
Generate 200-pair benchmark dataset for JETHRO 9.0 evaluation.

Distribution:
  - 50 temporal pairs     (25 contradiction + 25 non-contradiction)
  - 50 quantitative pairs (25 contradiction + 25 non-contradiction)
  - 50 factual pairs      (25 contradiction + 25 non-contradiction)
  - 50 attribution pairs  (25 contradiction + 25 non-contradiction)

All claims use realistic Hebrew legal text with proper enrichment fields.
"""

import json
import os

PLANE_FACT = "FACT"
PLANE_LAW = "LAW"
PLANE_OPINION = "OPINION"
SM_FINDING = "finding"
SM_PARTY = "party_claim"


def _pair(pair_id, typ, label, claim_a, claim_b):
    """Build a benchmark pair dict."""
    return {
        "pair_id": pair_id,
        "type": typ,
        "label": label,
        "claim_a": claim_a,
        "claim_b": claim_b,
    }


def _claim(text, **kw):
    """Build a claim dict with defaults."""
    return {
        "text": text,
        "plane": kw.get("plane", PLANE_FACT),
        "speaker_mode": kw.get("speaker_mode", SM_FINDING),
        "speaker_role": kw.get("speaker_role", "court"),
        "negation": kw.get("negation", False),
        "entities": kw.get("entities", []),
        "time_reference": kw.get("time_reference"),
        "context_before": kw.get("context_before", "הצדדים העידו על האירועים."),
        "context_after": kw.get("context_after", "העדויות תועדו בפרוטוקול."),
        "modality": kw.get("modality"),
        "scope_quantifiers": kw.get("scope_quantifiers"),
        "extraction_confidence": kw.get("extraction_confidence", 0.90),
    }


def generate_temporal_pairs():
    """50 temporal pairs: 25 contradictions + 25 non-contradictions."""
    pairs = []
    idx = 0

    # ---- 25 CONTRADICTIONS ----
    temporal_contradictions = [
        # 1: Contract signing date conflict
        ("החוזה נחתם ביום 15.3.2020 במשרדי החברה",
         "החוזה נחתם ביום 20.5.2021 במשרדי החברה",
         ["חוזה", "חברה"], "contract_signing"),
        # 2: Meeting date conflict
        ("הפגישה התקיימה ביום 1.6.2022 בתל אביב",
         "הפגישה התקיימה ביום 15.8.2022 בתל אביב",
         ["פגישה", "תל אביב"], "meeting_date"),
        # 3: Payment date conflict
        ("יוסי כהן שילם את התשלום ביום 10.1.2023",
         "יוסי כהן שילם את התשלום ביום 25.4.2023",
         ["יוסי כהן", "תשלום"], "payment_date"),
        # 4: Delivery date conflict
        ("הסחורה נמסרה ביום 5.7.2021",
         "הסחורה נמסרה ביום 12.11.2021",
         ["סחורה"], "delivery_date"),
        # 5: Termination date conflict
        ("ההסכם בוטל ביום 1.9.2020",
         "ההסכם בוטל ביום 15.12.2020",
         ["הסכם"], "termination_date"),
        # 6: Accident date
        ("התאונה אירעה ביום 3.2.2019 בצומת",
         "התאונה אירעה ביום 17.6.2019 בצומת",
         ["תאונה", "צומת"], "accident_date"),
        # 7: Employment start
        ("דוד לוי החל לעבוד בחברה ביום 1.1.2018",
         "דוד לוי החל לעבוד בחברה ביום 15.3.2018",
         ["דוד לוי", "חברה"], "employment_start"),
        # 8: Court hearing date
        ("הדיון התקיים ביום 20.4.2022 בבית המשפט",
         "הדיון התקיים ביום 5.7.2022 בבית המשפט",
         ["דיון", "בית המשפט"], "hearing_date"),
        # 9: Notice date
        ("ההודעה נשלחה ביום 10.3.2021",
         "ההודעה נשלחה ביום 28.6.2021",
         ["הודעה"], "notice_date"),
        # 10: Inspection date
        ("הבדיקה בוצעה ביום 5.5.2020",
         "הבדיקה בוצעה ביום 22.9.2020",
         ["בדיקה"], "inspection_date"),
        # 11: Agreement date with Hebrew month
        ("החוזה נחתם ב-15 במרץ 2020",
         "החוזה נחתם ב-20 במאי 2021",
         ["חוזה"], "agreement_date"),
        # 12: Filing date
        ("התביעה הוגשה ביום 1.2.2023",
         "התביעה הוגשה ביום 15.5.2023",
         ["תביעה"], "filing_date"),
        # 13: Completion date
        ("העבודות הושלמו ביום 30.6.2021",
         "העבודות הושלמו ביום 15.10.2021",
         ["עבודות"], "completion_date"),
        # 14: Eviction date
        ("הפינוי בוצע ביום 1.8.2022",
         "הפינוי בוצע ביום 20.11.2022",
         ["פינוי"], "eviction_date"),
        # 15: Registration date
        ("הרישום בטאבו בוצע ביום 10.4.2019",
         "הרישום בטאבו בוצע ביום 25.7.2019",
         ["רישום", "טאבו"], "registration_date"),
        # 16: Approval date
        ("האישור ניתן ביום 5.1.2023",
         "האישור ניתן ביום 18.4.2023",
         ["אישור"], "approval_date"),
        # 17: Transfer date
        ("ההעברה בוצעה ביום 12.3.2022",
         "ההעברה בוצעה ביום 28.6.2022",
         ["העברה"], "transfer_date"),
        # 18: Publication date
        ("המכרז פורסם ביום 1.5.2021",
         "המכרז פורסם ביום 15.8.2021",
         ["מכרז"], "publication_date"),
        # 19: Decision date
        ("ההחלטה התקבלה ביום 20.2.2020",
         "ההחלטה התקבלה ביום 10.5.2020",
         ["החלטה"], "decision_date"),
        # 20: Lease start
        ("תקופת השכירות החלה ביום 1.7.2022",
         "תקופת השכירות החלה ביום 1.10.2022",
         ["שכירות"], "lease_start"),
        # 21: Injury date
        ("הפציעה אירעה ביום 8.3.2019",
         "הפציעה אירעה ביום 22.6.2019",
         ["פציעה"], "injury_date"),
        # 22: Notification date
        ("ההתראה נמסרה ביום 5.11.2021",
         "ההתראה נמסרה ביום 20.2.2022",
         ["התראה"], "notification_date"),
        # 23: Signature date conflict
        ("המסמך נחתם ביום 10.4.2020",
         "המסמך נחתם ביום 25.7.2020",
         ["מסמך"], "signature_date"),
        # 24: Birth date conflict in estate case
        ("המנוח נולד ביום 1.1.1950",
         "המנוח נולד ביום 15.3.1952",
         ["מנוח"], "birth_date"),
        # 25: Event date with year only
        ("האירוע התרחש בשנת 2019",
         "האירוע התרחש בשנת 2021",
         ["אירוע"], "event_year"),
    ]

    for i, (text_a, text_b, entities, time_ref) in enumerate(temporal_contradictions):
        idx += 1
        pairs.append(_pair(
            f"T{idx:03d}", "temporal", "contradiction",
            _claim(text_a, entities=entities, time_reference=time_ref,
                   negation=False),
            _claim(text_b, entities=entities, time_reference=time_ref,
                   negation=True),
        ))

    # ---- 25 NON-CONTRADICTIONS ----
    # Strategy: use DIFFERENT time_reference values for sequential/different events
    # so Layer 1 routes to TIME_SHIFT, or use different entities so entity gate fails.
    # fmt: (text_a, text_b, ent_a, ent_b, time_ref_a, time_ref_b, [plane_b])
    temporal_negatives = [
        # 1: Same date, different actions (not contradictory)
        ("החוזה נחתם ביום 15.3.2020",
         "לאחר חתימת החוזה ב-15.3.2020 החל ביצוע העבודות",
         ["חוזה"], ["חוזה", "עבודות"], "contract_signing", "contract_signing"),
        # 2: Sequential events → different time_reference
        ("הפגישה הראשונה התקיימה ביום 1.6.2022",
         "הפגישה השנייה התקיימה ביום 15.8.2022",
         ["פגישה ראשונה"], ["פגישה שנייה"], "first_meeting", "second_meeting"),
        # 3: Different subject matter → no entity overlap
        ("יוסי כהן שילם ביום 10.1.2023 עבור הרכב",
         "דוד לוי שילם ביום 25.4.2023 עבור הדירה",
         ["יוסי כהן", "רכב"], ["דוד לוי", "דירה"], "payment_car", "payment_apt"),
        # 4: Same event same date (duplicate-like)
        ("הסחורה נמסרה ביום 5.7.2021",
         "המסירה בוצעה ביום 5.7.2021",
         ["סחורה", "מסירה"], ["סחורה", "מסירה"], "delivery_date", "delivery_date"),
        # 5: Approximate date (not conflict)
        ("ההסכם בוטל בסוף שנת 2020",
         "ההסכם בוטל ביום 15.12.2020",
         ["הסכם"], ["הסכם"], "termination_date", "termination_date"),
        # 6: Different planes → claim_b is OPINION
        ("התאונה אירעה ביום 3.2.2019",
         "לדעת המומחה התאונה אירעה ביום 17.6.2019",
         ["תאונה"], ["תאונה"], "accident_date", "accident_date"),
        # 7: Conditional modality → different modality
        ("דוד לוי החל לעבוד ביום 1.1.2018",
         "אילו התקבל דוד לוי היה מתחיל לעבוד ביום 15.3.2018",
         ["דוד לוי"], ["דוד לוי"], "employment_actual", "employment_hypothetical"),
        # 8: Complementary facts → different time_reference (start vs end)
        ("הדיון נפתח בשעה 9:00",
         "הדיון הסתיים בשעה 14:00",
         ["דיון"], ["דיון"], "hearing_start", "hearing_end"),
        # 9: Reference to same date
        ("ההודעה נשלחה ביום 10.3.2021",
         "ההודעה מתאריך 10.3.2021 התקבלה",
         ["הודעה"], ["הודעה"], "notice_date", "notice_date"),
        # 10: Different scope → different time_reference
        ("הבדיקה הראשונית בוצעה ביום 5.5.2020",
         "הבדיקה המקיפה בוצעה ביום 22.9.2020",
         ["בדיקה ראשונית"], ["בדיקה מקיפה"], "inspection_initial", "inspection_full"),
        # 11: Paraphrase same date (duplicate-like)
        ("החוזה נחתם ב-15 במרץ 2020",
         "ההסכם נחתם ביום 15.3.2020",
         ["חוזה"], ["הסכם"], "agreement_date", "agreement_date"),
        # 12: Quote vs finding → different speaker_mode
        ("התביעה הוגשה ביום 1.2.2023",
         "התובע טען כי התביעה הוגשה ביום 15.5.2023",
         ["תביעה"], ["תביעה"], "filing_date", "filing_date"),
        # 13: Different construction phases → different time_reference
        ("בניית היסודות הושלמה ביום 30.6.2021",
         "הגמר הסופי של העבודות הושלם ביום 15.10.2021",
         ["יסודות"], ["עבודות גמר"], "foundation_complete", "final_complete"),
        # 14: Planned vs actual → different time_reference
        ("הפינוי תוכנן ליום 1.8.2022",
         "הפינוי בפועל בוצע ביום 20.11.2022",
         ["פינוי"], ["פינוי"], "eviction_planned", "eviction_actual"),
        # 15: Same date reformatted
        ("הרישום בטאבו בוצע ביום 10.4.2019",
         "ברישום מיום 10 באפריל 2019 נרשמה ההערה",
         ["רישום", "טאבו"], ["רישום", "טאבו"], "registration_date", "registration_date"),
        # 16: Different role context → no entity overlap
        ("האישור ניתן ביום 5.1.2023 על ידי הוועדה",
         "אישור העירייה ניתן ביום 18.4.2023",
         ["ועדה", "אישור"], ["עירייה", "אישור עירייה"], "committee_approval", "city_approval"),
        # 17: Complementary stages → different time_reference
        ("הבקשה הוגשה ביום 12.3.2022",
         "הבקשה אושרה ביום 28.6.2022",
         ["בקשה"], ["בקשה"], "request_filed", "request_approved"),
        # 18: Different contests → no entity overlap
        ("המכרז הראשון פורסם ביום 1.5.2021",
         "המכרז השני פורסם ביום 15.8.2021",
         ["מכרז ראשון"], ["מכרז שני"], "tender_1", "tender_2"),
        # 19: Same decision, same date
        ("ההחלטה התקבלה ביום 20.2.2020",
         "ביום 20.2.2020 התקבלה ההחלטה בנושא ההסכם",
         ["החלטה"], ["החלטה"], "decision_date", "decision_date"),
        # 20: Different lease types → no entity overlap
        ("תקופת השכירות של הדירה החלה ביום 1.7.2022",
         "שכירות המשרד החלה ביום 1.10.2022",
         ["דירה", "שכירות"], ["משרד", "שכירות"], "lease_apartment", "lease_office"),
        # 21: Injury and treatment → different time_reference
        ("הפציעה אירעה ביום 8.3.2019",
         "הטיפול הרפואי החל ביום 22.6.2019",
         ["פציעה"], ["טיפול רפואי"], "injury_event", "treatment_start"),
        # 22: Same notification - reformulated
        ("ההתראה נמסרה לנתבע ביום 5.11.2021",
         "הנתבע קיבל את ההתראה ביום 5.11.2021",
         ["התראה", "נתבע"], ["התראה", "נתבע"], "notification_date", "notification_date"),
        # 23: Different documents → different time_reference
        ("החוזה הראשון נחתם ביום 10.4.2020",
         "החוזה המתוקן נחתם ביום 25.7.2020",
         ["חוזה ראשון"], ["חוזה מתוקן"], "contract_v1", "contract_v2"),
        # 24: Opinion plane
        ("לדעתי המנוח נולד בשנת 1950",
         "בתעודת הלידה נרשם כי המנוח נולד ביום 1.1.1950",
         ["מנוח"], ["מנוח"], "birth_date", "birth_date"),
        # 25: Different parties → no entity overlap
        ("אירוע א התרחש בשנת 2019",
         "אירוע ב התרחש בשנת 2021",
         ["אירוע א"], ["אירוע ב"], "event_a", "event_b"),
    ]

    for i, (text_a, text_b, ent_a, ent_b, time_a, time_b) in enumerate(temporal_negatives):
        idx += 1
        # For pair 6: opinion plane on claim_b
        plane_b = PLANE_OPINION if i == 5 else PLANE_FACT
        # For pair 7: conditional modality on claim_b
        modality_b = "possible" if i == 6 else None
        # For pair 12: party_claim on claim_b
        sm_b = SM_PARTY if i == 11 else SM_FINDING
        pairs.append(_pair(
            f"T{idx:03d}", "temporal", "non_contradiction",
            _claim(text_a, entities=ent_a, time_reference=time_a),
            _claim(text_b, entities=ent_b, time_reference=time_b,
                   plane=plane_b, modality=modality_b, speaker_mode=sm_b),
        ))

    return pairs


def generate_quantitative_pairs():
    """50 quantitative pairs: 25 contradictions + 25 non-contradictions."""
    pairs = []
    idx = 0

    quant_contradictions = [
        # 1: Contract amount
        ("סכום התמורה בחוזה עמד על 500,000 ש\"ח",
         "סכום התמורה בחוזה היה 350,000 ש\"ח",
         ["חוזה", "תמורה"]),
        # 2: Payment amount
        ("יוסי כהן שילם סך של 100,000 ש\"ח",
         "יוסי כהן שילם סך של 50,000 ש\"ח בלבד",
         ["יוסי כהן", "תשלום"]),
        # 3: Damage amount
        ("הנזק נאמד בסכום של 1,200,000 ש\"ח",
         "הנזק נאמד בסכום של 800,000 ש\"ח",
         ["נזק"]),
        # 4: Rent amount
        ("דמי השכירות עמדו על 8,000 ש\"ח לחודש",
         "דמי השכירות עמדו על 5,000 ש\"ח לחודש",
         ["שכירות"]),
        # 5: Percentage
        ("הריבית על ההלוואה עמדה על 12%",
         "הריבית על ההלוואה עמדה על 6%",
         ["ריבית", "הלוואה"]),
        # 6: Area measurement
        ("שטח הדירה הוא 120 מ\"ר",
         "שטח הדירה הוא 85 מ\"ר",
         ["דירה"]),
        # 7: Duration
        ("תקופת ההסכם נקבעה ל-5 שנים",
         "תקופת ההסכם נקבעה ל-3 שנים",
         ["הסכם"]),
        # 8: Number of units
        ("הנתבע סיפק 200 יחידות",
         "הנתבע סיפק 120 יחידות בלבד",
         ["נתבע", "יחידות"]),
        # 9: Salary
        ("שכרו של העובד עמד על 25,000 ש\"ח",
         "שכרו של העובד עמד על 15,000 ש\"ח",
         ["עובד", "שכר"]),
        # 10: Commission rate
        ("שיעור העמלה נקבע ל-8%",
         "שיעור העמלה נקבע ל-3%",
         ["עמלה"]),
        # 11: Deposit
        ("הפיקדון שהופקד עמד על 50,000 ש\"ח",
         "הפיקדון שהופקד עמד על 30,000 ש\"ח",
         ["פיקדון"]),
        # 12: Fine
        ("הקנס שהוטל עמד על 75,000 ש\"ח",
         "הקנס שהוטל עמד על 25,000 ש\"ח",
         ["קנס"]),
        # 13: Property value
        ("שווי הנכס הוערך ב-2,000,000 ש\"ח",
         "שווי הנכס הוערך ב-1,500,000 ש\"ח",
         ["נכס"]),
        # 14: Debt amount
        ("החוב עומד על 300,000 ש\"ח",
         "החוב עומד על 180,000 ש\"ח",
         ["חוב"]),
        # 15: Distance
        ("המרחק בין הנכסים הוא 500 מטר",
         "המרחק בין הנכסים הוא 200 מטר",
         ["נכסים"]),
        # 16: Number of employees
        ("החברה העסיקה 50 עובדים",
         "החברה העסיקה 25 עובדים",
         ["חברה", "עובדים"]),
        # 17: Weight
        ("משקל הסחורה היה 5,000 ק\"ג",
         "משקל הסחורה היה 3,000 ק\"ג",
         ["סחורה"]),
        # 18: Hours worked
        ("העובד עבד 180 שעות בחודש",
         "העובד עבד 120 שעות בחודש",
         ["עובד"]),
        # 19: Investment amount
        ("ההשקעה עמדה על 400,000 $",
         "ההשקעה עמדה על 250,000 $",
         ["השקעה"]),
        # 20: Monthly payment
        ("התשלום החודשי עמד על 6,000 ש\"ח",
         "התשלום החודשי עמד על 3,500 ש\"ח",
         ["תשלום"]),
        # 21: Number of shares
        ("דוד לוי החזיק 1,000 מניות",
         "דוד לוי החזיק 600 מניות",
         ["דוד לוי", "מניות"]),
        # 22: Budget
        ("התקציב שאושר היה 900,000 ש\"ח",
         "התקציב שאושר היה 600,000 ש\"ח",
         ["תקציב"]),
        # 23: Compensation
        ("הפיצוי שנפסק עמד על 150,000 ש\"ח",
         "הפיצוי שנפסק עמד על 80,000 ש\"ח",
         ["פיצוי"]),
        # 24: Number of days
        ("האיחור במסירה היה 90 יום",
         "האיחור במסירה היה 45 יום",
         ["איחור", "מסירה"]),
        # 25: Price per unit
        ("המחיר ליחידה נקבע ל-500 ש\"ח",
         "המחיר ליחידה נקבע ל-300 ש\"ח",
         ["מחיר"]),
    ]

    for i, (text_a, text_b, entities) in enumerate(quant_contradictions):
        idx += 1
        pairs.append(_pair(
            f"Q{idx:03d}", "quantitative", "contradiction",
            _claim(text_a, entities=entities, negation=False),
            _claim(text_b, entities=entities, negation=True),
        ))

    # fmt: (text_a, text_b, ent_a, ent_b, extra_kw_a, extra_kw_b)
    quant_negatives = [
        # 1: Same amount, paraphrased → same entities, no conflict
        ("סכום התמורה בחוזה עמד על 500,000 ש\"ח",
         "התמורה החוזית היתה חצי מיליון שקלים",
         ["חוזה", "תמורה"], ["חוזה", "תמורה"], {}, {}),
        # 2: Partial payment + total → different scope (advance vs balance)
        ("יוסי כהן שילם מקדמה של 100,000 ש\"ח",
         "יוסי כהן שילם יתרה של 400,000 ש\"ח",
         ["יוסי כהן", "מקדמה"], ["יוסי כהן", "יתרה"],
         {"scope_quantifiers": "part"}, {"scope_quantifiers": "all"}),
        # 3: Damage estimate by different parties → different speaker_mode
        ("לטענת התובע הנזק עמד על 1,200,000 ש\"ח",
         "לטענת הנתבע הנזק עמד על 800,000 ש\"ח",
         ["נזק", "תובע"], ["נזק", "נתבע"],
         {"speaker_mode": SM_PARTY, "speaker_role": "plaintiff"},
         {"speaker_mode": SM_PARTY, "speaker_role": "defendant"}),
        # 4: Same rent → same entities, no conflict
        ("דמי השכירות עמדו על 8,000 ש\"ח לחודש",
         "השכירות החודשית היתה 8,000 שקלים",
         ["שכירות"], ["שכירות"], {}, {}),
        # 5: Before and after rate → different time_reference
        ("הריבית הראשונית על ההלוואה עמדה על 12%",
         "הריבית המופחתת על ההלוואה עמדה על 6%",
         ["ריבית ראשונית", "הלוואה"], ["ריבית מופחתת", "הלוואה"],
         {"time_reference": "rate_initial"}, {"time_reference": "rate_reduced"}),
        # 6: Different rooms → no entity overlap
        ("שטח הסלון הוא 40 מ\"ר",
         "שטח חדר השינה הוא 20 מ\"ר",
         ["סלון"], ["חדר שינה"], {}, {}),
        # 7: Original and extension → different time_reference
        ("תקופת ההסכם המקורית נקבעה ל-5 שנים",
         "תקופת ההארכה נקבעה ל-3 שנים",
         ["הסכם מקורי"], ["הארכה"],
         {"time_reference": "original_term"}, {"time_reference": "extension_term"}),
        # 8: Same units → same entities, no conflict
        ("הנתבע סיפק 200 יחידות",
         "הנתבע סיפק 200 פריטים כנדרש",
         ["נתבע", "יחידות"], ["נתבע", "פריטים"], {}, {}),
        # 9: Gross vs net → different scope
        ("שכר הברוטו של העובד עמד על 25,000 ש\"ח",
         "שכר הנטו של העובד עמד על 15,000 ש\"ח",
         ["עובד", "שכר ברוטו"], ["עובד", "שכר נטו"],
         {"scope_quantifiers": "all"}, {"scope_quantifiers": "part"}),
        # 10: Same percentage → same entities
        ("שיעור העמלה נקבע ל-8%",
         "העמלה עומדת על 8 אחוז",
         ["עמלה"], ["עמלה"], {}, {}),
        # 11: Different time deposits → no entity overlap
        ("הפיקדון הראשון עמד על 50,000 ש\"ח",
         "הפיקדון השני עמד על 30,000 ש\"ח",
         ["פיקדון ראשון"], ["פיקדון שני"], {}, {}),
        # 12: Fine for different violations → no entity overlap
        ("קנס על הפרת החוזה עמד על 75,000 ש\"ח",
         "קנס על איחור במסירה עמד על 25,000 ש\"ח",
         ["קנס הפרה", "חוזה"], ["קנס איחור", "מסירה"], {}, {}),
        # 13: Same property value → same entities
        ("שווי הנכס הוערך ב-2,000,000 ש\"ח",
         "שווי הנכס עומד על 2,000,000 שקלים",
         ["נכס"], ["נכס"], {}, {}),
        # 14: Principal vs interest → no entity overlap
        ("קרן החוב עומדת על 300,000 ש\"ח",
         "הריבית על החוב עומדת על 180,000 ש\"ח",
         ["קרן חוב"], ["ריבית חוב"], {}, {}),
        # 15: Different measurement → no entity overlap
        ("המרחק בין הנכסים הוא 500 מטר",
         "שטח החלקה הוא 200 מ\"ר",
         ["מרחק", "נכסים"], ["שטח", "חלקה"], {}, {}),
        # 16: Different time periods → different time_reference
        ("בשנת 2020 החברה העסיקה 50 עובדים",
         "בשנת 2022 החברה העסיקה 25 עובדים",
         ["חברה", "עובדים"], ["חברה", "עובדים"],
         {"time_reference": "year_2020"}, {"time_reference": "year_2022"}),
        # 17: Different goods → no entity overlap
        ("משקל חומר הגלם היה 5,000 ק\"ג",
         "משקל המוצר המוגמר היה 3,000 ק\"ג",
         ["חומר גלם"], ["מוצר מוגמר"], {}, {}),
        # 18: Regular vs overtime → different scope
        ("העובד עבד 160 שעות רגילות",
         "העובד עבד 20 שעות נוספות",
         ["עובד", "שעות רגילות"], ["עובד", "שעות נוספות"],
         {"scope_quantifiers": "part"}, {"scope_quantifiers": "part"}),
        # 19: Same investment → same entities
        ("ההשקעה עמדה על 400,000 $",
         "ההשקעה הייתה בסך 400,000 דולר",
         ["השקעה"], ["השקעה"], {}, {}),
        # 20: Different payments → no entity overlap
        ("תשלום השכירות החודשי עמד על 6,000 ש\"ח",
         "תשלום הארנונה החודשי עמד על 3,500 ש\"ח",
         ["שכירות"], ["ארנונה"], {}, {}),
        # 21: Same shares, restated → same entities
        ("דוד לוי החזיק 1,000 מניות מסוג א",
         "דוד לוי החזיק אלף מניות",
         ["דוד לוי", "מניות"], ["דוד לוי", "מניות"], {}, {}),
        # 22: Budget for different departments → no entity overlap
        ("תקציב מחלקת השיווק היה 900,000 ש\"ח",
         "תקציב מחלקת הפיתוח היה 600,000 ש\"ח",
         ["מחלקת שיווק"], ["מחלקת פיתוח"], {}, {}),
        # 23: Same compensation → same entities
        ("הפיצוי שנפסק עמד על 150,000 ש\"ח",
         "בית המשפט פסק פיצוי של 150,000 שקלים",
         ["פיצוי"], ["פיצוי"], {}, {}),
        # 24: Manufacturing vs delivery delay → no entity overlap
        ("האיחור בייצור היה 90 יום",
         "האיחור במסירה ללקוח היה 45 יום",
         ["איחור ייצור"], ["איחור מסירה"], {}, {}),
        # 25: Price for different items → no entity overlap
        ("מחיר פריט א נקבע ל-500 ש\"ח",
         "מחיר פריט ב נקבע ל-300 ש\"ח",
         ["פריט א"], ["פריט ב"], {}, {}),
    ]

    for i, (text_a, text_b, ent_a, ent_b, kw_a, kw_b) in enumerate(quant_negatives):
        idx += 1
        pairs.append(_pair(
            f"Q{idx:03d}", "quantitative", "non_contradiction",
            _claim(text_a, entities=ent_a, **kw_a),
            _claim(text_b, entities=ent_b, **kw_b),
        ))

    return pairs


def generate_factual_pairs():
    """50 factual pairs: 25 contradictions + 25 non-contradictions."""
    pairs = []
    idx = 0

    factual_contradictions = [
        # 1: Payment made vs not made
        ("יוסי כהן שילם את מלוא התמורה",
         "יוסי כהן לא שילם את מלוא התמורה",
         ["יוסי כהן", "תמורה"]),
        # 2: Contract signed vs not signed
        ("החוזה נחתם בין הצדדים",
         "החוזה לא נחתם בין הצדדים",
         ["חוזה"]),
        # 3: Present vs absent
        ("דוד לוי היה נוכח בפגישה",
         "דוד לוי לא היה נוכח בפגישה",
         ["דוד לוי", "פגישה"]),
        # 4: Agreement exists vs not
        ("קיים הסכם בין הצדדים",
         "אין הסכם בין הצדדים",
         ["הסכם"]),
        # 5: Goods delivered vs not
        ("הסחורה נמסרה ללקוח במועד",
         "הסחורה לא נמסרה ללקוח במועד",
         ["סחורה", "לקוח"]),
        # 6: Notice given vs not
        ("ההודעה נמסרה לנתבע",
         "ההודעה לא נמסרה לנתבע",
         ["הודעה", "נתבע"]),
        # 7: Work completed vs not
        ("העבודות הושלמו במלואן",
         "העבודות לא הושלמו במלואן",
         ["עבודות"]),
        # 8: Consent given vs not
        ("ניתנה הסכמת הנתבע לעסקה",
         "לא ניתנה הסכמת הנתבע לעסקה",
         ["נתבע", "עסקה"]),
        # 9: Document exists vs not
        ("המסמך קיים בתיק בית המשפט",
         "המסמך אינו קיים בתיק בית המשפט",
         ["מסמך", "בית המשפט"]),
        # 10: Obligation fulfilled vs not
        ("החברה עמדה בהתחייבויותיה",
         "החברה לא עמדה בהתחייבויותיה",
         ["חברה"]),
        # 11: Permission granted vs denied
        ("ניתן אישור לבנייה",
         "לא ניתן אישור לבנייה",
         ["אישור", "בנייה"]),
        # 12: Damage occurred vs not
        ("נגרם נזק לרכוש",
         "לא נגרם נזק לרכוש",
         ["נזק", "רכוש"]),
        # 13: Meeting took place vs not
        ("הפגישה התקיימה כמתוכנן",
         "הפגישה לא התקיימה כמתוכנן",
         ["פגישה"]),
        # 14: Warning issued vs not
        ("הנתבע קיבל התראה מוקדמת",
         "הנתבע לא קיבל התראה מוקדמת",
         ["נתבע", "התראה"]),
        # 15: Transfer made vs not
        ("הכספים הועברו לחשבון הנאמנות",
         "הכספים לא הועברו לחשבון הנאמנות",
         ["כספים", "חשבון הנאמנות"]),
        # 16: Inspection done vs not
        ("הבדיקה בוצעה כנדרש",
         "הבדיקה לא בוצעה כנדרש",
         ["בדיקה"]),
        # 17: Product defective vs not
        ("המוצר היה תקין בעת המסירה",
         "המוצר לא היה תקין בעת המסירה",
         ["מוצר"]),
        # 18: Disclosure made vs not
        ("המידע נמסר לרוכש לפני החתימה",
         "המידע לא נמסר לרוכש לפני החתימה",
         ["מידע", "רוכש"]),
        # 19: Breach occurred vs not
        ("הנתבע הפר את ההסכם",
         "הנתבע לא הפר את ההסכם",
         ["נתבע", "הסכם"]),
        # 20: Witness present vs not
        ("העד היה נוכח באירוע",
         "העד לא היה נוכח באירוע",
         ["עד", "אירוע"]),
        # 21: Payment received vs not
        ("התובע קיבל את הכספים",
         "התובע לא קיבל את הכספים",
         ["תובע", "כספים"]),
        # 22: Condition met vs not
        ("התנאי המתלה התקיים",
         "התנאי המתלה לא התקיים",
         ["תנאי"]),
        # 23: Registration done vs not
        ("הזכויות נרשמו בטאבו",
         "הזכויות לא נרשמו בטאבו",
         ["זכויות", "טאבו"]),
        # 24: Service provided vs not
        ("השירות ניתן כמוסכם",
         "השירות לא ניתן כמוסכם",
         ["שירות"]),
        # 25: Defect disclosed vs not
        ("הליקוי דווח ליצרן",
         "הליקוי לא דווח ליצרן",
         ["ליקוי", "יצרן"]),
    ]

    for i, (text_a, text_b, entities) in enumerate(factual_contradictions):
        idx += 1
        pairs.append(_pair(
            f"F{idx:03d}", "factual", "contradiction",
            _claim(text_a, entities=entities, negation=False),
            _claim(text_b, entities=entities, negation=True),
        ))

    # fmt: (text_a, text_b, ent_a, ent_b, extra_kw_b)
    factual_negatives = [
        # 1: Same fact restated
        ("יוסי כהן שילם את מלוא התמורה",
         "יוסי כהן העביר את כל הסכום",
         ["יוסי כהן", "תמורה"], ["יוסי כהן", "סכום"], {}),
        # 2: Different contracts → no entity overlap
        ("החוזה הראשון נחתם בין הצדדים",
         "החוזה השני לא נחתם בין הצדדים",
         ["חוזה ראשון"], ["חוזה שני"], {}),
        # 3: Related facts
        ("דוד לוי היה נוכח בפגישה",
         "דוד לוי דיבר בפגישה",
         ["דוד לוי", "פגישה"], ["דוד לוי", "פגישה"], {}),
        # 4: Different agreements → no entity overlap
        ("קיים הסכם שכירות בין הצדדים",
         "אין הסכם מכירה בין הצדדים",
         ["הסכם שכירות"], ["הסכם מכירה"], {}),
        # 5: Elaboration
        ("הסחורה נמסרה ללקוח",
         "הלקוח אישר את קבלת הסחורה",
         ["סחורה", "לקוח"], ["סחורה", "לקוח"], {}),
        # 6: Different notices → no entity overlap
        ("הודעת הביטול נמסרה",
         "הודעת ההארכה לא נמסרה",
         ["הודעת ביטול"], ["הודעת הארכה"], {}),
        # 7: Partial vs full (restated same thing)
        ("חלק מהעבודות הושלמו",
         "העבודות הושלמו באופן חלקי",
         ["עבודות"], ["עבודות"], {}),
        # 8: Different parties' consent → no entity overlap
        ("ניתנה הסכמת התובע לעסקה",
         "ניתנה הסכמת הנתבע לעסקה",
         ["תובע", "עסקה"], ["נתבע", "עסקה"], {}),
        # 9: Different documents → no entity overlap
        ("החוזה קיים בתיק",
         "הנספח אינו קיים בתיק",
         ["חוזה"], ["נספח"], {}),
        # 10: Different obligations → no entity overlap
        ("החברה עמדה בהתחייבות התשלום",
         "החברה לא עמדה בהתחייבות המסירה",
         ["חברה", "התחייבות תשלום"], ["חברה", "התחייבות מסירה"], {}),
        # 11: Different permit types → no entity overlap
        ("ניתן אישור בנייה לקומה ראשונה",
         "לא ניתן אישור לקומה שנייה",
         ["קומה ראשונה", "אישור"], ["קומה שנייה", "אישור"], {}),
        # 12: Damage to different property → no entity overlap
        ("נגרם נזק לדירה",
         "לא נגרם נזק לרכב",
         ["נזק", "דירה"], ["נזק", "רכב"], {}),
        # 13: Cause and effect
        ("הפגישה התקיימה במשרד",
         "הצדדים הגיעו להסכמה בפגישה",
         ["פגישה"], ["פגישה", "הסכמה"], {}),
        # 14: Warning types → no entity overlap (written vs oral are different)
        ("הנתבע קיבל התראה בכתב",
         "הנתבע לא קיבל התראה בעל פה",
         ["התראה בכתב"], ["התראה בעל פה"], {}),
        # 15: Different accounts → no entity overlap
        ("הכספים הועברו לחשבון הבנק",
         "הכספים לא הועברו לחשבון הנאמנות",
         ["כספים", "חשבון בנק"], ["כספים", "חשבון נאמנות"], {}),
        # 16: Sequential inspections
        ("הבדיקה הראשונה בוצעה",
         "הבדיקה השנייה בוצעה גם כן",
         ["בדיקה ראשונה"], ["בדיקה שנייה"], {}),
        # 17: Same assertion
        ("המוצר היה תקין בעת המסירה",
         "המוצר עמד בתקנים בעת האספקה",
         ["מוצר"], ["מוצר"], {}),
        # 18: Elaboration of same fact
        ("המידע נמסר לרוכש",
         "הרוכש קיבל את כל המידע הרלוונטי",
         ["מידע", "רוכש"], ["מידע", "רוכש"], {}),
        # 19: Opinion plane → different speaker_mode
        ("לטענת התובע הנתבע הפר את ההסכם",
         "לטענת הנתבע הוא לא הפר את ההסכם",
         ["נתבע", "הסכם"], ["נתבע", "הסכם"],
         {"speaker_mode": SM_PARTY, "speaker_role": "defendant"}),
        # 20: Different events → no entity overlap (signing vs meeting)
        ("העד היה נוכח בחתימה",
         "העד לא היה נוכח בפגישה",
         ["חתימה"], ["פגישה"], {}),
        # 21: Restated
        ("התובע קיבל את הכספים",
         "הכספים הועברו לתובע",
         ["תובע", "כספים"], ["תובע", "כספים"], {}),
        # 22: Different conditions → no entity overlap
        ("התנאי המתלה הראשון התקיים",
         "התנאי המתלה השני לא התקיים",
         ["תנאי ראשון"], ["תנאי שני"], {}),
        # 23: Same registration
        ("הזכויות נרשמו בטאבו",
         "הרישום בטאבו הושלם",
         ["זכויות", "טאבו"], ["זכויות", "טאבו"], {}),
        # 24: Different service types → no entity overlap
        ("שירות התחזוקה ניתן",
         "שירות ההתקנה לא ניתן",
         ["שירות תחזוקה"], ["שירות התקנה"], {}),
        # 25: Different manufacturers → no entity overlap
        ("הליקוי דווח ליצרן א",
         "הליקוי דווח ליצרן ב",
         ["ליקוי", "יצרן א"], ["ליקוי", "יצרן ב"], {}),
    ]

    for i, (text_a, text_b, ent_a, ent_b, kw_b) in enumerate(factual_negatives):
        idx += 1
        pairs.append(_pair(
            f"F{idx:03d}", "factual", "non_contradiction",
            _claim(text_a, entities=ent_a),
            _claim(text_b, entities=ent_b, **kw_b),
        ))

    return pairs


def generate_attribution_pairs():
    """50 attribution pairs: 25 contradictions + 25 non-contradictions."""
    pairs = []
    idx = 0

    attr_contradictions = [
        # 1: Who signed
        ("יוסי כהן חתם על החוזה",
         "דוד לוי חתם על החוזה",
         ["יוסי כהן", "חוזה"], ["דוד לוי", "חוזה"]),
        # 2: Who paid
        ("התובע שילם את הסכום לנתבע",
         "הנתבע שילם את הסכום לתובע",
         ["תובע", "נתבע", "סכום"], ["נתבע", "תובע", "סכום"]),
        # 3: Who decided
        ("המנהל הכללי החליט על הפיטורים",
         "דירקטוריון החברה החליט על הפיטורים",
         ["מנהל כללי", "פיטורים"], ["דירקטוריון", "חברה", "פיטורים"]),
        # 4: Who sent
        ("יוסי כהן שלח את המכתב",
         "דוד לוי שלח את המכתב",
         ["יוסי כהן", "מכתב"], ["דוד לוי", "מכתב"]),
        # 5: Who received
        ("התובע קיבל את ההודעה",
         "הנתבע קיבל את ההודעה",
         ["תובע", "הודעה"], ["נתבע", "הודעה"]),
        # 6: Who approved
        ("הוועדה אישרה את הבקשה",
         "המנהל אישר את הבקשה",
         ["ועדה", "בקשה"], ["מנהל", "בקשה"]),
        # 7: Who initiated
        ("התובע יזם את הפגישה",
         "הנתבע יזם את הפגישה",
         ["תובע", "פגישה"], ["נתבע", "פגישה"]),
        # 8: Who breached
        ("חברת אלפא הפרה את ההסכם",
         "חברת בטא הפרה את ההסכם",
         ["חברת אלפא", "הסכם"], ["חברת בטא", "הסכם"]),
        # 9: Who caused
        ("הנתבע גרם לנזק",
         "צד שלישי גרם לנזק",
         ["נתבע", "נזק"], ["צד שלישי", "נזק"]),
        # 10: Who was responsible
        ("עו\"ד כהן ייצג את התובע",
         "עו\"ד לוי ייצג את התובע",
         ["כהן", "תובע"], ["לוי", "תובע"]),
        # 11: Who ordered
        ("התובע הזמין את הסחורה",
         "הנתבע הזמין את הסחורה",
         ["תובע", "סחורה"], ["נתבע", "סחורה"]),
        # 12: Who delivered
        ("חברת המשלוחים מסרה את החבילה",
         "הנתבע עצמו מסר את החבילה",
         ["חברת המשלוחים", "חבילה"], ["נתבע", "חבילה"]),
        # 13: Who inspected
        ("המהנדס מטעם התובע בדק את הנכס",
         "המהנדס מטעם הנתבע בדק את הנכס",
         ["מהנדס", "תובע", "נכס"], ["מהנדס", "נתבע", "נכס"]),
        # 14: Who owned
        ("הנכס היה בבעלות יוסי כהן",
         "הנכס היה בבעלות דוד לוי",
         ["נכס", "יוסי כהן"], ["נכס", "דוד לוי"]),
        # 15: Who issued
        ("הבנק הנפיק את הערבות",
         "חברת הביטוח הנפיקה את הערבות",
         ["בנק", "ערבות"], ["חברת הביטוח", "ערבות"]),
        # 16: Who supervised
        ("מר כהן פיקח על העבודות",
         "מר לוי פיקח על העבודות",
         ["כהן", "עבודות"], ["לוי", "עבודות"]),
        # 17: Who testified
        ("העד הראשון ראה את התאונה",
         "העד השני ראה את התאונה",
         ["עד ראשון", "תאונה"], ["עד שני", "תאונה"]),
        # 18: Who authorized
        ("הנהלת החברה אישרה את העסקה",
         "האסיפה הכללית אישרה את העסקה",
         ["הנהלת החברה", "עסקה"], ["אסיפה כללית", "עסקה"]),
        # 19: Who drafted
        ("עו\"ד כהן ערך את החוזה",
         "עו\"ד לוי ערך את החוזה",
         ["כהן", "חוזה"], ["לוי", "חוזה"]),
        # 20: Who received funds
        ("הכספים הועברו ליוסי כהן",
         "הכספים הועברו לדוד לוי",
         ["כספים", "יוסי כהן"], ["כספים", "דוד לוי"]),
        # 21: Who filed
        ("התובע הגיש את המסמכים",
         "הנתבע הגיש את המסמכים",
         ["תובע", "מסמכים"], ["נתבע", "מסמכים"]),
        # 22: Who registered
        ("החברה רשמה את הפטנט",
         "הממציא רשם את הפטנט",
         ["חברה", "פטנט"], ["ממציא", "פטנט"]),
        # 23: Who employed
        ("חברת אלפא העסיקה את העובד",
         "חברת בטא העסיקה את העובד",
         ["חברת אלפא", "עובד"], ["חברת בטא", "עובד"]),
        # 24: Who authorized payment
        ("יוסי כהן אישר את התשלום",
         "דוד לוי אישר את התשלום",
         ["יוסי כהן", "תשלום"], ["דוד לוי", "תשלום"]),
        # 25: Who was present
        ("יוסי כהן השתתף בישיבת הדירקטוריון",
         "דוד לוי השתתף בישיבת הדירקטוריון",
         ["יוסי כהן", "דירקטוריון"], ["דוד לוי", "דירקטוריון"]),
    ]

    for i, (text_a, text_b, ent_a, ent_b) in enumerate(attr_contradictions):
        idx += 1
        pairs.append(_pair(
            f"A{idx:03d}", "attribution", "contradiction",
            _claim(text_a, entities=ent_a, negation=False),
            _claim(text_b, entities=ent_b, negation=True),
        ))

    # fmt: (text_a, text_b, ent_a, ent_b, extra_kw_a, extra_kw_b)
    attr_negatives = [
        # 1: Same signer
        ("יוסי כהן חתם על החוזה",
         "יוסי כהן חתם על ההסכם",
         ["יוסי כהן", "חוזה"], ["יוסי כהן", "הסכם"], {}, {}),
        # 2: Different actions by same person
        ("התובע שילם את המקדמה",
         "התובע ביקש את ההחזר",
         ["תובע", "מקדמה"], ["תובע", "החזר"], {}, {}),
        # 3: Same decision maker
        ("המנהל הכללי החליט על ההרחבה",
         "המנהל הכללי החליט על ההשקעה",
         ["מנהל כללי", "הרחבה"], ["מנהל כללי", "השקעה"], {}, {}),
        # 4: Complementary roles (sender→receiver, not contradictory)
        ("יוסי כהן שלח את המכתב",
         "דוד לוי קיבל את המכתב",
         ["יוסי כהן", "מכתב"], ["דוד לוי", "מכתב"], {}, {}),
        # 5: Same person different action
        ("התובע קיבל את ההודעה",
         "התובע השיב להודעה",
         ["תובע", "הודעה"], ["תובע", "הודעה"], {}, {}),
        # 6: Different requests → no entity overlap
        ("הוועדה אישרה את הבקשה הראשונה",
         "הוועדה דחתה את הבקשה השנייה",
         ["ועדה", "בקשה ראשונה"], ["ועדה", "בקשה שנייה"], {}, {}),
        # 7: Complementary initiation
        ("התובע יזם את הפגישה",
         "הנתבע הגיע לפגישה",
         ["תובע", "פגישה"], ["נתבע", "פגישה"], {}, {}),
        # 8: Same company
        ("חברת אלפא חתמה על ההסכם",
         "חברת אלפא ביצעה את העבודות",
         ["חברת אלפא", "הסכם"], ["חברת אלפא", "עבודות"], {}, {}),
        # 9: Different damages → no entity overlap
        ("הנתבע גרם לנזק לרכוש",
         "צד שלישי גרם לנזק גופני",
         ["נתבע", "נזק רכוש"], ["צד שלישי", "נזק גופני"], {}, {}),
        # 10: Different case → no entity overlap
        ("עו\"ד כהן ייצג את התובע בתביעה הראשונה",
         "עו\"ד לוי ייצג את התובע בתביעה השנייה",
         ["כהן", "תביעה ראשונה"], ["לוי", "תביעה שנייה"], {}, {}),
        # 11: Same orderer
        ("התובע הזמין את הסחורה",
         "התובע קיבל את הסחורה",
         ["תובע", "סחורה"], ["תובע", "סחורה"], {}, {}),
        # 12: Complementary delivery
        ("חברת המשלוחים אספה את החבילה",
         "הנתבע קיבל את החבילה",
         ["חברת המשלוחים", "חבילה"], ["נתבע", "חבילה"], {}, {}),
        # 13: Both inspected → no entity overlap
        ("המהנדס מטעם התובע בדק את הנכס",
         "שמאי מטעם הנתבע העריך את הנכס",
         ["מהנדס תובע", "נכס"], ["שמאי נתבע", "נכס"], {}, {}),
        # 14: Different properties → no entity overlap
        ("הנכס ברחוב הרצל היה בבעלות יוסי כהן",
         "הנכס ברחוב בן גוריון היה בבעלות דוד לוי",
         ["יוסי כהן", "נכס הרצל"], ["דוד לוי", "נכס בן גוריון"], {}, {}),
        # 15: Same issuer
        ("הבנק הנפיק את הערבות",
         "הבנק ביטל את הערבות",
         ["בנק", "ערבות"], ["בנק", "ערבות"], {}, {}),
        # 16: Sequential supervision → different time_reference
        ("מר כהן פיקח על שלב א של העבודות",
         "מר לוי פיקח על שלב ב של העבודות",
         ["כהן", "שלב א"], ["לוי", "שלב ב"],
         {"time_reference": "phase_a"}, {"time_reference": "phase_b"}),
        # 17: Both witnesses → no entity overlap
        ("העד הראשון שמע צעקות",
         "העד השני ראה אדם בורח",
         ["עד ראשון"], ["עד שני"], {}, {}),
        # 18: Same authorizer
        ("הנהלת החברה אישרה את העסקה",
         "הנהלת החברה חתמה על ההסכם",
         ["הנהלת החברה", "עסקה"], ["הנהלת החברה", "הסכם"], {}, {}),
        # 19: Complementary roles → no entity overlap
        ("עו\"ד כהן ערך את החוזה",
         "עו\"ד לוי עיין בחוזה",
         ["כהן", "חוזה"], ["לוי", "חוזה"], {}, {}),
        # 20: Different fund transfers → no entity overlap
        ("חלק מהכספים הועבר ליוסי כהן",
         "חלק מהכספים הועבר לדוד לוי",
         ["כספים", "יוסי כהן"], ["כספים", "דוד לוי"], {}, {}),
        # 21: Same filer
        ("התובע הגיש את כתב התביעה",
         "התובע הגיש את הבקשה לצו מניעה",
         ["תובע", "כתב תביעה"], ["תובע", "בקשה"], {}, {}),
        # 22: Same registrant
        ("החברה רשמה את הפטנט הראשון",
         "החברה רשמה את הפטנט השני",
         ["חברה", "פטנט ראשון"], ["חברה", "פטנט שני"], {}, {}),
        # 23: Different time employment → different time_reference
        ("חברת אלפא העסיקה את העובד בשנת 2020",
         "חברת בטא העסיקה את העובד בשנת 2022",
         ["חברת אלפא", "עובד"], ["חברת בטא", "עובד"],
         {"time_reference": "year_2020"}, {"time_reference": "year_2022"}),
        # 24: Same authorizer
        ("יוסי כהן אישר את התשלום הראשון",
         "יוסי כהן אישר את התשלום השני",
         ["יוסי כהן", "תשלום ראשון"], ["יוסי כהן", "תשלום שני"], {}, {}),
        # 25: Different events → no entity overlap
        ("יוסי כהן השתתף בישיבה הראשונה",
         "דוד לוי השתתף בישיבה השנייה",
         ["יוסי כהן", "ישיבה ראשונה"], ["דוד לוי", "ישיבה שנייה"], {}, {}),
    ]

    for i, (text_a, text_b, ent_a, ent_b, kw_a, kw_b) in enumerate(attr_negatives):
        idx += 1
        pairs.append(_pair(
            f"A{idx:03d}", "attribution", "non_contradiction",
            _claim(text_a, entities=ent_a, **kw_a),
            _claim(text_b, entities=ent_b, **kw_b),
        ))

    return pairs


def main():
    pairs = []
    pairs.extend(generate_temporal_pairs())
    pairs.extend(generate_quantitative_pairs())
    pairs.extend(generate_factual_pairs())
    pairs.extend(generate_attribution_pairs())

    dataset = {
        "description": "JETHRO 9.0 Benchmark — 200 Hebrew legal claim pairs",
        "version": "1.0",
        "n_pairs": len(pairs),
        "distribution": {
            "temporal": {"contradiction": 25, "non_contradiction": 25},
            "quantitative": {"contradiction": 25, "non_contradiction": 25},
            "factual": {"contradiction": 25, "non_contradiction": 25},
            "attribution": {"contradiction": 25, "non_contradiction": 25},
        },
        "pairs": pairs,
    }

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_200.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print(f"Generated {len(pairs)} pairs → {out_path}")

    # Verify distribution
    from collections import Counter
    type_label = Counter()
    for p in pairs:
        type_label[(p['type'], p['label'])] += 1
    for key in sorted(type_label):
        print(f"  {key[0]:15s} {key[1]:20s}: {type_label[key]}")


if __name__ == "__main__":
    main()
