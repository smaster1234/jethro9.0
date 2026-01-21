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

logger = logging.getLogger(__name__)

# Maximum quote length for cross-exam questions
MAX_QUOTE_LENGTH = 120


@dataclass
class CrossExamQuestion:
    """Single cross-examination question"""
    id: str
    question: str
    purpose: str
    severity: Severity
    follow_up: Optional[str] = None
    trap_branch: Optional[str] = None


@dataclass
class CrossExamSet:
    """Set of questions for a contradiction"""
    contradiction_id: str
    target_party: Optional[str]
    questions: List[CrossExamQuestion]
    strategy_notes: List[str] = field(default_factory=list)


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

        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                        cls._playbooks = data.get('playbooks', {})
                        logger.info(f"Loaded playbooks from {path}")
                        return cls._playbooks
                except Exception as e:
                    logger.warning(f"Failed to load playbooks from {path}: {e}")

        # Fallback to embedded minimal playbooks
        cls._playbooks = cls._get_embedded_playbooks()
        logger.info("Using embedded playbooks")
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
        # Get appropriate playbook
        playbook_key = self.type_to_playbook.get(contradiction.type, "factual")
        playbook = self.playbooks.get(playbook_key, self.playbooks.get("factual", {}))

        cross_exam = playbook.get("cross_examination", {})
        question_templates = cross_exam.get("question_set", [])
        trap_branches = cross_exam.get("trap_branches", [])

        # Prepare template variables
        variables = self._extract_variables(contradiction)

        # Generate questions
        questions = []
        for i, template in enumerate(question_templates[:max_questions]):
            question_text = self._fill_template(template, variables)

            # GUARDRAIL: Skip questions that contain system text
            if contains_system_text(question_text):
                logger.warning(f"Skipping question with system text: {question_text[:50]}...")
                continue

            # Get corresponding trap branch if available
            trap = trap_branches[i] if i < len(trap_branches) else None

            questions.append(CrossExamQuestion(
                id=f"q_{uuid.uuid4().hex[:6]}",
                question=question_text,
                purpose=self._get_question_purpose(i, playbook_key),
                severity=contradiction.severity,
                follow_up=self._generate_follow_up(i, playbook_key),
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

        return CrossExamSet(
            contradiction_id=contradiction.id,
            target_party=target_party,
            questions=questions,
            strategy_notes=strategy_notes
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
        """Sanitize a quote by removing system text and limiting length."""
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

        # Truncate to max length, try to end at word boundary
        if len(sanitized) > MAX_QUOTE_LENGTH:
            # Find last space before limit
            cutoff = sanitized.rfind(' ', 0, MAX_QUOTE_LENGTH)
            if cutoff > MAX_QUOTE_LENGTH // 2:
                sanitized = sanitized[:cutoff] + "..."
            else:
                sanitized = sanitized[:MAX_QUOTE_LENGTH] + "..."

        return sanitized.strip()

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
        """Get purpose description for question"""
        purposes = {
            0: "קיבוע עובדה ראשונה",
            1: "קיבוע עובדה שנייה",
            2: "עימות ישיר",
            3: "בקשת הסבר",
            4: "בדיקת ראיות",
        }
        return purposes.get(index, "שאלת מעקב")

    def _generate_follow_up(self, index: int, playbook_key: str) -> str:
        """Generate follow-up suggestion"""
        follow_ups = {
            0: "אם מאשר - המשך לשאלה הבאה",
            1: "אם מכחיש - הצג את המסמך",
            2: "תן לעד להסביר לפני שתגיב",
            3: "אם ההסבר חלש - הדגש את הסתירה",
            4: "אם אין ראיה - הדגש את החוסר",
        }
        return follow_ups.get(index, "התאם לפי התשובה")

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
