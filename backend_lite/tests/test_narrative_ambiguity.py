"""
Tests for Narrative Ambiguity Classification
============================================

Acceptance criterion from user:
- "5 צוואות נערכו" vs "6 צוואות הותירו" should be classified as NARRATIVE_AMBIGUITY
  because "נערכו" (were created) vs "הותירו" (left/remained) are different aspects.
  Some wills may have been revoked, combined, or replaced.

Tests cover:
1. Created vs remaining pattern (5 vs 6 wills)
2. Same aspect same object = hard contradiction
3. Different temporal qualifications = narrative ambiguity
4. Scope differences = narrative ambiguity
"""

import pytest
from backend_lite.categorizer import (
    ContradictionCategorizer,
    categorize_contradiction,
    get_categorizer,
    CategorizationResult
)
from backend_lite.schemas import (
    ContradictionCategory,
    ContradictionType,
    Severity
)


class TestWillsAcceptanceCriterion:
    """Test the '5 vs 6 wills' acceptance criterion"""

    def test_created_vs_remaining_is_narrative_ambiguity(self):
        """
        ACCEPTANCE TEST: 5 wills created vs 6 wills remaining = NARRATIVE_AMBIGUITY

        Rationale: "נערכו" (were created/drafted) refers to how many were made.
        "הותירו" (left/remained) refers to how many exist now.
        Some wills could have been revoked or replaced, so the numbers
        can differ without contradiction.
        """
        claim1 = "במהלך חייו נערכו 5 צוואות על ידי המנוח"
        claim2 = "המנוח הותיר אחריו 6 צוואות"

        result = categorize_contradiction(
            claim1_text=claim1,
            claim2_text=claim2,
            contradiction_type=ContradictionType.QUANT_AMOUNT,
            normalized1="5",
            normalized2="6"
        )

        assert result.category == ContradictionCategory.NARRATIVE_AMBIGUITY, (
            f"Expected NARRATIVE_AMBIGUITY but got {result.category}. "
            f"'נערכו' (created) vs 'הותירו' (remaining) are different aspects."
        )
        assert result.ambiguity_explanation is not None
        assert result.badge == "🟡 עמימות נרטיבית"

    def test_explanation_includes_reconciliation(self):
        """Test that the ambiguity explanation explains why it's not a contradiction"""
        claim1 = "במהלך חייו נערכו 5 צוואות על ידי המנוח"
        claim2 = "המנוח הותיר אחריו 6 צוואות"

        result = categorize_contradiction(
            claim1_text=claim1,
            claim2_text=claim2,
            contradiction_type=ContradictionType.QUANT_AMOUNT,
            normalized1="5",
            normalized2="6"
        )

        assert result.ambiguity_explanation is not None
        # Should explain why this is not a contradiction
        assert result.ambiguity_explanation.why_not_contradiction


class TestSameAspectHardContradiction:
    """Test cases that SHOULD be classified as hard contradictions"""

    def test_same_verb_same_object_is_hard_contradiction(self):
        """
        When both claims use the same verb and describe the same object,
        different numbers = HARD_CONTRADICTION.
        """
        claim1 = "נחתמו 5 הסכמים"
        claim2 = "נחתמו 3 הסכמים"

        result = categorize_contradiction(
            claim1_text=claim1,
            claim2_text=claim2,
            contradiction_type=ContradictionType.QUANT_AMOUNT,
            normalized1="5",
            normalized2="3"
        )

        # Same verb (נחתמו), same object (הסכמים), same aspect = hard contradiction
        assert result.category == ContradictionCategory.HARD_CONTRADICTION
        assert result.badge == "🔴 סתירה מוכרחת"

    def test_explicit_total_amounts_hard_contradiction(self):
        """
        Explicit total amounts on the same subject = HARD_CONTRADICTION
        """
        claim1 = "סה\"כ שולם 100,000 ש\"ח"
        claim2 = "סה\"כ שולם 150,000 ש\"ח"

        result = categorize_contradiction(
            claim1_text=claim1,
            claim2_text=claim2,
            contradiction_type=ContradictionType.QUANT_AMOUNT,
            normalized1="100000",
            normalized2="150000"
        )

        # Same explicit total = hard contradiction
        assert result.category == ContradictionCategory.HARD_CONTRADICTION


class TestTemporalQualification:
    """Test temporal qualification patterns"""

    def test_before_vs_after_is_narrative_ambiguity(self):
        """
        'לפני' (before) vs 'אחרי' (after) = different timeframes = NARRATIVE_AMBIGUITY
        """
        claim1 = "לפני הפגישה היו 3 מסמכים"
        claim2 = "אחרי הפגישה היו 5 מסמכים"

        result = categorize_contradiction(
            claim1_text=claim1,
            claim2_text=claim2,
            contradiction_type=ContradictionType.QUANT_AMOUNT,
            normalized1="3",
            normalized2="5"
        )

        assert result.category == ContradictionCategory.NARRATIVE_AMBIGUITY

    def test_originally_vs_finally_is_narrative_ambiguity(self):
        """
        'במקור' (originally) vs 'בסוף' (in the end) = NARRATIVE_AMBIGUITY
        """
        claim1 = "במקור הוסכם על 50,000 ש\"ח"
        claim2 = "בסוף שולם 70,000 ש\"ח"

        result = categorize_contradiction(
            claim1_text=claim1,
            claim2_text=claim2,
            contradiction_type=ContradictionType.QUANT_AMOUNT,
            normalized1="50000",
            normalized2="70000"
        )

        assert result.category == ContradictionCategory.NARRATIVE_AMBIGUITY


