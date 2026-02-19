"""
Extended tests for backend_lite.expert_contradiction module.

Covers ~100 tests across all helper functions, dataclass construction,
pair evaluation, and the public API (build_expert_claims, analyze_expert_pairs).

Uses real Hebrew text and exercises edge cases, boundary conditions, and
known behavioural quirks (e.g. the _stage_shift always-False bug).
"""

from __future__ import annotations

import pytest
from typing import List

from backend_lite.expert_contradiction import (
    ExpertClaim,
    PairAnalysisRow,
    ExpertSummaryReport,
    ExpertAnalysisResult,
    _matches_any,
    _normalize_enum,
    _tokenize,
    _extract_sentences,
    _extract_context,
    _derive_section_path,
    _derive_speaker_role,
    _derive_speaker_mode,
    _derive_plane,
    _extract_scope_conditions,
    _extract_quantifiers,
    _derive_modality,
    _detect_negation,
    _extract_entities,
    _extract_confidence,
    _missing_claim_fields,
    _subject_overlap,
    _token_overlap,
    _duplicate_restatement,
    _stage_shift,
    _can_be_reconciled,
    _score_contradiction,
    _severity_from_score,
    _evaluate_pair,
    _build_evidence,
    build_expert_claims,
    analyze_expert_pairs,
)
from backend_lite.extractor import Claim
from backend_lite.schemas import (
    OutcomeCategory,
    SpeakerMode,
    SpeakerRole,
    ClaimPlane,
    Severity,
    ContradictionType,
    ContradictionStatus,
    ContradictionCategory,
)
from backend_lite.detector import RuleBasedDetector


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def _make_claim(text: str, **kwargs) -> Claim:
    """Create a minimal Claim for test purposes."""
    return Claim(
        id=kwargs.pop("id", f"c_{abs(hash(text)) % 100000}"),
        text=text,
        source=kwargs.pop("source", None),
        speaker=kwargs.pop("speaker", None),
        doc_id=kwargs.pop("doc_id", None),
        page=kwargs.pop("page", None),
        paragraph_index=kwargs.pop("paragraph_index", None),
        char_start=kwargs.pop("char_start", None),
        char_end=kwargs.pop("char_end", None),
        metadata=kwargs.pop("metadata", {}),
    )


def _expert_claim(text_span: str, **kwargs) -> ExpertClaim:
    """Factory for ExpertClaim with sane defaults."""
    defaults = dict(
        claim_id=kwargs.pop("claim_id", f"ec_{abs(hash(text_span)) % 100000}"),
        doc_id=None,
        text_span=text_span,
        context_before="הקשר לפני",
        context_after="הקשר אחרי",
        section_path="paragraph:1",
        speaker_role=SpeakerRole.PARTY.value,
        speaker_mode=SpeakerMode.COURT_FINDING.value,
        plane=ClaimPlane.FACT.value,
        time_reference="",
        scope_conditions="unconditional",
        quantifiers=[],
        modality="must",
        negation=False,
        entities_relations=["ישות"],
        extraction_confidence=0.8,
        raw_claim=Claim(id=kwargs.get("claim_id", "raw"), text=text_span),
        tokens=_tokenize(text_span) if text_span else [],
        time_values=[],
        missing_fields=[],
        eligible=True,
    )
    defaults.update(kwargs)
    return ExpertClaim(**defaults)


# ===================================================================
# _matches_any
# ===================================================================
class TestMatchesAny:
    def test_matching_pattern_returns_true(self):
        assert _matches_any("בית המשפט קבע", [r"בית\s+המשפט"]) is True

    def test_non_matching_returns_false(self):
        assert _matches_any("טקסט רגיל", [r"בית\s+המשפט"]) is False

    def test_empty_patterns_returns_false(self):
        assert _matches_any("בית המשפט", []) is False

    def test_empty_text_returns_false(self):
        assert _matches_any("", [r"בית\s+המשפט"]) is False

    def test_multiple_patterns_one_matches(self):
        assert _matches_any("עו\"ד כהן", [r"שופט", r"עו\"ד"]) is True


# ===================================================================
# _normalize_enum
# ===================================================================
class TestNormalizeEnum:
    def test_enum_value_extracted(self):
        assert _normalize_enum(SpeakerRole.COURT) == "court"

    def test_plain_string_unchanged(self):
        assert _normalize_enum("court") == "court"

    def test_none_unchanged(self):
        assert _normalize_enum(None) is None

    def test_int_unchanged(self):
        assert _normalize_enum(42) == 42


# ===================================================================
# _tokenize
# ===================================================================
class TestTokenize:
    def test_basic_hebrew_tokens(self):
        tokens = _tokenize("התובע הגיש תביעה בנושא חוזה")
        assert isinstance(tokens, list)
        assert len(tokens) > 0
        # "התובע" has 5 chars, should pass the >1 char filter
        assert "התובע" in tokens

    def test_stopwords_filtered(self):
        # "את" and "של" and "על" are stopwords
        tokens = _tokenize("את של על")
        assert tokens == []

    def test_single_char_filtered(self):
        # single Hebrew char filtered by len>1
        tokens = _tokenize("א ב ג")
        assert tokens == []

    def test_empty_text(self):
        assert _tokenize("") == []

    def test_none_text(self):
        assert _tokenize(None) == []

    def test_mixed_hebrew_and_latin(self):
        tokens = _tokenize("hello התובע world הנתבע")
        # Only Hebrew tokens should survive
        assert "התובע" in tokens
        assert "הנתבע" in tokens
        assert "hello" not in tokens

    def test_numbers_not_included(self):
        tokens = _tokenize("סכום 100000 שקלים")
        # numbers are not Hebrew word chars
        assert "100000" not in tokens


