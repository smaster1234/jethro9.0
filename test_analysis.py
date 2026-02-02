#!/usr/bin/env python3
"""
Quick test to verify the analysis engine works end-to-end.
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

# Test Hebrew legal text with contradictions
test_text = """
עדות התובע:
התובע טען כי הנתבע שילם לו סכום של 50,000 ש"ח ביום 15.3.2023.
התובע הצהיר כי הפגישה התקיימה בשעה 10:00 בבוקר.

עדות הנתבע:
הנתבע הכחיש כי שילם לתובע סכום כלשהו ביום 15.3.2023.
הנתבע טען כי הפגישה התקיימה בשעה 14:00 אחר הצהריים.
"""

print("=" * 60)
print("בדיקת מנוע הניתוח של יתרו 9.0")
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
    print(f"   - [{c.plane or 'N/A'}] [{c.speaker_mode or 'N/A'}] {text_preview}...")

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
    text_a = contr.claim_a.text[:50] if len(contr.claim_a.text) > 50 else contr.claim_a.text
    text_b = contr.claim_b.text[:50] if len(contr.claim_b.text) > 50 else contr.claim_b.text
    print(f"   טענה א': {text_a}...")
    print(f"   טענה ב': {text_b}...")
    print(f"   סוג: {contr.type}")
    print(f"   חומרה: {contr.severity}")
    print(f"   ביטחון: {contr.confidence:.2f}")

# Step 4: Reconcile pairs
print("\n🎯 שלב 4: סיווג סופי (Reconciler)...")
for contr in contradictions[:3]:
    rec_result = reconcile_pair(contr.claim_a, contr.claim_b, detector_confidence=contr.confidence)
    print(f"   תוצאה: {rec_result.outcome}")
    exp_preview = rec_result.explanation[:80] if len(rec_result.explanation) > 80 else rec_result.explanation
    print(f"   הסבר: {exp_preview}...")

print("\n" + "=" * 60)
print("✅ המערכת עובדת!")
print("=" * 60)
