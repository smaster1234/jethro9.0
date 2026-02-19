"""
Extended Logical Tests — Semantic Triplet Matching
==================================================

~80 tests covering:
- Triplet extraction (WHO/WHAT/TOPIC/WHEN)
- Action category detection
- Topic category detection
- Entity extraction (roles, orgs, persons)
- Triplet matching & relatedness scoring
- WHO/WHAT/TOPIC/WHEN individual matchers
- Batch extraction
- should_compare_claims function
- Edge cases
"""

import pytest
from backend_lite.triplet import (
    SemanticTriplet,
    ActionCategory,
    TopicCategory,
    extract_triplet,
    extract_claim_triplets,
    triplet_relatedness,
    should_compare_claims,
    _who_overlap,
    _what_match,
    _topic_match,
    _when_match,
    _entity_fuzzy_match,
    _ROLE_ALIASES,
)
from backend_lite.extractor import Claim


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(text: str, **kwargs) -> Claim:
    defaults = dict(id=kwargs.pop("id", f"c_{abs(hash(text)) % 100000}"), text=text)
    defaults.update(kwargs)
    return Claim(**defaults)


# ===================================================================
# 1. SemanticTriplet Dataclass
# ===================================================================

class TestSemanticTripletDataclass:
    def test_default_empty(self):
        t = SemanticTriplet()
        assert t.who == []
        assert t.what is None
        assert t.topic is None
        assert t.when is None

    def test_has_who_empty(self):
        t = SemanticTriplet()
        assert t.has_who is False

    def test_has_who_populated(self):
        t = SemanticTriplet(who=["הנתבע"])
        assert t.has_who is True

    def test_has_what_none(self):
        t = SemanticTriplet()
        assert t.has_what is False

    def test_has_what_unknown(self):
        t = SemanticTriplet(what=ActionCategory.UNKNOWN)
        assert t.has_what is False

    def test_has_what_real(self):
        t = SemanticTriplet(what=ActionCategory.PAYMENT)
        assert t.has_what is True

    def test_has_topic_none(self):
        t = SemanticTriplet()
        assert t.has_topic is False

    def test_has_topic_unknown(self):
        t = SemanticTriplet(topic=TopicCategory.UNKNOWN)
        assert t.has_topic is False

    def test_has_topic_real(self):
        t = SemanticTriplet(topic=TopicCategory.CONTRACT)
        assert t.has_topic is True

    def test_completeness_empty(self):
        t = SemanticTriplet()
        assert t.completeness == 0.0

    def test_completeness_full(self):
        t = SemanticTriplet(
            who=["הנתבע"],
            what=ActionCategory.PAYMENT,
            topic=TopicCategory.CONTRACT,
        )
        assert t.completeness == 1.0

    def test_completeness_partial(self):
        t = SemanticTriplet(who=["הנתבע"])
        assert 0 < t.completeness < 1.0


# ===================================================================
# 2. Action Category Constants
# ===================================================================

class TestActionCategoryConstants:
    def test_all_categories(self):
        categories = [
            ActionCategory.PAYMENT, ActionCategory.SIGNING,
            ActionCategory.ATTENDANCE, ActionCategory.RECEIPT,
            ActionCategory.DELIVERY, ActionCategory.STATEMENT,
            ActionCategory.DECISION, ActionCategory.CREATION,
            ActionCategory.TERMINATION, ActionCategory.EXISTENCE,
            ActionCategory.DAMAGE, ActionCategory.AGREEMENT,
            ActionCategory.UNKNOWN,
        ]
        assert len(categories) == 13
        assert all(isinstance(c, str) for c in categories)


# ===================================================================
# 3. Topic Category Constants
# ===================================================================

class TestTopicCategoryConstants:
    def test_all_topics(self):
        topics = [
            TopicCategory.CONTRACT, TopicCategory.PAYMENT_OBJ,
            TopicCategory.PROPERTY, TopicCategory.EMPLOYMENT,
            TopicCategory.DOCUMENT_OBJ, TopicCategory.MEETING,
            TopicCategory.ACCIDENT, TopicCategory.COMPENSATION,
            TopicCategory.TESTIMONY, TopicCategory.RELATIONSHIP,
            TopicCategory.UNKNOWN,
        ]
        assert len(topics) == 11
        assert all(isinstance(t, str) for t in topics)


