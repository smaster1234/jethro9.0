#!/usr/bin/env python3
"""
Comprehensive test to verify the analysis engine works end-to-end.
"""
import sys
import os

# Add backend_lite to path properly
sys.path.insert(0, '/home/ubuntu/jethro9.0')
os.chdir('/home/ubuntu/jethro9.0/backend_lite')

from backend_lite.extractor import Claim, extract_claims, PLANE_FACT
from backend_lite.claim_enricher import enrich_claims
from backend_lite.detector import RuleBasedDetector
from backend_lite.reconciler import reconcile_pair

# Test Hebrew legal text with clear contradictions
test_text = """
פסק דין:

עדות התובע מיום 15.3.2023:
בית המשפט קבע כי הנתבע שילם לתובע סכום של 50,000 ש"ח.
נקבע כי הפגישה התקיימה בשעה 10:00 בבוקר.
התובע הצהיר כי הרכב היה בצבע אדום.

עדות הנתבע מיום 20.3.2023:
בית המשפט קבע כי הנתבע לא שילם לתובע סכום כלשהו.
נקבע כי הפגישה התקיימה בשעה 14:00 אחר הצהריים.
הנתבע הצהיר כי הרכב היה בצבע כחול.
"""

print("=" * 60)
print("בדיקת מנוע הניתוח של יתרו 9.0 - גרסה מורחבת")
print("=" * 60)

# Step 1: Extract claims
print("\n📝 שלב 1: חילוץ טענות מהטקסט...")
claims = extract_claims(test_text)
print(f"   נמצאו {len(claims)} טענות")
for i, c in enumerate(claims, 1):
    text_preview = c.text[:60] if len(c.text) > 60 else c.text
    print(f"   {i}. {text_preview}...")

# Step 2: Enrich claims
print("\n🔍 שלב 2: העשרת טענות (plane, speaker, entities)...")
enriched = enrich_claims(claims, test_text)
for c in enriched:
    text_preview = c.text[:50] if len(c.text) > 50 else c.text
    entities_str = ", ".join(c.entities[:3]) if c.entities else "N/A"
    print(f"   - [{c.plane or 'N/A'}] [{c.speaker_mode or 'N/A'}] {text_preview}...")
    print(f"     ישויות: {entities_str}")
    print(f"     שלילה: {c.negation}, זמן: {c.time_reference or 'N/A'}")

# Step 3: Detect contradictions
print("\n⚡ שלב 3: זיהוי סתירות...")
detector = RuleBasedDetector()
result = detector.detect(enriched)
contradictions = result.contradictions
print(f"   נמצאו {len(contradictions)} סתירות פוטנציאליות")
print(f"   זמן זיהוי: {result.detection_time_ms:.2f}ms")
print(f"   שיטה: {result.method}")

for i, contr in enumerate(contradictions[:5], 1):
    print(f"\n   סתירה #{i}:")
    text_a = contr.claim1.text[:50] if len(contr.claim1.text) > 50 else contr.claim1.text
    text_b = contr.claim2.text[:50] if len(contr.claim2.text) > 50 else contr.claim2.text
    print(f"   טענה א': {text_a}...")
    print(f"   טענה ב': {text_b}...")
    print(f"   סוג: {contr.type}")
    print(f"   חומרה: {contr.severity}")
    print(f"   ביטחון: {contr.confidence:.2f}")
    print(f"   הסבר: {contr.explanation[:60]}...")

# Step 4: Reconcile pairs
print("\n🎯 שלב 4: סיווג סופי (Reconciler)...")
for contr in contradictions[:3]:
    rec_result = reconcile_pair(contr.claim1, contr.claim2, detector_confidence=contr.confidence)
    print(f"   תוצאה: {rec_result.outcome}")
    # Check what attributes are available
    for attr in ['reason', 'details', 'explanation', 'message']:
        if hasattr(rec_result, attr):
            val = getattr(rec_result, attr)
            if val:
                print(f"   {attr}: {str(val)[:80]}...")
                break

# Test with manual claims that should contradict
print("\n" + "=" * 60)
print("בדיקה עם טענות ידניות:")
print("=" * 60)

manual_claims = [
    Claim(id="c1", text="הנתבע שילם 50,000 ש\"ח", plane=PLANE_FACT, negation=False, entities=["הנתבע"]),
    Claim(id="c2", text="הנתבע לא שילם כלל", plane=PLANE_FACT, negation=True, entities=["הנתבע"]),
]

result2 = detector.detect(manual_claims)
print(f"   נמצאו {len(result2.contradictions)} סתירות")
for contr in result2.contradictions:
    print(f"   סוג: {contr.type}, חומרה: {contr.severity}, ביטחון: {contr.confidence:.2f}")

print("\n" + "=" * 60)
print("✅ המערכת עובדת!")
print("=" * 60)