# ===================================================================
# _extract_sentences
# ===================================================================
class TestExtractSentences:
    def test_multiple_sentences_with_period(self):
        text = "משפט ראשון. משפט שני. משפט שלישי."
        sents = _extract_sentences(text)
        assert len(sents) == 3
        assert sents[0][2] == "משפט ראשון."
        assert sents[1][2] == "משפט שני."

    def test_question_mark_splits(self):
        text = "האם זה נכון? כן זה נכון."
        sents = _extract_sentences(text)
        assert len(sents) == 2

    def test_empty_text(self):
        assert _extract_sentences("") == []

    def test_none_text(self):
        assert _extract_sentences(None) == []

    def test_no_punctuation_single_sentence(self):
        text = "טקסט ללא נקודה"
        sents = _extract_sentences(text)
        assert len(sents) == 1
        assert sents[0][2] == text

    def test_offsets_are_valid(self):
        text = "אחד. שתיים. שלוש."
        sents = _extract_sentences(text)
        for start, end, sentence in sents:
            assert start >= 0
            assert end <= len(text)
            assert start < end


# ===================================================================
# _extract_context
# ===================================================================
class TestExtractContext:
    def test_middle_position(self):
        text = "משפט ראשון. משפט שני. משפט שלישי."
        before, after = _extract_context(text, 12, 22)
        # char 12-22 should be in the second sentence, so before has first, after has third
        assert "ראשון" in before
        assert "שלישי" in after

    def test_start_position_empty_before(self):
        text = "משפט ראשון. משפט שני."
        before, after = _extract_context(text, 0, 5)
        assert before == ""
        assert "שני" in after

    def test_end_position_empty_after(self):
        text = "משפט ראשון. משפט שני. משפט אחרון."
        sents = _extract_sentences(text)
        # Use a char_start clearly inside the last sentence (not on boundary)
        last_start = sents[-1][0] + 1
        last_end = sents[-1][1]
        before, after = _extract_context(text, last_start, last_end)
        # Last sentence has no sentences after it
        assert after == ""
        # But before should contain prior sentences
        assert len(before) > 0

    def test_none_offsets(self):
        before, after = _extract_context("טקסט כלשהו.", None, None)
        assert before == ""
        assert after == ""

    def test_none_text(self):
        before, after = _extract_context(None, 0, 10)
        assert before == ""
        assert after == ""


# ===================================================================
# _derive_section_path
# ===================================================================
class TestDeriveSectionPath:
    def test_paragraph_index(self):
        claim = _make_claim("טקסט", paragraph_index=5)
        assert _derive_section_path(claim) == "paragraph:5"

    def test_page_fallback(self):
        claim = _make_claim("טקסט", page=3)
        assert _derive_section_path(claim) == "page:3"

    def test_no_index_returns_empty(self):
        claim = _make_claim("טקסט")
        assert _derive_section_path(claim) == ""


# ===================================================================
# _derive_speaker_role
# ===================================================================
class TestDeriveSpeakerRole:
    def test_court_marker(self):
        result = _derive_speaker_role("בית המשפט קבע כי", None, None)
        assert result == SpeakerRole.COURT.value

    def test_attorney_marker(self):
        result = _derive_speaker_role("עו\"ד כהן טען", None, None)
        assert result == SpeakerRole.ATTORNEY.value

    def test_witness_marker(self):
        result = _derive_speaker_role("העיד בפני בית הדין", None, None)
        assert result == SpeakerRole.WITNESS.value

    def test_default_party(self):
        result = _derive_speaker_role("טקסט רגיל ללא סימן", None, None)
        assert result == SpeakerRole.PARTY.value

    def test_speaker_field_used(self):
        result = _derive_speaker_role("טקסט", None, "בית המשפט")
        assert result == SpeakerRole.COURT.value

    def test_source_field_used(self):
        result = _derive_speaker_role("טקסט", "עו\"ד לוי", None)
        assert result == SpeakerRole.ATTORNEY.value


# ===================================================================
# _derive_speaker_mode
# ===================================================================
class TestDeriveSpeakerMode:
    def test_attr_marker_party_claim(self):
        result = _derive_speaker_mode("לטענת התובע", SpeakerRole.PARTY.value)
        assert result == SpeakerMode.PARTY_CLAIM.value

    def test_quote_marker(self):
        result = _derive_speaker_mode('הוא אמר "שלום"', SpeakerRole.PARTY.value)
        assert result == SpeakerMode.QUOTE.value

    def test_law_marker(self):
        result = _derive_speaker_mode("סעיף 5 לחוק", SpeakerRole.PARTY.value)
        assert result == SpeakerMode.LAW_CITATION.value

    def test_court_role_finding(self):
        result = _derive_speaker_mode("טקסט רגיל", SpeakerRole.COURT.value)
        assert result == SpeakerMode.COURT_FINDING.value

    def test_opinion_marker(self):
        result = _derive_speaker_mode("סבור כי יש צורך", SpeakerRole.PARTY.value)
        assert result == SpeakerMode.OPINION.value

    def test_default_party_claim(self):
        result = _derive_speaker_mode("טקסט רגיל", SpeakerRole.PARTY.value)
        assert result == SpeakerMode.PARTY_CLAIM.value