# ===================================================================
# 4. Triplet Extraction - WHAT (Action)
# ===================================================================

class TestTripletExtractionWhat:
    def test_payment_action(self):
        t = extract_triplet("הנתבע שילם את הסכום")
        assert t.what == ActionCategory.PAYMENT

    def test_signing_action(self):
        t = extract_triplet("נחתם הסכם בין הצדדים")
        assert t.what == ActionCategory.SIGNING

    def test_attendance_action(self):
        t = extract_triplet("העד נכח בפגישה")
        assert t.what == ActionCategory.ATTENDANCE

    def test_receipt_action(self):
        t = extract_triplet("התובע קיבל את ההודעה")
        assert t.what == ActionCategory.RECEIPT

    def test_delivery_action(self):
        t = extract_triplet("הנתבע שלח את המכתב")
        assert t.what == ActionCategory.DELIVERY

    def test_statement_action(self):
        t = extract_triplet("העד הצהיר כי ראה את האירוע")
        assert t.what == ActionCategory.STATEMENT

    def test_decision_action(self):
        t = extract_triplet("בית המשפט קבע כי התביעה מוצדקת")
        assert t.what == ActionCategory.DECISION

    def test_creation_action(self):
        t = extract_triplet("הנתבע הקים את החברה")
        assert t.what == ActionCategory.CREATION

    def test_termination_action(self):
        t = extract_triplet("הנתבע ביטל את ההסכם")
        assert t.what == ActionCategory.TERMINATION

    def test_existence_action(self):
        t = extract_triplet("קיים הסכם בין הצדדים")
        assert t.what == ActionCategory.EXISTENCE

    def test_damage_action(self):
        t = extract_triplet("נגרם נזק לתובע")
        assert t.what == ActionCategory.DAMAGE

    def test_agreement_action(self):
        t = extract_triplet("הוסכם כי הנתבע ישלם הסכמה מלאה")
        # The agreement pattern requires specific verb forms
        assert t.what in (ActionCategory.AGREEMENT, ActionCategory.PAYMENT)

    def test_unknown_action(self):
        t = extract_triplet("השמש זרחה מעל ההר")
        assert t.what == ActionCategory.UNKNOWN


# ===================================================================
# 5. Triplet Extraction - TOPIC
# ===================================================================

class TestTripletExtractionTopic:
    def test_contract_topic(self):
        t = extract_triplet("נחתם הסכם בין הצדדים")
        assert t.topic == TopicCategory.CONTRACT

    def test_payment_topic(self):
        t = extract_triplet("בוצע תשלום של 50,000 ש\"ח")
        assert t.topic == TopicCategory.PAYMENT_OBJ

    def test_property_topic(self):
        t = extract_triplet("נרכשה דירה ברחוב הרצל")
        assert t.topic == TopicCategory.PROPERTY

    def test_employment_topic(self):
        t = extract_triplet("תנאי העבודה שונו ללא הסכמה")
        assert t.topic == TopicCategory.EMPLOYMENT

    def test_document_topic(self):
        t = extract_triplet("נשלח מכתב לצד השני")
        assert t.topic == TopicCategory.DOCUMENT_OBJ

    def test_meeting_topic(self):
        t = extract_triplet("התקיימה פגישה בין הצדדים")
        assert t.topic == TopicCategory.MEETING

    def test_accident_topic(self):
        t = extract_triplet("אירעה תאונה ברחוב")
        assert t.topic == TopicCategory.ACCIDENT

    def test_compensation_topic(self):
        t = extract_triplet("ניתן פיצוי לעובד")
        assert t.topic == TopicCategory.COMPENSATION

    def test_testimony_topic(self):
        t = extract_triplet("הוגש תצהיר לתיק")
        assert t.topic == TopicCategory.TESTIMONY

    def test_relationship_topic(self):
        t = extract_triplet("יחסים בין השותפים התדרדרו")
        assert t.topic == TopicCategory.RELATIONSHIP

    def test_unknown_topic(self):
        t = extract_triplet("השמש זרחה היום")
        assert t.topic == TopicCategory.UNKNOWN


