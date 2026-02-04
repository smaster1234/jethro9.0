# Source Classifier System - מערכת סיווג מקורות

## סקירה כללית

מערכת סיווג המקורות (Source Classifier) היא רכיב קריטי במערכת החקירה הנגדית של Jethro 9.0. המערכת מאפשרת להבדיל בין מקורות שונים של טענות ולנסח שאלות שמתייחסות ספציפית למקור.

## הבעיה שנפתרה

לפני השדרוג, מערכת החקירה הנגדית לא הבדילה בין:
- **הצהרות העד עצמו** (תצהיר, עדות קודמת)
- **עדויות תומכות** מאותו צד
- **כתבי טענות** (תביעה/הגנה)
- **ראיות מהצד שכנגד**

כתוצאה מכך, השאלות היו גנריות ולא התייחסו למקור הספציפי.

## הפתרון

### 1. סוגי מקורות (SourceType)

```python
class SourceType(str, Enum):
    WITNESS_OWN_STATEMENT = "witness_own_statement"  # תצהיר העד הנחקר
    SUPPORTING_WITNESS = "supporting_witness"        # עד תומך מאותו צד
    PARTY_PLEADING = "party_pleading"                # כתב טענות
    OPPOSING_EVIDENCE = "opposing_evidence"          # ראיה מהצד השני
    COURT_FINDING = "court_finding"                  # קביעת בית משפט
    EXTERNAL_DOCUMENT = "external_document"          # מסמך חיצוני
```

### 2. גישות אסטרטגיות

המערכת מזהה את הגישה האסטרטגית המתאימה לפי סוג הסתירה:

| גישה | תיאור | דוגמה לניסוח |
|------|-------|--------------|
| `internal_contradiction` | סתירה פנימית - העד סותר את עצמו | "בתצהיר שלך מיום X כתבת... אבל בתצהיר מיום Y כתבת..." |
| `supporting_witness_conflict` | סתירה עם עד תומך | "העד Y מטעמך העיד ש... איך זה מתיישב עם מה שאתה אומר?" |
| `contradict_court_finding` | סתירה לקביעת בית משפט | "בית המשפט כבר קבע ש... אתה חולק על קביעה זו?" |
| `contradict_document` | סתירה למסמך | "במסמך X כתוב... איך אתה מסביר את הסתירה?" |
| `cross_party_conflict` | עימות עם הצד השני | "הצד השני טוען ש... מה תגובתך?" |

### 3. ביטויי ניסוח

לכל גישה אסטרטגית יש ביטויי ניסוח מותאמים:

```python
phrasing = {
    "opening": "אתה כתבת ש",           # פתיחת השאלה
    "confrontation": "הצד השני מציג ראיה ש",  # ביטוי העימות
    "closing": "מה תגובתך לטענה הזו?",  # סיום השאלה
    "strategy_note": "עימות בין צדדים - להיות מוכן לתשובה מתגוננת"
}
```

## דוגמאות לשאלות מנוסחות

### סתירה פנימית (Internal Contradiction)
```
בתצהיר שלך, כתבת: "הפגישה התקיימה בשעה 10:00". 
בתצהיר שלך, כתבת: "הפגישה התקיימה בשעה 14:00". 
שתי הטענות לא יכולות להיות נכונות יחד. איזו מהן נכונה?
```

### עימות בין צדדים (Cross-Party Conflict)
```
אתה כתבת ש: "הנתבע שילם את כל החוב במזומן". 
הצד השני מציג ראיה ש: "הנתבע לא שילם אף שקל". 
מה תגובתך לטענה הזו?
```

## שימוש במערכת

### יצירת מסווג מקורות
```python
from backend_lite.source_classifier import create_source_classifier

classifier = create_source_classifier(
    examined_witness_name="יוסי כהן",
    examined_witness_party="defendant"
)
```

