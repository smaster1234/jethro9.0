"""
Extended Tests — Expert Knowledge Base for Cross-Examination
=============================================================

~60 tests covering:
- WitnessType, QuestionStrategy, ImpeachmentType enums
- YoungerCommandment dataclass + get_commandment()
- ExpertTechnique dataclass + get_technique()
- WitnessProfile dataclass + get_witness_profile()
- Question templates retrieval
- Psychological insights
- suggest_strategy() logic
- generate_enhanced_question() logic
- analyze_witness_response() logic
- Singleton get_knowledge_base()
"""

import pytest

from backend_lite.expert_knowledge import (
    WitnessType,
    QuestionStrategy,
    ImpeachmentType,
    YoungerCommandment,
    ExpertTechnique,
    PsychologicalInsight,
    WitnessProfile,
    ExpertKnowledgeBase,
    get_knowledge_base,
)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def kb():
    """Fresh ExpertKnowledgeBase instance for each test."""
    return ExpertKnowledgeBase()


# ===========================================================================
# 1. TestWitnessTypeEnum
# ===========================================================================

class TestWitnessTypeEnum:
    """Tests for the WitnessType enum."""

    def test_all_seven_members_exist(self):
        members = list(WitnessType)
        assert len(members) == 7

    def test_member_values(self):
        assert WitnessType.EVASIVE.value == "evasive"
        assert WitnessType.HOSTILE.value == "hostile"
        assert WitnessType.VERBOSE.value == "verbose"
        assert WitnessType.EXPERT.value == "expert"
        assert WitnessType.EMOTIONAL.value == "emotional"
        assert WitnessType.COOPERATIVE.value == "cooperative"
        assert WitnessType.UNCERTAIN.value == "uncertain"

    def test_lookup_by_value(self):
        assert WitnessType("evasive") is WitnessType.EVASIVE
        assert WitnessType("hostile") is WitnessType.HOSTILE


# ===========================================================================
# 2. TestQuestionStrategyEnum
# ===========================================================================

class TestQuestionStrategyEnum:
    """Tests for the QuestionStrategy enum."""

    def test_all_six_members_exist(self):
        members = list(QuestionStrategy)
        assert len(members) == 6

    def test_commit_credit_confront_value_is_3c(self):
        assert QuestionStrategy.COMMIT_CREDIT_CONFRONT.value == "3c"

    def test_standard_values(self):
        assert QuestionStrategy.LADDER.value == "ladder"
        assert QuestionStrategy.LOOP.value == "loop"
        assert QuestionStrategy.SURPRISE.value == "surprise"
        assert QuestionStrategy.DECONSTRUCTION.value == "deconstruction"
        assert QuestionStrategy.COGNITIVE_LOAD.value == "cognitive_load"


# ===========================================================================
# 3. TestImpeachmentTypeEnum
# ===========================================================================

class TestImpeachmentTypeEnum:
    """Tests for the ImpeachmentType enum."""

    def test_all_seven_members_exist(self):
        members = list(ImpeachmentType)
        assert len(members) == 7

    def test_values(self):
        assert ImpeachmentType.BIAS.value == "bias"
        assert ImpeachmentType.PRIOR_INCONSISTENT.value == "prior"
        assert ImpeachmentType.OTHER_WITNESSES.value == "witnesses"
        assert ImpeachmentType.DOCUMENTS.value == "documents"
        assert ImpeachmentType.LACK_OF_CAPACITY.value == "capacity"
        assert ImpeachmentType.CRIMINAL_RECORD.value == "criminal"
        assert ImpeachmentType.BAD_REPUTATION.value == "reputation"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ImpeachmentType("nonexistent_value")


# ===========================================================================
# 4. TestYoungerCommandments
# ===========================================================================