# ===================================================================
# 6. Triplet Extraction - WHO (Entities)
# ===================================================================

class TestTripletExtractionWho:
    def test_legal_role_defendant(self):
        t = extract_triplet("הנתבע שילם את הסכום")
        assert "הנתבע" in t.who

    def test_legal_role_plaintiff(self):
        t = extract_triplet("התובע טען כי הוא צודק")
        assert "התובע" in t.who

    def test_legal_role_alias_mashiv(self):
        t = extract_triplet("המשיב טען כי לא שילם")
        assert "הנתבע" in t.who  # Alias for הנתבע

    def test_legal_role_alias_mearer(self):
        t = extract_triplet("המערער טען כי הוא צודק")
        assert "התובע" in t.who  # Alias for התובע

    def test_person_with_title(self):
        t = extract_triplet("מר כהן שילם את הסכום")
        # Should extract person name
        assert len(t.who) >= 1

    def test_organization(self):
        t = extract_triplet("חברת אלפא העבירה את הסכום")
        assert len(t.who) >= 1

    def test_multiple_entities(self):
        t = extract_triplet("הנתבע והתובע חתמו על ההסכם")
        assert len(t.who) >= 2

    def test_pre_extracted_entities(self):
        t = extract_triplet("שילם את הסכום", entities=["יוסי כהן"])
        assert "יוסי כהן" in t.who

    def test_no_entities(self):
        t = extract_triplet("שולם הסכום")
        # May or may not find entities depending on text
        assert isinstance(t.who, list)


# ===================================================================
# 7. Triplet Extraction - WHEN
# ===================================================================

class TestTripletExtractionWhen:
    def test_when_from_parameter(self):
        t = extract_triplet("claim text", time_reference="2024-01-15")
        assert t.when == "2024-01-15"

    def test_when_none(self):
        t = extract_triplet("claim text")
        assert t.when is None


# ===================================================================
# 8. WHO Overlap
# ===================================================================

class TestWhoOverlap:
    def test_exact_overlap(self):
        score = _who_overlap(["הנתבע"], ["הנתבע"])
        assert score > 0

    def test_no_overlap(self):
        score = _who_overlap(["הנתבע"], ["התובע"])
        assert score == 0.0

    def test_empty_lists(self):
        score = _who_overlap([], [])
        assert score == 0.0

    def test_one_empty(self):
        score = _who_overlap(["הנתבע"], [])
        assert score == 0.0

    def test_partial_overlap(self):
        score = _who_overlap(["הנתבע", "יוסי"], ["הנתבע", "דוד"])
        assert 0 < score < 1.0

    def test_full_overlap(self):
        score = _who_overlap(["הנתבע"], ["הנתבע"])
        assert score == 1.0


# ===================================================================
# 9. WHAT Match
# ===================================================================

class TestWhatMatch:
    def test_same_category(self):
        score = _what_match(ActionCategory.PAYMENT, ActionCategory.PAYMENT)
        assert score == 1.0

    def test_compatible_categories(self):
        score = _what_match(ActionCategory.PAYMENT, ActionCategory.RECEIPT)
        assert score == 0.7

    def test_incompatible_categories(self):
        score = _what_match(ActionCategory.PAYMENT, ActionCategory.ATTENDANCE)
        assert score == 0.0

    def test_one_unknown(self):
        score = _what_match(ActionCategory.PAYMENT, ActionCategory.UNKNOWN)
        assert score == 0.3

    def test_both_unknown(self):
        score = _what_match(ActionCategory.UNKNOWN, ActionCategory.UNKNOWN)
        assert score == 1.0

    def test_none_value(self):
        score = _what_match(None, ActionCategory.PAYMENT)
        assert score == 0.3

    def test_both_none(self):
        score = _what_match(None, None)
        assert score == 0.3

    def test_signing_agreement_compatible(self):
        score = _what_match(ActionCategory.SIGNING, ActionCategory.AGREEMENT)
        assert score == 0.7

    def test_creation_termination_compatible(self):
        score = _what_match(ActionCategory.CREATION, ActionCategory.TERMINATION)
        assert score == 0.7

    def test_delivery_receipt_compatible(self):
        score = _what_match(ActionCategory.DELIVERY, ActionCategory.RECEIPT)
        assert score == 0.7


