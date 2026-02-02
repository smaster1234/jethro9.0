"""
Cross-Examination Question Generator
====================================

Generates cross-examination questions based on:
1. Contradiction type (from playbooks YAML)
2. Severity level
3. Specific quotes/evidence

Uses contradiction_playbooks_v1.yaml patterns.
"""

import os
import yaml
import uuid
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path

from .detector import DetectedContradiction
from .schemas import Severity, ContradictionType, ContradictionCategory
from .extractor import SYSTEM_MARKERS, contains_system_text
from .categorizer import adapt_cross_exam_for_category
from .strategic_engine import (
    StrategicExaminationPlanner,
    WitnessProfile,
    QuestionIntent,
    ResponsePrediction,
    GameTheoryEngine,
    PredictiveResponseModel,
    UncertaintyManager,
    TimePositionOptimizer,
)
from .source_classifier import (
    DocumentSourceClassifier,
    SourceType,
    PartyRole,
    SourceClassification,
    CrossExamSourceContext,
    create_source_classifier,
    classify_contradiction_sources,
)

logger = logging.getLogger(__name__)

# Maximum quote length for cross-exam questions
MAX_QUOTE_LENGTH = 120

# Question type strategies
class QuestionType:
    """Types of cross-examination questions"""
    YES_NO = "yes_no"           # שאלה סגורה - כן/לא
    OPEN = "open"               # שאלה פתוחה
    LEADING = "leading"         # שאלה מנחה
    CONFRONTATION = "confront"  # עימות ישיר
    CLARIFICATION = "clarify"   # בקשת הבהרה
    TRAP = "trap"               # שאלת מלכודת


class QuestionTypeSelector:
    """
    בוחר את סוג השאלה האופטימלי לפי המצב.
    
    כללים:
    - שאלה פתוחה טובה לקיבוע עובדות בתחילה
    - שאלה סגורה טובה לעימות אחרי קיבוע
    - שאלה מנחה טובה לסתירות ברורות
    - שאלת מלכודת טובה לסתירות עם ביטחון גבוה
    """
    
    @staticmethod
    def select_type(
        position: int,
        total_questions: int,
        severity: 'Severity',
        contradiction_type: 'ContradictionType',
        confidence: float = 0.8
    ) -> str:
        """
        בוחר סוג שאלה אופטימלי.
        
        Args:
            position: מיקום השאלה ברצף (0-based)
            total_questions: סה"כ שאלות
            severity: חומרת הסתירה
            contradiction_type: סוג הסתירה
            confidence: רמת ביטחון בסתירה
        
        Returns:
            סוג השאלה המומלץ
        """
        # שאלה ראשונה - תמיד פתוחה לקיבוע
        if position == 0:
            return QuestionType.OPEN
        
        # שאלה שנייה - תלוי בסוג הסתירה
        if position == 1:
            if contradiction_type in [ContradictionType.TEMPORAL, ContradictionType.QUANTITATIVE]:
                return QuestionType.YES_NO  # עובדות מדידות - שאלה סגורה
            else:
                return QuestionType.OPEN  # עובדות פרשניות - שאלה פתוחה
        
        # שאלה שלישית - עימות
        if position == 2:
            if confidence >= 0.85:
                return QuestionType.CONFRONTATION  # ביטחון גבוה - עימות ישיר
            else:
                return QuestionType.CLARIFICATION  # ביטחון נמוך - בקשת הבהרה
        
        # שאלה רביעית - לפי חומרה
        if position == 3:
            if severity in [Severity.CRITICAL, Severity.HIGH]:
                return QuestionType.TRAP  # סתירה חמורה - שאלת מלכודת
            else:
                return QuestionType.LEADING  # סתירה קלה - שאלה מנחה
        
        # שאלה אחרונה - תמיד פתוחה לסיכום
        return QuestionType.OPEN
    
    @staticmethod
    def get_question_prefix(question_type: str) -> str:
        """מחזיר תחילית מומלצת לשאלה לפי הסוג"""
        prefixes = {
            QuestionType.YES_NO: "",  # ללא תחילית
            QuestionType.OPEN: "",  # ללא תחילית
            QuestionType.LEADING: "נכון לומר ש",
            QuestionType.CONFRONTATION: "",
            QuestionType.CLARIFICATION: "תוכל להבהיר ",
            QuestionType.TRAP: "",
        }
        return prefixes.get(question_type, "")
    
    @staticmethod
    def transform_to_type(question: str, question_type: str, variables: dict) -> str:
        """
        ממיר שאלה לסוג המבוקש.
        
        Args:
            question: השאלה המקורית
            question_type: סוג השאלה המבוקש
            variables: משתנים להחלפה
        
        Returns:
            שאלה מומרת
        """
        if question_type == QuestionType.OPEN:
            # המר לשאלה פתוחה
            open_starters = [
                "ספר לי על",
                "תאר את",
                "מה קרה",
                "איך",
                "מדוע",
            ]
            # אם השאלה כבר פתוחה, השאר כמו שהיא
            if any(question.startswith(s) for s in open_starters):
                return question
            # המר שאלה סגורה לפתוחה
            if question.endswith("?") and ("האם" in question or "נכון" in question):
                return question.replace("האם ", "תאר את הנסיבות שבהן ").replace(", נכון?", "?")
            return question
        
        elif question_type == QuestionType.YES_NO:
            # ודא שהשאלה סגורה
            if not question.endswith("?"):
                question = question + "?"
            # הוסף "נכון" אם חסר
            if ", נכון?" not in question and "נכון?" not in question:
                question = question.rstrip("?") + ", נכון?"
            return question
        
        elif question_type == QuestionType.LEADING:
            # שאלה מנחה - מניחה שהתשובה ידועה
            prefix = QuestionTypeSelector.get_question_prefix(question_type)
            if not question.startswith(prefix):
                # הסר "האם" והוסף תחילית מנחה
                question = question.replace("האם ", "").replace("האם", "")
                question = prefix + question.lstrip()
            return question
        
        elif question_type == QuestionType.CONFRONTATION:
            # עימות ישיר - הצגת שתי הגרסאות
            # השאלה המקורית כבר מנוסחת נכון עם התייחסות למקור
            # לא לשנות אותה כאן
            return question
        
        elif question_type == QuestionType.CLARIFICATION:
            # בקשת הבהרה - נימה רכה
            prefix = QuestionTypeSelector.get_question_prefix(question_type)
            if not question.startswith(prefix) and not question.startswith("תוכל"):
                question = prefix + question.lstrip().lower()
            return question
        
        elif question_type == QuestionType.TRAP:
            # שאלת מלכודת - שאלה שנראית תמימה אבל מובילה לסתירה
            trap_questions = [
                "האם יש סיבה כלשהי לכך שהגרסה השתנתה?",
                "האם אתה זוכר בדיוק מה אמרת קודם?",
                "האם יש מסמך שתומך בגרסה הנוכחית?",
            ]
            import random
            return random.choice(trap_questions)
        
        return question