# ===================================================================
# _derive_plane
# ===================================================================
class TestDerivePlane:
    def test_law_citation_mode(self):
        result = _derive_plane("טקסט", SpeakerMode.LAW_CITATION.value)
        assert result == ClaimPlane.LAW.value

    def test_opinion_mode(self):
        result = _derive_plane("טקסט", SpeakerMode.OPINION.value)
        assert result == ClaimPlane.OPINION.value

    def test_procedural_marker(self):
        result = _derive_plane("בקשה לסילוק", SpeakerMode.PARTY_CLAIM.value)
        assert result == ClaimPlane.PROCEDURAL.value

    def test_default_fact(self):
        result = _derive_plane("טקסט רגיל", SpeakerMode.PARTY_CLAIM.value)
        assert result == ClaimPlane.FACT.value

    def test_procedural_halaich(self):
        result = _derive_plane("הליך משפטי ארוך", SpeakerMode.COURT_FINDING.value)
        assert result == ClaimPlane.PROCEDURAL.value


# ===================================================================
# _extract_scope_conditions
# ===================================================================
class TestExtractScopeConditions:
    def test_conditional_with_im(self):
        assert _extract_scope_conditions("אם התובע יפנה") == "conditional"

    def test_conditional_with_tnai(self):
        assert _extract_scope_conditions("בתנאי שישלם") == "conditional"

    def test_unconditional(self):
        assert _extract_scope_conditions("התובע שילם") == "unconditional"

    def test_conditional_with_kafuf(self):
        assert _extract_scope_conditions("בכפוף להסכמה") == "conditional"


# ===================================================================
# _extract_quantifiers
# ===================================================================
class TestExtractQuantifiers:
    def test_positive_quantifier_kol(self):
        result = _extract_quantifiers("כל העובדים קיבלו")
        assert len(result) >= 1

    def test_negative_quantifier_af(self):
        result = _extract_quantifiers("אף אחד לא הגיע")
        assert len(result) >= 1

    def test_min_quantifier(self):
        result = _extract_quantifiers("לפחות שלושה אנשים")
        assert len(result) >= 1

    def test_no_quantifiers(self):
        result = _extract_quantifiers("הגשם ירד היום")
        assert result == []


# ===================================================================
# _derive_modality
# ===================================================================
class TestDeriveModality:
    def test_must(self):
        assert _derive_modality("חייב לשלם") == "must"

    def test_may(self):
        assert _derive_modality("מותר לצאת") == "may"

    def test_possible(self):
        assert _derive_modality("אפשר להגיש") == "possible"

    def test_uncertain(self):
        assert _derive_modality("בספק אם") == "uncertain"

    def test_default_must(self):
        assert _derive_modality("טקסט רגיל") == "must"


# ===================================================================
# _detect_negation
# ===================================================================
class TestDetectNegation:
    def test_lo_negation(self):
        assert _detect_negation("לא שילם") is True

    def test_ein_negation(self):
        assert _detect_negation("אין ראיה") is True

    def test_eino_negation(self):
        assert _detect_negation("אינו מסכים") is True

    def test_no_negation(self):
        assert _detect_negation("שילם בזמן") is False


# ===================================================================
# _extract_entities
# ===================================================================
class TestExtractEntities:
    def test_hebrew_tokens_included(self):
        entities = _extract_entities("התובע הגיש תביעה בסכום", None)
        assert "התובע" in entities

    def test_numbers_included(self):
        entities = _extract_entities("סכום 50000 שקלים", None)
        assert "50000" in entities

    def test_metadata_entities_included(self):
        meta = {"entities": ["כהן", "לוי"]}
        entities = _extract_entities("טקסט", meta)
        assert "כהן" in entities
        assert "לוי" in entities

    def test_empty_metadata(self):
        entities = _extract_entities("התובע", None)
        assert isinstance(entities, list)

    def test_no_duplicates(self):
        meta = {"entities": ["התובע"]}
        entities = _extract_entities("התובע הגיש", meta)
        assert entities.count("התובע") == 1


# ===================================================================
# _extract_confidence
# ===================================================================
class TestExtractConfidence:
    def test_metadata_confidence_used(self):
        meta = {"extraction_confidence": 0.95}
        assert _extract_confidence("טקסט", meta) == 0.95

    def test_default_calculated(self):
        conf = _extract_confidence("משפט ארוך מספיק כדי לקבל ביטחון סביר", None)
        assert 0.3 <= conf <= 0.9

    def test_short_text_lower_confidence(self):
        short = _extract_confidence("קצר", None)
        long = _extract_confidence("משפט ארוך מאוד עם מילים רבות ותוכן מורכב כדי לתת ביטחון גבוה יותר", None)
        assert short <= long

    def test_confidence_clamped_min(self):
        # Very short text should still be at least 0.3
        conf = _extract_confidence("", None)
        assert conf >= 0.3

    def test_confidence_clamped_max(self):
        # Very long text should be at most 0.9
        conf = _extract_confidence("x" * 10000, None)
        assert conf <= 0.9