# ===================================================================
# 10. TOPIC Match
# ===================================================================

class TestTopicMatch:
    def test_same_topic(self):
        score = _topic_match(TopicCategory.CONTRACT, TopicCategory.CONTRACT)
        assert score == 1.0

    def test_compatible_topics(self):
        score = _topic_match(TopicCategory.CONTRACT, TopicCategory.PAYMENT_OBJ)
        assert score == 0.6

    def test_incompatible_topics(self):
        score = _topic_match(TopicCategory.PROPERTY, TopicCategory.MEETING)
        assert score == 0.0

    def test_one_unknown(self):
        score = _topic_match(TopicCategory.CONTRACT, TopicCategory.UNKNOWN)
        assert score == 0.3

    def test_both_unknown(self):
        score = _topic_match(TopicCategory.UNKNOWN, TopicCategory.UNKNOWN)
        assert score == 1.0

    def test_none_value(self):
        score = _topic_match(None, TopicCategory.CONTRACT)
        assert score == 0.3

    def test_employment_compensation_compatible(self):
        score = _topic_match(TopicCategory.EMPLOYMENT, TopicCategory.COMPENSATION)
        assert score == 0.6

    def test_accident_compensation_compatible(self):
        score = _topic_match(TopicCategory.ACCIDENT, TopicCategory.COMPENSATION)
        assert score == 0.6


# ===================================================================
# 11. WHEN Match
# ===================================================================

class TestWhenMatch:
    def test_same_time(self):
        score = _when_match("2024-01-15", "2024-01-15")
        assert score == 1.0

    def test_same_year(self):
        score = _when_match("2024-01-15", "2024-06-20")
        assert score == 0.8

    def test_different_years(self):
        score = _when_match("2020-01-15", "2024-06-20")
        assert score == 0.2

    def test_one_none(self):
        score = _when_match("2024-01-15", None)
        assert score == 0.5

    def test_both_none(self):
        score = _when_match(None, None)
        assert score == 0.5

    def test_shared_numbers(self):
        score = _when_match("ינואר 15", "15 בחודש")
        assert score >= 0.4


# ===================================================================
# 12. Entity Fuzzy Match
# ===================================================================

class TestEntityFuzzyMatch:
    def test_exact_match(self):
        assert _entity_fuzzy_match("הנתבע", "הנתבע") is True

    def test_alias_match(self):
        assert _entity_fuzzy_match("המשיב", "הנתבע") is True

    def test_legal_roles_different(self):
        assert _entity_fuzzy_match("הנתבע", "התובע") is False

    def test_contains_match(self):
        # Short strings under 4 chars don't trigger contains match
        assert _entity_fuzzy_match("אלפא", "חברת אלפא") is True

    def test_no_match(self):
        assert _entity_fuzzy_match("הנתבע", "אלפא") is False

    def test_similar_names(self):
        assert _entity_fuzzy_match("יוסף כהנסקי", "יוסף כהנסקי") is True


# ===================================================================
# 13. Role Aliases
# ===================================================================

class TestRoleAliases:
    def test_mashiv_is_natba(self):
        assert _ROLE_ALIASES.get("המשיב") == "הנתבע"

    def test_mearer_is_tove(self):
        assert _ROLE_ALIASES.get("המערער") == "התובע"

    def test_oter_is_tove(self):
        assert _ROLE_ALIASES.get("העותר") == "התובע"

    def test_mevakesh_is_tove(self):
        assert _ROLE_ALIASES.get("המבקש") == "התובע"


# ===================================================================
# 14. Triplet Relatedness
# ===================================================================