@dataclass
class CrossExamQuestion:
    """Single cross-examination question with strategic metadata"""
    id: str
    question: str
    purpose: str
    severity: Severity
    follow_up: Optional[str] = None
    trap_branch: Optional[str] = None
    
    # Strategic fields
    question_type: str = "open"              # סוג השאלה
    intent: Optional[str] = None              # כוונה אסטרטגית
    position_pct: float = 50.0                # מיקום מומלץ (0-100%)
    time_allocation: float = 1.5              # זמן מומלץ בדקות
    risk_level: float = 0.3                   # רמת סיכון (0-1)
    reward_potential: float = 0.5             # פוטנציאל תגמול (0-1)
    
    # Predicted responses
    predicted_responses: Dict[str, float] = field(default_factory=dict)
    
    # Contingency plans
    if_admit: Optional[str] = None
    if_deny: Optional[str] = None
    if_evade: Optional[str] = None
    
    # Psychological notes
    psychological_notes: Optional[str] = None
    
    # Source reference fields (V3)
    source_reference: Optional[str] = None        # "בתצהיר שלך מיום X"
    attribution_phrase: Optional[str] = None      # "אתה כתבת ש"
    confrontation_phrase: Optional[str] = None    # "אבל בכתב ההגנה נאמר ש"
    source_type: Optional[str] = None             # witness_own_statement / opposing_evidence / etc
    strategic_approach: Optional[str] = None      # internal_contradiction / cross_party_conflict / etc


@dataclass
class CrossExamSet:
    """Set of questions for a contradiction with strategic analysis"""
    contradiction_id: str
    target_party: Optional[str]
    questions: List[CrossExamQuestion]
    strategy_notes: List[str] = field(default_factory=list)
    
    # Strategic analysis
    witness_profile: str = "cooperative"      # פרופיל העד המשוער
    total_time_minutes: float = 10.0          # זמן כולל מומלץ
    expected_value: float = 0.5               # תוחלת ערך
    risk_score: float = 0.3                   # ציון סיכון
    confidence_score: float = 0.7             # ציון ביטחון
    
    # Strategic summary
    strategy_summary: str = ""                # סיכום אסטרטגי
    key_objectives: List[str] = field(default_factory=list)
    potential_pitfalls: List[str] = field(default_factory=list)
    
    # Decision tree
    decision_points: Dict[int, Dict[str, int]] = field(default_factory=dict)
    alternative_paths: List[List[int]] = field(default_factory=list)
    
    # Source context (V3)
    source_context: Optional[Dict[str, Any]] = None  # הקשר מקורות לחקירה
    witness_claim_source: Optional[str] = None       # מקור טענת העד
    opposing_claim_source: Optional[str] = None      # מקור הטענה הסותרת
    strategic_approach: Optional[str] = None         # גישה אסטרטגית מומלצת


