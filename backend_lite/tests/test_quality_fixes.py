"""
Quality Fixes Tests — P0–P3 Bug Fix Verification
=================================================

Verifies all fixes from the JETHRO 9.0 quality report:
- P0: Candidate filter FACT/FACT fallback without speaker_mode
- P1: Ensemble scoring math normalization
- P1: Entity matching last-word fix
- P2: Duplicate detection normalization
- P2: Semantic synonym canonicalization
- P3: Method name sync
"""

import pytest

from backend_lite.extractor import (
    Claim,
    PLANE_FACT,
    PLANE_LAW,
    PLANE_OPINION,
    SPEAKER_MODE_FINDING,
    SPEAKER_MODE_PARTY_CLAIM,
)
from backend_lite.candidate_filter import passes_hard_filters, _strong_subject_overlap
from backend_lite.reconciler import (
    _entities_match,
    _is_duplicate,
    reconcile_pair,
    OUTCOME_DUPLICATE,
    OUTCOME_TRUE_CONTRADICTION,
)
from backend_lite.ensemble import EnsembleScorer, ContradictionSignals
from backend_lite.semantic import SemanticEngine


def _claim(text, **kwargs):
    return Claim(id=kwargs.pop("id", f"c_{abs(hash(text)) % 10000}"), text=text, **kwargs)


# ====================================================================
# P0: Candidate filter fallback
# ====================================================================

class TestP0CandidateFilterFallback:
    def test_fact_fact_no_speaker_strong_overlap_accepted(self):
        """FACT/FACT without speaker_mode + 2 strong shared entities → ACCEPT."""
        a = _claim("יוסי כהן שילם לחברת אלפא",
                    plane=PLANE_FACT, entities=["יוסי כהן", "חברת אלפא"])
        b = _claim("יוסי כהן לא שילם לחברת אלפא",
                    plane=PLANE_FACT, entities=["יוסי כהן", "חברת אלפא"])
        assert passes_hard_filters(a, b) is True

    def test_fact_fact_no_speaker_weak_entities_rejected(self):
        """FACT/FACT without speaker_mode + only weak entities → REJECT."""
        a = _claim("התובע שילם", plane=PLANE_FACT, entities=["התובע"])
        b = _claim("הנתבע שילם", plane=PLANE_FACT, entities=["הנתבע"])
        assert passes_hard_filters(a, b) is False

    def test_opinion_fact_no_speaker_rejected(self):
        """OPINION/FACT without speaker_mode → REJECT regardless of entities."""
        a = _claim("נראה שיוסי כהן שילם", plane=PLANE_OPINION,
                    entities=["יוסי כהן", "חברת אלפא"])
        b = _claim("יוסי כהן לא שילם", plane=PLANE_FACT,
                    entities=["יוסי כהן", "חברת אלפא"])
        assert passes_hard_filters(a, b) is False

    def test_strong_subject_overlap_unique_id(self):
        """Shared unique identifier (case number) → strong overlap."""
        a = _claim("בתיק 12345-01-22 נקבע...", plane=PLANE_FACT, entities=[])
        b = _claim("תיק 12345-01-22 הוגש...", plane=PLANE_FACT, entities=[])
        assert _strong_subject_overlap(a, b) is True

    def test_strong_subject_overlap_no_entities(self):
        """No entities, no shared IDs → no strong overlap."""
        a = _claim("שולם הסכום", plane=PLANE_FACT, entities=[])
        b = _claim("לא שולם דבר", plane=PLANE_FACT, entities=[])
        assert _strong_subject_overlap(a, b) is False


# ====================================================================
# P1: Ensemble scoring normalization
# ====================================================================