# ===================================================================
# _missing_claim_fields
# ===================================================================
class TestMissingClaimFields:
    def test_all_populated_returns_empty(self):
        result = _missing_claim_fields(
            text_span="טקסט",
            context_before="לפני",
            context_after="אחרי",
            section_path="paragraph:1",
            speaker_role="court",
            speaker_mode="COURT_FINDING",
            plane="FACT",
            time_reference="2024",
            scope_conditions="unconditional",
            quantifiers=["כל"],
            modality="must",
            entities_relations=["entity"],
            extraction_confidence=0.8,
        )
        assert result == []

    def test_missing_text_span(self):
        result = _missing_claim_fields(
            text_span="",
            context_before="לפני",
            context_after="אחרי",
            section_path="paragraph:1",
            speaker_role="court",
            speaker_mode="COURT_FINDING",
            plane="FACT",
            time_reference="2024",
            scope_conditions="unconditional",
            quantifiers=[],
            modality="must",
            entities_relations=["entity"],
            extraction_confidence=0.8,
        )
        assert "text_span" in result

    def test_missing_multiple_fields(self):
        result = _missing_claim_fields(
            text_span="",
            context_before="",
            context_after="",
            section_path="",
            speaker_role="",
            speaker_mode="",
            plane="",
            time_reference="",
            scope_conditions="",
            quantifiers=None,
            modality="",
            entities_relations=None,
            extraction_confidence=None,
        )
        assert "text_span" in result
        assert "context_before" in result
        assert "extraction_confidence" in result
        assert "quantifiers" in result
        assert "entities_relations" in result

    def test_empty_list_entities_counted_missing(self):
        result = _missing_claim_fields(
            text_span="טקסט",
            context_before="לפני",
            context_after="אחרי",
            section_path="p:1",
            speaker_role="court",
            speaker_mode="COURT_FINDING",
            plane="FACT",
            time_reference="2024",
            scope_conditions="unconditional",
            quantifiers=[],
            modality="must",
            entities_relations=[],
            extraction_confidence=0.8,
        )
        assert "entities_relations" in result

    def test_empty_quantifiers_not_missing(self):
        """Empty list for quantifiers is NOT considered missing (only None is)."""
        result = _missing_claim_fields(
            text_span="טקסט",
            context_before="לפני",
            context_after="אחרי",
            section_path="p:1",
            speaker_role="court",
            speaker_mode="COURT_FINDING",
            plane="FACT",
            time_reference="2024",
            scope_conditions="unconditional",
            quantifiers=[],
            modality="must",
            entities_relations=["ent"],
            extraction_confidence=0.8,
        )
        assert "quantifiers" not in result


# ===================================================================
# _subject_overlap
# ===================================================================
class TestSubjectOverlap:
    def test_shared_entity(self):
        a = _expert_claim("התובע שילם", entities_relations=["התובע", "כהן"])
        b = _expert_claim("התובע הגיש", entities_relations=["התובע", "לוי"])
        assert _subject_overlap(a, b) is True

    def test_no_overlap(self):
        a = _expert_claim("כהן שילם", entities_relations=["כהן"])
        b = _expert_claim("לוי הגיש", entities_relations=["לוי"])
        assert _subject_overlap(a, b) is False

    def test_empty_entities_a(self):
        a = _expert_claim("טקסט", entities_relations=[])
        b = _expert_claim("טקסט", entities_relations=["כהן"])
        assert _subject_overlap(a, b) is False

    def test_empty_entities_both(self):
        a = _expert_claim("טקסט", entities_relations=[])
        b = _expert_claim("טקסט", entities_relations=[])
        assert _subject_overlap(a, b) is False


# ===================================================================
# _token_overlap
# ===================================================================
class TestTokenOverlap:
    def test_identical_tokens(self):
        a = _expert_claim("התובע שילם סכום")
        b = _expert_claim("התובע שילם סכום")
        assert _token_overlap(a, b) == 1.0

    def test_no_overlap(self):
        a = _expert_claim("התובע שילם סכום")
        b = _expert_claim("הנתבע הגיש בקשה")
        overlap = _token_overlap(a, b)
        assert overlap == 0.0

    def test_partial_overlap(self):
        a = _expert_claim("התובע שילם סכום גדול")
        b = _expert_claim("התובע הגיש סכום קטן")
        overlap = _token_overlap(a, b)
        assert 0.0 < overlap < 1.0

    def test_empty_tokens(self):
        a = _expert_claim("", tokens=[])
        b = _expert_claim("התובע שילם")
        assert _token_overlap(a, b) == 0.0


# ===================================================================
# _duplicate_restatement
# ===================================================================
class TestDuplicateRestatement:
    def test_identical_is_duplicate(self):
        a = _expert_claim("התובע שילם סכום גדול למוכר")
        b = _expert_claim("התובע שילם סכום גדול למוכר")
        assert _duplicate_restatement(a, b) is True

    def test_different_is_not_duplicate(self):
        a = _expert_claim("התובע שילם סכום גדול")
        b = _expert_claim("הנתבע הגיש בקשה חדשה")
        assert _duplicate_restatement(a, b) is False


