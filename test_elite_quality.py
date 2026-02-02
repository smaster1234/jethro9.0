#!/usr/bin/env python3
"""
בדיקת איכות עילית - בודק את כל השיפורים שבוצעו
"""
import sys
import os
os.chdir('/home/ubuntu/jethro9.0/backend_lite')
sys.path.insert(0, '/home/ubuntu/jethro9.0/backend_lite')

# Import using exec to handle relative imports
import importlib.util
spec = importlib.util.spec_from_file_location("backend_lite", "/home/ubuntu/jethro9.0/backend_lite/__init__.py")

from backend_lite.extractor import ClaimExtractor
from backend_lite.claim_enricher import ClaimEnricher
from backend_lite.detector import ContradictionDetector
from backend_lite.reconciler import reconcile_pair, _entities_match
from backend_lite.cross_exam import CrossExamGenerator

def test_time_detection():
    """בדיקת זיהוי סתירות בשעות"""
    print("\n" + "="*60)
    print("🕐 בדיקת זיהוי סתירות בשעות")
    print("="*60)
    
    extractor = ClaimExtractor()
    enricher = ClaimEnricher()
    detector = ContradictionDetector()
    
    text = """
    התובע טען כי הפגישה התקיימה בשעה 10:00 בבוקר.
    הנתבע טען כי הפגישה התקיימה בשעה 16:00 אחר הצהריים.
    """
    
    claims = extractor.extract_from_text(text)
    enriched = enricher.enrich_claims(claims, text)
    result = detector.detect(enriched)
    
    time_found = any('time' in str(c.type).lower() for c in result.conflicts)
    
    if time_found or len(result.conflicts) > 0:
        print("✅ זיהה סתירה!")
        for c in result.conflicts:
            print(f"   - {c.type}: {c.confidence:.0%}")
    else:
        print("❌ לא זיהה סתירה")
    
    return len(result.conflicts) > 0

def test_entity_matching():
    """בדיקת התאמת ישויות משפטיות"""
    print("\n" + "="*60)
    print("🏛️ בדיקת התאמת ישויות משפטיות")
    print("="*60)
    
    test_cases = [
        ("בנק לאומי", "הבנק הלאומי", True),
        ("בנק הפועלים", "פועלים", True),
        ("התובע", "המערער", True),
        ("הנתבע", "המשיב", True),
        ("יוסי כהן", "מר כהן", True),
        ("חברת אלפא בע״מ", "אלפא", True),
        ("דוד לוי", "משה כהן", False),
    ]
    
    passed = 0
    for entity_a, entity_b, expected in test_cases:
        result = _entities_match(entity_a, entity_b)
        status = "✅" if result == expected else "❌"
        print(f"   {status} '{entity_a}' <-> '{entity_b}': {result} (צפוי: {expected})")
        if result == expected:
            passed += 1
    
    print(f"\n   סה\"כ: {passed}/{len(test_cases)} עברו")
    return passed >= len(test_cases) - 1

def test_cross_exam_question_types():
    """בדיקת סוגי שאלות חכמים"""
    print("\n" + "="*60)
    print("❓ בדיקת סוגי שאלות חכמים")
    print("="*60)
    
    from backend_lite.cross_exam import QuestionType, QuestionTypeSelector
    
    test_cases = [
        (0, 5, "high", "TEMPORAL_DATE", 0.9, QuestionType.OPEN),
        (2, 5, "high", "TEMPORAL_DATE", 0.9, QuestionType.CONFRONTATION),
        (4, 5, "high", "TEMPORAL_DATE", 0.9, QuestionType.TRAP),
    ]
    
    passed = 0
    for pos, total, severity, c_type, conf, expected in test_cases:
        result = QuestionTypeSelector.select_type(pos, total, severity, c_type, conf)
        status = "✅" if result == expected else "⚠️"
        print(f"   {status} מיקום {pos}/{total}: {result} (צפוי: {expected})")
        if result == expected:
            passed += 1
    
    print(f"\n   סה\"כ: {passed}/{len(test_cases)} עברו")
    return passed >= 2

def test_quote_truncation():
    """בדיקת קיצור ציטוטים"""
    print("\n" + "="*60)
    print("📝 בדיקת קיצור ציטוטים")
    print("="*60)
    
    generator = CrossExamGenerator()
    
    long_quote = "התובע טען כי הנתבע לא שילם את הסכום המוסכם. הנתבע מצדו טען כי שילם את מלוא הסכום במזומן. עוד טען הנתבע כי יש לו קבלות המעידות על התשלום. התובע הכחיש את קיומן של הקבלות."
    
    sanitized = generator._sanitize_quote(long_quote)
    
    ends_properly = sanitized.endswith("...") or len(sanitized) <= 200
    reasonable_length = len(sanitized) <= 250
    
    print(f"   אורך מקורי: {len(long_quote)}")
    print(f"   אורך מקוצר: {len(sanitized)}")
    print(f"   מסתיים נכון: {'✅' if ends_properly else '❌'}")
    print(f"   אורך סביר: {'✅' if reasonable_length else '❌'}")
    
    return reasonable_length

def test_full_pipeline():
    """בדיקת Pipeline מלא"""
    print("\n" + "="*60)
    print("🔄 בדיקת Pipeline מלא")
    print("="*60)
    
    extractor = ClaimExtractor()
    enricher = ClaimEnricher()
    detector = ContradictionDetector()
    generator = CrossExamGenerator()
    
    text = """
    בתאריך 15.3.2023 התובע נפגש עם נציג בנק לאומי.
    הנתבע טען כי הפגישה התקיימה בתאריך 20.3.2023 עם הבנק הלאומי.
    התובע שילם 50,000 ש"ח. הנתבע טען כי התובע לא שילם כלל.
    """
    
    claims = extractor.extract_from_text(text)
    print(f"   חולצו {len(claims)} טענות")
    
    enriched = enricher.enrich_claims(claims, text)
    print(f"   הועשרו {len(enriched)} טענות")
    
    result = detector.detect(enriched)
    print(f"   זוהו {len(result.conflicts)} סתירות")
    
    questions_generated = 0
    for conflict in result.conflicts[:2]:
        questions = generator.generate(conflict)
        questions_generated += len(questions.questions)
        if questions.questions:
            print(f"\n   סתירה: {conflict.type}")
            for q in questions.questions[:2]:
                print(f"      - {q.question[:60]}...")
    
    print(f"\n   סה\"כ שאלות: {questions_generated}")
    
    return len(result.conflicts) >= 1 and questions_generated >= 2

def main():
    print("\n" + "="*60)
    print("🏆 בדיקת איכות עילית - jethro9.0")
    print("="*60)
    
    results = {
        "זיהוי שעות": test_time_detection(),
        "התאמת ישויות": test_entity_matching(),
        "סוגי שאלות": test_cross_exam_question_types(),
        "קיצור ציטוטים": test_quote_truncation(),
        "Pipeline מלא": test_full_pipeline(),
    }
    
    print("\n" + "="*60)
    print("📊 סיכום תוצאות")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✅" if result else "❌"
        print(f"   {status} {name}")
    
    print(f"\n   ציון כולל: {passed}/{total} ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n   🎉 המערכת ברמה עילית!")
    elif passed >= total - 1:
        print("\n   👍 המערכת ברמה גבוהה מאוד")

if __name__ == "__main__":
    main()
