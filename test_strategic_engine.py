#!/usr/bin/env python3
"""
Test Strategic Cross-Examination Engine
"""
import sys
sys.path.insert(0, '/home/ubuntu/jethro9.0/backend_lite')

from strategic_engine import (
    StrategicExaminationPlanner,
    WitnessProfile,
    QuestionIntent,
    GameTheoryEngine,
    PredictiveResponseModel,
    UncertaintyManager,
    TimePositionOptimizer,
)

def test_strategic_engine():
    print("=" * 60)
    print("🎯 בדיקת מנוע אסטרטגי לחקירה נגדית")
    print("=" * 60)
    
    # יצירת מתכנן אסטרטגי
    planner = StrategicExaminationPlanner()
    
    # תרחיש בדיקה - סתירה כמותית
    claim_a = "התובע טען שקיבל 50,000 ש\"ח כפיצוי"
    claim_b = "בתצהיר הנתבע נכתב שהועברו רק 30,000 ש\"ח"
    
    print("\n📋 תרחיש בדיקה:")
    print(f"   טענה א': {claim_a}")
    print(f"   טענה ב': {claim_b}")
    
    # בדיקה עם פרופילים שונים
    profiles = [
        WitnessProfile.COOPERATIVE,
        WitnessProfile.HOSTILE,
        WitnessProfile.EVASIVE,
        WitnessProfile.CALCULATED,
    ]
    
    for profile in profiles:
        print(f"\n{'='*60}")
        print(f"🎭 פרופיל עד: {profile.value}")
        print("=" * 60)
        
        plan = planner.create_examination_plan(
            contradiction_type="QUANTITATIVE_AMOUNT",
            contradiction_confidence=0.85,
            claim_a=claim_a,
            claim_b=claim_b,
            witness_profile=profile,
            total_time_minutes=15.0
        )
        
        print(f"\n📊 ניתוח אסטרטגי:")
        print(f"   תוחלת ערך: {plan.expected_value:.2f}")
        print(f"   ציון סיכון: {plan.risk_score:.2f}")
        print(f"   ציון ביטחון: {plan.confidence_score:.2f}")
        print(f"   זמן כולל: {plan.total_time_minutes:.1f} דקות")
        
        print(f"\n🎯 מטרות מפתח:")
        for obj in plan.key_objectives:
            print(f"   • {obj}")
        
        print(f"\n⚠️ מלכודות פוטנציאליות:")
        for pitfall in plan.potential_pitfalls:
            print(f"   • {pitfall}")
        
        print(f"\n📝 שאלות מומלצות ({len(plan.questions)}):")
        for i, q in enumerate(plan.questions[:4], 1):
            print(f"\n   שאלה {i}: [{q.intent.value}]")
            print(f"   {q.question[:80]}...")
            print(f"   ⏱️ זמן: {q.time_allocation:.1f} דק | 🎲 סיכון: {q.risk_level:.1%} | 🏆 פוטנציאל: {q.reward_potential:.1%}")
            if q.psychological_notes:
                print(f"   🧠 {q.psychological_notes}")
    
    # בדיקת תורת משחקים
    print("\n" + "=" * 60)
    print("🎮 בדיקת תורת משחקים (Nash Equilibrium)")
    print("=" * 60)
    
    for intent in [QuestionIntent.ESTABLISH_BASELINE, QuestionIntent.EXPLOIT_CONTRADICTION, QuestionIntent.PSYCHOLOGICAL_PRESSURE]:
        print(f"\n   כוונה: {intent.value}")
        nash = GameTheoryEngine.calculate_nash_equilibrium(intent, WitnessProfile.DEFENSIVE)
        for response, prob in nash.items():
            print(f"      {response.value}: {prob:.1%}")
    
    # בדיקת חיזוי תגובות
    print("\n" + "=" * 60)
    print("🔮 בדיקת מודל חיזוי תגובות")
    print("=" * 60)
    
    predictor = PredictiveResponseModel()
    
    test_questions = [
        ("ספר לי מה קרה באותו יום", "open"),
        ("האם קיבלת את הכסף?", "yes_no"),
        ("אז אתה מאשר שקיבלת 50,000 ש\"ח?", "leading"),
    ]
    
    for question, q_type in test_questions:
        print(f"\n   שאלה ({q_type}): {question}")
        prediction = predictor.predict_response(
            question=question,
            question_type=q_type,
            witness_profile=WitnessProfile.DEFENSIVE,
            contradiction_severity=0.8
        )
        print(f"      תגובה צפויה: {prediction['most_likely']}")
        print(f"      ביטחון: {prediction['confidence']:.1%}")
    
    print("\n" + "=" * 60)
    print("✅ בדיקת מנוע אסטרטגי הושלמה בהצלחה!")
    print("=" * 60)

if __name__ == "__main__":
    test_strategic_engine()