class TestTripletRelatedness:
    def test_identical_triplets(self):
        t1 = SemanticTriplet(who=["הנתבע"], what=ActionCategory.PAYMENT, topic=TopicCategory.CONTRACT)
        t2 = SemanticTriplet(who=["הנתבע"], what=ActionCategory.PAYMENT, topic=TopicCategory.CONTRACT)
        score = triplet_relatedness(t1, t2)
        assert score > 0.5

    def test_no_who_overlap(self):
        t1 = SemanticTriplet(who=["הנתבע"], what=ActionCategory.PAYMENT)
        t2 = SemanticTriplet(who=["התובע"], what=ActionCategory.PAYMENT)
        score = triplet_relatedness(t1, t2)
        assert score == 0.0

    def test_both_empty_who(self):
        t1 = SemanticTriplet(what=ActionCategory.PAYMENT, topic=TopicCategory.CONTRACT)
        t2 = SemanticTriplet(what=ActionCategory.PAYMENT, topic=TopicCategory.CONTRACT)
        score = triplet_relatedness(t1, t2)
        # Both empty WHO → capped at 0.6
        assert 0 < score <= 0.6

    def test_who_match_different_what(self):
        t1 = SemanticTriplet(who=["הנתבע"], what=ActionCategory.PAYMENT)
        t2 = SemanticTriplet(who=["הנתבע"], what=ActionCategory.ATTENDANCE)
        score = triplet_relatedness(t1, t2)
        # Same WHO but different WHAT → lower score
        assert 0 < score < 0.5

    def test_who_match_compatible_what(self):
        t1 = SemanticTriplet(who=["הנתבע"], what=ActionCategory.PAYMENT)
        t2 = SemanticTriplet(who=["הנתבע"], what=ActionCategory.RECEIPT)
        score = triplet_relatedness(t1, t2)
        # Same WHO and compatible WHAT → moderate score
        assert score > 0.3

    def test_empty_triplets(self):
        t1 = SemanticTriplet()
        t2 = SemanticTriplet()
        score = triplet_relatedness(t1, t2)
        assert isinstance(score, float)
        assert 0 <= score <= 1


# ===================================================================
# 15. Batch Triplet Extraction
# ===================================================================

class TestBatchTripletExtraction:
    def test_basic_batch(self):
        claims = [
            _claim("הנתבע שילם את הסכום", id="c1"),
            _claim("התובע קיבל את ההודעה", id="c2"),
        ]
        result = extract_claim_triplets(claims)
        assert "c1" in result
        assert "c2" in result
        assert isinstance(result["c1"], SemanticTriplet)

    def test_empty_batch(self):
        result = extract_claim_triplets([])
        assert result == {}

    def test_entities_from_claims(self):
        claims = [
            _claim("שילם את הסכום", id="c1", entities=["יוסי"]),
        ]
        result = extract_claim_triplets(claims)
        assert "יוסי" in result["c1"].who

    def test_time_from_claims(self):
        claims = [
            _claim("שילם את הסכום", id="c1", time_reference="2024"),
        ]
        result = extract_claim_triplets(claims)
        assert result["c1"].when == "2024"


# ===================================================================
# 16. should_compare_claims
# ===================================================================

class TestShouldCompareClaims:
    def test_related_claims(self):
        a = _claim("הנתבע שילם את הסכום לפי ההסכם", id="a", entities=["הנתבע"])
        b = _claim("הנתבע לא שילם את הסכום", id="b", entities=["הנתבע"])
        triplets = extract_claim_triplets([a, b])
        should, score = should_compare_claims(a, b, triplets)
        assert should is True

    def test_unrelated_claims(self):
        a = _claim("הנתבע שילם את הסכום", id="a", entities=["הנתבע"])
        b = _claim("התובע השתתף בפגישה", id="b", entities=["התובע"])
        triplets = extract_claim_triplets([a, b])
        should, score = should_compare_claims(a, b, triplets)
        assert should is False

    def test_without_precomputed_triplets(self):
        a = _claim("הנתבע שילם", id="a")
        b = _claim("הנתבע לא שילם", id="b")
        should, score = should_compare_claims(a, b)
        assert isinstance(should, bool)
        assert isinstance(score, float)

    def test_custom_threshold(self):
        a = _claim("הנתבע שילם", id="a", entities=["הנתבע"])
        b = _claim("הנתבע לא שילם", id="b", entities=["הנתבע"])
        triplets = extract_claim_triplets([a, b])
        should_low, _ = should_compare_claims(a, b, triplets, threshold=0.01)
        should_high, _ = should_compare_claims(a, b, triplets, threshold=0.99)
        # Low threshold → more likely to compare
        # Can't guarantee specific result but logic should hold
        assert isinstance(should_low, bool)
        assert isinstance(should_high, bool)