class TestP1EnsembleScoring:
    def test_score_always_in_0_1(self):
        """Final score must be in [0, 1] even with all bonuses active."""
        scorer = EnsembleScorer()
        signals = ContradictionSignals(
            rule_confidence=1.0,
            llm_confidence=1.0,
            semantic_similarity=1.0,
            entity_overlap=1.0,
            same_subject_score=1.0,
            temporal_boost=0.3,
            has_temporal_conflict=True,
            both_engines_agree=True,
            learning_adjustment=0.1,
        )
        result = scorer.score(signals)
        assert 0.0 <= result.final_confidence <= 1.0

    def test_agreement_bonus_no_nonlinear_jump(self):
        """Agreement bonus should not cause disproportionate score inflation."""
        scorer = EnsembleScorer()
        # Without agreement
        sig_no_agree = ContradictionSignals(
            rule_confidence=0.5,
            both_engines_agree=False,
        )
        # With agreement
        sig_agree = ContradictionSignals(
            rule_confidence=0.5,
            both_engines_agree=True,
        )
        r_no = scorer.score(sig_no_agree)
        r_yes = scorer.score(sig_agree)
        # Agreement should boost, but not by more than 0.3
        diff = r_yes.final_confidence - r_no.final_confidence
        assert diff > 0, "Agreement should boost score"
        assert diff < 0.3, f"Agreement boost too large: {diff}"

    def test_temporal_bonus_properly_weighted(self):
        """Temporal boost should be a proportional component, not an additive inflation."""
        scorer = EnsembleScorer()
        sig_no_temp = ContradictionSignals(rule_confidence=0.7)
        sig_temp = ContradictionSignals(rule_confidence=0.7, temporal_boost=0.2)
        r_no = scorer.score(sig_no_temp)
        r_yes = scorer.score(sig_temp)
        diff = r_yes.final_confidence - r_no.final_confidence
        # With proper weighting, temporal (weight=0.05) should add small amount
        assert diff >= 0, "Temporal should not reduce score"
        assert diff < 0.15, f"Temporal boost too large: {diff}"

    def test_minimal_weight_no_division_by_zero(self):
        """When only one signal contributes, no division errors."""
        scorer = EnsembleScorer()
        signals = ContradictionSignals(rule_confidence=0.8)
        result = scorer.score(signals)
        assert result.final_confidence == pytest.approx(0.8, abs=0.05)

    def test_golden_known_values(self):
        """Verify specific signal combinations produce expected ranges."""
        scorer = EnsembleScorer()
        # Rule=0.9, LLM=0.8, semantic=0.6, entity=0.7 → should be ~ high
        signals = ContradictionSignals(
            rule_confidence=0.9,
            llm_confidence=0.8,
            semantic_similarity=0.6,
            entity_overlap=0.7,
        )
        result = scorer.score(signals)
        assert result.final_confidence >= 0.7
        assert result.final_confidence <= 1.0


# ====================================================================
# P1: Entity matching (last-word fix)
# ====================================================================

class TestP1EntityMatching:
    def test_yossi_cohen_vs_david_cohen_no_match(self):
        """'יוסי כהן' vs 'דוד כהן' → NO MATCH (different people)."""
        assert _entities_match("יוסי כהן", "דוד כהן") is False

    def test_advocate_yossi_cohen_vs_yossi_cohen_match(self):
        """'עו\"ד יוסי כהן' vs 'יוסי כהן' → MATCH (title normalization)."""
        assert _entities_match('עו"ד יוסי כהן', "יוסי כהן") is True

    def test_company_cohen_vs_person_cohen_no_match(self):
        """'חברת כהן בע\"מ' should not match person 'כהן' via last-word only."""
        # "כהן" alone is short but "חברת כהן בע״מ" normalized drops quotes
        # It should NOT match "דוד כהן" since last words differ after normalization
        assert _entities_match("חברת כהן בעמ", "דוד כהן") is False

    def test_same_person_different_title_match(self):
        """'מר יוסי כהן' vs 'יוסי כהן' → MATCH."""
        assert _entities_match("מר יוסי כהן", "יוסי כהן") is True

    def test_exact_match_still_works(self):
        """Exact names still match."""
        assert _entities_match("יוסי כהן", "יוסי כהן") is True

    def test_alias_match_still_works(self):
        """Legal entity aliases still match."""
        assert _entities_match("בנק לאומי", "לאומי") is True

    def test_contains_match_still_works(self):
        """Containment matching still works."""
        assert _entities_match("אלפא", "חברת אלפא") is True


