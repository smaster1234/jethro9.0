#!/usr/bin/env python3
"""
Test cross-examination question generation quality.
"""
import sys
import os

sys.path.insert(0, '/home/ubuntu/jethro9.0')
os.chdir('/home/ubuntu/jethro9.0/backend_lite')

from backend_lite.extractor import Claim, extract_claims, PLANE_FACT
from backend_lite.claim_enricher import enrich_claims
from backend_lite.detector import RuleBasedDetector
from backend_lite.cross_exam import generate_cross_exam_questions

# Test Hebrew legal text with clear contradictions
test_text = """
פסק דין בעניין תביעת נזיקין:

עדות התובע מיום 15.3.2023:
התובע הצהיר כי הנתבע שילם לו סכום של 50,000 ש"ח במזומן.
התובע טען כי הפגישה התקיימה בשעה 10:00 בבוקר במשרדו.
התובע הצהיר כי הרכב שנפגע היה בצבע אדום.
התובע אמר כי היה לבד בזמן האירוע.

עדות הנתבע מיום 20.3.2023:
הנתבע הכחיש כי שילם לתובע סכום כלשהו.
הנתבע טען כי הפגישה התקיימה בשעה 14:00 אחר הצהריים בביתו.
הנתבע הצהיר כי הרכב היה בצבע כחול ולא אדום.
הנתבע טען כי היו שני עדים נוספים בזמן האירוע.
"""

print("=" * 70)
print("בדיקת איכות יצירת שאלות לחקירה נגדית")
print("=" * 70)

# Step 1: Extract and enrich claims
print("\n📝 שלב 1: חילוץ והעשרת טענות...")
claims = extract_claims(test_text)
enriched = enrich_claims(claims, test_text)
print(f"   נמצאו {len(enriched)} טענות מועשרות")

# Step 2: Detect contradictions
print("\n⚡ שלב 2: זיהוי סתירות...")
detector = RuleBasedDetector()
result = detector.detect(enriched)
contradictions = result.contradictions
print(f"   נמצאו {len(contradictions)} סתירות")

# Step 3: Generate cross-examination questions
print("\n🎯 שלב 3: יצירת שאלות לחקירה נגדית...")
cross_exam_sets = generate_cross_exam_questions(contradictions, max_questions_per=5)
print(f"   נוצרו {len(cross_exam_sets)} סטים של שאלות")

# Display results
for i, ce_set in enumerate(cross_exam_sets, 1):
    print(f"\n{'='*70}")
    print(f"סט שאלות #{i} - סתירה: {ce_set.contradiction_id}")
    print(f"צד יעד: {ce_set.target_party or 'לא מוגדר'}")
    print(f"{'='*70}")
    
    # Find the corresponding contradiction
    contr = next((c for c in contradictions if c.id == ce_set.contradiction_id), None)
    if contr:
        print(f"\n📌 סוג הסתירה: {contr.type}")
        print(f"📌 חומרה: {contr.severity}")
        print(f"📌 ביטחון: {contr.confidence:.2f}")
        print(f"\n📄 טענה א': {contr.claim1.text[:80]}...")
        print(f"📄 טענה ב': {contr.claim2.text[:80]}...")
    
    print(f"\n🔍 שאלות לחקירה נגדית ({len(ce_set.questions)} שאלות):")
    for j, q in enumerate(ce_set.questions, 1):
        print(f"\n   שאלה {j}:")
        print(f"   ❓ {q.question}")
        print(f"   🎯 מטרה: {q.purpose}")
        if q.follow_up:
            print(f"   ➡️ המשך: {q.follow_up}")
        if q.trap_branch:
            print(f"   🪤 מלכודת: {q.trap_branch}")
    
    if ce_set.strategy_notes:
        print(f"\n📋 הערות אסטרטגיות:")
        for note in ce_set.strategy_notes:
            print(f"   • {note}")

print("\n" + "=" * 70)
print("✅ בדיקה הושלמה!")
print("=" * 70)