### סיווג מקורות סתירה
```python
from backend_lite.source_classifier import classify_contradiction_sources

context = classify_contradiction_sources(
    classifier=classifier,
    claim1_doc_name="תצהיר יוסי כהן",
    claim1_speaker="יוסי כהן",
    claim1_speaker_role="defendant",
    claim1_speaker_mode="party_claim",
    claim2_doc_name="כתב תביעה",
    claim2_speaker="התובע",
    claim2_speaker_role="plaintiff",
    claim2_speaker_mode="party_claim",
)

# קבלת גישה אסטרטגית
approach = context.get_strategic_approach()  # "cross_party_conflict"

# קבלת ביטויי ניסוח
phrasing = context.get_question_phrasing()
```

### יצירת שאלה עם התייחסות למקור
```python
question = context.generate_source_aware_question(
    quote_a="הנתבע שילם את כל החוב",
    quote_b="הנתבע לא שילם",
    question_type="confrontation"
)
```

## אינטגרציה עם CrossExamGenerator

מחולל החקירה הנגדית משתמש אוטומטית במערכת סיווג המקורות:

```python
from backend_lite.cross_exam import CrossExamGenerator

generator = CrossExamGenerator()
cross_exam_set = generator.generate(contradiction, max_questions=5)

# השאלות כוללות מטא-דאטה של מקורות
for q in cross_exam_set.questions:
    print(f"Source type: {q.source_type}")
    print(f"Strategic approach: {q.strategic_approach}")
    print(f"Source reference: {q.source_reference}")
```

## שדות חדשים ב-CrossExamQuestion

| שדה | תיאור | דוגמה |
|-----|-------|-------|
| `source_reference` | התייחסות למקור | "בתצהיר שלך מיום X" |
| `attribution_phrase` | ביטוי ייחוס | "אתה כתבת ש" |
| `confrontation_phrase` | ביטוי עימות | "אבל בכתב ההגנה נאמר ש" |
| `source_type` | סוג המקור | "witness_own_statement" |
| `strategic_approach` | גישה אסטרטגית | "internal_contradiction" |

## שדות חדשים ב-CrossExamSet

| שדה | תיאור |
|-----|-------|
| `source_context` | הקשר מקורות מלא |
| `witness_claim_source` | מקור טענת העד |
| `opposing_claim_source` | מקור הטענה הסותרת |
| `strategic_approach` | גישה אסטרטגית מומלצת |

## הערות אסטרטגיות לפי סוג סתירה

### סתירה פנימית
> סתירה פנימית - העד לא יכול להאשים אחרים. להישאר עם הציטוטים המדויקים.

### סתירה עם עד תומך
> סתירה עם עד תומך - להדגיש שאחד מהם טועה או משקר.

### סתירה לקביעת בית משפט
> סתירה לקביעה שיפוטית - ראיה חזקה מאוד. להדגיש את הסמכות.

### סתירה למסמך
> סתירה למסמך - להציג את המסמך פיזית. לשאול אם העד מכיר אותו.

### עימות בין צדדים
> עימות בין צדדים - להיות מוכן לתשובה מתגוננת. לדרוש הסבר, לא רק הכחשה.

## קבצים שנוספו/עודכנו

1. **`backend_lite/source_classifier.py`** - מודול סיווג המקורות (~750 שורות)
2. **`backend_lite/cross_exam.py`** - אינטגרציה עם מחולל החקירה הנגדית (+120 שורות)

## תוצאות בדיקות

```
✅ source_classifier.py - עובד
✅ cross_exam.py - עובד
✅ אינטגרציה מלאה - עובדת
✅ 128/130 בדיקות עוברות (98.5%)
```

## שיפורים עתידיים אפשריים

1. **זיהוי אוטומטי של שם העד** מתוך המסמכים
2. **תמיכה בריבוי עדים** באותו תיק
3. **למידה מתוצאות** - שיפור הניסוח לפי תגובות בפועל
4. **תמיכה בסוגי מסמכים נוספים** (חוות דעת מומחה, פרוטוקולים)
