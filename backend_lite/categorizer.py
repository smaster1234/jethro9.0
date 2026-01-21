"""
Contradiction Categorizer
=========================

Classifies contradictions into categories:
- HARD_CONTRADICTION: Clear factual contradiction - both claims cannot be true
- LOGICAL_INCONSISTENCY: Logically incompatible statements
- NARRATIVE_AMBIGUITY: Apparent discrepancy with reasonable explanations
- RHETORICAL_SHIFT: Change in emphasis without factual contradiction

Decision criteria for HARD_CONTRADICTION:
1. Same object/entity
2. Same aspect (the same attribute is being described)
3. Same timeframe
4. No reasonable interpretation that reconciles both claims
"""

import re
import logging
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from .schemas import (
    ContradictionCategory,
    ContradictionType,
    ContradictionSubtype,
    ContradictionStatus,
    Severity,
    AmbiguityExplanation
)

logger = logging.getLogger(__name__)


# =============================================================================
# Categorization Rules
# =============================================================================

@dataclass
class CategorizationResult:
    """Result of contradiction categorization"""
    category: ContradictionCategory
    severity_adjustment: Optional[Severity] = None  # Override severity for ambiguity
    ambiguity_explanation: Optional[AmbiguityExplanation] = None
    badge: str = ""
    label_short: str = ""
    reasoning: str = ""