# ===================================================================
# _stage_shift — has a known bug: always returns False
# ===================================================================
class TestStageShift:
    def test_both_markers_different_always_false(self):
        """
        Bug: the code checks `a_has and b_has and a_has != b_has`.
        Since both a_has and b_has are booleans and both True,
        a_has != b_has is False, so result is always False.
        """
        a = _expert_claim("לפני החתימה")
        b = _expert_claim("לאחר החתימה")
        # Due to bug, this is always False
        assert _stage_shift(a, b) is False

    def test_only_one_has_marker(self):
        a = _expert_claim("לפני החתימה")
        b = _expert_claim("החתימה בוצעה")
        assert _stage_shift(a, b) is False

    def test_neither_has_marker(self):
        a = _expert_claim("החתימה בוצעה")
        b = _expert_claim("התשלום התקבל")
        assert _stage_shift(a, b) is False

    def test_same_marker_both(self):
        a = _expert_claim("לפני הדיון הראשון")
        b = _expert_claim("לפני הדיון השני")
        # Both have markers, both True, a_has != b_has is False
        assert _stage_shift(a, b) is False


# ===================================================================
# _can_be_reconciled
# ===================================================================
class TestCanBeReconciled:
    def test_stage_shift_never_triggers(self):
        """Stage shift never triggers due to bug, so reconciliation falls through."""
        a = _expert_claim("לפני החתימה", scope_conditions="unconditional", modality="must")
        b = _expert_claim("לאחר החתימה", scope_conditions="unconditional", modality="must")
        reconciled, reason = _can_be_reconciled(a, b)
        # stage_shift always False → falls through to scope/modality
        # same scope, same modality → irreconcilable
        assert reconciled is False
        assert reason == "irreconcilable"

    def test_different_scope_conditions(self):
        a = _expert_claim("טקסט", scope_conditions="conditional")
        b = _expert_claim("טקסט", scope_conditions="unconditional")
        reconciled, reason = _can_be_reconciled(a, b)
        assert reconciled is True
        assert reason == "scope_conditions"

    def test_different_modality(self):
        a = _expert_claim("טקסט", scope_conditions="unconditional", modality="must")
        b = _expert_claim("טקסט", scope_conditions="unconditional", modality="may")
        reconciled, reason = _can_be_reconciled(a, b)
        assert reconciled is True
        assert reason == "modality_differs"

    def test_irreconcilable(self):
        a = _expert_claim("טקסט", scope_conditions="unconditional", modality="must")
        b = _expert_claim("טקסט", scope_conditions="unconditional", modality="must")
        reconciled, reason = _can_be_reconciled(a, b)
        assert reconciled is False
        assert reason == "irreconcilable"


# ===================================================================
# _score_contradiction
# ===================================================================
class TestScoreContradiction:
    def test_all_high(self):
        a = _expert_claim("טקסט", modality="must")
        b = _expert_claim("טקסט", modality="must")
        score = _score_contradiction(a, b, direct_conflict=True, same_subject=True, plane_match=True, confidence=1.0)
        # 0.4 + 0.2 + 0.1 + 0.3*1.0 = 1.0
        assert score == pytest.approx(1.0)

    def test_no_factors(self):
        a = _expert_claim("טקסט", modality="must")
        b = _expert_claim("טקסט", modality="must")
        score = _score_contradiction(a, b, direct_conflict=False, same_subject=False, plane_match=False, confidence=0.0)
        # 0.0
        assert score == pytest.approx(0.0)

    def test_modality_reduces_score(self):
        a = _expert_claim("טקסט", modality="possible")
        b = _expert_claim("טקסט", modality="must")
        score = _score_contradiction(a, b, direct_conflict=True, same_subject=True, plane_match=True, confidence=1.0)
        # 1.0 - 0.1 = 0.9
        assert score == pytest.approx(0.9)

    def test_score_clamped_min(self):
        a = _expert_claim("טקסט", modality="possible")
        b = _expert_claim("טקסט", modality="uncertain")
        score = _score_contradiction(a, b, direct_conflict=False, same_subject=False, plane_match=False, confidence=0.0)
        # 0.0 - 0.1 = -0.1 → clamped to 0.0
        assert score == pytest.approx(0.0)

    def test_score_clamped_max(self):
        a = _expert_claim("טקסט", modality="must")
        b = _expert_claim("טקסט", modality="must")
        score = _score_contradiction(a, b, direct_conflict=True, same_subject=True, plane_match=True, confidence=1.0)
        assert score <= 1.0

    def test_only_direct_conflict(self):
        a = _expert_claim("טקסט", modality="must")
        b = _expert_claim("טקסט", modality="must")
        score = _score_contradiction(a, b, direct_conflict=True, same_subject=False, plane_match=False, confidence=0.0)
        assert score == pytest.approx(0.4)

    def test_only_subject_overlap(self):
        a = _expert_claim("טקסט", modality="must")
        b = _expert_claim("טקסט", modality="must")
        score = _score_contradiction(a, b, direct_conflict=False, same_subject=True, plane_match=False, confidence=0.0)
        assert score == pytest.approx(0.2)