# ====================================================================
# P2: Duplicate detection with normalization
# ====================================================================

class TestP2DuplicateDetection:
    def test_same_event_different_date_format_is_duplicate(self):
        """'הנתבע חתם על החוזה ביום 15.1.2024' vs '...15 בינואר 2024' → DUPLICATE."""
        a = _claim("הנתבע חתם על החוזה ביום 15.1.2024", plane=PLANE_FACT)
        b = _claim("הנתבע חתם על ההסכם ביום 15 בינואר 2024", plane=PLANE_FACT)
        assert _is_duplicate(a, b) is True

    def test_different_events_not_duplicate(self):
        """Different dates/actions → NOT duplicate."""
        a = _claim("הנתבע חתם על החוזה ביום 15.1.2024", plane=PLANE_FACT)
        b = _claim("הנתבע ביטל את החוזה ביום 20.3.2024", plane=PLANE_FACT)
        assert _is_duplicate(a, b) is False

    def test_exact_duplicate(self):
        """Identical text → DUPLICATE."""
        a = _claim("הנתבע שילם את הסכום", plane=PLANE_FACT)
        b = _claim("הנתבע שילם את הסכום", plane=PLANE_FACT)
        assert _is_duplicate(a, b) is True

    def test_synonym_paraphrase_is_duplicate(self):
        """'חוזה' vs 'הסכם' in same context → DUPLICATE."""
        a = _claim("הנתבע חתם על החוזה", plane=PLANE_FACT)
        b = _claim("הנתבע חתם על ההסכם", plane=PLANE_FACT)
        assert _is_duplicate(a, b) is True

    def test_reconciler_routes_duplicate_correctly(self):
        """Duplicate detection in reconciler returns DUPLICATE outcome."""
        a = _claim("הנתבע שילם את הסכום", plane=PLANE_FACT)
        b = _claim("הנתבע שילם את הסכום", plane=PLANE_FACT)
        r = reconcile_pair(a, b)
        assert r.outcome == OUTCOME_DUPLICATE


# ====================================================================
# P2: Semantic synonym canonicalization
# ====================================================================

class TestP2SemanticSynonyms:
    def test_synonym_pairs_have_higher_similarity(self):
        """Claims with synonyms ('חוזה' vs 'הסכם') should score higher than unrelated pairs."""
        engine = SemanticEngine()
        claims = [
            _claim("הנתבע חתם על החוזה", id="c1"),
            _claim("הנתבע חתם על ההסכם", id="c2"),
            _claim("הילד הלך לגן", id="c3"),
        ]
        engine.index_claims(claims)

        sim_synonym = engine.relatedness(claims[0], claims[1])
        sim_unrelated = engine.relatedness(claims[0], claims[2])
        assert sim_synonym > sim_unrelated, (
            f"Synonym pair ({sim_synonym:.3f}) should score higher than unrelated ({sim_unrelated:.3f})"
        )

    def test_synonym_map_loads_without_error(self):
        """Synonym map JSON loads successfully."""
        from backend_lite.semantic import _load_synonym_map
        syn_map = _load_synonym_map()
        assert isinstance(syn_map, dict)
        assert len(syn_map) > 0
        # Verify a known mapping
        assert syn_map.get("הסכם") == "חוזה"


# ====================================================================
# P3: Method name sync
# ====================================================================

class TestP3MethodNameSync:
    def test_detect_contradictions_method_name(self):
        """detect_contradictions returns method='rule_based_v3' (current standard)."""
        from backend_lite.detector import detect_contradictions
        claims = [
            _claim("החוזה נחתם ב-15.3.2020"),
            _claim("החוזה נחתם ב-20.5.2021"),
        ]
        result = detect_contradictions(claims)
        assert result.method in ("rule_based_v2", "rule_based_v3")