class ContradictionCategorizer:
    """
    Categorizes contradictions based on semantic analysis.

    Distinguishes between hard contradictions (mutually exclusive facts)
    and narrative ambiguity (discrepancies that may have reasonable explanations).
    """

    def __init__(self):
        # Aspect indicators - different aspects of the same subject
        self.aspect_markers = {
            "temporal": ["נערכו", "נחתמו", "הוגשו", "בוטלו", "נמסרו"],
            "result": ["הותירו", "גרמו", "יצרו", "הפיקו", "נתנו"],
            "quantity_created": ["נערכו", "נוצרו", "הופקו", "נכתבו"],
            "quantity_remaining": ["נותרו", "הותירו", "נשארו", "קיימות"],
            "state": ["היה", "הייתה", "היו", "נמצא", "נמצאה"],
            "action": ["עשה", "ביצע", "הוציא", "שלח", "קיבל"],
        }

        # Reconciliation patterns - phrases that suggest possible reconciliation
        self.reconciliation_patterns = [
            r'לא נערכו\s.*\sהותירו',  # "נערכו" vs "הותירו" - different aspects
            r'הותיר(?:ו|ה)?\s+אחרי',  # "left behind" implies past action
            r'במקור\s.*\sבסוף',  # "originally... in the end"
            r'תחילה\s.*\sלאחר מכן',  # "first... then"
            r'לפני\s.*\sאחרי',  # "before... after"
        ]

        # Same-aspect indicators - when two claims talk about exact same thing
        self.same_aspect_indicators = [
            (r'(?:נחתם|נחתמו)\s.*\s(?:נחתם|נחתמו)', 'same_signing'),
            (r'(?:שילם|שילמו)\s.*\s(?:שילם|שילמו)', 'same_payment'),
            (r'(?:היה|הייתה)\s.*\s(?:היה|הייתה)', 'same_state'),
        ]

    def categorize(
        self,
        claim1_text: str,
        claim2_text: str,
        contradiction_type: ContradictionType,
        normalized1: Optional[str] = None,
        normalized2: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CategorizationResult:
        """
        Categorize a contradiction.

        Args:
            claim1_text: Text of first claim
            claim2_text: Text of second claim
            contradiction_type: Detected type of contradiction
            normalized1: Normalized value from claim 1 (if applicable)
            normalized2: Normalized value from claim 2 (if applicable)
            metadata: Additional metadata from detection

        Returns:
            CategorizationResult with category, explanation, and UI helpers
        """
        metadata = metadata or {}

        # Step 1: Check if there's a reasonable reconciliation
        reconciliation = self._find_reconciliation(claim1_text, claim2_text, contradiction_type, metadata)

        if reconciliation:
            # This is narrative ambiguity
            return self._create_ambiguity_result(
                claim1_text, claim2_text, contradiction_type, reconciliation, metadata
            )

        # Step 2: Check if same aspect
        same_aspect = self._is_same_aspect(claim1_text, claim2_text, contradiction_type)

        if not same_aspect:
            # Different aspects - likely narrative ambiguity
            return self._create_ambiguity_result(
                claim1_text, claim2_text, contradiction_type,
                "הטענות מתייחסות להיבטים שונים של אותו עניין",
                metadata
            )

        # Step 3: For quantitative - check if same object being measured
        if contradiction_type == ContradictionType.QUANT_AMOUNT:
            same_object = self._is_same_quantified_object(claim1_text, claim2_text, metadata)

            if not same_object:
                return self._create_ambiguity_result(
                    claim1_text, claim2_text, contradiction_type,
                    "המספרים מתייחסים לאובייקטים או מדדים שונים",
                    metadata
                )

        # Step 4: For temporal - check same event
        if contradiction_type == ContradictionType.TEMPORAL_DATE:
            same_event = self._is_same_temporal_event(claim1_text, claim2_text, metadata)

            if not same_event:
                return self._create_ambiguity_result(
                    claim1_text, claim2_text, contradiction_type,
                    "התאריכים עשויים להתייחס לאירועים שונים",
                    metadata
                )

        # If we get here, it's a hard contradiction
        return CategorizationResult(
            category=ContradictionCategory.HARD_CONTRADICTION,
            badge="🔴 סתירה מוכרחת",
            label_short="סתירה",
            reasoning="שתי הטענות אינן יכולות להיות נכונות יחד - סתירה עובדתית ישירה"
        )

    def _find_reconciliation(
        self,
        claim1: str,
        claim2: str,
        contr_type: ContradictionType,
        metadata: Dict[str, Any]
    ) -> Optional[str]:
        """
        Find a reasonable reconciliation between two claims.

        Returns description of possible reconciliation, or None if claims are irreconcilable.
        """
        combined = claim1 + " " + claim2

        # Check for different aspect patterns
        for pattern in self.reconciliation_patterns:
            if re.search(pattern, combined, re.DOTALL):
                return "הטענות מתארות היבטים שונים או שלבים שונים בזמן"

        # Check for "נערכו" vs "הותירו" pattern (the wills example)
        if self._is_created_vs_remaining(claim1, claim2):
            return "ייתכן שמספר הפריטים שנוצרו שונה ממספר הפריטים שנותרו"

        # Check for temporal qualification
        if self._has_temporal_qualification(claim1, claim2):
            return "הטענות עשויות להתייחס לתקופות זמן שונות"

        # Check for scope difference
        if self._has_scope_difference(claim1, claim2):
            return "הטענות עשויות להתייחס להיקפים שונים של אותו עניין"

        return None

    def _is_created_vs_remaining(self, claim1: str, claim2: str) -> bool:
        """Check if one claim talks about creation and another about remaining"""
        creation_verbs = r'נערכ|נוצר|הוכנ|נכתב|הופק|חתמ'
        remaining_verbs = r'נותר|הותיר|נשאר|קיימ'

        has_creation = bool(re.search(creation_verbs, claim1 + claim2))
        has_remaining = bool(re.search(remaining_verbs, claim1 + claim2))

        # One talks about creation, other about what remained
        if has_creation and has_remaining:
            # Ensure they're in different claims
            c1_creation = bool(re.search(creation_verbs, claim1))
            c1_remaining = bool(re.search(remaining_verbs, claim1))
            c2_creation = bool(re.search(creation_verbs, claim2))
            c2_remaining = bool(re.search(remaining_verbs, claim2))

            return (c1_creation and c2_remaining) or (c1_remaining and c2_creation)

        return False

    def _has_temporal_qualification(self, claim1: str, claim2: str) -> bool:
        """Check if claims have different temporal qualifications"""
        temporal_markers = [
            (r'בתחילה|במקור|בהתחלה', r'בסוף|לבסוף|לאחר'),
            (r'לפני|קודם', r'אחרי|לאחר'),
            (r'עד\s+\d', r'מ[־-]?\d'),  # "until X" vs "from X"
        ]

        for early, late in temporal_markers:
            if (re.search(early, claim1) and re.search(late, claim2)) or \
               (re.search(late, claim1) and re.search(early, claim2)):
                return True

        return False

    def _has_scope_difference(self, claim1: str, claim2: str) -> bool:
        """Check if claims have different scopes"""
        scope_indicators = [
            (r'כל|כלל|מלא|שלם', r'חלק|רק|מקצת'),  # all vs part
            (r'סה"כ|בסך הכל', r'בנפרד|לחוד'),  # total vs separate
        ]

        for broad, narrow in scope_indicators:
            if (re.search(broad, claim1) and re.search(narrow, claim2)) or \
               (re.search(narrow, claim1) and re.search(broad, claim2)):
                return True

        return False

    def _is_same_aspect(
        self,
        claim1: str,
        claim2: str,
        contr_type: ContradictionType
    ) -> bool:
        """Check if both claims refer to the same aspect of a subject"""
        # Extract verbs/actions from both claims
        aspects1 = self._extract_aspects(claim1)
        aspects2 = self._extract_aspects(claim2)

        if not aspects1 or not aspects2:
            # If we can't identify aspects, assume same aspect
            return True

        # Check for overlap
        common_aspects = aspects1 & aspects2

        # If they share aspect categories, it's same aspect
        return len(common_aspects) > 0

    def _extract_aspects(self, text: str) -> set:
        """Extract aspect categories from text"""
        aspects = set()

        for aspect_name, markers in self.aspect_markers.items():
            for marker in markers:
                if re.search(marker, text):
                    aspects.add(aspect_name)

        return aspects

    def _is_same_quantified_object(
        self,
        claim1: str,
        claim2: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """Check if quantitative claims refer to the same object"""
        # Extract the nouns associated with the numbers
        object1 = self._extract_counted_object(claim1)
        object2 = self._extract_counted_object(claim2)

        if not object1 or not object2:
            # Can't determine, assume same
            return True

        # Check if objects are semantically similar
        return self._objects_similar(object1, object2)

    def _extract_counted_object(self, text: str) -> Optional[str]:
        """Extract the object being counted in a quantitative claim"""
        # Pattern: number + object
        patterns = [
            r'(\d+)\s+(\w+)',  # 5 wills
            r'(\w+)\s+(\d+)',  # wills 5
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                # Return the non-numeric group
                g1, g2 = match.groups()
                return g2 if g1.isdigit() else g1

        return None

    def _objects_similar(self, obj1: str, obj2: str) -> bool:
        """Check if two objects are semantically similar"""
        # Normalize
        obj1 = obj1.strip().lower()
        obj2 = obj2.strip().lower()

        # Exact match
        if obj1 == obj2:
            return True

        # Check if one contains the other
        if obj1 in obj2 or obj2 in obj1:
            return True

        # Hebrew plural handling (simple)
        if obj1 + 'ים' == obj2 or obj2 + 'ים' == obj1:
            return True
        if obj1 + 'ות' == obj2 or obj2 + 'ות' == obj1:
            return True

        return False

    def _is_same_temporal_event(
        self,
        claim1: str,
        claim2: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """Check if temporal claims refer to the same event"""
        # Extract event descriptors
        event1 = self._extract_event_descriptor(claim1)
        event2 = self._extract_event_descriptor(claim2)

        if not event1 or not event2:
            return True  # Assume same if can't determine

        # Check for overlap in key terms
        words1 = set(event1.lower().split())
        words2 = set(event2.lower().split())

        common = words1 & words2

        # Need some overlap to be same event
        return len(common) >= 1

    def _extract_event_descriptor(self, text: str) -> Optional[str]:
        """Extract the event being dated"""
        # Pattern: ה{noun} {verb} or {verb} {noun}
        patterns = [
            r'(ה\w+)\s+(?:נחתם|נחתמה|נערך|נערכה|הוגש|הוגשה)',
            r'(?:נחתם|נחתמה|נערך|נערכה|הוגש|הוגשה)\s+(\w+)',
            r'(?:יום|תאריך|מועד)\s+(?:ה)?(\w+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return None

    def _create_ambiguity_result(
        self,
        claim1: str,
        claim2: str,
        contr_type: ContradictionType,
        reconciliation: str,
        metadata: Dict[str, Any]
    ) -> CategorizationResult:
        """Create a result for narrative ambiguity"""
        # Build ambiguity explanation
        gap_description = self._generate_gap_description(claim1, claim2, contr_type)
        litigation_importance = self._generate_litigation_importance(contr_type)

        possible_reconciliations = [reconciliation]

        # Add type-specific reconciliations
        if contr_type == ContradictionType.QUANT_AMOUNT:
            possible_reconciliations.append("המספרים עשויים להתייחס למדדים שונים")
            possible_reconciliations.append("ייתכן הבדל בין ברוטו לנטו או בין סה״כ לחלק")
        elif contr_type == ContradictionType.TEMPORAL_DATE:
            possible_reconciliations.append("התאריכים עשויים להתייחס לשלבים שונים")
            possible_reconciliations.append("ייתכן מועד חתימה שונה ממועד כניסה לתוקף")

        ambiguity_explanation = AmbiguityExplanation(
            gap_description=gap_description,
            why_not_contradiction=reconciliation,
            litigation_importance=litigation_importance,
            possible_reconciliations=possible_reconciliations[:3]  # Max 3
        )

        return CategorizationResult(
            category=ContradictionCategory.NARRATIVE_AMBIGUITY,
            severity_adjustment=Severity.MEDIUM,  # Reduce severity for ambiguity
            ambiguity_explanation=ambiguity_explanation,
            badge="🟡 עמימות נרטיבית",
            label_short="עמימות",
            reasoning=reconciliation
        )

    def _generate_gap_description(
        self,
        claim1: str,
        claim2: str,
        contr_type: ContradictionType
    ) -> str:
        """Generate Hebrew description of the gap between claims"""
        type_templates = {
            ContradictionType.QUANT_AMOUNT: "קיים פער מספרי בין הטענות",
            ContradictionType.TEMPORAL_DATE: "קיים פער בתאריכים הנזכרים בטענות",
            ContradictionType.ACTOR_ATTRIBUTION: "קיימת אי-בהירות לגבי מיהו הגורם הרלוונטי",
            ContradictionType.PRESENCE_PARTICIPATION: "קיימת אי-בהירות לגבי נוכחות או השתתפות",
            ContradictionType.DOCUMENT_EXISTENCE: "קיימת אי-בהירות לגבי קיום המסמך",
            ContradictionType.IDENTITY_BASIC: "קיימת אי-בהירות בפרטי זיהוי",
        }

        return type_templates.get(contr_type, "קיים פער בין שתי הטענות")

    def _generate_litigation_importance(self, contr_type: ContradictionType) -> str:
        """Generate explanation of why the ambiguity is litigatively important"""
        type_importance = {
            ContradictionType.QUANT_AMOUNT:
                "גם אם אין סתירה מוחלטת, הפער המספרי עשוי להעיד על חוסר דיוק או חוסר עקביות שניתן לחקור בחקירה נגדית",
            ContradictionType.TEMPORAL_DATE:
                "גם אם התאריכים מתייחסים לאירועים שונים, חוסר העקביות בציר הזמן עשוי לפגוע באמינות העדות",
            ContradictionType.ACTOR_ATTRIBUTION:
                "אי-בהירות לגבי מיהו הגורם הפועל עשויה להעיד על חוסר ידיעה או ניסיון להסתיר",
            ContradictionType.PRESENCE_PARTICIPATION:
                "אי-עקביות בנוגע לנוכחות עשויה להעיד על בעיית אמינות או זיכרון",
            ContradictionType.DOCUMENT_EXISTENCE:
                "אי-בהירות לגבי קיום מסמך עשויה להיות קריטית להוכחת טענות",
            ContradictionType.IDENTITY_BASIC:
                "אי-עקביות בפרטי זיהוי עשויה להטיל ספק בידיעת העד את העובדות",
        }

        return type_importance.get(
            contr_type,
            "אי-עקביות זו עשויה להעיד על בעיית אמינות או דיוק שיש לחקור"
        )


# =============================================================================
# Cross-exam adaptation for categories
# =============================================================================

def adapt_cross_exam_for_category(
    category: ContradictionCategory,
    original_questions: List[str],
    ambiguity_explanation: Optional[AmbiguityExplanation]
) -> List[Dict[str, str]]:
    """
    Adapt cross-examination questions based on contradiction category.

    For HARD_CONTRADICTION: Direct confrontation
    For NARRATIVE_AMBIGUITY: Clarification + credibility questions

    Args:
        category: The contradiction category
        original_questions: Original cross-exam questions
        ambiguity_explanation: Explanation for narrative ambiguity

    Returns:
        List of adapted questions with purpose
    """
    if category == ContradictionCategory.HARD_CONTRADICTION:
        # Direct confrontation is appropriate
        return [
            {"question": q, "purpose": "עימות ישיר על הסתירה"}
            for q in original_questions
        ]

    elif category == ContradictionCategory.NARRATIVE_AMBIGUITY:
        adapted = []

        # Add clarification questions
        adapted.append({
            "question": "האם תוכל להבהיר את הפער בין הנתונים?",
            "purpose": "שאלת הבהרה - לא עימות"
        })

        if ambiguity_explanation:
            # Add question about possible reconciliation
            adapted.append({
                "question": f"האם ייתכן ש{ambiguity_explanation.possible_reconciliations[0] if ambiguity_explanation.possible_reconciliations else 'יש הסבר לפער'}?",
                "purpose": "בדיקת הסבר אפשרי"
            })

        # Add credibility question
        adapted.append({
            "question": "למה לא ציינת את הפרט הזה קודם?",
            "purpose": "פגיעה באמינות דרך חוסר עקביות"
        })

        # Filter out any confrontational questions
        for q in original_questions:
            # Don't include "both cannot be true" type questions
            if "אינן יכולות להיות" not in q and "סתירה" not in q.lower():
                adapted.append({
                    "question": q,
                    "purpose": "שאלת המשך"
                })

        return adapted[:5]  # Max 5 questions

    elif category == ContradictionCategory.LOGICAL_INCONSISTENCY:
        return [
            {"question": q, "purpose": "בירור אי-עקביות לוגית"}
            for q in original_questions
        ]

    else:  # RHETORICAL_SHIFT
        return [
            {"question": "למה הניסוח השתנה?", "purpose": "בדיקת שינוי רטורי"},
            {"question": "האם המשמעות שונה?", "purpose": "בירור משמעות"}
        ]


# =============================================================================
# Singleton
# =============================================================================

_categorizer: Optional[ContradictionCategorizer] = None


def get_categorizer() -> ContradictionCategorizer:
    """Get singleton categorizer instance"""
    global _categorizer
    if _categorizer is None:
        _categorizer = ContradictionCategorizer()
    return _categorizer


def categorize_contradiction(
    claim1_text: str,
    claim2_text: str,
    contradiction_type: ContradictionType,
    normalized1: Optional[str] = None,
    normalized2: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> CategorizationResult:
    """
    Convenience function to categorize a contradiction.

    Returns CategorizationResult with category, explanation, and UI helpers.
    """
    return get_categorizer().categorize(
        claim1_text, claim2_text, contradiction_type,
        normalized1, normalized2, metadata
    )