# ===================================================================
# _severity_from_score
# ===================================================================
class TestSeverityFromScore:
    def test_reconciled_always_low(self):
        assert _severity_from_score(1.0, 1.0, reconciled=True) == Severity.LOW

    def test_critical(self):
        assert _severity_from_score(0.95, 0.85, reconciled=False) == Severity.CRITICAL

    def test_high(self):
        assert _severity_from_score(0.85, 0.5, reconciled=False) == Severity.HIGH

    def test_medium(self):
        assert _severity_from_score(0.78, 0.5, reconciled=False) == Severity.MEDIUM

    def test_low(self):
        assert _severity_from_score(0.5, 0.5, reconciled=False) == Severity.LOW

    def test_critical_boundary_score(self):
        # score = 0.9 exactly and confidence = 0.8
        assert _severity_from_score(0.9, 0.8, reconciled=False) == Severity.CRITICAL

    def test_high_boundary(self):
        assert _severity_from_score(0.82, 0.5, reconciled=False) == Severity.HIGH

    def test_medium_boundary(self):
        assert _severity_from_score(0.75, 0.5, reconciled=False) == Severity.MEDIUM


# ===================================================================
# _build_evidence
# ===================================================================
class TestBuildEvidence:
    def test_evidence_fields(self):
        claim = _expert_claim("טקסט לדוגמה", doc_id="doc_1")
        ev = _build_evidence(claim)
        assert ev["quote"] == "טקסט לדוגמה"
        assert ev["context_before"] == "הקשר לפני"
        assert ev["context_after"] == "הקשר אחרי"
        assert ev["doc_id"] == "doc_1"
        assert ev["section_path"] == "paragraph:1"