class TestYoungerCommandments:
    """Tests for the 10 Younger Commandments of Cross-Examination."""

    def test_all_ten_commandments_exist(self, kb):
        for i in range(1, 11):
            cmd = kb.get_commandment(i)
            assert cmd is not None, f"Commandment {i} should exist"

    def test_get_commandment_returns_correct_number(self, kb):
        for i in range(1, 11):
            cmd = kb.get_commandment(i)
            assert cmd.number == i

    def test_invalid_commandment_zero_returns_none(self, kb):
        assert kb.get_commandment(0) is None

    def test_invalid_commandment_eleven_returns_none(self, kb):
        assert kb.get_commandment(11) is None

    def test_invalid_commandment_negative_returns_none(self, kb):
        assert kb.get_commandment(-1) is None

    def test_commandment_3_about_leading_questions(self, kb):
        cmd = kb.get_commandment(3)
        assert "leading" in cmd.title_en.lower()
        assert "מנחות" in cmd.title_he

    def test_commandment_4_about_knowing_answers(self, kb):
        cmd = kb.get_commandment(4)
        assert "know the answer" in cmd.title_en.lower()
        assert "לא יודע" in cmd.title_he

    def test_every_commandment_has_hebrew_fields(self, kb):
        for i in range(1, 11):
            cmd = kb.get_commandment(i)
            assert isinstance(cmd, YoungerCommandment)
            assert len(cmd.title_he) > 0
            assert len(cmd.description) > 0
            assert len(cmd.violation_risk) > 0
            assert len(cmd.application_tip) > 0


# ===========================================================================
# 5. TestExpertTechniques
# ===========================================================================

class TestExpertTechniques:
    """Tests for expert cross-examination techniques."""

    TECHNIQUE_NAMES = [
        "chapter_method",
        "commit_credit_confront",
        "cognitive_load",
        "russell_direct",
        "choate_gentle",
        "sue_technique",
        "lincoln_almanac",
    ]

    def test_all_seven_techniques_exist(self, kb):
        for name in self.TECHNIQUE_NAMES:
            tech = kb.get_technique(name)
            assert tech is not None, f"Technique '{name}' should exist"

    def test_invalid_technique_returns_none(self, kb):
        assert kb.get_technique("nonexistent_technique") is None

    def test_each_technique_has_nonempty_example_questions(self, kb):
        for name in self.TECHNIQUE_NAMES:
            tech = kb.get_technique(name)
            assert isinstance(tech.example_questions, list)
            assert len(tech.example_questions) > 0

    def test_sue_technique_is_high_risk(self, kb):
        tech = kb.get_technique("sue_technique")
        assert tech.risk_level == "high"

    def test_chapter_method_is_low_risk(self, kb):
        tech = kb.get_technique("chapter_method")
        assert tech.risk_level == "low"

    def test_cognitive_load_is_medium_risk(self, kb):
        tech = kb.get_technique("cognitive_load")
        assert tech.risk_level == "medium"

    def test_each_technique_has_source_attribution(self, kb):
        for name in self.TECHNIQUE_NAMES:
            tech = kb.get_technique(name)
            assert isinstance(tech.source, str)
            assert len(tech.source) > 0, f"Technique '{name}' must have a source"

    def test_lincoln_almanac_is_low_risk(self, kb):
        tech = kb.get_technique("lincoln_almanac")
        assert tech.risk_level == "low"
        assert "Lincoln" in tech.source or "Abraham" in tech.source


# ===========================================================================
# 6. TestWitnessProfiles
# ===========================================================================

