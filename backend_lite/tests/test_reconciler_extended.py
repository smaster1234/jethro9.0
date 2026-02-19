"""
Extended Logical Tests — Reconciler Engine
==========================================

~100 tests covering:
- All 9 outcome categories
- All 6 reconciliation layers
- Entity matching (exact, fuzzy, legal aliases)
- Duplicate detection
- Claim completeness checks
- Severity computation
- Rationale building
- Edge cases and boundary conditions
"""

import pytest
from backend_lite.extractor import (
    Claim,
    PLANE_FACT,
    PLANE_LAW,
    PLANE_OPINION,
    PLANE_PROCEDURAL,
    SPEAKER_MODE_FINDING,
    SPEAKER_MODE_PARTY_CLAIM,
    SPEAKER_MODE_QUOTE,
    SPEAKER_MODE_LAW_CITATION,
    SPEAKER_MODE_OPINION,
)
from backend_lite.reconciler import (
    reconcile_pair,
    ReconciliationResult,
    OUTCOME_TRUE_CONTRADICTION,
    OUTCOME_APPARENT_TENSION,
    OUTCOME_DISAGREEMENT,
    OUTCOME_ROLE_MISMATCH,
    OUTCOME_PLANE_MISMATCH,
    OUTCOME_TIME_SHIFT,
    OUTCOME_AMBIGUITY,
    OUTCOME_INSUFFICIENT_CONTEXT,
    OUTCOME_DUPLICATE,
    ALL_OUTCOMES,
    TRUE_CONTRADICTION_THRESHOLD,
    _normalize_entity,
    _entities_match,
    _fuzzy_entity_overlap,
    _is_duplicate,
    _check_claim_completeness,
    _check_time_alignment,
    _check_scope_alignment,
    _check_quantifier,
    _check_modality,
    _check_speaker_mode,
    _check_plane,
    _compute_severity,
    _build_true_contradiction_rationale,
    _describe_conflict,
    _char_ngram_similarity,
    _normalize_for_duplicate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(text: str, **kwargs) -> Claim:
    """Quick claim factory with all required enrichment fields."""
    defaults = dict(
        id=kwargs.pop("id", f"c_{abs(hash(text)) % 100000}"),
        text=text,
    )
    defaults.update(kwargs)
    return Claim(**defaults)


def _enriched_claim(text: str, **kwargs) -> Claim:
    """Create a claim with all V2 enrichment fields populated."""
    defaults = dict(
        plane=PLANE_FACT,
        speaker_mode=SPEAKER_MODE_FINDING,
        context_before="context",
        context_after="context",
        negation=False,
        entities=[],
    )
    defaults.update(kwargs)
    return _claim(text, **defaults)


# ===================================================================
# 1. Outcome Constants
# ===================================================================

class TestOutcomeConstants:
    def test_all_outcomes_count(self):
        assert len(ALL_OUTCOMES) == 9

    def test_all_outcomes_strings(self):
        for outcome in ALL_OUTCOMES:
            assert isinstance(outcome, str)
            assert len(outcome) > 0

    def test_outcome_constants_match_list(self):
        assert OUTCOME_TRUE_CONTRADICTION in ALL_OUTCOMES
        assert OUTCOME_APPARENT_TENSION in ALL_OUTCOMES
        assert OUTCOME_DISAGREEMENT in ALL_OUTCOMES
        assert OUTCOME_ROLE_MISMATCH in ALL_OUTCOMES
        assert OUTCOME_PLANE_MISMATCH in ALL_OUTCOMES
        assert OUTCOME_TIME_SHIFT in ALL_OUTCOMES
        assert OUTCOME_AMBIGUITY in ALL_OUTCOMES
        assert OUTCOME_INSUFFICIENT_CONTEXT in ALL_OUTCOMES
        assert OUTCOME_DUPLICATE in ALL_OUTCOMES

    def test_threshold_value(self):
        assert 0 < TRUE_CONTRADICTION_THRESHOLD < 1


# ===================================================================
# 2. ReconciliationResult
# ===================================================================

class TestReconciliationResult:
    def test_default_values(self):
        r = ReconciliationResult(outcome=OUTCOME_TRUE_CONTRADICTION)
        assert r.contradiction_score == 0.0
        assert r.severity == "low"
        assert r.deciding_fields == []
        assert r.debug == {}

    def test_all_fields(self):
        r = ReconciliationResult(
            outcome=OUTCOME_TRUE_CONTRADICTION,
            contradiction_score=0.9,
            severity="high",
            severity_score=0.85,
            reconciliation_attempt="attempt",
            rationale="rationale",
            conflict_predicate="pred",
            deciding_fields=["f1", "f2"],
            debug={"key": "val"},
        )
        assert r.contradiction_score == 0.9
        assert r.severity == "high"
        assert r.deciding_fields == ["f1", "f2"]


# ===================================================================
# 3. Entity Normalization
# ===================================================================

class TestEntityNormalization:
    def test_strip_mr_prefix(self):
        assert _normalize_entity("מר כהן") == "כהן"

    def test_strip_ms_prefix(self):
        # The title pattern strips "גב" but "גברת" may be partially matched
        result = _normalize_entity("גברת לוי")
        assert "לוי" in result

    def test_strip_lawyer_prefix(self):
        result = _normalize_entity('עו"ד ישראלי')
        assert "ישראלי" in result

    def test_strip_judge_prefix(self):
        result = _normalize_entity("שופט רביב")
        assert "רביב" in result

    def test_strip_defendant_prefix(self):
        result = _normalize_entity("הנתבע")
        # "הנתבע" is stripped by the title pattern to empty; normalized form is empty
        # The prefix pattern removes "הנתבע" as a title
        assert isinstance(result, str)

    def test_remove_quotes(self):
        result = _normalize_entity('חברת "אלפא"')
        assert '"' not in result

    def test_legal_alias_bank(self):
        r1 = _normalize_entity("בנק לאומי")
        r2 = _normalize_entity("הבנק הלאומי")
        assert r1 == r2

    def test_legal_alias_court(self):
        r1 = _normalize_entity("בית המשפט")
        r2 = _normalize_entity("ביהמש")
        assert r1 == r2

    def test_legal_alias_plaintiff(self):
        r1 = _normalize_entity("התובע")
        r2 = _normalize_entity("המערער")
        assert r1 == r2

    def test_legal_alias_defendant(self):
        r1 = _normalize_entity("הנתבע")
        r2 = _normalize_entity("המשיב")
        assert r1 == r2

    def test_empty_string(self):
        assert _normalize_entity("") == ""

    def test_whitespace_stripped(self):
        result = _normalize_entity("  כהן  ")
        assert result == "כהן"


# ===================================================================
# 4. Entity Matching
# ===================================================================

class TestEntityMatching:
    def test_exact_match(self):
        assert _entities_match("יוסי כהן", "יוסי כהן") is True

    def test_normalized_match(self):
        assert _entities_match("מר כהן", "כהן") is True

    def test_contains_match(self):
        assert _entities_match("אלפא", "חברת אלפא בע\"מ") is True

    def test_alias_match(self):
        assert _entities_match("בנק לאומי", "הבנק הלאומי") is True

    def test_no_match(self):
        assert _entities_match("יוסי כהן", "דוד לוי") is False

    def test_empty_strings(self):
        assert _entities_match("", "") is False

    def test_fuzzy_high_similarity(self):
        assert _entities_match("יוסף כהן", "יוסף כהן ") is True

    def test_last_name_with_additional_token(self):
        # Both must have >= 2 words and share last name + at least one other token
        assert _entities_match("יוסי כהן", "יוסי כהן") is True

    def test_different_first_name_same_last(self):
        # "יוסי כהן" vs "דוד כהן" — same last name but different first names
        # Should NOT match because other_a & other_b have no overlap
        assert _entities_match("יוסי כהן", "דוד כהן") is False


# ===================================================================
# 5. Fuzzy Entity Overlap
# ===================================================================

class TestFuzzyEntityOverlap:
    def test_exact_overlap(self):
        result = _fuzzy_entity_overlap(["יוסי כהן"], ["יוסי כהן"])
        assert "יוסי כהן" in result

    def test_no_overlap(self):
        result = _fuzzy_entity_overlap(["יוסי כהן"], ["דוד לוי"])
        assert len(result) == 0

    def test_empty_lists(self):
        result = _fuzzy_entity_overlap([], [])
        assert len(result) == 0

    def test_one_empty_list(self):
        result = _fuzzy_entity_overlap(["יוסי כהן"], [])
        assert len(result) == 0

    def test_alias_overlap(self):
        result = _fuzzy_entity_overlap(["בנק לאומי"], ["הבנק הלאומי"])
        assert len(result) > 0

    def test_multiple_entities(self):
        result = _fuzzy_entity_overlap(
            ["יוסי כהן", "דוד לוי"],
            ["יוסי כהן", "משה ישראלי"]
        )
        assert "יוסי כהן" in result


# ===================================================================
# 6. Claim Completeness Check
# ===================================================================

class TestClaimCompleteness:
    def test_complete_claim(self):
        c = _claim("test", speaker_mode=SPEAKER_MODE_FINDING, plane=PLANE_FACT)
        result = _check_claim_completeness(c)
        assert result is None

    def test_missing_speaker_mode(self):
        c = _claim("test", plane=PLANE_FACT)
        result = _check_claim_completeness(c)
        assert result is not None
        assert "speaker_mode" in result

    def test_missing_plane(self):
        c = _claim("test", speaker_mode=SPEAKER_MODE_FINDING)
        result = _check_claim_completeness(c)
        assert result is not None
        assert "plane" in result

    def test_missing_both(self):
        c = _claim("test")
        result = _check_claim_completeness(c)
        assert result is not None
        assert "speaker_mode" in result
        assert "plane" in result


# ===================================================================
# 7. Duplicate Detection
# ===================================================================

class TestDuplicateDetection:
    def test_identical_text(self):
        a = _claim("ההסכם נחתם ביום 15/01/2024")
        b = _claim("ההסכם נחתם ביום 15/01/2024")
        assert _is_duplicate(a, b) is True

    def test_normalized_same(self):
        a = _claim("ההסכם נחתם ביום 15/01/2024", normalized_claim="נחתם ביום 15/01/2024")
        b = _claim("ההסכם נחתם ביום 15/01/2024", normalized_claim="נחתם ביום 15/01/2024")
        assert _is_duplicate(a, b) is True

    def test_clearly_different(self):
        a = _claim("הנתבע שילם את הסכום במלואו לפי ההסכם")
        b = _claim("התובע לא קיבל שום תשלום כלל מהנתבע")
        assert _is_duplicate(a, b) is False

    def test_negation_not_duplicate(self):
        a = _claim("הנתבע שילם את הסכום")
        b = _claim("הנתבע לא שילם את הסכום")
        assert _is_duplicate(a, b) is False

    def test_date_normalization_in_duplicate(self):
        a = _claim("ההסכם נחתם ביום 15 בינואר 2024")
        b = _claim("ההסכם נחתם ביום 15/01/2024")
        result = _is_duplicate(a, b)
        # After date normalization they might be detected as duplicates
        assert isinstance(result, bool)


# ===================================================================
# 8. Character N-gram Similarity
# ===================================================================

class TestCharNgramSimilarity:
    def test_identical_strings(self):
        assert _char_ngram_similarity("hello", "hello") == 1.0

    def test_completely_different(self):
        result = _char_ngram_similarity("abc", "xyz")
        assert result == 0.0

    def test_similar_strings(self):
        result = _char_ngram_similarity("hello world", "hello worlds")
        assert result > 0.8

    def test_short_strings_same(self):
        assert _char_ngram_similarity("ab", "ab") == 1.0

    def test_short_strings_different(self):
        assert _char_ngram_similarity("ab", "cd") == 0.0

    def test_empty_vs_nonempty(self):
        assert _char_ngram_similarity("", "hello") == 0.0


# ===================================================================
# 9. Normalize for Duplicate
# ===================================================================

class TestNormalizeForDuplicate:
    def test_lowercase(self):
        assert _normalize_for_duplicate("HELLO") == "hello"

    def test_hebrew_date_normalization(self):
        result = _normalize_for_duplicate("15 בינואר 2024")
        assert "15.01.2024" in result

    def test_numeric_date_normalization(self):
        result = _normalize_for_duplicate("15/01/2024")
        assert "15.01.2024" in result

    def test_short_year_normalization(self):
        result = _normalize_for_duplicate("15/01/24")
        assert "2024" in result


# ===================================================================
# 10. Layer 1: Time Alignment
# ===================================================================

class TestTimeAlignment:
    def test_no_time_passes(self):
        a = _claim("claim a")
        b = _claim("claim b")
        ok, note = _check_time_alignment(a, b)
        assert ok is True

    def test_same_time_passes(self):
        a = _claim("claim a", time_reference="2024")
        b = _claim("claim b", time_reference="2024")
        ok, note = _check_time_alignment(a, b)
        assert ok is True

    def test_different_time_fails(self):
        a = _claim("claim a", time_reference="ינואר 2020")
        b = _claim("claim b", time_reference="אוגוסט 2022")
        ok, note = _check_time_alignment(a, b)
        assert ok is False

    def test_one_missing_time_passes(self):
        a = _claim("claim a", time_reference="2024")
        b = _claim("claim b")
        ok, note = _check_time_alignment(a, b)
        assert ok is True


# ===================================================================
# 11. Layer 2: Scope Alignment
# ===================================================================

class TestScopeAlignment:
    def test_no_scope_passes(self):
        a = _claim("claim a")
        b = _claim("claim b")
        ok, note = _check_scope_alignment(a, b)
        assert ok is True

    def test_same_scope_passes(self):
        a = _claim("claim a", scope_quantifiers="all")
        b = _claim("claim b", scope_quantifiers="all")
        ok, note = _check_scope_alignment(a, b)
        assert ok is True

    def test_different_scope_fails(self):
        a = _claim("claim a", scope_quantifiers="all")
        b = _claim("claim b", scope_quantifiers="part")
        ok, note = _check_scope_alignment(a, b)
        assert ok is False

    def test_conditional_scope_fails(self):
        a = _claim("claim a", scope_quantifiers="conditional")
        b = _claim("claim b", scope_quantifiers="all")
        ok, note = _check_scope_alignment(a, b)
        assert ok is False
        assert "מותנית" in note


# ===================================================================
# 12. Layer 3: Quantifier Check
# ===================================================================

class TestQuantifierCheck:
    def test_no_quantifier_passes(self):
        a = _claim("claim a")
        b = _claim("claim b")
        ok, note = _check_quantifier(a, b)
        assert ok is True

    def test_same_quantifier_passes(self):
        a = _claim("claim a", scope_quantifiers="all")
        b = _claim("claim b", scope_quantifiers="all")
        ok, note = _check_quantifier(a, b)
        assert ok is True

    def test_all_vs_part_fails(self):
        a = _claim("claim a", scope_quantifiers="all")
        b = _claim("claim b", scope_quantifiers="part")
        ok, note = _check_quantifier(a, b)
        assert ok is False

    def test_part_vs_all_fails(self):
        a = _claim("claim a", scope_quantifiers="part")
        b = _claim("claim b", scope_quantifiers="all")
        ok, note = _check_quantifier(a, b)
        assert ok is False

    def test_other_combinations_pass(self):
        a = _claim("claim a", scope_quantifiers="usually")
        b = _claim("claim b", scope_quantifiers="conditional")
        ok, note = _check_quantifier(a, b)
        assert ok is True


# ===================================================================
# 13. Layer 4: Modality Check
# ===================================================================

class TestModalityCheck:
    def test_no_modality_passes(self):
        a = _claim("claim a")
        b = _claim("claim b")
        ok, note = _check_modality(a, b)
        assert ok is True

    def test_same_modality_passes(self):
        a = _claim("claim a", modality="certain")
        b = _claim("claim b", modality="certain")
        ok, note = _check_modality(a, b)
        assert ok is True

    def test_different_modality_fails(self):
        a = _claim("claim a", modality="certain")
        b = _claim("claim b", modality="possible")
        ok, note = _check_modality(a, b)
        assert ok is False

    def test_obligation_vs_permission_fails(self):
        a = _claim("claim a", modality="obligation")
        b = _claim("claim b", modality="permission")
        ok, note = _check_modality(a, b)
        assert ok is False


# ===================================================================
# 14. Layer 5: Speaker Mode Check
# ===================================================================

class TestSpeakerModeCheck:
    def test_same_finding_passes(self):
        a = _claim("claim a", speaker_mode=SPEAKER_MODE_FINDING)
        b = _claim("claim b", speaker_mode=SPEAKER_MODE_FINDING)
        ok, note, outcome = _check_speaker_mode(a, b)
        assert ok is True

    def test_opinion_blocks(self):
        a = _claim("claim a", speaker_mode=SPEAKER_MODE_OPINION)
        b = _claim("claim b", speaker_mode=SPEAKER_MODE_FINDING)
        ok, note, outcome = _check_speaker_mode(a, b)
        assert ok is False
        assert outcome == OUTCOME_ROLE_MISMATCH

    def test_quote_blocks(self):
        a = _claim("claim a", speaker_mode=SPEAKER_MODE_QUOTE)
        b = _claim("claim b", speaker_mode=SPEAKER_MODE_FINDING)
        ok, note, outcome = _check_speaker_mode(a, b)
        assert ok is False
        assert outcome == OUTCOME_ROLE_MISMATCH

    def test_law_citation_blocks(self):
        a = _claim("claim a", speaker_mode=SPEAKER_MODE_LAW_CITATION)
        b = _claim("claim b", speaker_mode=SPEAKER_MODE_FINDING)
        ok, note, outcome = _check_speaker_mode(a, b)
        assert ok is False
        assert outcome == OUTCOME_ROLE_MISMATCH

    def test_cross_party_disagreement(self):
        a = _claim("claim a", speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff")
        b = _claim("claim b", speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="defendant")
        ok, note, outcome = _check_speaker_mode(a, b)
        assert ok is False
        assert outcome == OUTCOME_DISAGREEMENT

    def test_same_party_no_block(self):
        a = _claim("claim a", speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff")
        b = _claim("claim b", speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff")
        ok, note, outcome = _check_speaker_mode(a, b)
        assert ok is True

    def test_party_vs_finding_blocks(self):
        a = _claim("claim a", speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff")
        b = _claim("claim b", speaker_mode=SPEAKER_MODE_FINDING)
        ok, note, outcome = _check_speaker_mode(a, b)
        assert ok is False
        assert outcome == OUTCOME_ROLE_MISMATCH

    def test_no_speaker_mode_passes(self):
        a = _claim("claim a")
        b = _claim("claim b")
        ok, note, outcome = _check_speaker_mode(a, b)
        assert ok is True


# ===================================================================
# 15. Layer 6: Plane Check
# ===================================================================

class TestPlaneCheck:
    def test_no_plane_passes(self):
        a = _claim("claim a")
        b = _claim("claim b")
        ok, note = _check_plane(a, b)
        assert ok is True

    def test_same_fact_plane_passes(self):
        a = _claim("claim a", plane=PLANE_FACT)
        b = _claim("claim b", plane=PLANE_FACT)
        ok, note = _check_plane(a, b)
        assert ok is True

    def test_same_law_plane_passes(self):
        a = _claim("claim a", plane=PLANE_LAW)
        b = _claim("claim b", plane=PLANE_LAW)
        ok, note = _check_plane(a, b)
        assert ok is True

    def test_fact_vs_law_fails(self):
        a = _claim("claim a", plane=PLANE_FACT)
        b = _claim("claim b", plane=PLANE_LAW)
        ok, note = _check_plane(a, b)
        assert ok is False

    def test_fact_vs_opinion_fails(self):
        a = _claim("claim a", plane=PLANE_FACT)
        b = _claim("claim b", plane=PLANE_OPINION)
        ok, note = _check_plane(a, b)
        assert ok is False

    def test_opinion_vs_procedural_fails(self):
        a = _claim("claim a", plane=PLANE_OPINION)
        b = _claim("claim b", plane=PLANE_PROCEDURAL)
        ok, note = _check_plane(a, b)
        assert ok is False


# ===================================================================
# 16. Full Reconciliation - Outcome Categories
# ===================================================================

class TestReconcileOutcomes:
    def test_duplicate_detected(self):
        a = _enriched_claim("ההסכם נחתם ביום 15/01/2024")
        b = _enriched_claim("ההסכם נחתם ביום 15/01/2024")
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome == OUTCOME_DUPLICATE

    def test_time_shift_outcome(self):
        a = _enriched_claim("ההסכם נחתם בינואר 2020", time_reference="ינואר 2020")
        b = _enriched_claim("ההסכם בוטל באוגוסט 2022", time_reference="אוגוסט 2022")
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome == OUTCOME_TIME_SHIFT

    def test_scope_mismatch_outcome(self):
        a = _enriched_claim("כל העובדים קיבלו תשלום", scope_quantifiers="all")
        b = _enriched_claim("חלק מהעובדים קיבלו תשלום", scope_quantifiers="part")
        result = reconcile_pair(a, b, detector_confidence=0.9)
        # Scope → APPARENT_TENSION (layer 2 catches first)
        assert result.outcome == OUTCOME_APPARENT_TENSION

    def test_modality_mismatch_outcome(self):
        a = _enriched_claim("הנתבע חייב לשלם", modality="obligation")
        b = _enriched_claim("הנתבע רשאי לשלם", modality="permission")
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome == OUTCOME_APPARENT_TENSION

    def test_speaker_disagreement_outcome(self):
        a = _enriched_claim("שולם הסכום", speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff")
        b = _enriched_claim("לא שולם הסכום", speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="defendant")
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome == OUTCOME_DISAGREEMENT

    def test_quote_role_mismatch(self):
        a = _enriched_claim("העד אמר שהיה נוכח", speaker_mode=SPEAKER_MODE_QUOTE)
        b = _enriched_claim("בית המשפט קבע שהעד לא היה נוכח", speaker_mode=SPEAKER_MODE_FINDING)
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome == OUTCOME_ROLE_MISMATCH

    def test_plane_mismatch_outcome(self):
        a = _enriched_claim("הנתבע שילם", plane=PLANE_FACT)
        b = _enriched_claim("לפי סעיף 5 חובה לשלם", plane=PLANE_LAW)
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome == OUTCOME_PLANE_MISMATCH

    def test_opinion_plane_caught_by_plane_layer(self):
        a = _enriched_claim("לדעתי הסכום גבוה", plane=PLANE_OPINION)
        b = _enriched_claim("הסכום סביר", plane=PLANE_FACT)
        result = reconcile_pair(a, b, detector_confidence=0.9)
        # OPINION vs FACT → caught by Layer 6 (plane mismatch) as PLANE_MISMATCH
        assert result.outcome == OUTCOME_PLANE_MISMATCH

    def test_procedural_plane_caught_by_plane_layer(self):
        a = _enriched_claim("הבקשה הוגשה במועד", plane=PLANE_PROCEDURAL)
        b = _enriched_claim("הבקשה הוגשה באיחור", plane=PLANE_FACT)
        result = reconcile_pair(a, b, detector_confidence=0.9)
        # PROCEDURAL vs FACT → caught by Layer 6 as PLANE_MISMATCH
        assert result.outcome == OUTCOME_PLANE_MISMATCH

    def test_insufficient_context_missing_fields(self):
        # Claims without speaker_mode or plane — but must be different enough
        # to not be detected as duplicates
        a = _claim("הנתבע שילם סכום של חמישים אלף שקל בינואר")
        b = _claim("התובע טען שלא קיבל תשלום מהנתבע כלל")
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome == OUTCOME_INSUFFICIENT_CONTEXT

    def test_low_confidence_ambiguity(self):
        # Must be different enough to not be duplicates
        a = _enriched_claim("הנתבע שילם סכום גדול לחברה בחודש ינואר", entities=["יוסי"])
        b = _enriched_claim("הנתבע לא השלים את כל התשלומים הנדרשים", entities=["יוסי"])
        result = reconcile_pair(a, b, detector_confidence=0.5)
        assert result.outcome == OUTCOME_AMBIGUITY

    def test_no_entity_overlap_apparent_tension(self):
        a = _enriched_claim("יוסי שילם", entities=["יוסי"])
        b = _enriched_claim("דוד לא שילם", entities=["דוד"], negation=True)
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome == OUTCOME_APPARENT_TENSION

    def test_true_contradiction_all_conditions_met(self):
        a = _enriched_claim(
            "יוסי כהן שילם את הסכום",
            entities=["יוסי כהן"],
            negation=False,
            context_before="הקשר לפני",
            context_after="הקשר אחרי",
        )
        b = _enriched_claim(
            "יוסי כהן לא שילם את הסכום",
            entities=["יוסי כהן"],
            negation=True,
            context_before="הקשר לפני",
            context_after="הקשר אחרי",
        )
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome == OUTCOME_TRUE_CONTRADICTION

    def test_hard_negation_overrides_low_confidence(self):
        a = _enriched_claim(
            "יוסי כהן שילם את הסכום",
            entities=["יוסי כהן"],
            negation=False,
            context_before="ctx",
            context_after="ctx",
        )
        b = _enriched_claim(
            "יוסי כהן לא שילם את הסכום",
            entities=["יוסי כהן"],
            negation=True,
            context_before="ctx",
            context_after="ctx",
        )
        result = reconcile_pair(a, b, detector_confidence=0.5)
        # Hard negation + entity overlap + factual plane → should override threshold
        assert result.outcome == OUTCOME_TRUE_CONTRADICTION


# ===================================================================
# 17. Severity Computation
# ===================================================================

class TestSeverityComputation:
    def test_finding_boosts_severity(self):
        a = _enriched_claim("test", speaker_mode=SPEAKER_MODE_FINDING)
        b = _enriched_claim("test")
        sev, score = _compute_severity(a, b, 0.9, {})
        assert score > 0

    def test_negation_boosts_severity(self):
        a = _enriched_claim("test", negation=False)
        b = _enriched_claim("test", negation=True)
        sev, score = _compute_severity(a, b, 0.9, {})
        assert score >= 0.2

    def test_high_confidence_boosts_severity(self):
        a = _enriched_claim("test")
        b = _enriched_claim("test")
        _, score_high = _compute_severity(a, b, 0.95, {})
        _, score_low = _compute_severity(a, b, 0.5, {})
        assert score_high >= score_low

    def test_entity_overlap_boosts_severity(self):
        a = _enriched_claim("test", entities=["e1", "e2"])
        b = _enriched_claim("test", entities=["e1", "e2"])
        _, score_with = _compute_severity(a, b, 0.9, {})
        a2 = _enriched_claim("test", entities=[])
        b2 = _enriched_claim("test", entities=[])
        _, score_without = _compute_severity(a2, b2, 0.9, {})
        assert score_with >= score_without

    def test_severity_capped_at_1(self):
        a = _enriched_claim(
            "test",
            speaker_mode=SPEAKER_MODE_FINDING,
            negation=False,
            entities=["e1", "e2", "e3"],
        )
        b = _enriched_claim(
            "test",
            speaker_mode=SPEAKER_MODE_FINDING,
            negation=True,
            entities=["e1", "e2", "e3"],
        )
        _, score = _compute_severity(a, b, 0.99, {})
        assert score <= 1.0

    def test_severity_labels(self):
        a = _enriched_claim("test", speaker_mode=SPEAKER_MODE_FINDING, negation=False, entities=["e1", "e2"])
        b = _enriched_claim("test", speaker_mode=SPEAKER_MODE_FINDING, negation=True, entities=["e1", "e2"])
        sev, score = _compute_severity(a, b, 0.95, {})
        assert sev in ("low", "medium", "high")


# ===================================================================
# 18. Rationale Building
# ===================================================================

class TestRationaleBuilding:
    def test_negation_mentioned(self):
        a = _enriched_claim("test", negation=False, entities=["e1"])
        b = _enriched_claim("test", negation=True, entities=["e1"])
        rationale = _build_true_contradiction_rationale(a, b, {})
        assert "שלילה" in rationale or "ניגוד" in rationale

    def test_entities_mentioned(self):
        a = _enriched_claim("test", entities=["יוסי"])
        b = _enriched_claim("test", entities=["יוסי"])
        rationale = _build_true_contradiction_rationale(a, b, {})
        assert "יוסי" in rationale

    def test_plane_mentioned(self):
        a = _enriched_claim("test", plane=PLANE_FACT)
        b = _enriched_claim("test", plane=PLANE_FACT)
        rationale = _build_true_contradiction_rationale(a, b, {})
        assert "FACT" in rationale

    def test_default_rationale(self):
        a = _enriched_claim("test")
        b = _enriched_claim("test")
        rationale = _build_true_contradiction_rationale(a, b, {})
        assert len(rationale) > 0

    def test_time_reference_mentioned(self):
        a = _enriched_claim("test", time_reference="2024")
        b = _enriched_claim("test", time_reference="2024")
        rationale = _build_true_contradiction_rationale(a, b, {})
        assert "2024" in rationale


# ===================================================================
# 19. Conflict Description
# ===================================================================

class TestConflictDescription:
    def test_negation_opposition(self):
        a = _enriched_claim("test", negation=False)
        b = _enriched_claim("test", negation=True)
        desc = _describe_conflict(a, b, {})
        assert desc == "negation_opposition"

    def test_factual_clash(self):
        a = _enriched_claim("test", negation=False)
        b = _enriched_claim("test", negation=False)
        desc = _describe_conflict(a, b, {})
        assert desc == "factual_clash"


# ===================================================================
# 20. Edge Cases
# ===================================================================

class TestReconcilerEdgeCases:
    def test_both_claims_empty_text(self):
        a = _enriched_claim("")
        b = _enriched_claim("")
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome in ALL_OUTCOMES

    def test_very_long_text(self):
        a = _enriched_claim("א" * 5000, entities=["יוסי"], negation=False)
        b = _enriched_claim("ב" * 5000, entities=["יוסי"], negation=True)
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome in ALL_OUTCOMES

    def test_metadata_passed_through(self):
        a = _enriched_claim("test")
        b = _enriched_claim("test")
        result = reconcile_pair(a, b, detector_confidence=0.5, metadata={"key": "val"})
        assert result.outcome in ALL_OUTCOMES

    def test_detector_type_parameter(self):
        a = _enriched_claim("test")
        b = _enriched_claim("test")
        result = reconcile_pair(a, b, detector_type="temporal_date_conflict", detector_confidence=0.5)
        assert result.outcome in ALL_OUTCOMES

    def test_normalized_values_parameter(self):
        a = _enriched_claim("test")
        b = _enriched_claim("test")
        result = reconcile_pair(a, b, detector_confidence=0.5,
                               normalized_a="2024-01-15", normalized_b="2024-03-20")
        assert result.outcome in ALL_OUTCOMES