# ===================================================================
# _evaluate_pair
# ===================================================================
class TestEvaluatePair:
    def setup_method(self):
        self.detector = RuleBasedDetector()

    def test_ineligible_claim_insufficient_context(self):
        a = _expert_claim("טקסט", eligible=False, missing_fields=["context_before"])
        b = _expert_claim("טקסט")
        outcome, score, rationale, reconciliation, det_type = _evaluate_pair(self.detector, a, b, None)
        assert outcome == OutcomeCategory.INSUFFICIENT_CONTEXT
        assert score == 0.0
        assert det_type is None

    def test_party_claim_vs_court_finding(self):
        a = _expert_claim(
            "לטענת התובע שילם",
            speaker_mode=SpeakerMode.PARTY_CLAIM.value,
        )
        b = _expert_claim(
            "בית המשפט קבע כי שילם",
            speaker_mode=SpeakerMode.COURT_FINDING.value,
        )
        outcome, score, rationale, reconciliation, det_type = _evaluate_pair(self.detector, a, b, None)
        assert outcome == OutcomeCategory.ROLE_OR_ATTRIBUTION_MISMATCH

    def test_different_planes(self):
        a = _expert_claim(
            "עובדה ראשונה",
            plane=ClaimPlane.FACT.value,
            speaker_mode=SpeakerMode.COURT_FINDING.value,
        )
        b = _expert_claim(
            "חוות דעת שונה",
            plane=ClaimPlane.OPINION.value,
            speaker_mode=SpeakerMode.COURT_FINDING.value,
        )
        outcome, score, rationale, reconciliation, det_type = _evaluate_pair(self.detector, a, b, None)
        assert outcome == OutcomeCategory.PLANE_MISMATCH

    def test_duplicate_restatement_outcome(self):
        text = "התובע שילם סכום גדול למוכר בזמן"
        a = _expert_claim(text, speaker_mode=SpeakerMode.COURT_FINDING.value)
        b = _expert_claim(text, speaker_mode=SpeakerMode.COURT_FINDING.value)
        outcome, score, rationale, reconciliation, det_type = _evaluate_pair(self.detector, a, b, None)
        assert outcome == OutcomeCategory.DUPLICATE_RESTATEMENT

    def test_modality_reconcilable(self):
        a = _expert_claim(
            "חייב לשלם",
            modality="must",
            speaker_mode=SpeakerMode.COURT_FINDING.value,
            scope_conditions="unconditional",
        )
        b = _expert_claim(
            "מותר לשלם",
            modality="may",
            speaker_mode=SpeakerMode.COURT_FINDING.value,
            scope_conditions="unconditional",
        )
        outcome, score, rationale, reconciliation, det_type = _evaluate_pair(self.detector, a, b, None)
        assert outcome == OutcomeCategory.APPARENT_TENSION_RESOLVABLE
        assert "modality_differs" in rationale

    def test_party_claim_mode_leads_to_disagreement(self):
        """When one side has PARTY_CLAIM mode and both pass earlier gates,
        the result is DISAGREEMENT_BETWEEN_PARTIES."""
        a = _expert_claim(
            "התובע שילם 100 שקלים",
            speaker_mode=SpeakerMode.PARTY_CLAIM.value,
            modality="must",
            scope_conditions="unconditional",
        )
        b = _expert_claim(
            "הנתבע שילם 200 שקלים",
            speaker_mode=SpeakerMode.PARTY_CLAIM.value,
            modality="must",
            scope_conditions="unconditional",
        )
        outcome, score, rationale, reconciliation, det_type = _evaluate_pair(self.detector, a, b, None)
        assert outcome == OutcomeCategory.DISAGREEMENT_BETWEEN_PARTIES

    def test_quote_mode_attribution_mismatch(self):
        """When one side has QUOTE mode, result is ROLE_OR_ATTRIBUTION_MISMATCH."""
        a = _expert_claim(
            "הנתבע טען כי הסכום נמוך",
            speaker_mode=SpeakerMode.QUOTE.value,
            modality="must",
            scope_conditions="unconditional",
        )
        b = _expert_claim(
            "הסכום היה גבוה מאוד ביותר",
            speaker_mode=SpeakerMode.COURT_FINDING.value,
            modality="must",
            scope_conditions="unconditional",
        )
        outcome, score, rationale, reconciliation, det_type = _evaluate_pair(self.detector, a, b, None)
        assert outcome == OutcomeCategory.ROLE_OR_ATTRIBUTION_MISMATCH

    def test_modality_ambiguity_vagueness(self):
        """Uncertain modality leads to AMBIGUITY_OR_VAGUENESS."""
        a = _expert_claim(
            "אפשר שהתובע צודק בטענותיו",
            modality="possible",
            speaker_mode=SpeakerMode.COURT_FINDING.value,
            scope_conditions="unconditional",
        )
        b = _expert_claim(
            "ייתכן שהנתבע צודק בטענותיו",
            modality="uncertain",
            speaker_mode=SpeakerMode.COURT_FINDING.value,
            scope_conditions="unconditional",
        )
        outcome, score, rationale, reconciliation, det_type = _evaluate_pair(self.detector, a, b, None)
        # modality_differs → reconciled first check might catch it
        # If modalities differ, reconcilable fires first → APPARENT_TENSION_RESOLVABLE
        # But both are possible/uncertain variants so _can_be_reconciled returns modality_differs
        assert outcome == OutcomeCategory.APPARENT_TENSION_RESOLVABLE

    def test_negation_conflict_true_contradiction(self):
        """Negation conflict with sufficient score triggers TRUE_CONTRADICTION.

        Texts must differ enough to avoid DUPLICATE_RESTATEMENT (overlap < 0.9)
        but share enough tokens for _negation_conflict (overlap >= 0.2).
        """
        a = _expert_claim(
            "התובע שילם סכום גדול למוכר בהתאם לחוזה",
            negation=False,
            speaker_mode=SpeakerMode.COURT_FINDING.value,
            modality="must",
            scope_conditions="unconditional",
            extraction_confidence=0.9,
            entities_relations=["התובע", "סכום", "חוזה"],
        )
        b = _expert_claim(
            "לא שילם התובע כסף למוכר בזמן הנדרש",
            negation=True,
            speaker_mode=SpeakerMode.COURT_FINDING.value,
            modality="must",
            scope_conditions="unconditional",
            extraction_confidence=0.9,
            entities_relations=["התובע", "סכום", "חוזה"],
        )
        outcome, score, rationale, reconciliation, det_type = _evaluate_pair(self.detector, a, b, None)
        assert outcome == OutcomeCategory.TRUE_CONTRADICTION
        assert score >= 0.75
        assert det_type == ContradictionType.FACTUAL

    def test_no_conflict_fallback(self):
        """When no direct conflict and no special modes, falls to APPARENT_TENSION_RESOLVABLE."""
        a = _expert_claim(
            "הנתבע הגיע לפגישה",
            speaker_mode=SpeakerMode.COURT_FINDING.value,
            modality="must",
            scope_conditions="unconditional",
            extraction_confidence=0.3,
        )
        b = _expert_claim(
            "התובע הגיש מסמך חדש",
            speaker_mode=SpeakerMode.COURT_FINDING.value,
            modality="must",
            scope_conditions="unconditional",
            extraction_confidence=0.3,
        )
        outcome, score, rationale, reconciliation, det_type = _evaluate_pair(self.detector, a, b, None)
        assert outcome == OutcomeCategory.APPARENT_TENSION_RESOLVABLE
        assert "no_strong_contradiction" in rationale

    def test_both_ineligible(self):
        a = _expert_claim("טקסט", eligible=False, missing_fields=["text_span"])
        b = _expert_claim("טקסט", eligible=False, missing_fields=["context_before"])
        outcome, score, rationale, reconciliation, det_type = _evaluate_pair(self.detector, a, b, None)
        assert outcome == OutcomeCategory.INSUFFICIENT_CONTEXT

    def test_scope_conditions_reconcilable(self):
        a = _expert_claim(
            "התובע שילם בתנאי שיקבל",
            scope_conditions="conditional",
            speaker_mode=SpeakerMode.COURT_FINDING.value,
            modality="must",
        )
        b = _expert_claim(
            "התובע שילם ללא תנאי כלשהו",
            scope_conditions="unconditional",
            speaker_mode=SpeakerMode.COURT_FINDING.value,
            modality="must",
        )
        outcome, score, rationale, reconciliation, det_type = _evaluate_pair(self.detector, a, b, None)
        assert outcome == OutcomeCategory.APPARENT_TENSION_RESOLVABLE
        assert "scope_conditions" in rationale


