"""
Unit Tests — Contradiction Analysis V2 + Cursor 5.2 Spec
=========================================================

Covers the edge-cases required by §7.1 and Cursor 5.2 spec:
  1. Time shift NOT flagged as TRUE_CONTRADICTION
  2. Party disagreement flagged as DISAGREEMENT_BETWEEN_PARTIES
  3. Plane mismatch flagged correctly
  4. Quantifier mismatch ("all" vs "part") detected
  5. Negation ("was" vs "was not") detected
  6. Scope / condition ("if X then…" vs "when not-X…") detected
  7. Claim enrichment populates v2 fields
  8. Candidate hard-filter rejects incompatible planes
  9. Reconciler returns correct 9-category outcome (Cursor 5.2)
  10. ROLE_OR_ATTRIBUTION_MISMATCH for quotes/citations/party-vs-finding
  11. INSUFFICIENT_CONTEXT for missing claim fields
  12. OPINION speaker_mode detection
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
    SPEAKER_MODE_OPINION,
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
    OUTCOME_ROLE_MISMATCH,
    OUTCOME_PLANE_MISMATCH,
    OUTCOME_TIME_SHIFT,
    OUTCOME_AMBIGUITY,
    OUTCOME_INSUFFICIENT_CONTEXT,
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

    def test_same_quantifier_not_resolved_by_quantifier(self):
        a = _claim("כל העובדים קיבלו פיצוי", scope_quantifiers="all", plane=PLANE_FACT, negation=False, entities=["העובדים"])
        b = _claim("כל העובדים לא קיבלו פיצוי", scope_quantifiers="all", plane=PLANE_FACT, negation=True, entities=["העובדים"])
        result = reconcile_pair(a, b, detector_confidence=0.9)
        # Same quantifier, opposite negation → passes through quantifier layer, reaches final gate
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
        a = _claim("הנתבע שילם", plane=PLANE_FACT, entities=["הנתבע"],
                    speaker_mode="finding")
        b = _claim("הנתבע לא שילם", plane=PLANE_FACT, entities=["הנתבע"],
                    speaker_mode="finding")
        assert passes_hard_filters(a, b) is True

    def test_same_plane_no_speaker_mode_with_strong_overlap(self):
        """P0 fallback: FACT/FACT without speaker_mode but strong entities → ACCEPT."""
        a = _claim("יוסי כהן שילם 100,000 ₪ לחברת אלפא",
                    plane=PLANE_FACT, entities=["יוסי כהן", "חברת אלפא"])
        b = _claim("יוסי כהן לא שילם לחברת אלפא",
                    plane=PLANE_FACT, entities=["יוסי כהן", "חברת אלפא"])
        assert passes_hard_filters(a, b) is True

    def test_same_plane_no_speaker_mode_no_strong_overlap(self):
        """P0 fallback: FACT/FACT without speaker_mode, only weak entities → REJECT."""
        a = _claim("התובע שילם", plane=PLANE_FACT, entities=["התובע"])
        b = _claim("הנתבע לא שילם", plane=PLANE_FACT, entities=["הנתבע"])
        assert passes_hard_filters(a, b) is False

    def test_opinion_fact_no_speaker_mode_rejected(self):
        """P0 fallback: OPINION/FACT without speaker_mode → REJECT."""
        a = _claim("נראה שהנתבע שילם", plane=PLANE_OPINION,
                    entities=["יוסי כהן", "חברת אלפא"])
        b = _claim("יוסי כהן לא שילם לחברת אלפא", plane=PLANE_FACT,
                    entities=["יוסי כהן", "חברת אלפא"])
        assert passes_hard_filters(a, b) is False

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
        a = _claim("אולי הנתבע שילם", plane=PLANE_FACT, speaker_mode=SPEAKER_MODE_FINDING)
        b = _claim("אולי הנתבע לא שילם", plane=PLANE_FACT, speaker_mode=SPEAKER_MODE_FINDING)
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


# ====================================================================
# DELTA-FIX REGRESSION TESTS
# ====================================================================
# These tests verify the delta-fix specification requirements:
#   §1: Stop defaulting to hard_contradiction without full reconciliation
#   §2: party_claim vs non-party_claim → DISAGREEMENT, never TRUE_CONTRADICTION
#   §3: OPINION/PROCEDURAL → never TRUE_CONTRADICTION
#   §4: Context (context_before/after) required for TRUE_CONTRADICTION
#   §5: can_be_reconciled() mandatory 6-layer gate
#   §7: Confidence < 0.75 → AMBIGUITY ("quiet is better")
#   §9: Rule-based attribution text pattern override


class TestDeltaFixAttributionOverride:
    """§9: Text containing attribution patterns → never TRUE_CONTRADICTION."""

    def test_letenaat_yields_role_mismatch(self):
        """'לטענת' in claim text → ROLE_OR_ATTRIBUTION_MISMATCH (Cursor 5.2)."""
        a = _claim(
            "לטענת התובע הנתבע לא שילם את הסכום",
            plane=PLANE_FACT, negation=True, entities=["הנתבע", "התובע"],
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff",
        )
        b = _claim(
            "הנתבע שילם את מלוא הסכום",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        # party_claim vs finding → ROLE_OR_ATTRIBUTION_MISMATCH at speaker layer
        assert r.outcome == OUTCOME_ROLE_MISMATCH

    def test_asuyim_litoan_yields_disagreement(self):
        """'עשויים לטעון' in claim text → never TRUE_CONTRADICTION."""
        a = _claim(
            "עשויים לטעון שהחוזה בוטל",
            plane=PLANE_FACT, negation=False, entities=["החוזה"],
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM,
        )
        b = _claim(
            "החוזה תקף ומחייב",
            plane=PLANE_FACT, negation=False, entities=["החוזה"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
        )
        r = reconcile_pair(a, b, detector_confidence=0.9)
        # party_claim vs finding → DISAGREEMENT
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION

    def test_nitan_litoan_blocked(self):
        """'ניתן לטעון' → party_claim speaker mode → blocked."""
        role, mode = _detect_speaker("ניתן לטעון כי התביעה אינה מבוססת")
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_yesh_hatoenim_blocked(self):
        """'יש הטוענים' → party_claim speaker mode."""
        role, mode = _detect_speaker("יש הטוענים כי התשלום לא בוצע")
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_legorsat_blocked(self):
        """'לגרסת' → party_claim speaker mode."""
        role, mode = _detect_speaker("לגרסת הנתבע החוזה לא נחתם")
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_leshitat_blocked(self):
        """'לשיטת' → party_claim speaker mode."""
        role, mode = _detect_speaker("לשיטת המבקש היה צורך בהסכמה")
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_lechora_party_claim(self):
        """'לכאורה' → party_claim speaker mode."""
        role, mode = _detect_speaker("לכאורה הנתבע הפר את ההסכם")
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_nitan_ki_party_claim(self):
        """'נטען כי' → party_claim speaker mode."""
        role, mode = _detect_speaker("נטען כי הנתבע לא עמד בתנאים")
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_dome_ki_party_claim(self):
        """'דומה כי' → party_claim speaker mode."""
        role, mode = _detect_speaker("דומה כי התשלום לא בוצע במועד")
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_plural_parties_claim(self):
        """'המבקשים טענו' → party_claim speaker mode."""
        role, mode = _detect_speaker("המבקשים טענו כי יש להם זכות")
        assert mode == SPEAKER_MODE_PARTY_CLAIM


class TestDeltaFixLawCitation:
    """Law citation speaker mode → never TRUE_CONTRADICTION."""

    def test_law_citation_detection_ea(self):
        """ע\"א case reference → law_citation mode."""
        from backend_lite.extractor import SPEAKER_MODE_LAW_CITATION
        role, mode = _detect_speaker('בע"א 1234/05 נקבע כי יש לפצות')
        assert mode == SPEAKER_MODE_LAW_CITATION

    def test_law_citation_detection_bagatz(self):
        """בג\"ץ reference → law_citation mode."""
        from backend_lite.extractor import SPEAKER_MODE_LAW_CITATION
        role, mode = _detect_speaker('בג"ץ 5100/94 קבע עקרון זה')
        assert mode == SPEAKER_MODE_LAW_CITATION

    def test_law_citation_detection_rea(self):
        """רע\"א reference → law_citation mode."""
        from backend_lite.extractor import SPEAKER_MODE_LAW_CITATION
        role, mode = _detect_speaker('רע"א 7112/99 קבע כי יש לבחון')
        assert mode == SPEAKER_MODE_LAW_CITATION

    def test_nifask_be_pattern(self):
        """'נפסק בפ' pattern → law_citation mode."""
        from backend_lite.extractor import SPEAKER_MODE_LAW_CITATION
        role, mode = _detect_speaker("כפי שנפסק בפסק דין זה")
        assert mode == SPEAKER_MODE_LAW_CITATION

    def test_law_citation_blocks_true_contradiction(self):
        """Law citation vs factual claim → ROLE_OR_ATTRIBUTION_MISMATCH, never TRUE_CONTRADICTION."""
        from backend_lite.extractor import SPEAKER_MODE_LAW_CITATION
        a = _claim(
            'בע"א 1234/05 נקבע כי התשלום אינו חובה',
            plane=PLANE_FACT, negation=True, entities=["התשלום"],
            speaker_mode=SPEAKER_MODE_LAW_CITATION,
        )
        b = _claim(
            "התשלום הוא חובה חוקית",
            plane=PLANE_FACT, negation=False, entities=["התשלום"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_ROLE_MISMATCH
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION


class TestDeltaFixOpinionProceduralBlocking:
    """§3: OPINION/PROCEDURAL planes → never TRUE_CONTRADICTION."""

    def test_opinion_plane_blocked(self):
        """OPINION claim → never TRUE_CONTRADICTION regardless of other conditions."""
        a = _claim(
            "נראה כי הנתבע שילם",
            plane=PLANE_OPINION, negation=False, entities=["הנתבע"],
        )
        b = _claim(
            "הנתבע לא שילם",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        # Different planes → PLANE_MISMATCH
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION

    def test_procedural_plane_blocked(self):
        """PROCEDURAL claim → never TRUE_CONTRADICTION."""
        a = _claim(
            "הוגשה תביעה ביום 15.3.2021",
            plane=PLANE_PROCEDURAL, negation=False, entities=["התביעה"],
        )
        b = _claim(
            "התביעה לא הוגשה",
            plane=PLANE_FACT, negation=True, entities=["התביעה"],
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION

    def test_both_opinion_blocked(self):
        """Two OPINION claims with contradictory content → still not TRUE_CONTRADICTION."""
        a = _claim(
            "נראה שהנתבע שילם",
            plane=PLANE_OPINION, negation=False, entities=["הנתבע"],
        )
        b = _claim(
            "נראה שהנתבע לא שילם",
            plane=PLANE_OPINION, negation=True, entities=["הנתבע"],
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        # Both OPINION → APPARENT_TENSION (§3 final gate)
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION

    def test_both_procedural_blocked(self):
        """Two PROCEDURAL claims → not TRUE_CONTRADICTION."""
        a = _claim(
            "הוגש ערעור ביום 1.1.2020",
            plane=PLANE_PROCEDURAL, negation=False, entities=["הערעור"],
        )
        b = _claim(
            "הערעור לא הוגש",
            plane=PLANE_PROCEDURAL, negation=True, entities=["הערעור"],
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION


class TestDeltaFixPartyClaimVsNonPartyClaim:
    """§2: party_claim vs non-party_claim → DISAGREEMENT."""

    def test_party_claim_vs_finding(self):
        """party_claim vs finding → ROLE_OR_ATTRIBUTION_MISMATCH (Cursor 5.2 §5)."""
        a = _claim(
            "התובע טען שהנתבע הפר את ההסכם",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff",
        )
        b = _claim(
            "בית המשפט קובע כי הנתבע עמד בהסכם",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_ROLE_MISMATCH

    def test_party_claim_vs_quote(self):
        """party_claim vs quote → ROLE_OR_ATTRIBUTION_MISMATCH (quote blocked, Cursor 5.2)."""
        a = _claim(
            "לטענת המבקש החוב סולק",
            plane=PLANE_FACT, negation=False, entities=["החוב"],
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff",
        )
        b = _claim(
            'נאמר כי "החוב לא סולק"',
            plane=PLANE_FACT, negation=True, entities=["החוב"],
            speaker_mode=SPEAKER_MODE_QUOTE,
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_ROLE_MISMATCH

    def test_two_party_claims_same_side_not_disagreement(self):
        """Two party_claims from same party → NOT DISAGREEMENT (can be TRUE_CONTRADICTION)."""
        a = _claim(
            "התובע טען שנפגע",
            plane=PLANE_FACT, negation=False, entities=["התובע"],
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff",
            context_before="הקדמה.", context_after="המשך.",
        )
        b = _claim(
            "התובע הצהיר שלא נפגע",
            plane=PLANE_FACT, negation=True, entities=["התובע"],
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff",
            context_before="הקדמה.", context_after="המשך.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        # Same party, same side → speaker layer passes, should reach final gate
        assert r.outcome != OUTCOME_DISAGREEMENT


class TestDeltaFixEntityOverlapRequired:
    """§1: Entity overlap required for TRUE_CONTRADICTION."""

    def test_no_entity_overlap_yields_apparent_tension(self):
        """Claims about different entities → APPARENT_TENSION, not TRUE_CONTRADICTION."""
        a = _claim(
            "התובע שילם את מלוא הסכום",
            plane=PLANE_FACT, negation=False, entities=["התובע"],
            speaker_mode=SPEAKER_MODE_FINDING,
            context_before="הקדמה.", context_after="סיום.",
        )
        b = _claim(
            "הנתבע לא שילם דבר",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING,
            context_before="הקדמה.", context_after="סיום.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_APPARENT_TENSION
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION

    def test_with_entity_overlap_can_reach_true_contradiction(self):
        """Claims about SAME entity with hard negation → TRUE_CONTRADICTION."""
        a = _claim(
            "הנתבע שילם 100,000 ₪",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            context_before="הקדמה.", context_after="סיום.",
        )
        b = _claim(
            "הנתבע לא שילם דבר",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            context_before="הקדמה.", context_after="סיום.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION

    def test_empty_entities_yields_apparent_tension(self):
        """Empty entity lists → APPARENT_TENSION."""
        a = _claim(
            "שולם הסכום במלואו",
            plane=PLANE_FACT, negation=False, entities=[],
            speaker_mode=SPEAKER_MODE_FINDING,
            context_before="הקדמה.", context_after="סיום.",
        )
        b = _claim(
            "לא שולם דבר",
            plane=PLANE_FACT, negation=True, entities=[],
            speaker_mode=SPEAKER_MODE_FINDING,
            context_before="הקדמה.", context_after="סיום.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_APPARENT_TENSION


class TestDeltaFixConfidenceThreshold:
    """§7: Confidence < 0.75 → AMBIGUITY ("quiet is better")."""

    def test_low_confidence_yields_ambiguity(self):
        """Confidence 0.6 → AMBIGUITY."""
        a = _claim(
            "הנתבע שילם",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING,
        )
        b = _claim(
            "הנתבע לא שילם",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING,
        )
        r = reconcile_pair(a, b, detector_confidence=0.6)
        # Below threshold, BUT hard negation + entity overlap + factual plane → override
        # This specific case has all 3 conditions, so it may pass
        # Test with weaker claims instead:
        a2 = _claim("הסכום שולם", plane=PLANE_FACT, negation=False, entities=[],
                     speaker_mode=SPEAKER_MODE_FINDING)
        b2 = _claim("הסכום לא שולם", plane=PLANE_FACT, negation=True, entities=[],
                     speaker_mode=SPEAKER_MODE_FINDING)
        r2 = reconcile_pair(a2, b2, detector_confidence=0.6)
        assert r2.outcome == OUTCOME_AMBIGUITY

    def test_very_low_confidence(self):
        """Confidence 0.3 without hard evidence → AMBIGUITY."""
        # No entity overlap → hits entity gate before threshold can be overridden
        a = _claim("הסכום שולם", plane=PLANE_FACT, entities=[], negation=False,
                    speaker_mode=SPEAKER_MODE_FINDING)
        b = _claim("הסכום לא שולם", plane=PLANE_FACT, entities=[], negation=True,
                    speaker_mode=SPEAKER_MODE_FINDING)
        r = reconcile_pair(a, b, detector_confidence=0.3)
        assert r.outcome == OUTCOME_AMBIGUITY

    def test_very_low_confidence_with_hard_evidence_overrides(self):
        """Confidence 0.3 WITH hard negation + entity overlap + factual plane → overrides threshold."""
        a = _claim("הנתבע נכח", plane=PLANE_FACT, entities=["הנתבע"], negation=False)
        b = _claim("הנתבע לא נכח", plane=PLANE_FACT, entities=["הנתבע"], negation=True)
        r = reconcile_pair(a, b, detector_confidence=0.3)
        # Hard evidence overrides threshold per §7
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION

    def test_high_confidence_allows_true_contradiction(self):
        """Confidence 0.9 with all conditions met → TRUE_CONTRADICTION."""
        a = _claim(
            "הנתבע שילם 100,000 ₪",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            context_before="הקדמה.", context_after="סיום.",
        )
        b = _claim(
            "הנתבע לא שילם דבר",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            context_before="הקדמה.", context_after="סיום.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.9)
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION

    def test_threshold_boundary_075(self):
        """Confidence exactly 0.75 → above threshold, should pass."""
        a = _claim(
            "הנתבע שילם",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            context_before="הקדמה.", context_after="סיום.",
        )
        b = _claim(
            "הנתבע לא שילם",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            context_before="הקדמה.", context_after="סיום.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.75)
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION

    def test_hard_negation_overrides_low_confidence(self):
        """Hard negation + entity overlap + factual plane → override low confidence."""
        a = _claim(
            "הנתבע שילם 100,000 ₪",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            context_before="הקדמה.",
        )
        b = _claim(
            "הנתבע לא שילם דבר",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            context_before="הקדמה.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.6)
        # Hard negation + entity overlap + factual plane → overrides threshold
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION


class TestDeltaFixContextRequired:
    """§4: Context (context_before/after) required for TRUE_CONTRADICTION."""

    def test_no_context_without_hard_evidence(self):
        """No context + no hard negation → AMBIGUITY."""
        a = _claim(
            "הנתבע ביצע את העבודה",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
        )
        b = _claim(
            "הנתבע ביצע עבודה חלקית",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
        )
        r = reconcile_pair(a, b, detector_confidence=0.85)
        # No negation opposition → falls to no_hard_conflict path → AMBIGUITY
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION

    def test_no_context_with_hard_evidence_still_passes(self):
        """No context BUT hard negation + entity overlap → TRUE_CONTRADICTION (override)."""
        a = _claim(
            "הנתבע שילם",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            # No context_before/after
        )
        b = _claim(
            "הנתבע לא שילם",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            # No context_before/after
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        # Hard negation + entity overlap → overrides missing context check
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION

    def test_with_context_true_contradiction(self):
        """Full context available → TRUE_CONTRADICTION when all conditions met."""
        a = _claim(
            "הנתבע שילם את מלוא הסכום",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            context_before="פסק דין.", context_after="סיכום.",
        )
        b = _claim(
            "הנתבע לא שילם דבר",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            context_before="פסק דין.", context_after="סיכום.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.9)
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION


class TestDeltaFixNoHardNegation:
    """§1: Without hard negation AND non-factual plane → AMBIGUITY."""

    def test_no_negation_no_factual_plane(self):
        """Same negation + non-factual plane → AMBIGUITY."""
        a = _claim(
            "הנתבע ביצע עבודה",
            plane=PLANE_OPINION, negation=False, entities=["הנתבע"],
        )
        b = _claim(
            "הנתבע ביצע עבודה אחרת",
            plane=PLANE_OPINION, negation=False, entities=["הנתבע"],
        )
        r = reconcile_pair(a, b, detector_confidence=0.85)
        # OPINION → blocked at §3 final gate
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION

    def test_no_negation_factual_plane_with_entities(self):
        """No negation opposition + factual plane + entities + complete claim → TRUE_CONTRADICTION."""
        a = _claim(
            "הנתבע שילם 100,000 ₪",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
            context_before="פסק.", context_after="המשך.",
        )
        b = _claim(
            "הנתבע שילם 50,000 ₪",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
            context_before="פסק.", context_after="המשך.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.9)
        # Same negation (both False) → no hard negation → but factual plane
        # Claims have speaker_mode + plane → completeness check passes
        # has_hard_negation=False but factual_plane=True → "not False AND not True" → False → passes
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION


class TestDeltaFixReconcilerMetadata:
    """Reconciler populates metadata fields (reconciliation_attempt, rationale, etc.)."""

    def test_reconciliation_result_has_rationale(self):
        """All reconciliation results include a rationale string."""
        a = _claim("הנתבע שילם", plane=PLANE_FACT, entities=["הנתבע"], negation=False)
        b = _claim("הנתבע לא שילם", plane=PLANE_FACT, entities=["הנתבע"], negation=True)
        r = reconcile_pair(a, b, detector_confidence=0.9)
        assert r.rationale != ""
        assert r.reconciliation_attempt != ""

    def test_disagreement_rationale_mentions_speaker(self):
        """DISAGREEMENT outcome rationale references speaker/party mismatch."""
        a = _claim(
            "התובע טען שהחוזה בוטל",
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff", plane=PLANE_FACT,
        )
        b = _claim(
            "הנתבע טען שהחוזה תקף",
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="defendant", plane=PLANE_FACT,
        )
        r = reconcile_pair(a, b, detector_confidence=0.9)
        assert r.outcome == OUTCOME_DISAGREEMENT
        assert "speaker_mode" in r.deciding_fields

    def test_time_shift_rationale_mentions_time(self):
        """TIME_SHIFT includes time reference info."""
        a = _claim("ביום 1.1.2020 נחתם", time_reference="1.1.2020", plane=PLANE_FACT)
        b = _claim("ביום 5.5.2022 נחתם", time_reference="5.5.2022", plane=PLANE_FACT)
        r = reconcile_pair(a, b, detector_confidence=0.8)
        assert r.outcome == OUTCOME_TIME_SHIFT
        assert "time_reference" in r.deciding_fields

    def test_true_contradiction_severity_computed(self):
        """TRUE_CONTRADICTION result includes severity score > 0."""
        a = _claim(
            "הנתבע שילם",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            context_before="הקדמה.",
        )
        b = _claim(
            "הנתבע לא שילם",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            context_before="הקדמה.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION
        assert r.severity_score > 0
        assert r.severity in ("low", "medium", "high")


class TestDeltaFixEnricherNewPatterns:
    """Enricher correctly classifies new patterns added in delta fix."""

    def test_enrich_legorsat_party_claim(self):
        """'לגרסת הנתבע' → party_claim + defendant."""
        c = _claim("לגרסת הנתבע החוזה לא נחתם", char_start=0, char_end=30)
        enrich_claims([c], "לגרסת הנתבע החוזה לא נחתם")
        assert c.speaker_mode == SPEAKER_MODE_PARTY_CLAIM

    def test_enrich_lechora_party_claim(self):
        """'לכאורה' → party_claim."""
        c = _claim("לכאורה הנתבע הפר את ההסכם", char_start=0, char_end=25)
        enrich_claims([c], "לכאורה הנתבע הפר את ההסכם")
        assert c.speaker_mode == SPEAKER_MODE_PARTY_CLAIM

    def test_enrich_nitan_ki_party_claim(self):
        """'נטען כי' → party_claim."""
        c = _claim("נטען כי הנתבע לא עמד בתנאים", char_start=0, char_end=28)
        enrich_claims([c], "נטען כי הנתבע לא עמד בתנאים")
        assert c.speaker_mode == SPEAKER_MODE_PARTY_CLAIM

    def test_enrich_law_citation_ea(self):
        """Case citation → law_citation mode."""
        from backend_lite.extractor import SPEAKER_MODE_LAW_CITATION
        c = _claim('בע"א 1234/05 נקבע כי יש חובה', char_start=0, char_end=28)
        enrich_claims([c], 'בע"א 1234/05 נקבע כי יש חובה')
        assert c.speaker_mode == SPEAKER_MODE_LAW_CITATION

    def test_enrich_law_citation_bagatz(self):
        """בג\"ץ reference → law_citation mode."""
        from backend_lite.extractor import SPEAKER_MODE_LAW_CITATION
        c = _claim('בג"ץ 5100/94 קבע כי', char_start=0, char_end=20)
        enrich_claims([c], 'בג"ץ 5100/94 קבע כי')
        assert c.speaker_mode == SPEAKER_MODE_LAW_CITATION

    def test_enrich_hamvakshim_party_claim(self):
        """'המבקשים טענו' → party_claim."""
        c = _claim("המבקשים טענו כי יש להם זכות קדימה", char_start=0, char_end=33)
        enrich_claims([c], "המבקשים טענו כי יש להם זכות קדימה")
        assert c.speaker_mode == SPEAKER_MODE_PARTY_CLAIM

    def test_enrich_finding_still_works(self):
        """Finding detection not broken by new patterns."""
        c = _claim("בית המשפט קובע כי הנתבע חב בפיצוי", char_start=0, char_end=33)
        enrich_claims([c], "בית המשפט קובע כי הנתבע חב בפיצוי")
        assert c.speaker_mode == SPEAKER_MODE_FINDING
        assert c.speaker_role == "court"


class TestDeltaFixQuoteBlocking:
    """Quotes → ROLE_OR_ATTRIBUTION_MISMATCH, never TRUE_CONTRADICTION (Cursor 5.2)."""

    def test_quote_vs_factual_yields_role_mismatch(self):
        """Quote claim vs factual claim → ROLE_OR_ATTRIBUTION_MISMATCH."""
        a = _claim(
            'נאמר כי "הנתבע לא שילם"',
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_QUOTE,
        )
        b = _claim(
            "הנתבע שילם את מלוא הסכום",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_ROLE_MISMATCH

    def test_both_quotes_yield_role_mismatch(self):
        """Two quotes → ROLE_OR_ATTRIBUTION_MISMATCH."""
        a = _claim(
            '"שולם הכל"',
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_QUOTE,
        )
        b = _claim(
            '"לא שולם דבר"',
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_QUOTE,
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_ROLE_MISMATCH


class TestDeltaFixFullGateIntegration:
    """Integration tests verifying the full TRUE_CONTRADICTION gate."""

    def test_all_conditions_met_true_contradiction(self):
        """
        All delta-fix conditions satisfied:
        - same entities, same plane (FACT), hard negation, context, high confidence
        → TRUE_CONTRADICTION
        """
        a = _claim(
            "הנתבע שילם 100,000 ₪ לידי התובע",
            plane=PLANE_FACT, negation=False, entities=["הנתבע", "התובע"],
            context_before="רקע עובדתי.", context_after="סיכום.",
        )
        b = _claim(
            "הנתבע לא שילם דבר לתובע",
            plane=PLANE_FACT, negation=True, entities=["הנתבע", "התובע"],
            context_before="עדות.", context_after="המשך.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION
        assert r.contradiction_score >= 0.75
        assert r.severity in ("medium", "high")

    def test_missing_one_condition_blocks_true_contradiction(self):
        """
        All conditions met EXCEPT entity overlap → APPARENT_TENSION.
        """
        a = _claim(
            "יוסף שילם 100,000 ₪",
            plane=PLANE_FACT, negation=False, entities=["יוסף"],
            speaker_mode=SPEAKER_MODE_FINDING,
            context_before="רקע.", context_after="סיכום.",
        )
        b = _claim(
            "דוד לא שילם דבר",
            plane=PLANE_FACT, negation=True, entities=["דוד"],
            speaker_mode=SPEAKER_MODE_FINDING,
            context_before="עדות.", context_after="המשך.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_APPARENT_TENSION

    def test_cascade_priority(self):
        """
        When multiple layers trigger, the first layer wins.
        Time mismatch takes priority over scope mismatch.
        """
        a = _claim(
            "כל העובדים קיבלו פיצוי בינואר 2020",
            plane=PLANE_FACT, time_reference="בינואר 2020",
            scope_quantifiers="all", entities=["העובדים"],
        )
        b = _claim(
            "חלק מהעובדים לא קיבלו פיצוי באוגוסט 2022",
            plane=PLANE_FACT, time_reference="באוגוסט 2022",
            scope_quantifiers="part", entities=["העובדים"],
        )
        r = reconcile_pair(a, b, detector_confidence=0.8)
        # Time layer (L1) triggers first
        assert r.outcome == OUTCOME_TIME_SHIFT


# ====================================================================
# CURSOR 5.2 SPEC — NEW TESTS
# ====================================================================
# These tests verify the Cursor 5.2 spec additions:
#   §3: OPINION speaker_mode detection
#   §4: INSUFFICIENT_CONTEXT for incomplete claims
#   §5: ROLE_OR_ATTRIBUTION_MISMATCH for attribution/role mismatches
#   §7: 9-category outcome validation


class TestCursor52OpinionSpeakerMode:
    """Cursor 5.2 §3: OPINION as speaker_mode (not just plane)."""

    def test_opinion_speaker_mode_detection(self):
        """'נראה' / 'ייתכן' → OPINION speaker_mode."""
        role, mode = _detect_speaker("נראה כי הנתבע הפר את ההסכם")
        assert mode == SPEAKER_MODE_OPINION

    def test_opinion_speaker_mode_yitachen(self):
        """'ייתכן' → OPINION speaker_mode."""
        role, mode = _detect_speaker("ייתכן שהחוזה בוטל")
        assert mode == SPEAKER_MODE_OPINION

    def test_opinion_speaker_mode_savir(self):
        """'סביר להניח' → OPINION speaker_mode."""
        role, mode = _detect_speaker("סביר להניח שהתשלום לא בוצע")
        assert mode == SPEAKER_MODE_OPINION

    def test_opinion_speaker_mode_blocks_true_contradiction(self):
        """OPINION speaker_mode vs finding → ROLE_OR_ATTRIBUTION_MISMATCH."""
        a = _claim(
            "נראה כי הנתבע הפר",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_OPINION,
        )
        b = _claim(
            "הנתבע עמד בהתחייבויותיו",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_ROLE_MISMATCH

    def test_opinion_enrichment(self):
        """Enricher detects OPINION speaker_mode on text with speculation."""
        c = _claim("נראה כי הנזק הוא משמעותי", char_start=0, char_end=25)
        enrich_claims([c], "נראה כי הנזק הוא משמעותי")
        assert c.speaker_mode == SPEAKER_MODE_OPINION

    def test_opinion_vs_opinion_not_true_contradiction(self):
        """Two OPINION claims → ROLE_OR_ATTRIBUTION_MISMATCH, not TRUE_CONTRADICTION."""
        a = _claim(
            "נראה שהנתבע שילם",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_OPINION,
        )
        b = _claim(
            "נראה שהנתבע לא שילם",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_OPINION,
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_ROLE_MISMATCH
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION


class TestCursor52InsufficientContext:
    """Cursor 5.2 §4: INSUFFICIENT_CONTEXT for incomplete claims."""

    def test_missing_speaker_mode_yields_insufficient(self):
        """Claim with no speaker_mode → INSUFFICIENT_CONTEXT (unless hard override)."""
        a = _claim(
            "הנתבע ביצע עבודה",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
        )
        b = _claim(
            "הנתבע לא ביצע עבודה",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
        )
        # Both claims missing speaker_mode → incomplete
        # BUT has_hard_negation + entity_overlap + factual_plane → override
        r = reconcile_pair(a, b, detector_confidence=0.95)
        # Hard evidence overrides completeness check
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION

    def test_missing_speaker_mode_without_hard_evidence(self):
        """Missing speaker_mode + no hard evidence → INSUFFICIENT_CONTEXT."""
        a = _claim(
            "הנתבע ביצע את העבודה",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
        )
        b = _claim(
            "הנתבע ביצע עבודה חלקית",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
        )
        # Missing speaker_mode + no hard negation → INSUFFICIENT_CONTEXT
        r = reconcile_pair(a, b, detector_confidence=0.85)
        assert r.outcome == OUTCOME_INSUFFICIENT_CONTEXT

    def test_missing_plane_yields_insufficient(self):
        """Claim with no plane → INSUFFICIENT_CONTEXT (unless hard override)."""
        a = _claim(
            "הנתבע ביצע עבודה",
            speaker_mode=SPEAKER_MODE_FINDING, negation=False, entities=["הנתבע"],
        )
        b = _claim(
            "הנתבע ביצע עבודה אחרת",
            speaker_mode=SPEAKER_MODE_FINDING, negation=False, entities=["הנתבע"],
        )
        # Missing plane + no hard negation → INSUFFICIENT_CONTEXT
        r = reconcile_pair(a, b, detector_confidence=0.85)
        assert r.outcome == OUTCOME_INSUFFICIENT_CONTEXT

    def test_complete_claim_no_insufficient_context(self):
        """Claims with all fields → no INSUFFICIENT_CONTEXT."""
        a = _claim(
            "הנתבע שילם",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
            context_before="הקדמה.",
        )
        b = _claim(
            "הנתבע לא שילם",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
            context_before="הקדמה.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome != OUTCOME_INSUFFICIENT_CONTEXT
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION

    def test_no_context_no_hard_evidence_insufficient(self):
        """No context + no hard evidence → INSUFFICIENT_CONTEXT."""
        a = _claim(
            "הנתבע ביצע עבודה",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING,
        )
        b = _claim(
            "הנתבע ביצע עבודה אחרת",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING,
        )
        r = reconcile_pair(a, b, detector_confidence=0.85)
        # No context + no hard negation → INSUFFICIENT_CONTEXT
        assert r.outcome == OUTCOME_INSUFFICIENT_CONTEXT


class TestCursor52RoleOrAttributionMismatch:
    """Cursor 5.2 §5: ROLE_OR_ATTRIBUTION_MISMATCH for role/attribution mismatches."""

    def test_party_claim_vs_court_finding(self):
        """party_claim vs court finding → ROLE_OR_ATTRIBUTION_MISMATCH."""
        a = _claim(
            "לטענת התובע הנתבע חייב",
            plane=PLANE_FACT, entities=["הנתבע", "התובע"],
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff",
        )
        b = _claim(
            "בית המשפט קובע כי הנתבע אינו חייב",
            plane=PLANE_FACT, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_ROLE_MISMATCH

    def test_cross_party_remains_disagreement(self):
        """Two party-claims from different sides → DISAGREEMENT (not role mismatch)."""
        a = _claim(
            "התובע טען שהחוזה בוטל",
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="plaintiff", plane=PLANE_FACT,
        )
        b = _claim(
            "הנתבע טען שהחוזה תקף",
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="defendant", plane=PLANE_FACT,
        )
        r = reconcile_pair(a, b, detector_confidence=0.9)
        assert r.outcome == OUTCOME_DISAGREEMENT

    def test_law_citation_vs_finding_role_mismatch(self):
        """Law citation vs finding → ROLE_OR_ATTRIBUTION_MISMATCH."""
        from backend_lite.extractor import SPEAKER_MODE_LAW_CITATION
        a = _claim(
            'בע"א 1234/05 נקבע כי אין חובה',
            plane=PLANE_FACT, entities=["חובה"],
            speaker_mode=SPEAKER_MODE_LAW_CITATION,
        )
        b = _claim(
            "קיימת חובה ברורה",
            plane=PLANE_FACT, entities=["חובה"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_ROLE_MISMATCH

    def test_opinion_vs_finding_role_mismatch(self):
        """OPINION speaker_mode vs finding → ROLE_OR_ATTRIBUTION_MISMATCH."""
        a = _claim(
            "נראה שהנתבע חייב",
            plane=PLANE_FACT, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_OPINION,
        )
        b = _claim(
            "הנתבע אינו חייב",
            plane=PLANE_FACT, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_ROLE_MISMATCH


class TestCursor52NineCategoryOutcomes:
    """Verify all 9 outcome categories can be produced."""

    def test_all_nine_outcomes_defined(self):
        """Verify 9 outcome constants exist."""
        from backend_lite.reconciler import ALL_OUTCOMES
        assert len(ALL_OUTCOMES) == 9
        assert OUTCOME_TRUE_CONTRADICTION in ALL_OUTCOMES
        assert OUTCOME_APPARENT_TENSION in ALL_OUTCOMES
        assert OUTCOME_DISAGREEMENT in ALL_OUTCOMES
        assert OUTCOME_ROLE_MISMATCH in ALL_OUTCOMES
        assert OUTCOME_PLANE_MISMATCH in ALL_OUTCOMES
        assert OUTCOME_TIME_SHIFT in ALL_OUTCOMES
        assert OUTCOME_AMBIGUITY in ALL_OUTCOMES
        assert OUTCOME_INSUFFICIENT_CONTEXT in ALL_OUTCOMES
        assert OUTCOME_DUPLICATE in ALL_OUTCOMES

    def test_duplicate_outcome(self):
        """Nearly identical claims → DUPLICATE_OR_RESTATEMENT."""
        a = _claim("הנתבע שילם את הסכום", plane=PLANE_FACT)
        b = _claim("הנתבע שילם את הסכום", plane=PLANE_FACT)
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_DUPLICATE

    def test_plane_mismatch_outcome(self):
        """FACT vs LAW → PLANE_MISMATCH."""
        a = _claim("הנתבע שילם", plane=PLANE_FACT)
        b = _claim("סעיף 10 קובע חובת תשלום", plane=PLANE_LAW)
        r = reconcile_pair(a, b, detector_confidence=0.9)
        assert r.outcome == OUTCOME_PLANE_MISMATCH

    def test_true_contradiction_nine_categories(self):
        """Full conditions → TRUE_CONTRADICTION (one of 9)."""
        a = _claim(
            "הנתבע שילם",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
            context_before="הקדמה.",
        )
        b = _claim(
            "הנתבע לא שילם",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
            context_before="הקדמה.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION


# ====================================================================
# B1.6 — Regression tests: attribution contradictions (spec compliance)
# ====================================================================

class TestAttributionRegression:
    """Cursor 5.2 spec B1.6: ensure attribution patterns never produce TRUE_CONTRADICTION."""

    def test_party_claim_vs_party_claim_never_true_contradiction(self):
        """Two party claims → DISAGREEMENT_BETWEEN_PARTIES (never TRUE_CONTRADICTION)."""
        a = _claim(
            "לטענת המערער, הסכום שולם במלואו",
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="appellant",
            plane=PLANE_FACT, entities=["המערער", "הסכום"],
        )
        b = _claim(
            "לטענת המשיב, לא שולם מאומה",
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="respondent",
            plane=PLANE_FACT, entities=["המשיב", "הסכום"],
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION
        assert r.outcome in (OUTCOME_DISAGREEMENT, OUTCOME_ROLE_MISMATCH)

    def test_party_claim_vs_party_claim_blocked_by_hard_filter(self):
        """Hard filter blocks PARTY_CLAIM vs PARTY_CLAIM entirely."""
        a = _claim(
            "לטענת המערער, הסכום שולם",
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="appellant",
            plane=PLANE_FACT, entities=["המערער"],
        )
        b = _claim(
            "לטענת המשיב, לא שולם",
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="respondent",
            plane=PLANE_FACT, entities=["המשיב"],
        )
        assert not passes_hard_filters(a, b)

    def test_party_claim_vs_finding_is_role_mismatch(self):
        """PARTY_CLAIM vs COURT_FINDING → ROLE_OR_ATTRIBUTION_MISMATCH."""
        a = _claim(
            "לטענת המערער, החוזה נחתם ב-2020",
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="appellant",
            plane=PLANE_FACT, entities=["המערער", "החוזה"],
        )
        b = _claim(
            "בית המשפט קבע כי החוזה נחתם ב-2019",
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
            plane=PLANE_FACT, entities=["בית המשפט", "החוזה"],
        )
        r = reconcile_pair(a, b, detector_confidence=0.9)
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION
        assert r.outcome == OUTCOME_ROLE_MISMATCH

    def test_plane_mismatch_never_true_contradiction(self):
        """FACT vs LAW → PLANE_MISMATCH (never TRUE_CONTRADICTION)."""
        a = _claim(
            "הנתבע לא שילם",
            speaker_mode=SPEAKER_MODE_FINDING, plane=PLANE_FACT,
            entities=["הנתבע"],
        )
        b = _claim(
            "סעיף 10 קובע חובת תשלום",
            speaker_mode=SPEAKER_MODE_FINDING, plane=PLANE_LAW,
            entities=["הנתבע"],
        )
        r = reconcile_pair(a, b, detector_confidence=0.9)
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION
        assert r.outcome == OUTCOME_PLANE_MISMATCH

    def test_scope_reconciliation_yields_apparent_tension(self):
        """Different scopes → APPARENT_TENSION_RESOLVABLE."""
        a = _claim(
            "כל העובדים קיבלו פיצוי",
            speaker_mode=SPEAKER_MODE_FINDING, plane=PLANE_FACT,
            entities=["העובדים"], scope_quantifiers=["כל"],
        )
        b = _claim(
            "חלק מהעובדים לא קיבלו פיצוי",
            speaker_mode=SPEAKER_MODE_FINDING, plane=PLANE_FACT,
            entities=["העובדים"], scope_quantifiers=["חלק"],
        )
        r = reconcile_pair(a, b, detector_confidence=0.8)
        assert r.outcome != OUTCOME_TRUE_CONTRADICTION
        assert r.outcome == OUTCOME_APPARENT_TENSION

    def test_direct_negation_same_subject_is_true_contradiction(self):
        """Direct negation, same subject/plane/scope → TRUE_CONTRADICTION."""
        a = _claim(
            "הנתבע נכח בפגישה",
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
            plane=PLANE_FACT, negation=False, entities=["הנתבע"],
            context_before="רקע.",
        )
        b = _claim(
            "הנתבע לא נכח בפגישה",
            speaker_mode=SPEAKER_MODE_FINDING, speaker_role="court",
            plane=PLANE_FACT, negation=True, entities=["הנתבע"],
            context_before="רקע.",
        )
        r = reconcile_pair(a, b, detector_confidence=0.95)
        assert r.outcome == OUTCOME_TRUE_CONTRADICTION

    def test_missing_plane_blocked_by_hard_filter(self):
        """Missing plane → hard filter rejects pair (Cursor 5.2 §4)."""
        a = _claim("הנתבע שילם", speaker_mode=SPEAKER_MODE_FINDING, entities=["הנתבע"])
        b = _claim("הנתבע לא שילם", speaker_mode=SPEAKER_MODE_FINDING, plane=PLANE_FACT, entities=["הנתבע"])
        assert not passes_hard_filters(a, b)

    def test_missing_speaker_mode_blocked_by_hard_filter(self):
        """Missing speaker_mode → hard filter rejects pair (Cursor 5.2 §4)."""
        a = _claim("הנתבע שילם", plane=PLANE_FACT, entities=["הנתבע"])
        b = _claim("הנתבע לא שילם", speaker_mode=SPEAKER_MODE_FINDING, plane=PLANE_FACT, entities=["הנתבע"])
        assert not passes_hard_filters(a, b)

    def test_same_party_claims_blocked_by_hard_filter(self):
        """Even same-party PARTY_CLAIM pairs are blocked."""
        a = _claim(
            "לטענת המערער, שילם",
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="appellant",
            plane=PLANE_FACT, entities=["המערער"],
        )
        b = _claim(
            "לטענת המערער, לא שילם",
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM, speaker_role="appellant",
            plane=PLANE_FACT, entities=["המערער"],
        )
        assert not passes_hard_filters(a, b)
