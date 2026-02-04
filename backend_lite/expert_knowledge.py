"""
Expert Knowledge Base for Cross-Examination
מאגר ידע מומחה לחקירה נגדית

Based on academic research, expert lawyer methodologies, and psychological studies.
מבוסס על מחקר אקדמי, שיטות עורכי דין מומחים, ומחקרים פסיכולוגיים.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Tuple
import random


class WitnessType(Enum):
    """סוגי עדים"""
    EVASIVE = "evasive"          # מתחמק
    HOSTILE = "hostile"          # עוין
    VERBOSE = "verbose"          # נרבולוגי
    EXPERT = "expert"            # מומחה
    EMOTIONAL = "emotional"      # רגשי
    COOPERATIVE = "cooperative"  # משתף פעולה
    UNCERTAIN = "uncertain"      # לא בטוח


class QuestionStrategy(Enum):
    """אסטרטגיות שאלות"""
    LADDER = "ladder"            # סולם - בניית הסכמות
    LOOP = "loop"                # לולאה - חזרה מזוויות שונות
    SURPRISE = "surprise"        # הפתעה - שמירת ראיה לסוף
    DECONSTRUCTION = "deconstruction"  # פירוק - פירוק טענה לרכיבים
    COGNITIVE_LOAD = "cognitive_load"  # עומס קוגניטיבי
    COMMIT_CREDIT_CONFRONT = "3c"      # התחייבות-אמינות-עימות


class ImpeachmentType(Enum):
    """סוגי הפרכה"""
    BIAS = "bias"                      # הטיה, אינטרס ומניע
    PRIOR_INCONSISTENT = "prior"       # סתירה עם הצהרה קודמת
    OTHER_WITNESSES = "witnesses"      # סתירה עם עדים אחרים
    DOCUMENTS = "documents"            # סתירה עם מסמכים
    LACK_OF_CAPACITY = "capacity"      # חוסר יכולת לדעת
    CRIMINAL_RECORD = "criminal"       # עבר פלילי
    BAD_REPUTATION = "reputation"      # מוניטין רע


@dataclass
class YoungerCommandment:
    """דיבר מ-10 הדיברות של Irving Younger"""
    number: int
    title_en: str
    title_he: str
    description: str
    violation_risk: str
    application_tip: str


@dataclass
class ExpertTechnique:
    """טכניקה מומחית"""
    name: str
    source: str
    description: str
    when_to_use: str
    example_questions: List[str]
    risk_level: str  # low, medium, high


@dataclass
class PsychologicalInsight:
    """תובנה פסיכולוגית"""
    topic: str
    finding: str
    source: str
    application: str
    warning: Optional[str] = None


@dataclass
class WitnessProfile:
    """פרופיל עד"""
    witness_type: WitnessType
    characteristics: List[str]
    recommended_strategies: List[QuestionStrategy]
    avoid_strategies: List[QuestionStrategy]
    sample_questions: List[str]
    warnings: List[str]


class ExpertKnowledgeBase:
    """מאגר הידע המומחה"""
    
    def __init__(self):
        self._init_younger_commandments()
        self._init_expert_techniques()
        self._init_psychological_insights()
        self._init_witness_profiles()
        self._init_question_templates()
        self._init_deception_cues()
    
    def _init_younger_commandments(self):
        """אתחול 10 הדיברות של Irving Younger"""
        self.younger_commandments = [
            YoungerCommandment(
                number=1,
                title_en="Be brief",
                title_he="היה קצר",
                description="שאלות קצרות ופשוטות. כל שאלה צריכה להכיל עובדה אחת בלבד.",
                violation_risk="העד יכול להתחמק או להוסיף הסברים",
                application_tip="פרק שאלות מורכבות לשאלות קצרות של עובדה אחת"
            ),
            YoungerCommandment(
                number=2,
                title_en="Use plain words",
                title_he="השתמש במילים פשוטות",
                description="הימנע ממונחים משפטיים או מקצועיים. דבר בשפה שהעד והמושבעים מבינים.",
                violation_risk="העד יכול לטעון שלא הבין את השאלה",
                application_tip="אם צריך להשתמש במונח מקצועי, הגדר אותו קודם"
            ),
            YoungerCommandment(
                number=3,
                title_en="Use only leading questions",
                title_he="השתמש רק בשאלות מנחות",
                description="שאלות שהתשובה כלולה בהן. 'נכון ש...?', 'אתה מסכים ש...?'",
                violation_risk="שאלה פתוחה נותנת לעד שליטה",
                application_tip="כל שאלה צריכה להסתיים ב'נכון?' או 'לא כך?'"
            ),
            YoungerCommandment(
                number=4,
                title_en="Don't ask a question you don't know the answer to",
                title_he="אל תשאל שאלה שאתה לא יודע את התשובה לה",
                description="חקירה נגדית היא לא משלחת דיג. דע את התשובה מראש.",
                violation_risk="העד יכול להפתיע אותך בתשובה מזיקה",
                application_tip="מקור כל תשובה - תצהיר, עדות קודמת, מסמך"
            ),
            YoungerCommandment(
                number=5,
                title_en="Listen to the witness's answers",
                title_he="הקשב לתשובות העד",
                description="אל תהיה כל כך תפוס במה שאתה עושה שתתעלם מתשובות מועילות.",
                violation_risk="תפספס הזדמנויות או תשאל שאלות לא רלוונטיות",
                application_tip="התשובה הבאה צריכה להתבסס על התשובה הקודמת"
            ),
            YoungerCommandment(
                number=6,
                title_en="Don't quarrel with the witness",
                title_he="אל תתווכח עם העד",
                description="זה לא דיון. אם תיכנס לוויכוח, סביר שתפסיד.",
                violation_risk="המושבעים יזדהו עם העד",
                application_tip="אם העד מנסה להתווכח, פשוט חזור על השאלה"
            ),
            YoungerCommandment(
                number=7,
                title_en="Don't allow the witness to repeat direct testimony",
                title_he="אל תאפשר לעד לחזור על עדותו הראשית",
                description="אל תשאל שאלות שמאפשרות לעד לחזק את הגרסה שלו.",
                violation_risk="העד יחזק את העדות שלו בפני המושבעים",
                application_tip="אל תשאל 'למה?' או 'הסבר' - זה מזמין חזרה"
            ),
            YoungerCommandment(
                number=8,
                title_en="Don't permit the witness to explain",
                title_he="אל תאפשר לעד להסביר",
                description="שמור על השאלות קצרות ושמור את המיקוד על השאלות שלך.",
                violation_risk="העד ישתמש בהסבר כדי לתקן נזק",
                application_tip="אם העד מתחיל להסביר, הפסק בנימוס ועבור לשאלה הבאה"
            ),
            YoungerCommandment(
                number=9,
                title_en="Don't ask the one question too many",
                title_he="אל תשאל שאלה אחת יותר מדי",
                description="כשהגעת לנקודה שרצית, עצור. אל תהיה חמדן.",
                violation_risk="השאלה האחרונה יכולה להרוס את כל מה שבנית",
                application_tip="כשהעד הודה במה שרצית, עבור לנושא הבא"
            ),
            YoungerCommandment(
                number=10,
                title_en="Save the ultimate point for summation",
                title_he="שמור את הנקודה העיקרית לסיכום",
                description="אל תנסה להדגיש את הנקודה בשאלת ניצחון אחת.",
                violation_risk="העד יכול לתת תשובה שתהרוס את הנקודה",
                application_tip="תן לעובדות לדבר, והסק מסקנות בסיכום"
            )
        ]
    
    def _init_expert_techniques(self):
        """אתחול טכניקות מומחים"""
        self.expert_techniques = {
            "chapter_method": ExpertTechnique(
                name="שיטת הפרקים (Pozner & Dodd)",
                source="Cross-Examination: Science and Techniques",
                description="חלק את החקירה לפרקים. כל פרק מתמקד בנקודה אחת בלבד.",
                when_to_use="תמיד - זו השיטה הבסיסית לארגון חקירה נגדית",
                example_questions=[
                    "הפגישה הייתה ב-10 בבוקר, נכון?",
                    "הפגישה הייתה במשרד שלך, נכון?",
                    "רק אתה והתובע הייתם בפגישה, נכון?",
                    "אף אחד אחר לא שמע את השיחה, נכון?"
                ],
                risk_level="low"
            ),
            "commit_credit_confront": ExpertTechnique(
                name="שלושת ה-C (Commit, Credit, Confront)",
                source="Holland & Knight - Dan Small",
                description="1. נעל את העד לגרסה 2. הראה שהמקור הקודם אמין 3. הצג את הסתירה",
                when_to_use="כשיש סתירה בין עדות נוכחית להצהרה קודמת",
                example_questions=[
                    "אתה אומר היום שהפגישה הייתה ב-10, נכון?",
                    "נתת תצהיר לפני שלושה חודשים, נכון?",
                    "קראת את התצהיר לפני שחתמת, נכון?",
                    "בתצהיר כתבת שהפגישה הייתה ב-14:00, נכון?"
                ],
                risk_level="low"
            ),
            "cognitive_load": ExpertTechnique(
                name="הגברת עומס קוגניטיבי",
                source="FBI Research - Matsumoto et al.",
                description="הגבר את העומס הקוגניטיבי על העד כדי לחשוף שקר",
                when_to_use="כשחושדים שהעד משקר",
                example_questions=[
                    "ספר לי את האירוע מהסוף להתחלה",
                    "מה בדיוק שמעת באותו רגע?",
                    "מה היה הריח במקום?",
                    "מה קרה רגע לפני שזה התחיל?"
                ],
                risk_level="medium"
            ),
            "russell_direct": ExpertTechnique(
                name="הגישה הישירה (Sir Charles Russell)",
                source="Francis Wellman - The Art of Cross-Examination",
                description="לך ישר אל העד ואל הנקודה. שים את הקלפים על השולחן.",
                when_to_use="כשיש ראיה חזקה נגד העד",
                example_questions=[
                    "אתה חתמת על המסמך הזה, נכון?",
                    "התאריך על המסמך הוא 15 בינואר, נכון?",
                    "אבל היום אתה אומר שזה קרה ב-20 בינואר, נכון?"
                ],
                risk_level="medium"
            ),
            "choate_gentle": ExpertTechnique(
                name="הגישה העדינה (Rufus Choate)",
                source="Francis Wellman - The Art of Cross-Examination",
                description="התייחס לעד כג'נטלמן. שאל מעט שאלות, אבל כל אחת פוגעת במטרה.",
                when_to_use="כשהעד נראה אמין ואתה צריך לערער אותו בעדינות",
                example_questions=[
                    "אני מבין שאתה מנסה לעזור, נכון?",
                    "אבל אתה מסכים שהזיכרון יכול לטעות לפעמים?",
                    "ואתה לא היית שם כל הזמן, נכון?"
                ],
                risk_level="low"
            ),
            "sue_technique": ExpertTechnique(
                name="שימוש אסטרטגי בראיות (SUE)",
                source="Psychological Research",
                description="אל תחשוף את כל הראיות מיד. תן לעד לספר גרסה, ואז הצג ראיות סותרות.",
                when_to_use="כשיש ראיות שהעד לא יודע שיש לך",
                example_questions=[
                    "ספר לי מה עשית באותו ערב",
                    "אז לא היית ליד הבנק בכלל?",
                    "אתה בטוח?",
                    "[הצג צילום ממצלמת אבטחה]"
                ],
                risk_level="high"
            ),
            "lincoln_almanac": ExpertTechnique(
                name="טכניקת לינקולן (עובדה בלתי ניתנת להכחשה)",
                source="Abraham Lincoln - Almanac Trial",
                description="השתמש בעובדה אובייקטיבית שהעד לא יכול להכחיש כדי להפיל את כל העדות",
                when_to_use="כשיש עובדה מדעית/אובייקטיבית שסותרת את העדות",
                example_questions=[
                    "אתה אומר שראית את הרצח לאור הירח המלא, נכון?",
                    "זה היה ב-29 באוגוסט, נכון?",
                    "לפי לוח השנה, הירח שקע ב-23:00 באותו לילה. הרצח היה ב-01:00, נכון?"
                ],
                risk_level="low"
            )
        }
    
    def _init_psychological_insights(self):
        """אתחול תובנות פסיכולוגיות"""
        self.psychological_insights = [
            PsychologicalInsight(
                topic="אפקט המידע המוטעה",
                finding="ניסוח השאלה יכול לשנות את מה שהעד 'זוכר'. שאלה עם 'ה' הידיעה ('הפנס השבור') מגבירה סיכוי לתשובה חיובית.",
                source="Elizabeth Loftus (1978)",
                application="השתמש בניסוח מדויק כדי להנחות את העד לתשובה הרצויה",
                warning="זה יכול גם לעוות זיכרון אמיתי - השתמש באחריות"
            ),
            PsychologicalInsight(
                topic="זיהום חברתי של זיכרון",
                finding="עדים שדיברו ביניהם אחרי אירוע מראים ירידה בדיוק מ-79% ל-34%",
                source="Gabbert et al. (2004)",
                application="שאל את העד אם דיבר עם עדים אחרים - זה פוגע באמינות",
                warning=None
            ),
            PsychologicalInsight(
                topic="ביטחון לא שווה דיוק",
                finding="עדים יכולים להיות בטוחים מאוד בזיכרון שגוי לחלוטין",
                source="Loftus & Pickrell (1995)",
                application="אל תתרשם מביטחון העד - בדוק עובדות",
                warning=None
            ),
            PsychologicalInsight(
                topic="עומס קוגניטיבי",
                finding="שקרנים מראים יותר סימני מאמץ קוגניטיבי - הם צריכים לבנות סיפור, לזכור מה אמרו, ולשלוט בהבעות",
                source="Vrij et al. (2006)",
                application="הגבר עומס קוגניטיבי: בקש סיפור הפוך, שאל על פרטים היקפיים",
                warning=None
            ),
            PsychologicalInsight(
                topic="מיתוס מבט העיניים",
                finding="23 מתוך 24 מחקרים דחו את ההשערה שהימנעות ממבט מעידה על שקר",
                source="FBI Research (2011)",
                application="אל תסתמך על מבט עיניים כסימן לשקר",
                warning="זה מיתוס נפוץ שיכול להוביל לטעויות"
            ),
            PsychologicalInsight(
                topic="סימנים מילוליים לשקר",
                finding="שקרנים נותנים פחות פרטים ספציפיים, פחות תיאורים חושיים, ויותר הכללות",
                source="Statement Analysis Research",
                application="שאל על פרטים חושיים ספציפיים - שקרנים מתקשים להמציא אותם",
                warning=None
            ),
            PsychologicalInsight(
                topic="זיכרונות כוזבים",
                finding="ניתן להשתיל זיכרונות שלמים לאירועים שמעולם לא התרחשו ב-25% מהנבדקים",
                source="Loftus (1995)",
                application="היזהר מעדות שנבנתה על סמך הנחיות חוזרות או תמונות",
                warning="זה יכול לקרות גם לעדים כנים"
            )
        ]
    
    def _init_witness_profiles(self):
        """אתחול פרופילי עדים"""
        self.witness_profiles = {
            WitnessType.EVASIVE: WitnessProfile(
                witness_type=WitnessType.EVASIVE,
                characteristics=[
                    "לא עונה ישירות על שאלות",
                    "מוסיף הסברים לא נדרשים",
                    "מסיט את השיחה לנושאים אחרים",
                    "משתמש ב'אני לא זוכר' הרבה"
                ],
                recommended_strategies=[
                    QuestionStrategy.LADDER,
                    QuestionStrategy.COMMIT_CREDIT_CONFRONT
                ],
                avoid_strategies=[
                    QuestionStrategy.COGNITIVE_LOAD  # יכול להיראות כהתעמרות
                ],
                sample_questions=[
                    "אני שואל שאלה פשוטה: כן או לא?",
                    "בוא נחזור לשאלה שלי: [חזור על השאלה]",
                    "אתה יכול לענות כן או לא?"
                ],
                warnings=[
                    "אל תיראה כאילו אתה מתעמר בעד",
                    "תן לעד להתחמק - זה נראה רע למושבעים"
                ]
            ),
            WitnessType.HOSTILE: WitnessProfile(
                witness_type=WitnessType.HOSTILE,
                characteristics=[
                    "מתנגד בגלוי לחקירה",
                    "מנסה להזיק לצד שחוקר",
                    "עונה בתוקפנות",
                    "מערער על השאלות עצמן"
                ],
                recommended_strategies=[
                    QuestionStrategy.LADDER,
                    QuestionStrategy.DECONSTRUCTION
                ],
                avoid_strategies=[
                    QuestionStrategy.SURPRISE  # העד יהיה מוכן להילחם
                ],
                sample_questions=[
                    "אני מבין שאתה לא אוהב את השאלות שלי, אבל אני צריך לשאול אותן",
                    "בוא נתמקד בעובדות: [עובדה פשוטה], נכון?",
                    "אתה מסכים לפחות ש-[עובדה בסיסית]?"
                ],
                warnings=[
                    "שמור על קור רוח - אל תיכנס לוויכוח",
                    "השתמש במסמכים כדי לנעול את העד"
                ]
            ),
            WitnessType.VERBOSE: WitnessProfile(
                witness_type=WitnessType.VERBOSE,
                characteristics=[
                    "מדבר הרבה יותר מהנדרש",
                    "נותן הסברים ארוכים",
                    "מוסיף פרטים לא רלוונטיים",
                    "קשה לעצור אותו"
                ],
                recommended_strategies=[
                    QuestionStrategy.LADDER,
                    QuestionStrategy.LOOP
                ],
                avoid_strategies=[
                    QuestionStrategy.COGNITIVE_LOAD  # יגרום לעוד דיבורים
                ],
                sample_questions=[
                    "תודה, אבל השאלה שלי הייתה פשוטה: [חזור על השאלה]",
                    "אני מבקש תשובה קצרה: כן או לא?",
                    "בוא נתמקד: [עובדה ספציפית], נכון?"
                ],
                warnings=[
                    "לפעמים כדאי לתת לו לדבר - הוא עלול לחשוף מידע",
                    "אבל שלוט בכיוון השיחה"
                ]
            ),
            WitnessType.EXPERT: WitnessProfile(
                witness_type=WitnessType.EXPERT,
                characteristics=[
                    "בטוח בעצמו ובידע שלו",
                    "משתמש במונחים מקצועיים",
                    "מסתמך על מומחיות",
                    "קשה לערער עליו"
                ],
                recommended_strategies=[
                    QuestionStrategy.DECONSTRUCTION,
                    QuestionStrategy.LADDER
                ],
                avoid_strategies=[
                    QuestionStrategy.COGNITIVE_LOAD  # מומחה יתמודד טוב
                ],
                sample_questions=[
                    "המסקנה שלך מבוססת על הנחות מסוימות, נכון?",
                    "אם הנחה X הייתה שגויה, המסקנה הייתה משתנה?",
                    "יש מומחים אחרים שחולקים על השיטה הזו, נכון?",
                    "לא בדקת את [פרט ספציפי], נכון?"
                ],
                warnings=[
                    "אל תנסה להתחרות במומחיות - אתה תפסיד",
                    "התמקד בהנחות יסוד ומגבלות"
                ]
            ),
            WitnessType.EMOTIONAL: WitnessProfile(
                witness_type=WitnessType.EMOTIONAL,
                characteristics=[
                    "מגיב ברגש חזק",
                    "עלול לבכות או לכעוס",
                    "קשה לו להתמקד בעובדות",
                    "המושבעים עלולים להזדהות איתו"
                ],
                recommended_strategies=[
                    QuestionStrategy.LADDER
                ],
                avoid_strategies=[
                    QuestionStrategy.SURPRISE,
                    QuestionStrategy.COGNITIVE_LOAD
                ],
                sample_questions=[
                    "אני מבין שזה קשה, אבל אני צריך לשאול כמה שאלות",
                    "קח את הזמן שלך",
                    "בוא נתמקד בעובדות: [עובדה ניטרלית], נכון?"
                ],
                warnings=[
                    "אל תיראה כבריון - המושבעים יזדהו עם העד",
                    "היה אנושי ומכבד"
                ]
            ),
            WitnessType.UNCERTAIN: WitnessProfile(
                witness_type=WitnessType.UNCERTAIN,
                characteristics=[
                    "לא בטוח בזיכרון שלו",
                    "משתמש ב'אני חושב', 'כנראה'",
                    "משנה גרסה בקלות",
                    "ניתן להשפיע עליו"
                ],
                recommended_strategies=[
                    QuestionStrategy.COMMIT_CREDIT_CONFRONT,
                    QuestionStrategy.LOOP
                ],
                avoid_strategies=[],
                sample_questions=[
                    "אז אתה לא בטוח?",
                    "יכול להיות שטעית?",
                    "אם אני אראה לך מסמך, זה יעזור לך לזכור?"
                ],
                warnings=[
                    "היזהר - עד לא בטוח יכול להיות כנה",
                    "אל תנצל חולשה באופן לא אתי"
                ]
            )
        }
    
    def _init_question_templates(self):
        """אתחול תבניות שאלות"""
        self.question_templates = {
            "opening": {
                "build_agreement": [
                    "אתה מסכים ש{fact}, נכון?",
                    "נכון ש{fact}?",
                    "זה נכון ש{fact}?",
                    "{fact}, לא כך?"
                ],
                "establish_baseline": [
                    "בתצהיר שלך מיום {date}, כתבת ש{statement}, נכון?",
                    "בעדות שלך בחקירה המוקדמת, אמרת ש{statement}, נכון?",
                    "אתה זוכר שאמרת ש{statement}?"
                ]
            },
            "confrontation": {
                "internal_contradiction": [
                    "אבל היום אתה אומר ש{new_statement}, נכון?",
                    "אז איך זה מתיישב עם מה שאמרת קודם?",
                    "מה השתנה מאז?"
                ],
                "external_contradiction": [
                    "הצד השני טוען ש{opposing_claim}. מה תגובתך?",
                    "יש מסמך שמראה ש{document_content}. אתה מכיר אותו?",
                    "עד אחר העיד ש{other_testimony}. הוא טועה?"
                ],
                "document_impeachment": [
                    "אני מציג לך מסמך [מס' ראיה]. אתה מזהה אותו?",
                    "זו החתימה שלך?",
                    "המסמך אומר ש{document_content}. זה לא מה שאמרת היום, נכון?"
                ]
            },
            "cognitive_load": {
                "reverse_order": [
                    "ספר לי מה קרה, אבל הפעם מהסוף להתחלה",
                    "מה היה הדבר האחרון שקרה? ומה קרה לפני כן?"
                ],
                "sensory_details": [
                    "מה בדיוק שמעת באותו רגע?",
                    "מה היה הריח במקום?",
                    "מה הרגשת פיזית באותו רגע?",
                    "איזה צבע היה ל{object}?"
                ],
                "peripheral_details": [
                    "מה קרה רגע לפני שזה התחיל?",
                    "מי עוד היה שם?",
                    "מה היה מזג האוויר?",
                    "מה לבשת באותו יום?"
                ]
            },
            "closing": {
                "lock_in": [
                    "אז אם אני מבין נכון, אתה טוען ש{summary}?",
                    "זו הגרסה הסופית שלך?",
                    "ואין לך הסבר אחר?"
                ],
                "highlight_weakness": [
                    "אז אתה מודה ש{admission}?",
                    "ואין לך ראיה ל{claim}?",
                    "זה רק מה שאתה זוכר, לא מה שבהכרח קרה?"
                ]
            }
        }
    
    def _init_deception_cues(self):
        """אתחול סימני שקר"""
        self.deception_cues = {
            "verbal_cues": {
                "reliable": [
                    ("פחות פרטים ספציפיים", "שקרנים נותנים תיאורים כלליים יותר"),
                    ("פחות תיאורים חושיים", "קשה להמציא מה שמעת/הרחת/הרגשת"),
                    ("יותר הכללות", "שימוש ב'תמיד', 'אף פעם', 'כולם'"),
                    ("סיפור 'חלק מדי'", "ללא היסוסים טבעיים או תיקונים"),
                    ("שינויי זמן פועל", "מעבר פתאומי מעבר להווה או עתיד")
                ],
                "unreliable_myths": [
                    ("הימנעות ממבט עין", "לא קשור לשקר - 23/24 מחקרים דחו"),
                    ("תנועות יד מוגברות", "לא מעיד על שקר"),
                    ("גירוד או נגיעה בפנים", "לא מעיד על שקר"),
                    ("שינויים בתנוחה", "לא מעיד על שקר")
                ]
            },
            "linguistic_markers": {
                "minimizing": ["רק", "פשוט", "קצת", "סתם"],
                "intensifying": ["בהחלט", "לגמרי", "ממש", "באמת", "בטוח"],
                "distancing": ["הוא", "היא", "הם", "האיש הזה"],
                "hedging": ["למיטב זכרוני", "אני חושב", "כנראה", "אולי", "נדמה לי"]
            }
        }
    
    # === Public Methods ===
    
    def get_commandment(self, number: int) -> Optional[YoungerCommandment]:
        """קבל דיבר ספציפי"""
        for cmd in self.younger_commandments:
            if cmd.number == number:
                return cmd
        return None
    
    def get_technique(self, name: str) -> Optional[ExpertTechnique]:
        """קבל טכניקה ספציפית"""
        return self.expert_techniques.get(name)
    
    def get_witness_profile(self, witness_type: WitnessType) -> Optional[WitnessProfile]:
        """קבל פרופיל עד"""
        return self.witness_profiles.get(witness_type)
    
    def get_question_templates(self, category: str, subcategory: str) -> List[str]:
        """קבל תבניות שאלות"""
        return self.question_templates.get(category, {}).get(subcategory, [])
    
    def get_random_insight(self) -> PsychologicalInsight:
        """קבל תובנה פסיכולוגית אקראית"""
        return random.choice(self.psychological_insights)
    
    def suggest_strategy(self, 
                        contradiction_type: str,
                        witness_behavior: Optional[str] = None) -> Dict:
        """הצע אסטרטגיה מומלצת"""
        
        # בחר טכניקה לפי סוג הסתירה
        if contradiction_type == "internal":
            primary_technique = "commit_credit_confront"
            secondary_technique = "chapter_method"
        elif contradiction_type == "external":
            primary_technique = "sue_technique"
            secondary_technique = "russell_direct"
        else:
            primary_technique = "chapter_method"
            secondary_technique = "choate_gentle"
        
        # התאם לפי התנהגות העד
        if witness_behavior == "evasive":
            approach = "שליטה הדוקה - עובדה אחת לשאלה"
        elif witness_behavior == "hostile":
            approach = "שמור על קור רוח - השתמש במסמכים"
        elif witness_behavior == "emotional":
            approach = "היה אנושי - אל תיראה כבריון"
        else:
            approach = "גישה סטנדרטית - בנה הסכמות"
        
        return {
            "primary_technique": self.expert_techniques.get(primary_technique),
            "secondary_technique": self.expert_techniques.get(secondary_technique),
            "approach": approach,
            "relevant_commandments": [
                self.get_commandment(1),  # Be brief
                self.get_commandment(3),  # Leading questions
                self.get_commandment(4),  # Know the answer
                self.get_commandment(9)   # Don't ask one too many
            ]
        }
    
    def generate_enhanced_question(self,
                                  base_question: str,
                                  context: Dict) -> Dict:
        """שפר שאלה עם ידע מומחה"""
        
        # הוסף מטא-דאטה מבוסס מחקר
        enhancement = {
            "original_question": base_question,
            "enhanced_question": base_question,
            "technique_used": None,
            "psychological_basis": None,
            "commandment_reference": None,
            "risk_assessment": "low",
            "follow_up_suggestions": []
        }
        
        # זהה סוג השאלה והוסף הקשר
        if "בתצהיר" in base_question or "כתבת" in base_question:
            enhancement["technique_used"] = "commit_credit_confront"
            enhancement["psychological_basis"] = "נעילת העד לגרסה לפני עימות"
            enhancement["commandment_reference"] = self.get_commandment(4)
            enhancement["follow_up_suggestions"] = [
                "אם העד מאשר - עבור לשלב ה-Credit",
                "אם העד מכחיש - הצג את המסמך"
            ]
        
        elif "הצד השני" in base_question or "טוען" in base_question:
            enhancement["technique_used"] = "sue_technique"
            enhancement["psychological_basis"] = "שימוש אסטרטגי בראיות"
            enhancement["commandment_reference"] = self.get_commandment(10)
            enhancement["risk_assessment"] = "medium"
            enhancement["follow_up_suggestions"] = [
                "אם העד מכחיש - הצג ראיה תומכת",
                "אם העד מודה - עבור לנקודה הבאה"
            ]
        
        elif "מה שמעת" in base_question or "מה ראית" in base_question:
            enhancement["technique_used"] = "cognitive_load"
            enhancement["psychological_basis"] = "פרטים חושיים קשים להמצאה"
            enhancement["commandment_reference"] = self.get_commandment(5)
            enhancement["follow_up_suggestions"] = [
                "בקש פרטים נוספים על אותו רגע",
                "שאל על פרטים היקפיים"
            ]
        
        return enhancement
    
    def analyze_witness_response(self, response: str) -> Dict:
        """נתח תגובת עד"""
        analysis = {
            "linguistic_markers": [],
            "potential_deception_cues": [],
            "reliability_assessment": "unknown",
            "suggested_follow_up": []
        }
        
        # בדוק סמנים לשוניים
        for marker_type, markers in self.deception_cues["linguistic_markers"].items():
            for marker in markers:
                if marker in response:
                    analysis["linguistic_markers"].append({
                        "type": marker_type,
                        "marker": marker,
                        "interpretation": self._interpret_marker(marker_type)
                    })
        
        # בדוק סימני שקר אמינים
        for cue, explanation in self.deception_cues["verbal_cues"]["reliable"]:
            # זה דורש ניתוח מתקדם יותר - כאן רק דוגמה
            pass
        
        return analysis
    
    def _interpret_marker(self, marker_type: str) -> str:
        """פרש סמן לשוני"""
        interpretations = {
            "minimizing": "העד מנסה להקטין חשיבות - שאל למה",
            "intensifying": "העד מנסה לשכנע יתר על המידה - בדוק עובדות",
            "distancing": "העד מרחיק את עצמו - שאל על מעורבות ישירה",
            "hedging": "העד לא בטוח - נעל אותו לגרסה ספציפית"
        }
        return interpretations.get(marker_type, "לא ידוע")


# === Singleton Instance ===
_knowledge_base = None

def get_knowledge_base() -> ExpertKnowledgeBase:
    """קבל את מאגר הידע (Singleton)"""
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = ExpertKnowledgeBase()
    return _knowledge_base