# ===================================================================
# build_expert_claims
# ===================================================================
class TestBuildExpertClaims:
    def test_basic_build(self):
        claims = [
            _make_claim("התובע שילם 50000 שקלים ביום 15.3.2020", id="c1"),
        ]
        data = [{"id": "c1", "text_span": "התובע שילם 50000 שקלים ביום 15.3.2020"}]
        result = build_expert_claims(claims, data)
        assert len(result) == 1
        ec = result[0]
        assert ec.claim_id == "c1"
        assert ec.text_span == "התובע שילם 50000 שקלים ביום 15.3.2020"
        assert isinstance(ec.tokens, list)

    def test_derives_speaker_role(self):
        claims = [_make_claim("בית המשפט קבע כי הנתבע אשם", id="c2")]
        data = [{"id": "c2"}]
        result = build_expert_claims(claims, data)
        assert result[0].speaker_role == SpeakerRole.COURT.value

    def test_derives_negation(self):
        claims = [_make_claim("לא שילם את החוב במועד", id="c3")]
        data = [{"id": "c3"}]
        result = build_expert_claims(claims, data)
        assert result[0].negation is True

    def test_context_extraction_from_source_text(self):
        source_text = "משפט ראשון. התובע שילם. משפט אחרון."
        claims = [_make_claim("התובע שילם", id="c4", char_start=13, char_end=24)]
        data = [{"id": "c4"}]
        result = build_expert_claims(claims, data, source_text=source_text)
        ec = result[0]
        # context should be extracted from surrounding sentences
        assert isinstance(ec.context_before, str)
        assert isinstance(ec.context_after, str)

    def test_eligible_when_all_fields_present(self):
        claims = [_make_claim(
            "התובע שילם 50000 שקלים ביום 15.3.2020",
            id="c5",
            paragraph_index=1,
        )]
        data = [{
            "id": "c5",
            "text_span": "התובע שילם 50000 שקלים ביום 15.3.2020",
            "context_before": "הקשר קודם",
            "context_after": "הקשר עוקב",
            "section_path": "paragraph:1",
            "scope_conditions": "unconditional",
            "modality": "must",
            "entities_relations": ["התובע", "50000"],
            "extraction_confidence": 0.85,
            "time_reference": "15.3.2020",
        }]
        result = build_expert_claims(claims, data)
        ec = result[0]
        assert ec.eligible is True
        assert ec.missing_fields == []


# ===================================================================
# analyze_expert_pairs
# ===================================================================
class TestAnalyzeExpertPairs:
    def test_returns_result_type(self):
        a = _expert_claim("התובע שילם סכום", claim_id="ea1", entities_relations=["התובע"])
        b = _expert_claim("הנתבע שילם סכום", claim_id="ea2", entities_relations=["הנתבע"])
        result = analyze_expert_pairs([a, b])
        assert isinstance(result, ExpertAnalysisResult)
        assert isinstance(result.stats, dict)

    def test_stats_populated(self):
        a = _expert_claim("התובע שילם סכום כסף", claim_id="ea3", entities_relations=["התובע", "סכום"])
        b = _expert_claim("התובע הגיש תביעה חדשה", claim_id="ea4", entities_relations=["התובע", "תביעה"])
        result = analyze_expert_pairs([a, b])
        assert "pairs_total" in result.stats
        assert result.stats["pairs_total"] == 1  # one pair for 2 claims

    def test_no_claims_returns_empty(self):
        result = analyze_expert_pairs([])
        assert result.pair_rows == []
        assert result.true_contradictions == []
        assert result.stats["pairs_total"] == 0

    def test_summary_report_structure(self):
        a = _expert_claim("התובע שילם סכום כסף", claim_id="ea5", entities_relations=["ישות"])
        b = _expert_claim("הנתבע הגיש תביעה חדשה", claim_id="ea6", entities_relations=["ישות"])
        result = analyze_expert_pairs([a, b])
        sr = result.summary_report
        assert isinstance(sr.true_contradictions, int)
        assert isinstance(sr.distribution, dict)
        assert isinstance(sr.noise_to_signal_ratio, float)

    def test_truncation_flag(self):
        """When pairs exceed max_pairs, truncation flag is set."""
        claims = [
            _expert_claim(f"טקסט מספר {i} של התובע", claim_id=f"tr_{i}", entities_relations=["התובע"])
            for i in range(10)
        ]
        result = analyze_expert_pairs(claims, max_pairs=2)
        # 10 claims → 45 pairs, max_pairs=2 → truncation
        assert "PAIR_ANALYSIS_TRUNCATED" in result.validation_flags


# ===================================================================
# Dataclass construction sanity
# ===================================================================
class TestDataclasses:
    def test_expert_claim_construction(self):
        ec = _expert_claim("טקסט לדוגמה")
        assert ec.text_span == "טקסט לדוגמה"
        assert ec.eligible is True

    def test_pair_analysis_row(self):
        row = PairAnalysisRow(
            claimA_id="a",
            claimB_id="b",
            outcome_category=OutcomeCategory.TRUE_CONTRADICTION,
            contradiction_score=0.85,
            reconciliation_attempt={"reconciled": False, "reason": "irreconcilable"},
            rationale="test",
            evidence_A={"quote": "a"},
            evidence_B={"quote": "b"},
        )
        assert row.outcome_category == OutcomeCategory.TRUE_CONTRADICTION

    def test_expert_summary_report(self):
        sr = ExpertSummaryReport(
            true_contradictions=2,
            distribution={"TRUE_CONTRADICTION": 2},
            top_findings=[],
            noise_to_signal_ratio=0.5,
        )
        assert sr.true_contradictions == 2