class TestScopeDifference:
    """Test scope difference patterns"""

    def test_all_vs_part_is_narrative_ambiguity(self):
        """
        'כל' (all) vs 'חלק' (part) = different scopes = NARRATIVE_AMBIGUITY
        """
        claim1 = "כל העובדים קיבלו 10,000 ש\"ח"
        claim2 = "חלק מהעובדים קיבלו 5,000 ש\"ח"

        result = categorize_contradiction(
            claim1_text=claim1,
            claim2_text=claim2,
            contradiction_type=ContradictionType.QUANT_AMOUNT,
            normalized1="10000",
            normalized2="5000"
        )

        assert result.category == ContradictionCategory.NARRATIVE_AMBIGUITY

    def test_total_vs_separate_is_narrative_ambiguity(self):
        """
        'סה"כ' (total) vs 'בנפרד' (separately) = NARRATIVE_AMBIGUITY
        """
        claim1 = "סה\"כ הוציא 100,000 ש\"ח"
        claim2 = "בנפרד הוציא 30,000 ש\"ח על כל פריט"

        result = categorize_contradiction(
            claim1_text=claim1,
            claim2_text=claim2,
            contradiction_type=ContradictionType.QUANT_AMOUNT,
            normalized1="100000",
            normalized2="30000"
        )

        assert result.category == ContradictionCategory.NARRATIVE_AMBIGUITY


class TestCrossCategoryVerification:
    """Verify category-based output fields"""

    def test_hard_contradiction_has_correct_ui_fields(self):
        """Hard contradictions should have correct badge and label"""
        # Use identical verb and structure for clear hard contradiction
        claim1 = "ההסכם נחתם ביום 15.3.2020"
        claim2 = "ההסכם נחתם ביום 20.5.2021"

        result = categorize_contradiction(
            claim1_text=claim1,
            claim2_text=claim2,
            contradiction_type=ContradictionType.TEMPORAL_DATE,
            normalized1="2020-03-15",
            normalized2="2021-05-20"
        )

        # Same event, same verb (נחתם), explicit dates = hard contradiction
        assert result.category == ContradictionCategory.HARD_CONTRADICTION
        assert result.badge == "🔴 סתירה מוכרחת"
        assert result.label_short == "סתירה"

    def test_narrative_ambiguity_has_correct_ui_fields(self):
        """Narrative ambiguity should have correct badge and label"""
        claim1 = "במהלך חייו נערכו 5 צוואות"
        claim2 = "הותירו 6 צוואות"

        result = categorize_contradiction(
            claim1_text=claim1,
            claim2_text=claim2,
            contradiction_type=ContradictionType.QUANT_AMOUNT,
            normalized1="5",
            normalized2="6"
        )

        assert result.category == ContradictionCategory.NARRATIVE_AMBIGUITY
        assert result.badge == "🟡 עמימות נרטיבית"
        assert result.label_short == "עמימות"

    def test_narrative_ambiguity_severity_adjusted(self):
        """Narrative ambiguity should have reduced severity"""
        claim1 = "במקור היו 3 מסמכים"
        claim2 = "בסוף היו 5 מסמכים"

        result = categorize_contradiction(
            claim1_text=claim1,
            claim2_text=claim2,
            contradiction_type=ContradictionType.QUANT_AMOUNT,
            normalized1="3",
            normalized2="5"
        )

        # Ambiguity should have MEDIUM severity (adjusted down)
        assert result.severity_adjustment == Severity.MEDIUM


class TestIntegrationWithDetector:
    """Test integration with the full detector flow"""

    def test_detector_categorizes_contradictions(self):
        """Test that detector applies categorization"""
        from backend_lite.detector import RuleBasedDetector
        from backend_lite.extractor import Claim

        detector = RuleBasedDetector()

        # Use claims with more shared words so detector finds them related
        # The detector needs word overlap to consider claims related
        claims = [
            Claim(
                id="claim_1",
                text="החוזה נחתם ביום 15.3.2020 בתל אביב",
                source="תצהיר א"
            ),
            Claim(
                id="claim_2",
                text="החוזה נחתם ביום 20.5.2021 בתל אביב",
                source="תצהיר ב"
            ),
        ]

        result = detector.detect(claims)

        # Should find temporal contradiction
        assert len(result.contradictions) >= 1

        # Find the temporal contradiction
        temp_contrs = [
            c for c in result.contradictions
            if c.type == ContradictionType.TEMPORAL_DATE
        ]

        assert len(temp_contrs) >= 1, "Should find temporal contradiction"
        contr = temp_contrs[0]
        # Same verb (נחתם), same object (החוזה) = hard contradiction
        assert contr.category == ContradictionCategory.HARD_CONTRADICTION
        assert contr.category_badge == "🔴 סתירה מוכרחת"