class TestWitnessProfiles:
    """Tests for witness profiles."""

    PROFILED_TYPES = [
        WitnessType.EVASIVE,
        WitnessType.HOSTILE,
        WitnessType.VERBOSE,
        WitnessType.EXPERT,
        WitnessType.EMOTIONAL,
        WitnessType.UNCERTAIN,
    ]

    def test_all_six_profiled_types_exist(self, kb):
        for wt in self.PROFILED_TYPES:
            profile = kb.get_witness_profile(wt)
            assert profile is not None, f"Profile for {wt.name} should exist"

    def test_cooperative_has_no_profile(self, kb):
        # COOPERATIVE is a WitnessType member but has no profile entry
        profile = kb.get_witness_profile(WitnessType.COOPERATIVE)
        assert profile is None

    def test_evasive_recommends_ladder(self, kb):
        profile = kb.get_witness_profile(WitnessType.EVASIVE)
        assert QuestionStrategy.LADDER in profile.recommended_strategies

    def test_hostile_avoids_surprise(self, kb):
        profile = kb.get_witness_profile(WitnessType.HOSTILE)
        assert QuestionStrategy.SURPRISE in profile.avoid_strategies

    def test_emotional_avoids_cognitive_load(self, kb):
        profile = kb.get_witness_profile(WitnessType.EMOTIONAL)
        assert QuestionStrategy.COGNITIVE_LOAD in profile.avoid_strategies

    def test_each_profile_has_sample_questions(self, kb):
        for wt in self.PROFILED_TYPES:
            profile = kb.get_witness_profile(wt)
            assert isinstance(profile.sample_questions, list)
            assert len(profile.sample_questions) > 0

    def test_each_profile_has_warnings(self, kb):
        for wt in self.PROFILED_TYPES:
            profile = kb.get_witness_profile(wt)
            assert isinstance(profile.warnings, list)
            assert len(profile.warnings) > 0

    def test_profile_witness_type_matches(self, kb):
        for wt in self.PROFILED_TYPES:
            profile = kb.get_witness_profile(wt)
            assert profile.witness_type is wt


# ===========================================================================
# 7. TestQuestionTemplates
# ===========================================================================

class TestQuestionTemplates:
    """Tests for question template retrieval."""

    def test_opening_build_agreement_exists(self, kb):
        templates = kb.get_question_templates("opening", "build_agreement")
        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_confrontation_internal_contradiction_exists(self, kb):
        templates = kb.get_question_templates("confrontation", "internal_contradiction")
        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_invalid_category_returns_empty_list(self, kb):
        result = kb.get_question_templates("nonexistent_category", "any")
        assert result == []

    def test_invalid_subcategory_returns_empty_list(self, kb):
        result = kb.get_question_templates("opening", "nonexistent_sub")
        assert result == []

    def test_templates_contain_hebrew_with_placeholders(self, kb):
        templates = kb.get_question_templates("opening", "build_agreement")
        # At least one template should have a {variable} placeholder
        has_placeholder = any("{" in t and "}" in t for t in templates)
        assert has_placeholder, "Expected at least one template with a {variable} placeholder"
        # All templates should contain Hebrew characters
        for t in templates:
            has_hebrew = any("\u0590" <= c <= "\u05FF" for c in t)
            assert has_hebrew, f"Template should contain Hebrew text: {t}"


# ===========================================================================
# 8. TestPsychologicalInsights
# ===========================================================================

class TestPsychologicalInsights:
    """Tests for psychological insights."""

    def test_get_random_insight_returns_insight(self, kb):
        insight = kb.get_random_insight()
        assert isinstance(insight, PsychologicalInsight)

    def test_all_insights_have_source_attribution(self, kb):
        for insight in kb.psychological_insights:
            assert isinstance(insight.source, str)
            assert len(insight.source) > 0

    def test_loftus_insight_exists(self, kb):
        sources = [i.source for i in kb.psychological_insights]
        loftus_found = any("Loftus" in s for s in sources)
        assert loftus_found, "Expected at least one insight from Loftus"

    def test_fbi_insight_exists(self, kb):
        sources = [i.source for i in kb.psychological_insights]
        fbi_found = any("FBI" in s for s in sources)
        assert fbi_found, "Expected at least one insight from FBI research"

    def test_total_insights_count(self, kb):
        assert len(kb.psychological_insights) == 7


# ===========================================================================
# 9. TestSuggestStrategy
# ===========================================================================