class PlaybookLoader:
    """Load and cache playbook YAML"""

    _playbooks: Optional[Dict] = None

    @classmethod
    def load(cls) -> Dict:
        """Load playbooks, with caching"""
        if cls._playbooks is not None:
            return cls._playbooks

        # Try multiple locations
        possible_paths = [
            Path(__file__).parent.parent / "backend" / "knowledge" / "contradiction_playbooks_v1.yaml",
            Path(__file__).parent / "playbooks.yaml",
            Path("/home/user/JETHRO4/backend/knowledge/contradiction_playbooks_v1.yaml"),
        ]

        loaded_playbooks = {}
        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                        loaded_playbooks = data.get('playbooks', {})
                        logger.info(f"Loaded playbooks from {path}")
                        break
                except Exception as e:
                    logger.warning(f"Failed to load playbooks from {path}: {e}")

        # תמיד מזג עם embedded playbooks כדי להוסיף cross_party ו-internal
        embedded = cls._get_embedded_playbooks()
        cls._playbooks = {**embedded, **loaded_playbooks}
        
        # ודא ש-cross_party ו-internal תמיד קיימים
        if "cross_party" not in cls._playbooks:
            cls._playbooks["cross_party"] = embedded.get("cross_party", {})
        if "internal" not in cls._playbooks:
            cls._playbooks["internal"] = embedded.get("internal", {})
        
        logger.info(f"Loaded playbooks: {list(cls._playbooks.keys())}")
        return cls._playbooks

    @classmethod
    def _get_embedded_playbooks(cls) -> Dict:
        """Embedded minimal playbooks"""
        return {
            "temporal": {
                "name_he": "סתירה כרונולוגית",
                "cross_examination": {
                    "question_set": [
                        "אתה מאשר שביום {date_a} התרחש האירוע?",
                        "ובמסמך אחר אתה טוען שזה קרה ב-{date_b}?",
                        "איך אתה מסביר את הפער בתאריכים?",
                        "יש לך מסמך שתומך בגרסה הנוכחית?",
                        "האם ייתכן שאחד התאריכים שגוי?"
                    ],
                    "trap_branches": [
                        "אם העד טוען לבלבול: שאל על מסמך מאותו יום",
                        "אם העד טוען לטעות: שאל מי רשם את התאריך"
                    ]
                }
            },
            "quantitative": {
                "name_he": "סתירה כמותית",
                "cross_examination": {
                    "question_set": [
                        "אתה טוען שהסכום היה {amount_a}?",
                        "אבל במסמך אחר מופיע הסכום {amount_b}?",
                        "איזה סכום הוא הנכון?",
                        "יש לך קבלה או אישור לסכום?",
                        "מאיפה נלקח הסכום שציינת?"
                    ],
                    "trap_branches": [
                        "אם העד טוען לטעות: שאל מי חישב את הסכום",
                        "אם העד טוען לעיגול: בקש את הסכום המדויק"
                    ]
                }
            },
            "attribution": {
                "name_he": "סתירה בייחוס",
                "cross_examination": {
                    "question_set": [
                        "אתה טוען ש-{person_a} ביצע את הפעולה?",
                        "אבל במסמך אחר כתוב ש-{person_b} עשה זאת?",
                        "מי בפועל ביצע את הפעולה?",
                        "היית נוכח כשהפעולה בוצעה?",
                        "מאיפה המידע שלך על מי עשה זאת?"
                    ],
                    "trap_branches": [
                        "אם העד לא היה נוכח: שאל מאיפה הוא יודע",
                        "אם העד משנה גרסה: שאל למה"
                    ]
                }
            },
            "factual": {
                "name_he": "סתירה עובדתית",
                "cross_examination": {
                    "question_set": [
                        "אתה טוען ש-{fact_a}?",
                        "ובמקביל אתה טוען ש-{fact_b}?",
                        "שתי הטענות לא יכולות להיות נכונות יחד, נכון?",
                        "איזו מהטענות נכונה?",
                        "יש לך ראיה שתומכת בגרסה שבחרת?"
                    ],
                    "trap_branches": [
                        "אם העד מנסה לגשר: דרוש הסבר מפורט",
                        "אם העד בוחר עובדה אחת: שאל על הראיות לעובדה השנייה"
                    ]
                }
            },
            "version": {
                "name_he": "שינוי גרסה",
                "cross_examination": {
                    "question_set": [
                        "בתצהירך הראשון אמרת: {quote_a}?",
                        "היום אתה אומר: {quote_b}?",
                        "מה השתנה בין לבין?",
                        "למה הגרסה השתנתה?",
                        "מתי נזכרת בפרטים החדשים?"
                    ],
                    "trap_branches": [
                        "אם העד טוען שנזכר: שאל למה לא ציין קודם",
                        "אם העד טוען לאי-דיוק: שאל מי ניסח את התצהיר"
                    ]
                }
            },
            "witness": {
                "name_he": "סתירה בין עדים",
                "cross_examination": {
                    "question_set": [
                        "בעדותך הקודמת אמרת: {quote_a}, נכון?",
                        "היום אתה אומר: {quote_b}, נכון?",
                        "איזו מהגרסאות היא הנכונה?",
                        "למה בית המשפט צריך להאמין לגרסה הנוכחית?",
                        "האם יש עדים נוספים לאירוע?"
                    ],
                    "trap_branches": [
                        "אם העד בוחר גרסה: שאל על הראיות לגרסה השנייה",
                        "אם העד טוען לטעות: שאל כמה טעויות נוספות יש בעדותו"
                    ]
                }
            },
            "cross_party": {
                "name_he": "עימות בין צדדים",
                "cross_examination": {
                    "question_set": [
                        "אתה טוען ש-{fact_a}, נכון?",
                        "הצד השני טוען ש-{fact_b}. מה תגובתך?",
                        "יש לך ראיה שתומכת בגרסה שלך?",
                        "למה הצד השני היה ממציא גרסה שונה?",
                        "אם הגרסה שלך נכונה, איך אתה מסביר את הראיות של הצד השני?"
                    ],
                    "trap_branches": [
                        "אם העד מכחיש: הצג את הראיה הסותרת",
                        "אם העד מתחמק: דרוש תשובה ישירה",
                        "אם העד מודה: שאל למה לא אמר את זה קודם"
                    ]
                }
            },
            "internal": {
                "name_he": "סתירה פנימית",
                "cross_examination": {
                    "question_set": [
                        "בתצהירך כתבת: {quote_a}, נכון?",
                        "אבל במקום אחר כתבת: {quote_b}, נכון?",
                        "שתי הטענות האלה לא יכולות להיות נכונות יחד. איזו נכונה?",
                        "למה הגרסה השתנתה?",
                        "אין לך הסבר לסתירה הזו?"
                    ],
                    "trap_branches": [
                        "אם העד טוען לטעות: שאל מי ניסח את התצהיר",
                        "אם העד מנסה לגשר: הצג את שתי הגרסאות זו ליד זו"
                    ]
                }
            }
        }


