"""
Unit Tests — Contradiction Analysis V2
=======================================

Covers the edge-cases required by §7.1:
  1. Time shift NOT flagged as TRUE_CONTRADICTION
  2. Party disagreement flagged as DISAGREEMENT_BETWEEN_PARTIES
  3. Plane mismatch flagged correctly
  4. Quantifier mismatch ("all" vs "part") detected
  5. Negation ("was" vs "was not") detected
  6. Scope / condition ("if X then…" vs "when not-X…") detected
  7. Claim enrichment populates v2 fields
  8. Candidate hard-filter rejects incompatible planes
  9. Reconciler returns correct 7-category outcome
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
)
from backend_lite.claim_enricher import (
    enrich_claims,
    resolve_entities,
    _detect_plane,
    _detect_speaker,
    _detect_negation,
    _detect_modality,
    _detect_scope,
    _detect_time_reference,
    _extract_entities,
)
from backend_lite.reconciler import (
    reconcile_pair,
    OUTCOME_TRUE_CONTRADICTION,
    OUTCOME_APPARENT_TENSION,
    OUTCOME_DISAGREEMENT,
    OUTCOME_PLANE_MISMATCH,
    OUTCOME_TIME_SHIFT,
    OUTCOME_AMBIGUITY,
    OUTCOME_DUPLICATE,
)
from backend_lite.candidate_filter import (
    passes_hard_filters,
    generate_candidate_pairs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(text: str, **kwargs) -> Claim:
    """Quick claim factory."""
    return Claim(
        id=kwargs.pop("id", f"c_{abs(hash(text)) % 10000}"),
        text=text,
        **kwargs,
    )


# ====================================================================
# §7.1 — Test 1: Time shift NOT flagged as contradiction
# ====================================================================

class TestTimeShift:
    def test_different_time_references_yield_time_shift(self):
        a = _claim("ההסכם נחתם בינואר 2020", time_reference="בינואר 2020", plane=PLANE_FACT)
        b = _claim("ההסכם בוטל באוגוסט 2022", time_reference="באוגוסט 2022", plane=PLANE_FACT)
        result = reconcile_pair(a, b, detector_confidence=0.8)
        assert result.outcome == OUTCOME_TIME_SHIFT
        assert result.outcome != OUTCOME_TRUE_CONTRADICTION

    def test_same_time_reference_not_shifted(self):
        a = _claim("שולם סכום של 100,000 ₪ ביום 1.1.2020", time_reference="1.1.2020", plane=PLANE_FACT, negation=False)
        b = _claim("לא שולם סכום ביום 1.1.2020", time_reference="1.1.2020", plane=PLANE_FACT, negation=True)
        result = reconcile_pair(a, b, detector_confidence=0.9)
        # Same time → should NOT be time-shifted
        assert result.outcome != OUTCOME_TIME_SHIFT


# ====================================================================
# §7.1 — Test 2: Party disagreement
# ====================================================================

class TestPartyDisagreement:
    def test_cross_party_claims_yield_disagreement(self):
        a = _claim("התובע טען שהחוזה בוטל", speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff", plane=PLANE_FACT)
        b = _claim("הנתבע טען שהחוזה תקף", speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="defendant", plane=PLANE_FACT)
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome == OUTCOME_DISAGREEMENT

    def test_same_party_claims_not_disagreement(self):
        a = _claim("התובע טען שנפגע", speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff", plane=PLANE_FACT, negation=False)
        b = _claim("התובע הצהיר שלא נפגע", speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff", plane=PLANE_FACT, negation=True)
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome != OUTCOME_DISAGREEMENT


# ====================================================================
# §7.1 — Test 3: Plane mismatch
# ====================================================================

class TestPlaneMismatch:
    def test_fact_vs_law_yields_plane_mismatch(self):
        a = _claim("התשלום בוצע ביום 15.1.2020", plane=PLANE_FACT)
        b = _claim("סעיף 5 לחוק קובע חובת תשלום", plane=PLANE_LAW)
        result = reconcile_pair(a, b, detector_confidence=0.8)
        assert result.outcome == OUTCOME_PLANE_MISMATCH

    def test_fact_vs_opinion_yields_plane_mismatch(self):
        a = _claim("הנתבע שילם 50,000 ₪", plane=PLANE_FACT)
        b = _claim("ייתכן שהתשלום אינו מספיק", plane=PLANE_OPINION)
        result = reconcile_pair(a, b, detector_confidence=0.7)
        assert result.outcome == OUTCOME_PLANE_MISMATCH

    def test_fact_vs_fact_no_plane_mismatch(self):
        a = _claim("הנתבע שילם 50,000 ₪", plane=PLANE_FACT, negation=False)
        b = _claim("הנתבע לא שילם דבר", plane=PLANE_FACT, negation=True)
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome != OUTCOME_PLANE_MISMATCH


# ====================================================================
# §7.1 — Test 4: Quantifier mismatch ("all" vs "part")
# ====================================================================

class TestQuantifierMismatch:
    def test_all_vs_part_yields_apparent_tension(self):
        a = _claim("כל העובדים קיבלו פיצוי", scope_quantifiers="all", plane=PLANE_FACT)
        b = _claim("חלק מהעובדים לא קיבלו פיצוי", scope_quantifiers="part", plane=PLANE_FACT)
        result = reconcile_pair(a, b, detector_confidence=0.8)
        assert result.outcome == OUTCOME_APPARENT_TENSION

    def test_same_quantifier_not_apparent_tension(self):
        a = _claim("כל העובדים קיבלו פיצוי", scope_quantifiers="all", plane=PLANE_FACT, negation=False)
        b = _claim("כל העובדים לא קיבלו פיצוי", scope_quantifiers="all", plane=PLANE_FACT, negation=True)
        result = reconcile_pair(a, b, detector_confidence=0.9)
        # Same quantifier, opposite negation → not resolved by quantifier
        assert result.outcome != OUTCOME_APPARENT_TENSION or result.outcome == OUTCOME_TRUE_CONTRADICTION


# ====================================================================
# §7.1 — Test 5: Negation detection
# ====================================================================

class TestNegation:
    def test_negation_detected_in_text(self):
        assert _detect_negation("הנתבע לא שילם את החוב") is True

    def test_no_negation_in_affirmative(self):
        assert _detect_negation("הנתבע שילם את החוב") is False

    def test_strong_negation_pattern(self):
        assert _detect_negation("מעולם לא הסכים לכך") is True


# ====================================================================
# §7.1 — Test 6: Scope / condition detection
# ====================================================================

class TestScopeCondition:
    def test_conditional_vs_unconditional_yields_apparent_tension(self):
        a = _claim("אם הנתבע ישלם, ההסכם יהיה תקף", scope_quantifiers="conditional", plane=PLANE_FACT)
        b = _claim("ההסכם תקף ללא תנאי", scope_quantifiers="all", plane=PLANE_FACT)
        result = reconcile_pair(a, b, detector_confidence=0.8)
        assert result.outcome == OUTCOME_APPARENT_TENSION


# ====================================================================
# Claim enrichment — v2 fields
# ====================================================================

class TestClaimEnrichment:
    def test_plane_detection_fact(self):
        assert _detect_plane("התשלום בוצע ביום 1.1.2020") == PLANE_FACT

    def test_plane_detection_law(self):
        assert _detect_plane("סעיף 5 לחוק קובע חובת תשלום") == PLANE_LAW

    def test_plane_detection_opinion(self):
        assert _detect_plane("נראה כי הסכום אינו מספיק") == PLANE_OPINION

    def test_plane_detection_procedural(self):
        assert _detect_plane("הוגשה תביעה ביום 15.3.2021") == PLANE_PROCEDURAL

    def test_speaker_detection_party_claim(self):
        role, mode = _detect_speaker("לטענת התובע הנזק היה כבד")
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_speaker_detection_finding(self):
        role, mode = _detect_speaker("בית המשפט קובע כי הנתבע חב בפיצוי")
        assert mode == SPEAKER_MODE_FINDING
        assert role == "court"

    def test_speaker_detection_quote(self):
        role, mode = _detect_speaker('נאמר כי "הנתבע לא שילם"')
        assert mode == SPEAKER_MODE_QUOTE

    def test_time_reference_detection(self):
        assert _detect_time_reference("החוזה נחתם ביום 15.3.2020") is not None

    def test_modality_obligation(self):
        assert _detect_modality("על הנתבע לשלם את הסכום") == "obligation"

    def test_modality_possibility(self):
        assert _detect_modality("ייתכן שהתשלום יבוצע") == "possible"

    def test_scope_detection_all(self):
        assert _detect_scope("כל העובדים קיבלו פיצוי") == "all"

    def test_scope_detection_part(self):
        assert _detect_scope("חלק מהעובדים לא קיבלו") == "part"

    def test_scope_detection_conditional(self):
        assert _detect_scope("בתנאי שישולם הסכום") == "conditional"

    def test_entity_extraction(self):
        entities = _extract_entities("התובע הגיש תביעה לפי סעיף 5 לחוק")
        assert any("תובע" in e for e in entities)
        assert any("סעיף" in e for e in entities)

    def test_enrich_claims_populates_fields(self):
        c = _claim("בית המשפט קובע כי הנתבע שילם 50,000 ₪ ביום 1.1.2020", char_start=0, char_end=50)
        enrich_claims([c], full_text="בית המשפט קובע כי הנתבע שילם 50,000 ₪ ביום 1.1.2020")
        assert c.plane is not None
        assert c.speaker_mode is not None
        assert c.normalized_claim is not None
        assert c.confidence_extraction > 0

    def test_entity_resolution_aliases(self):
        c1 = _claim("המשיב טען", entities=["המשיב"])
        c2 = _claim("הנתבע טען", entities=["הנתבע"])
        resolve_entities([c1, c2])
        assert c1.entities == ["הנתבע"]
        assert c2.entities == ["הנתבע"]


# ====================================================================
# Candidate hard-filter
# ====================================================================

class TestCandidateFilter:
    def test_different_planes_rejected(self):
        a = _claim("עובדה", plane=PLANE_FACT, entities=["הנתבע"])
        b = _claim("סעיף 5 לחוק", plane=PLANE_LAW, entities=["הנתבע"])
        assert passes_hard_filters(a, b) is False

    def test_same_plane_accepted(self):
        a = _claim("הנתבע שילם", plane=PLANE_FACT, entities=["הנתבע"])
        b = _claim("הנתבע לא שילם", plane=PLANE_FACT, entities=["הנתבע"])
        assert passes_hard_filters(a, b) is True

    def test_cross_party_disagreement_rejected(self):
        a = _claim("שילם", speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff", plane=PLANE_FACT, entities=["הנתבע"])
        b = _claim("לא שילם", speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="defendant", plane=PLANE_FACT, entities=["הנתבע"])
        assert passes_hard_filters(a, b) is False


# ====================================================================
# Reconciler — 7-category outcomes
# ====================================================================

class TestReconcilerOutcomes:
    def test_duplicate_detection(self):
        a = _claim("הנתבע שילם את הסכום", plane=PLANE_FACT)
        b = _claim("הנתבע שילם את הסכום", plane=PLANE_FACT)
        r = reconcile_pair(a, b)
        assert r.outcome == OUTCOME_DUPLICATE

    def test_true_contradiction(self):
        a = _claim("הנתבע שילם 100,000 ₪", plane=PLANE_FACT, negation=False, entities=["הנתבע"])
        b = _claim("הנתבע לא שילם דבר", plane=PLANE_FACT, negation=True, entities=["הנתבע"])
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION

    def test_low_confidence_yields_ambiguity(self):
        a = _claim("אולי הנתבע שילם", plane=PLANE_FACT)
        b = _claim("אולי הנתבע לא שילם", plane=PLANE_FACT)
        r = reconcile_pair(a, b, detector_confidence=0.3)
        assert r.outcome == OUTCOME_AMBIGUITY

    def test_modality_mismatch_yields_apparent_tension(self):
        a = _claim("הנתבע חייב לשלם", modality="obligation", plane=PLANE_FACT)
        b = _claim("ייתכן שהנתبע ישלם", modality="possible", plane=PLANE_FACT)
        r = reconcile_pair(a, b, detector_confidence=0.8)
        assert r.outcome == OUTCOME_APPARENT_TENSION


# ====================================================================
# Integration: enrichment → filter → reconcile
# ====================================================================

class TestIntegration:
    def test_full_pipeline_no_crash(self):
        """Smoke test: enrich → filter → reconcile without errors."""
        claims = [
            _claim("ההסכם נחתם ביום 1.1.2020 על ידי הנתבע", char_start=0, char_end=40),
            _claim("הנתבע טען שההסכם לא נחתם מעולם", char_start=50, char_end=80),
        ]
        full_text = "ההסכם נחתם ביום 1.1.2020 על ידי הנתבע. הנתבע טען שההסכם לא נחתם מעולם."
        enrich_claims(claims, full_text)
        resolve_entities(claims)

        pairs = generate_candidate_pairs(claims)
        results = [reconcile_pair(a, b, detector_confidence=0.8) for a, b in pairs]

        # Should not crash, should produce results
        assert isinstance(results, list)
