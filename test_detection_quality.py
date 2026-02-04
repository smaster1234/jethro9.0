#!/usr/bin/env python3
"""
Test contradiction detection quality with complex legal scenarios.
"""
import sys
import os

sys.path.insert(0, '/home/ubuntu/jethro9.0')
os.chdir('/home/ubuntu/jethro9.0/backend_lite')

from backend_lite.extractor import Claim, PLANE_FACT
from backend_lite.detector import RuleBasedDetector

# Test scenarios with expected results
test_cases = [
    {
        "name": "סתירה כמותית - סכומים שונים",
        "claims": [
            Claim(id="c1", text="התובע קיבל סכום של 50,000 ש\"ח", plane=PLANE_FACT, entities=["התובע"]),
            Claim(id="c2", text="התובע קיבל סכום של 30,000 ש\"ח", plane=PLANE_FACT, entities=["התובע"]),
        ],
        "expected_type": "QUANT",
        "should_detect": True
    },
    {
        "name": "סתירה זמנית - תאריכים שונים",
        "claims": [
            Claim(id="c3", text="האירוע התרחש ביום 15.3.2023", plane=PLANE_FACT, time_reference="15.3.2023"),
            Claim(id="c4", text="האירוע התרחש ביום 20.5.2023", plane=PLANE_FACT, time_reference="20.5.2023"),
        ],
        "expected_type": "TEMPORAL",
        "should_detect": True
    },
    {
        "name": "סתירה בנוכחות - היה/לא היה",
        "claims": [
            Claim(id="c5", text="הנתבע היה נוכח בפגישה", plane=PLANE_FACT, negation=False, entities=["הנתבע"]),
            Claim(id="c6", text="הנתבע לא היה נוכח בפגישה", plane=PLANE_FACT, negation=True, entities=["הנתבע"]),
        ],
        "expected_type": "PRESENCE",
        "should_detect": True
    },
    {
        "name": "סתירה בזהות - אנשים שונים",
        "claims": [
            Claim(id="c7", text="דוד ביצע את העבודה", plane=PLANE_FACT, entities=["דוד"]),
            Claim(id="c8", text="יוסי ביצע את העבודה", plane=PLANE_FACT, entities=["יוסי"]),
        ],
        "expected_type": "IDENTITY",
        "should_detect": True
    },
    {
        "name": "לא סתירה - אותו מידע",
        "claims": [
            Claim(id="c9", text="הפגישה התקיימה בתל אביב", plane=PLANE_FACT),
            Claim(id="c10", text="הפגישה התקיימה בתל אביב", plane=PLANE_FACT),
        ],
        "expected_type": None,
        "should_detect": False
    },
    {
        "name": "סתירה בשעות - זמנים שונים",
        "claims": [
            Claim(id="c11", text="הפגישה התקיימה בשעה 10:00", plane=PLANE_FACT),
            Claim(id="c12", text="הפגישה התקיימה בשעה 16:00", plane=PLANE_FACT),
        ],
        "expected_type": "TEMPORAL",
        "should_detect": True
    },
]

print("=" * 70)
print("בדיקת איכות זיהוי סתירות - תרחישים מורכבים")
print("=" * 70)

detector = RuleBasedDetector()
passed = 0
failed = 0

for test in test_cases:
    print(f"\n📋 תרחיש: {test['name']}")
    print(f"   טענה א': {test['claims'][0].text}")
    print(f"   טענה ב': {test['claims'][1].text}")
    
    result = detector.detect(test['claims'])
    detected = len(result.contradictions) > 0
    
    if detected == test['should_detect']:
        status = "✅ עבר"
        passed += 1
    else:
        status = "❌ נכשל"
        failed += 1
    
    print(f"   צפוי: {'כן' if test['should_detect'] else 'לא'} | בפועל: {'כן' if detected else 'לא'} | {status}")
    
    if detected:
        contr = result.contradictions[0]
        print(f"   סוג: {contr.type} | חומרה: {contr.severity} | ביטחון: {contr.confidence:.2f}")
        if test['expected_type'] and test['expected_type'] not in str(contr.type):
            print(f"   ⚠️ סוג לא תואם: צפוי {test['expected_type']}")

print(f"\n{'='*70}")
print(f"סיכום: {passed}/{len(test_cases)} עברו ({100*passed/len(test_cases):.0f}%)")
print(f"{'='*70}")