class TestSuggestStrategy:
    """Tests for the suggest_strategy() method."""

    def test_internal_contradiction_primary_is_commit_credit_confront(self, kb):
        result = kb.suggest_strategy("internal")
        assert result["primary_technique"] is not None
        assert result["primary_technique"].name == kb.get_technique("commit_credit_confront").name

    def test_external_contradiction_primary_is_sue_technique(self, kb):
        result = kb.suggest_strategy("external")
        assert result["primary_technique"] is not None
        assert result["primary_technique"].name == kb.get_technique("sue_technique").name

    def test_unknown_type_falls_back_to_chapter_method(self, kb):
        result = kb.suggest_strategy("something_else")
        assert result["primary_technique"] is not None
        assert result["primary_technique"].name == kb.get_technique("chapter_method").name

    def test_evasive_witness_approach(self, kb):
        result = kb.suggest_strategy("internal", witness_behavior="evasive")
        assert "שליטה הדוקה" in result["approach"]

    def test_hostile_witness_approach(self, kb):
        result = kb.suggest_strategy("internal", witness_behavior="hostile")
        assert "קור רוח" in result["approach"]

    def test_emotional_witness_approach(self, kb):
        result = kb.suggest_strategy("internal", witness_behavior="emotional")
        assert "אנושי" in result["approach"]

    def test_strategy_returns_relevant_commandments(self, kb):
        result = kb.suggest_strategy("internal")
        cmds = result["relevant_commandments"]
        assert len(cmds) == 4
        cmd_numbers = [c.number for c in cmds]
        assert 1 in cmd_numbers
        assert 3 in cmd_numbers
        assert 4 in cmd_numbers
        assert 9 in cmd_numbers


# ===========================================================================
# 10. TestGenerateEnhancedQuestion
# ===========================================================================

class TestGenerateEnhancedQuestion:
    """Tests for generate_enhanced_question()."""

    def test_question_with_btzhir_uses_commit_credit_confront(self, kb):
        result = kb.generate_enhanced_question(
            "בתצהיר שלך כתבת שהפגישה הייתה ב-10, נכון?",
            context={}
        )
        assert result["technique_used"] == "commit_credit_confront"

    def test_question_with_opposing_party_uses_sue_technique(self, kb):
        result = kb.generate_enhanced_question(
            "הצד השני טוען שלא היית שם",
            context={}
        )
        assert result["technique_used"] == "sue_technique"

    def test_question_with_sensory_uses_cognitive_load(self, kb):
        result = kb.generate_enhanced_question(
            "מה שמעת באותו רגע?",
            context={}
        )
        assert result["technique_used"] == "cognitive_load"

    def test_plain_question_has_no_technique(self, kb):
        result = kb.generate_enhanced_question(
            "האם נכון שהיית במשרד?",
            context={}
        )
        assert result["technique_used"] is None

    def test_always_returns_original_question(self, kb):
        original = "שאלה כללית בעברית"
        result = kb.generate_enhanced_question(original, context={})
        assert result["original_question"] == original

    def test_enhanced_result_has_follow_up_suggestions(self, kb):
        result = kb.generate_enhanced_question(
            "בתצהיר שלך כתבת שהפגישה הייתה ב-10, נכון?",
            context={}
        )
        assert isinstance(result["follow_up_suggestions"], list)
        assert len(result["follow_up_suggestions"]) > 0


# ===========================================================================
# 11. TestAnalyzeWitnessResponse
# ===========================================================================

class TestAnalyzeWitnessResponse:
    """Tests for analyze_witness_response()."""

    def test_response_with_rak_detects_minimizing(self, kb):
        result = kb.analyze_witness_response("רק דיברנו על דברים כלליים")
        types = [m["type"] for m in result["linguistic_markers"]]
        assert "minimizing" in types

    def test_response_with_behechlet_detects_intensifying(self, kb):
        result = kb.analyze_witness_response("בהחלט הייתי שם")
        types = [m["type"] for m in result["linguistic_markers"]]
        assert "intensifying" in types

    def test_response_with_nidme_li_detects_hedging(self, kb):
        result = kb.analyze_witness_response("נדמה לי שהפגישה הייתה בבוקר")
        types = [m["type"] for m in result["linguistic_markers"]]
        assert "hedging" in types

    def test_clean_response_has_no_markers(self, kb):
        result = kb.analyze_witness_response("הפגישה הייתה בשעה עשר בבוקר")
        assert len(result["linguistic_markers"]) == 0


# ===========================================================================
# 12. TestSingleton
# ===========================================================================

class TestSingleton:
    """Tests for the get_knowledge_base() singleton."""

    def test_returns_expert_knowledge_base(self):
        instance = get_knowledge_base()
        assert isinstance(instance, ExpertKnowledgeBase)

    def test_called_twice_returns_same_instance(self):
        a = get_knowledge_base()
        b = get_knowledge_base()
        assert a is b