class CrossExamGenerator:
    """Generate cross-examination questions from contradictions"""

    def __init__(self):
        self.playbooks = PlaybookLoader.load()

        # Map ContradictionType to playbook key
        self.type_to_playbook = {
            ContradictionType.TEMPORAL: "temporal",
            ContradictionType.QUANTITATIVE: "quantitative",
            ContradictionType.ATTRIBUTION: "attribution",
            ContradictionType.FACTUAL: "factual",
            ContradictionType.VERSION: "version",
            ContradictionType.WITNESS: "witness",
            ContradictionType.DOCUMENT: "factual",  # Use factual as fallback
        }

    def generate(
        self,
        contradiction: DetectedContradiction,
        max_questions: int = 5
    ) -> CrossExamSet:
        """
        Generate cross-examination questions for a contradiction.

        Args:
            contradiction: The detected contradiction
            max_questions: Maximum questions to generate (3-7 recommended)

        Returns:
            CrossExamSet with questions
        """
        # קודם כל - זהה את סוג העימות (פנימי/חיצוני)
        source_context = self._create_source_context(contradiction)
        strategic_approach = None
        
        if source_context:
            phrasing = source_context.get_question_phrasing()
            strategic_approach = phrasing.get("approach", "general_contradiction")
        
        # בחר playbook לפי הגישה האסטרטגית
        approach_to_playbook = {
            "internal_contradiction": "internal",
            "cross_party_conflict": "cross_party",
            "supporting_witness_conflict": "witness",
        }
        
        if strategic_approach and strategic_approach in approach_to_playbook:
            playbook_key = approach_to_playbook[strategic_approach]
        else:
            playbook_key = self.type_to_playbook.get(contradiction.type, "factual")
        
        playbook = self.playbooks.get(playbook_key, self.playbooks.get("factual", {}))

        cross_exam = playbook.get("cross_examination", {})
        question_templates = cross_exam.get("question_set", [])
        trap_branches = cross_exam.get("trap_branches", [])

        # Prepare template variables
        variables = self._extract_variables(contradiction)

        # Generate questions with smart type selection
        questions = []
        confidence = getattr(contradiction, 'confidence', 0.8)
        
        for i, template in enumerate(question_templates[:max_questions]):
            question_text = self._fill_template(template, variables)

            # GUARDRAIL: Skip questions that contain system text
            if contains_system_text(question_text):
                logger.warning(f"Skipping question with system text: {question_text[:50]}...")
                continue

            # Smart question type selection
            question_type = QuestionTypeSelector.select_type(
                position=i,
                total_questions=max_questions,
                severity=contradiction.severity,
                contradiction_type=contradiction.type,
                confidence=confidence
            )
            
            # Transform question to the selected type
            question_text = QuestionTypeSelector.transform_to_type(
                question=question_text,
                question_type=question_type,
                variables=variables
            )

            # Get corresponding trap branch if available
            trap = trap_branches[i] if i < len(trap_branches) else None

            questions.append(CrossExamQuestion(
                id=f"q_{uuid.uuid4().hex[:6]}",
                question=question_text,
                purpose=self._get_question_purpose_smart(i, playbook_key, question_type),
                severity=contradiction.severity,
                follow_up=self._generate_follow_up_smart(i, playbook_key, question_type),
                trap_branch=trap
            ))

        # Adapt questions based on category (hard contradiction vs narrative ambiguity)
        category = getattr(contradiction, 'category', None)
        if category:
            questions = self._adapt_for_category(
                questions=questions,
                category=category,
                ambiguity_explanation=getattr(contradiction, 'ambiguity_explanation', None)
            )

        # Determine target party
        target_party = self._determine_target(contradiction)

        # Strategy notes
        strategy_notes = self._generate_strategy_notes(contradiction, playbook)

        # ========================================
        # SOURCE-AWARE QUESTION GENERATION (V3)
        # ========================================
        
        # source_context כבר נוצר בתחילת הפונקציה
        
        # Enhance questions with source references
        if source_context:
            questions = self._enhance_with_source_references(
                questions=questions,
                source_context=source_context,
                contradiction=contradiction
            )
        
        # ========================================
        # STRATEGIC ENGINE INTEGRATION
        # ========================================
        
        # Create strategic planner
        strategic_planner = StrategicExaminationPlanner()
        
        # Infer witness profile from contradiction context
        witness_profile = self._infer_witness_profile(contradiction)
        
        # Generate strategic examination plan
        claim_a = contradiction.quote1 or ""
        claim_b = contradiction.quote2 or ""
        contradiction_type_str = str(contradiction.type.value) if contradiction.type else "FACTUAL"
        
        strategic_plan = strategic_planner.create_examination_plan(
            contradiction_type=contradiction_type_str,
            contradiction_confidence=confidence,
            claim_a=claim_a,
            claim_b=claim_b,
            witness_profile=witness_profile,
            total_time_minutes=15.0  # Default 15 minutes per contradiction
        )
        
        # Enhance questions with strategic metadata
        enhanced_questions = self._enhance_with_strategic_data(
            questions=questions,
            strategic_plan=strategic_plan,
            witness_profile=witness_profile
        )
        
        # Build decision tree for adaptive questioning
        decision_points = self._build_decision_points(enhanced_questions)
        
        # Build source context summary
        source_context_dict = None
        witness_claim_source = None
        opposing_claim_source = None
        strategic_approach = None
        
        if source_context:
            phrasing = source_context.get_question_phrasing()
            source_context_dict = {
                "approach": phrasing.get("approach"),
                "opening": phrasing.get("opening"),
                "confrontation": phrasing.get("confrontation"),
                "closing": phrasing.get("closing"),
                "strategy_note": phrasing.get("strategy_note"),
            }
            witness_claim_source = source_context.claim1_source.reference_phrase
            opposing_claim_source = source_context.claim2_source.reference_phrase
            strategic_approach = phrasing.get("approach")
        
        return CrossExamSet(
            contradiction_id=contradiction.id,
            target_party=target_party,
            questions=enhanced_questions,
            strategy_notes=strategy_notes,
            witness_profile=witness_profile.value,
            total_time_minutes=strategic_plan.total_time_minutes,
            expected_value=strategic_plan.expected_value,
            risk_score=strategic_plan.risk_score,
            confidence_score=strategic_plan.confidence_score,
            strategy_summary=strategic_plan.strategy_summary,
            key_objectives=strategic_plan.key_objectives,
            potential_pitfalls=strategic_plan.potential_pitfalls,
            decision_points=decision_points,
            alternative_paths=strategic_plan.alternative_paths,
            # Source context (V3)
            source_context=source_context_dict,
            witness_claim_source=witness_claim_source,
            opposing_claim_source=opposing_claim_source,
            strategic_approach=strategic_approach,
        )

    def generate_for_all(
        self,
        contradictions: List[DetectedContradiction],
        max_questions_per: int = 5
    ) -> List[CrossExamSet]:
        """Generate questions for all contradictions"""
        return [
            self.generate(contr, max_questions_per)
            for contr in contradictions
        ]

    def _extract_variables(self, contradiction: DetectedContradiction) -> Dict[str, str]:
        """Extract template variables from contradiction"""
        # Sanitize quotes - remove system text
        quote1 = self._sanitize_quote(contradiction.quote1)
        quote2 = self._sanitize_quote(contradiction.quote2)

        variables = {
            "quote_a": quote1[:MAX_QUOTE_LENGTH] if quote1 else "",
            "quote_b": quote2[:MAX_QUOTE_LENGTH] if quote2 else "",
            "fact_a": quote1[:80] if quote1 else "",
            "fact_b": quote2[:80] if quote2 else "",
        }

        # Extract from metadata
        metadata = contradiction.metadata or {}

        # Dates
        if "date1" in metadata:
            variables["date_a"] = str(metadata["date1"])
        if "date2" in metadata:
            variables["date_b"] = str(metadata["date2"])

        # Amounts
        if "amount1" in metadata:
            variables["amount_a"] = self._format_amount(metadata["amount1"])
        if "amount2" in metadata:
            variables["amount_b"] = self._format_amount(metadata["amount2"])

        # Attribution
        if "attr1" in metadata:
            variables["person_a"] = ", ".join(metadata["attr1"])
        if "attr2" in metadata:
            variables["person_b"] = ", ".join(metadata["attr2"])

        return variables

    def _sanitize_quote(self, quote: Optional[str]) -> str:
        """
        Sanitize a quote by removing system text and limiting length.
        Tries to end at natural sentence boundaries for better readability.
        """
        if not quote:
            return ""

        # Check if quote contains system text - if so, skip it entirely
        if contains_system_text(quote):
            return ""

        # Remove any system markers inline
        sanitized = quote
        for marker in SYSTEM_MARKERS:
            sanitized = sanitized.replace(marker, "")

        # Clean up whitespace
        sanitized = ' '.join(sanitized.split())

        # If short enough, return as-is
        if len(sanitized) <= MAX_QUOTE_LENGTH:
            return sanitized.strip()

        # Try to find a natural sentence boundary
        # Hebrew sentence endings: . ! ? : ; ,
        sentence_endings = ['. ', '! ', '? ', ': ', '; ', ', ']
        best_cutoff = -1
        
        for ending in sentence_endings:
            # Find the last occurrence before the limit
            pos = sanitized.rfind(ending, 0, MAX_QUOTE_LENGTH)
            if pos > best_cutoff and pos > MAX_QUOTE_LENGTH // 3:
                best_cutoff = pos + len(ending) - 1  # Include the punctuation
        
        if best_cutoff > MAX_QUOTE_LENGTH // 3:
            # Found a good sentence boundary
            return sanitized[:best_cutoff].strip() + "..."
        
        # Fallback: try to end at word boundary
        cutoff = sanitized.rfind(' ', 0, MAX_QUOTE_LENGTH)
        if cutoff > MAX_QUOTE_LENGTH // 2:
            return sanitized[:cutoff].strip() + "..."
        
        # Last resort: hard cut
        return sanitized[:MAX_QUOTE_LENGTH].strip() + "..."

    def _fill_template(self, template: str, variables: Dict[str, str]) -> str:
        """Fill template with variables"""
        result = template
        for key, value in variables.items():
            result = result.replace(f"{{{key}}}", str(value))

        # Clean unfilled placeholders
        import re
        result = re.sub(r'\{[^}]+\}', '[לא זמין]', result)

        return result

    def _format_amount(self, amount: Any) -> str:
        """Format amount for display"""
        try:
            num = float(amount)
            if num >= 1_000_000:
                return f"{num/1_000_000:.1f} מיליון ש\"ח"
            elif num >= 1_000:
                return f"{num/1_000:.1f} אלף ש\"ח"
            else:
                return f"{num:,.0f} ש\"ח"
        except (ValueError, TypeError):
            return str(amount)

    def _get_question_purpose(self, index: int, playbook_key: str) -> str:
        """Get purpose description for question (legacy)"""
        purposes = {
            0: "קיבוע עובדה ראשונה",
            1: "קיבוע עובדה שנייה",
            2: "עימות ישיר",
            3: "בקשת הסבר",
            4: "בדיקת ראיות",
        }
        return purposes.get(index, "שאלת מעקב")
    
    def _get_question_purpose_smart(self, index: int, playbook_key: str, question_type: str) -> str:
        """מחזיר מטרה לפי סוג השאלה"""
        type_purposes = {
            QuestionType.OPEN: "קיבוע עובדות במילים של העד",
            QuestionType.YES_NO: "אישור עובדה ספציפית",
            QuestionType.LEADING: "הנחיית העד למסקנה",
            QuestionType.CONFRONTATION: "עימות ישיר עם הסתירה",
            QuestionType.CLARIFICATION: "בקשת הבהרה לפני עימות",
            QuestionType.TRAP: "בדיקת עקביות הגרסה",
        }
        return type_purposes.get(question_type, self._get_question_purpose(index, playbook_key))

    def _generate_follow_up(self, index: int, playbook_key: str) -> str:
        """Generate follow-up suggestion (legacy)"""
        follow_ups = {
            0: "אם מאשר - המשך לשאלה הבאה",
            1: "אם מכחיש - הצג את המסמך",
            2: "תן לעד להסביר לפני שתגיב",
            3: "אם ההסבר חלש - הדגש את הסתירה",
            4: "אם אין ראיה - הדגש את החוסר",
        }
        return follow_ups.get(index, "התאם לפי התשובה")
    
    def _generate_follow_up_smart(self, index: int, playbook_key: str, question_type: str) -> str:
        """מחזיר המלצה למעקב לפי סוג השאלה"""
        type_follow_ups = {
            QuestionType.OPEN: "הקשב לתשובה וחפש פרטים לקיבוע",
            QuestionType.YES_NO: "אם מאשר - המשך. אם מכחיש - הצג מסמך",
            QuestionType.LEADING: "אם מסכים - המשך לעימות. אם מכחיש - בקש הסבר",
            QuestionType.CONFRONTATION: "תן לעד להסביר. אם מתבלבל - חזור לשאלה",
            QuestionType.CLARIFICATION: "הקשב להבהרה. אם לא מספקת - עבור לעימות",
            QuestionType.TRAP: "אם נלכד במלכודת - הדגש את הסתירה",
        }
        return type_follow_ups.get(question_type, self._generate_follow_up(index, playbook_key))

    def _determine_target(self, contradiction: DetectedContradiction) -> Optional[str]:
        """Determine target witness/party"""
        # Try to extract from claim metadata
        speakers = set()

        if contradiction.claim1.speaker:
            speakers.add(contradiction.claim1.speaker)
        if contradiction.claim2.speaker:
            speakers.add(contradiction.claim2.speaker)

        if speakers:
            return ", ".join(speakers)

        return None

    def _generate_strategy_notes(
        self,
        contradiction: DetectedContradiction,
        playbook: Dict
    ) -> List[str]:
        """Generate strategy notes"""
        notes = []

        # Severity-based notes
        if contradiction.severity == Severity.CRITICAL:
            notes.append("סתירה קריטית - התמקד בה כנקודת תורפה מרכזית")
        elif contradiction.severity == Severity.HIGH:
            notes.append("סתירה משמעותית - שווה להקדיש זמן בחקירה")

        # Type-based notes
        type_notes = {
            ContradictionType.TEMPORAL: "קבע את התאריכים לפני שתעמת",
            ContradictionType.QUANTITATIVE: "בקש תיעוד לסכומים",
            ContradictionType.ATTRIBUTION: "ודא שהעד היה נוכח לאירוע",
            ContradictionType.VERSION: "הדגש את שינוי הגרסה לאורך זמן",
        }
        if contradiction.type in type_notes:
            notes.append(type_notes[contradiction.type])

        # General notes
        notes.extend([
            "שמור על קור רוח - אל תתקוף",
            "תן לעד להסביר לפני שתגיב",
            "השתמש במסמכים לתמיכה"
        ])

        return notes

    def _adapt_for_category(
        self,
        questions: List[CrossExamQuestion],
        category: ContradictionCategory,
        ambiguity_explanation: Optional[Any] = None
    ) -> List[CrossExamQuestion]:
        """
        Adapt questions based on contradiction category.

        For HARD_CONTRADICTION: Keep direct confrontation
        For NARRATIVE_AMBIGUITY: Use softer clarification approach
        """
        if category == ContradictionCategory.HARD_CONTRADICTION:
            # Hard contradictions - direct confrontation is appropriate
            return questions

        if category == ContradictionCategory.NARRATIVE_AMBIGUITY:
            # Use the categorizer's adapt function
            original_questions = [q.question for q in questions]
            adapted_list = adapt_cross_exam_for_category(
                category=category,
                original_questions=original_questions,
                ambiguity_explanation=ambiguity_explanation
            )

            # Convert back to CrossExamQuestion objects
            adapted_questions = []
            for i, item in enumerate(adapted_list):
                adapted_questions.append(CrossExamQuestion(
                    id=f"q_{uuid.uuid4().hex[:6]}",
                    question=item['question'],
                    purpose=item.get('purpose', 'שאלת בירור'),
                    severity=questions[0].severity if questions else Severity.MEDIUM,
                    follow_up="התאם לפי התשובה",
                    trap_branch=None
                ))

            logger.info(
                f"Adapted {len(questions)} questions for narrative ambiguity "
                f"-> {len(adapted_questions)} clarification questions"
            )
            return adapted_questions

        if category == ContradictionCategory.LOGICAL_INCONSISTENCY:
            # Logical inconsistency - keep but soften language
            adapted = []
            for q in questions:
                # Replace confrontational phrases with softer ones
                question_text = q.question
                question_text = question_text.replace("סתירה", "אי-עקביות")
                question_text = question_text.replace("איך אתה מסביר", "תוכל להבהיר")
                adapted.append(CrossExamQuestion(
                    id=q.id,
                    question=question_text,
                    purpose="בירור אי-עקביות לוגית",
                    severity=q.severity,
                    follow_up=q.follow_up,
                    trap_branch=q.trap_branch
                ))
            return adapted

        if category == ContradictionCategory.RHETORICAL_SHIFT:
            # Rhetorical shift - focus on why the framing changed
            return [CrossExamQuestion(
                id=f"q_{uuid.uuid4().hex[:6]}",
                question="למה הניסוח שונה בין המסמכים?",
                purpose="בדיקת שינוי רטורי",
                severity=questions[0].severity if questions else Severity.LOW,
                follow_up="התאם לפי התשובה",
                trap_branch=None
            ), CrossExamQuestion(
                id=f"q_{uuid.uuid4().hex[:6]}",
                question="האם המשמעות שונה בין הגרסאות?",
                purpose="בירור משמעות",
                severity=questions[0].severity if questions else Severity.LOW,
                follow_up="התאם לפי התשובה",
                trap_branch=None
            )]

        return questions

    # ========================================
    # STRATEGIC ENGINE HELPER METHODS
    # ========================================
    
    def _infer_witness_profile(self, contradiction: DetectedContradiction) -> WitnessProfile:
        """
        הסקת פרופיל עד מהקשר הסתירה
        
        מנתח את הסתירה כדי להסיק את פרופיל העד הצפוי
        """
        # בדיקת סימנים לעוינות
        hostile_markers = ["מכחיש", "שקרי", "מסרב", "מתכחש"]
        evasive_markers = ["לא זוכר", "אולי", "ייתכן", "אפשרי"]
        confident_markers = ["בוודאי", "בטוח", "בהחלט", "ברור"]
        nervous_markers = ["לא בטוח", "אולי לא", "לא יודע", "מבולבל"]
        
        text = f"{contradiction.quote1 or ''} {contradiction.quote2 or ''}".lower()
        
        # בדיקת סימנים
        if any(marker in text for marker in hostile_markers):
            return WitnessProfile.HOSTILE
        if any(marker in text for marker in evasive_markers):
            return WitnessProfile.EVASIVE
        if any(marker in text for marker in confident_markers):
            return WitnessProfile.CONFIDENT
        if any(marker in text for marker in nervous_markers):
            return WitnessProfile.NERVOUS
        
        # בדיקת חומרת הסתירה
        if contradiction.severity in [Severity.CRITICAL, Severity.HIGH]:
            # סתירות חמורות מרמזות על עד מתגונן
            return WitnessProfile.DEFENSIVE
        
        # ברירת מחדל
        return WitnessProfile.COOPERATIVE
    
    def _enhance_with_strategic_data(
        self,
        questions: List[CrossExamQuestion],
        strategic_plan,
        witness_profile: WitnessProfile
    ) -> List[CrossExamQuestion]:
        """
        העשרת שאלות עם מטא-דאטה אסטרטגי
        """
        enhanced = []
        strategic_questions = strategic_plan.questions if strategic_plan else []
        
        for i, q in enumerate(questions):
            # מציאת שאלה אסטרטגית מתאימה
            strategic_q = strategic_questions[i] if i < len(strategic_questions) else None
            
            # חישוב תגובות צפויות
            predicted_responses = {}
            if strategic_q:
                nash_eq = GameTheoryEngine.calculate_nash_equilibrium(
                    strategic_q.intent,
                    witness_profile
                )
                predicted_responses = {r.value: p for r, p in nash_eq.items()}
            
            # יצירת תוכניות חלופיות
            contingency = UncertaintyManager.generate_contingency_plans(
                strategic_q, predicted_responses
            ) if strategic_q else {}
            
            enhanced.append(CrossExamQuestion(
                id=q.id,
                question=q.question,
                purpose=q.purpose,
                severity=q.severity,
                follow_up=q.follow_up,
                trap_branch=q.trap_branch,
                question_type=q.question_type if hasattr(q, 'question_type') else "open",
                intent=strategic_q.intent.value if strategic_q else None,
                position_pct=strategic_q.position if strategic_q else (i / len(questions)) * 100,
                time_allocation=strategic_q.time_allocation if strategic_q else 1.5,
                risk_level=strategic_q.risk_level if strategic_q else 0.3,
                reward_potential=strategic_q.reward_potential if strategic_q else 0.5,
                predicted_responses=predicted_responses,
                if_admit=contingency.get(ResponsePrediction.ADMIT, "המשך לשאלה הבאה"),
                if_deny=contingency.get(ResponsePrediction.DENY, "הצג ראיה סותרת"),
                if_evade=contingency.get(ResponsePrediction.EVADE, "חזור על השאלה בניסוח ישיר"),
                psychological_notes=strategic_q.psychological_notes if strategic_q else None,
                # Preserve source reference fields (V3)
                source_reference=getattr(q, 'source_reference', None),
                attribution_phrase=getattr(q, 'attribution_phrase', None),
                confrontation_phrase=getattr(q, 'confrontation_phrase', None),
                source_type=getattr(q, 'source_type', None),
                strategic_approach=getattr(q, 'strategic_approach', None),
            ))
        
        return enhanced
    
    def _build_decision_points(
        self,
        questions: List[CrossExamQuestion]
    ) -> Dict[int, Dict[str, int]]:
        """
        בניית נקודות החלטה לחקירה אדפטיבית
        
        מחזיר: מיפוי של (אינדקס שאלה -> תגובה -> אינדקס שאלה הבאה)
        """
        decision_points = {}
        
        for i, q in enumerate(questions):
            if i >= len(questions) - 1:
                continue
            
            decision_points[i] = {
                "admit": i + 1,  # אם מודה - המשך לשאלה הבאה
                "deny": i + 1,   # אם מכחיש - המשך לשאלה הבאה
                "evade": i,      # אם מתחמק - חזור על אותה שאלה
            }
            
            # התאמות לפי סוג השאלה
            if q.intent == "exploit_contradiction":
                # אחרי ניצול סתירה - אפשר לדלג שאלות
                decision_points[i]["admit"] = min(i + 2, len(questions) - 1)
            elif q.intent == "psychological_pressure":
                # אם העד נשבר - נצל מקסימלי
                decision_points[i]["break_down"] = len(questions) - 1  # קפוץ לסיום
        
        return decision_points
    
    # ========================================
    # SOURCE-AWARE QUESTION GENERATION (V3)
    # ========================================
    
    def _create_source_context(
        self,
        contradiction: DetectedContradiction
    ) -> Optional[CrossExamSourceContext]:
        """
        יוצר הקשר מקורות לסתירה.
        
        מנתח את המטא-דאטה של הסתירה ומסווג את מקורות הטענות.
        """
        try:
            metadata = contradiction.metadata or {}
            
            # חילוץ מידע על העד הנחקר
            examined_witness_name = metadata.get('examined_witness_name', '')
            examined_witness_party = metadata.get('examined_witness_party', 'unknown')
            
            # יצירת מסווג מקורות
            classifier = create_source_classifier(
                examined_witness_name=examined_witness_name,
                examined_witness_party=examined_witness_party,
                documents=metadata.get('documents', [])
            )
            
            # סיווג מקורות הטענות
            source_context = classify_contradiction_sources(
                classifier=classifier,
                claim1_doc_id=metadata.get('claim1_doc_id'),
                claim1_doc_name=metadata.get('claim1_doc_name'),
                claim1_speaker=metadata.get('claim1_speaker'),
                claim1_speaker_role=metadata.get('claim1_speaker_role'),
                claim1_speaker_mode=metadata.get('claim1_speaker_mode'),
                claim2_doc_id=metadata.get('claim2_doc_id'),
                claim2_doc_name=metadata.get('claim2_doc_name'),
                claim2_speaker=metadata.get('claim2_speaker'),
                claim2_speaker_role=metadata.get('claim2_speaker_role'),
                claim2_speaker_mode=metadata.get('claim2_speaker_mode'),
            )
            
            return source_context
            
        except Exception as e:
            logger.warning(f"Failed to create source context: {e}")
            return None
    
    def _enhance_with_source_references(
        self,
        questions: List[CrossExamQuestion],
        source_context: CrossExamSourceContext,
        contradiction: DetectedContradiction
    ) -> List[CrossExamQuestion]:
        """
        משפר שאלות עם התייחסויות למקורות.
        
        מוסיף לשאלות ביטויים כמו:
        - "בתצהיר שלך כתבת..."
        - "אבל הצד שכנגד טוען..."
        """
        phrasing = source_context.get_question_phrasing()
        approach = phrasing.get("approach", "general_contradiction")
        
        # בחירת playbook מותאם לגישה האסטרטגית
        approach_to_playbook = {
            "internal_contradiction": "internal",
            "cross_party_conflict": "cross_party",
            "supporting_witness_conflict": "witness",
            "contradict_court_finding": "factual",
            "contradict_document": "factual",
        }
        
        playbook_key = approach_to_playbook.get(approach)
        approach_playbook = None
        if playbook_key and playbook_key in self.playbooks:
            approach_playbook = self.playbooks[playbook_key]
        
        enhanced = []
        for i, q in enumerate(questions):
            # השאלה הראשונה - הוסף התייחסות למקור
            if i == 0:
                # יצירת שאלה עם התייחסות מלאה למקור
                source_aware_question = source_context.generate_source_aware_question(
                    quote_a=contradiction.quote1 or "",
                    quote_b=contradiction.quote2 or "",
                    question_type="confrontation"
                )
                
                enhanced.append(CrossExamQuestion(
                    id=q.id,
                    question=source_aware_question,
                    purpose="עימות ראשוני עם הסתירה",
                    severity=q.severity,
                    follow_up=q.follow_up,
                    trap_branch=q.trap_branch,
                    question_type="confrontation",
                    # Source reference fields
                    source_reference=source_context.claim1_source.reference_phrase,
                    attribution_phrase=phrasing.get("opening", ""),
                    confrontation_phrase=phrasing.get("confrontation", ""),
                    source_type=source_context.claim1_source.source_type.value,
                    strategic_approach=approach,
                ))
            else:
                # שאר השאלות - השתמש ב-playbook מותאם לגישה
                new_question = q.question
                
                # אם יש playbook מותאם, השתמש בשאלות שלו
                if approach_playbook:
                    cross_exam = approach_playbook.get("cross_examination", {})
                    question_set = cross_exam.get("question_set", [])
                    if i < len(question_set):
                        variables = self._extract_variables(contradiction)
                        new_question = self._fill_template(question_set[i], variables)
                
                enhanced.append(CrossExamQuestion(
                    id=q.id,
                    question=new_question,
                    purpose=q.purpose,
                    severity=q.severity,
                    follow_up=q.follow_up,
                    trap_branch=q.trap_branch,
                    question_type=q.question_type if hasattr(q, 'question_type') else "open",
                    # Source reference fields
                    source_reference=source_context.claim1_source.reference_phrase,
                    attribution_phrase=phrasing.get("opening", ""),
                    confrontation_phrase=phrasing.get("confrontation", ""),
                    source_type=source_context.claim1_source.source_type.value,
                    strategic_approach=approach,
                ))
        
        # הוספת הערה אסטרטגית לרשימה
        strategy_note = phrasing.get("strategy_note", "")
        if strategy_note:
            logger.info(f"Source-aware strategy: {strategy_note}")
        
        return enhanced


# Singleton
_generator = None

def get_cross_exam_generator() -> CrossExamGenerator:
    """Get singleton generator instance"""
    global _generator
    if _generator is None:
        _generator = CrossExamGenerator()
    return _generator


def generate_cross_exam_questions(
    contradictions: List[DetectedContradiction],
    max_questions_per: int = 5
) -> List[CrossExamSet]:
    """
    Convenience function to generate cross-exam questions.

    Args:
        contradictions: List of detected contradictions
        max_questions_per: Max questions per contradiction

    Returns:
        List of CrossExamSet
    """
    return get_cross_exam_generator().generate_for_all(contradictions, max_questions_per)
