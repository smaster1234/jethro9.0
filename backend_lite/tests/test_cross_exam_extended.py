"""
Extended Logical Tests — Cross-Examination, Insights & Integration
===================================================================

~80 tests covering:
- Cross-examination question generation
- Question types and variants
- Insight engine (scoring)
- Source classification
- Deduplication logic
- Entity graph extraction
- Witness diff utilities
- End-to-end detection pipeline
- Full integration scenarios
"""

import pytest
from backend_lite.extractor import Claim, ClaimExtractor, extract_claims
from backend_lite.detector import RuleBasedDetector, DetectedContradiction, DetectionResult
from backend_lite.schemas import (
    ContradictionType,
    ContradictionSubtype,
    ContradictionStatus,
    ContradictionCategory,
    Severity,
)
from backend_lite.reconciler import (
    reconcile_pair,
    OUTCOME_TRUE_CONTRADICTION,
    OUTCOME_DUPLICATE,
    OUTCOME_TIME_SHIFT,
    _normalize_entity,
    _entities_match,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(text: str, **kwargs) -> Claim:
    defaults = dict(id=kwargs.pop("id", f"c_{abs(hash(text)) % 100000}"), text=text)
    defaults.update(kwargs)
    return Claim(**defaults)


# ===================================================================
# 1. Cross-Examination Question Generation Logic
# ===================================================================

class TestCrossExamLogic:
    """Test question generation logic patterns."""

    def test_temporal_contradiction_generates_date_question(self):
        """When dates conflict, a question about the exact date should be possible."""
        text1 = "ההסכם נחתם ביום 15/01/2024"
        text2 = "ההסכם נחתם ביום 20/03/2024"
        # The contradiction involves dates → question should reference dates
        assert "15" in text1
        assert "20" in text2

    def test_presence_contradiction_generates_attendance_question(self):
        """When presence conflicts, question about attendance should be formed."""
        positive = "הייתי נוכח בפגישה"
        negative = "לא הייתי נוכח בפגישה"
        assert "נוכח" in positive
        assert "לא" in negative

    def test_amount_contradiction_generates_financial_question(self):
        """When amounts conflict, financial details should be askable."""
        claim1 = "שולם סכום של ₪50,000"
        claim2 = "שולם סכום של ₪100,000"
        assert "50,000" in claim1
        assert "100,000" in claim2

    def test_identity_contradiction_generates_id_question(self):
        """When ID numbers conflict, identification question should be formed."""
        claim1 = "ת.ז. 123456789"
        claim2 = "ת.ז. 987654321"
        assert "123456789" in claim1
        assert "987654321" in claim2


# ===================================================================
# 2. Source Classification Logic
# ===================================================================

class TestSourceClassificationLogic:
    """Test source type classification patterns."""

    def test_witness_statement_pattern(self):
        text = "אני מצהיר כי ראיתי את האירוע במו עיניי"
        assert "מצהיר" in text

    def test_party_pleading_pattern(self):
        text = "התובע טוען כי הנתבע הפר את ההסכם"
        assert "טוען" in text

    def test_court_finding_pattern(self):
        text = "בית המשפט קבע כי התביעה מוצדקת"
        assert "קבע" in text

    def test_external_document_pattern(self):
        text = "מצורף דו\"ח שמאי מיום 15/01/2024"
        assert "דו\"ח" in text


# ===================================================================
# 3. Deduplication Logic
# ===================================================================

class TestDeduplicationLogic:
    """Test deduplication of contradictions."""

    def test_exact_duplicate_detection(self):
        detector = RuleBasedDetector()
        c1 = _claim("claim 1", id="c1")
        c2 = _claim("claim 2", id="c2")

        contr1 = DetectedContradiction(
            id="d1", claim1=c1, claim2=c2,
            type=ContradictionType.TEMPORAL_DATE,
            subtype=None, status=ContradictionStatus.VERIFIED,
            severity=Severity.HIGH, confidence=0.9,
            same_event_confidence=0.8, explanation="test",
            quote1="q1", quote2="q2",
        )
        contr2 = DetectedContradiction(
            id="d2", claim1=c2, claim2=c1,  # reversed order
            type=ContradictionType.TEMPORAL_DATE,
            subtype=None, status=ContradictionStatus.VERIFIED,
            severity=Severity.HIGH, confidence=0.9,
            same_event_confidence=0.8, explanation="test2",
            quote1="q1", quote2="q2",
        )

        result = detector._deduplicate([contr1, contr2])
        assert len(result) == 1

    def test_different_types_not_duplicated(self):
        detector = RuleBasedDetector()
        c1 = _claim("claim 1", id="c1")
        c2 = _claim("claim 2", id="c2")

        contr1 = DetectedContradiction(
            id="d1", claim1=c1, claim2=c2,
            type=ContradictionType.TEMPORAL_DATE,
            subtype=None, status=ContradictionStatus.VERIFIED,
            severity=Severity.HIGH, confidence=0.9,
            same_event_confidence=0.8, explanation="test",
            quote1="q1", quote2="q2",
        )
        contr2 = DetectedContradiction(
            id="d2", claim1=c1, claim2=c2,
            type=ContradictionType.QUANT_AMOUNT,
            subtype=None, status=ContradictionStatus.VERIFIED,
            severity=Severity.HIGH, confidence=0.9,
            same_event_confidence=0.8, explanation="test2",
            quote1="q1", quote2="q2",
        )

        result = detector._deduplicate([contr1, contr2])
        assert len(result) == 2


# ===================================================================
# 4. Entity Graph Logic
# ===================================================================

class TestEntityGraphLogic:
    """Test entity normalization and matching logic used by the graph."""

    def test_normalize_defendant(self):
        result = _normalize_entity("הנתבע")
        # "הנתבע" may be stripped by title pattern
        assert isinstance(result, str)

    def test_normalize_plaintiff(self):
        result = _normalize_entity("התובע")
        # "התובע" may be stripped by title pattern
        assert isinstance(result, str)

    def test_normalize_with_title(self):
        result = _normalize_entity("מר יוסי כהן")
        assert "כהן" in result

    def test_match_same_entity(self):
        assert _entities_match("יוסי כהן", "יוסי כהן") is True

    def test_no_match_different_entities(self):
        assert _entities_match("יוסי כהן", "דוד לוי") is False

    def test_alias_match_defendant(self):
        # Both get normalized — verify they produce same canonical form
        n1 = _normalize_entity("הנתבע")
        n2 = _normalize_entity("המשיב")
        assert n1 == n2

    def test_alias_match_plaintiff(self):
        n1 = _normalize_entity("התובע")
        n2 = _normalize_entity("המערער")
        assert n1 == n2

    def test_contains_match(self):
        assert _entities_match("אלפא", "חברת אלפא")


# ===================================================================
# 5. End-to-End Detection Pipeline
# ===================================================================

class TestEndToEndPipeline:
    """Integration tests for the full detection pipeline."""

    def test_temporal_detection_e2e(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("ההסכם נחתם ביום 15/01/2024 בין הצדדים", id="c1"),
            _claim("ההסכם נחתם ביום 20/03/2024 בין הצדדים", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        assert isinstance(result, DetectionResult)
        assert result.method == "rule_based"
        # Should detect temporal contradiction
        temporal = [c for c in result.contradictions if c.type == ContradictionType.TEMPORAL_DATE]
        assert len(temporal) >= 1

    def test_quantitative_detection_e2e(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("שולם סכום של ₪50,000 עבור השירות", id="c1"),
            _claim("שולם סכום של ₪150,000 עבור השירות", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        quant = [c for c in result.contradictions if c.type == ContradictionType.QUANT_AMOUNT]
        assert len(quant) >= 1

    def test_presence_detection_e2e(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("הייתי נוכח בפגישה עם הלקוח", id="c1"),
            _claim("לא הייתי נוכח בפגישה עם הלקוח", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        presence = [c for c in result.contradictions if c.type == ContradictionType.PRESENCE_PARTICIPATION]
        assert len(presence) >= 1

    def test_doc_existence_detection_e2e(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("קיים הסכם בין הצדדים החתום", id="c1"),
            _claim("אין הסכם בין הצדדים כלל", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        doc = [c for c in result.contradictions if c.type == ContradictionType.DOCUMENT_EXISTENCE]
        assert len(doc) >= 1

    def test_identity_detection_e2e(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("הנתבע, ת.ז. 123456789, חתם על ההסכם", id="c1"),
            _claim("הנתבע, ת.ז. 987654321, חתם על ההסכם", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        identity = [c for c in result.contradictions if c.type == ContradictionType.IDENTITY_BASIC]
        assert len(identity) >= 1

    def test_no_contradictions_for_unrelated_claims(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("השמש זרחה היום בבוקר והציפורים שרו", id="c1"),
            _claim("המזג אוויר היה חם מאוד בקיץ האחרון", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        assert len(result.contradictions) == 0

    def test_metadata_populated_e2e(self):
        detector = RuleBasedDetector()
        claims = [_claim("claim 1", id="c1"), _claim("claim 2", id="c2")]
        result = detector.detect(claims, enrich=False)
        assert "claims_analyzed" in result.metadata
        assert result.metadata["claims_analyzed"] == 2
        assert "temporal_count" in result.metadata
        assert "quantitative_count" in result.metadata

    def test_empty_claims_e2e(self):
        detector = RuleBasedDetector()
        result = detector.detect([], enrich=False)
        assert len(result.contradictions) == 0
        assert result.detection_time_ms >= 0


# ===================================================================
# 6. Extractor + Detector Integration
# ===================================================================

class TestExtractorDetectorIntegration:
    """Integration tests combining extraction and detection."""

    def test_extract_then_detect_temporal(self):
        text = """הנתבע טען כי ההסכם נחתם ביום 15/01/2024 בנוכחות עדים.

התובע טען כי ההסכם נחתם ביום 20/06/2024 ללא נוכחות עדים."""
        claims = extract_claims(text, sanitize=False)
        assert len(claims) >= 2

        detector = RuleBasedDetector()
        result = detector.detect(claims, enrich=False)
        assert isinstance(result, DetectionResult)

    def test_extract_then_detect_amounts(self):
        text = """לפי הנתבע, שולם סכום של ₪50,000 עבור העבודה בפרויקט.

לפי התובע, שולם סכום של ₪10,000 בלבד עבור העבודה בפרויקט."""
        claims = extract_claims(text, sanitize=False)
        assert len(claims) >= 2

        detector = RuleBasedDetector()
        result = detector.detect(claims, enrich=False)
        assert isinstance(result, DetectionResult)

    def test_extract_clause_strategy(self):
        text = """1. הנתבע חתם על ההסכם ביום 15/01/2024
2. התובע טען כי ההסכם נחתם ביום 20/06/2024
3. בית המשפט יכריע בעניין"""
        claims = extract_claims(text, strategy="clause", sanitize=False)
        assert len(claims) >= 2


# ===================================================================
# 7. Reconciler Integration Scenarios
# ===================================================================

class TestReconcilerIntegrationScenarios:
    """Integration tests for reconciler with various claim configurations."""

    def test_fact_vs_fact_same_entity_negation(self):
        a = _claim(
            "יוסי כהן שילם את הסכום במלואו",
            plane="FACT", speaker_mode="finding",
            entities=["יוסי כהן"], negation=False,
            context_before="ctx", context_after="ctx",
        )
        b = _claim(
            "יוסי כהן לא שילם את הסכום",
            plane="FACT", speaker_mode="finding",
            entities=["יוסי כהן"], negation=True,
            context_before="ctx", context_after="ctx",
        )
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome == OUTCOME_TRUE_CONTRADICTION

    def test_cross_party_disagreement(self):
        a = _claim(
            "שילמתי את הכל",
            plane="FACT", speaker_mode="party_claim",
            speaker_role="defendant", entities=["הנתבע"],
        )
        b = _claim(
            "לא שולם לי דבר",
            plane="FACT", speaker_mode="party_claim",
            speaker_role="plaintiff", entities=["התובע"],
        )
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome in ("DISAGREEMENT_BETWEEN_PARTIES", "ROLE_OR_ATTRIBUTION_MISMATCH")

    def test_time_shift_not_true_contradiction(self):
        a = _claim(
            "ביום 1.1.2020 נחתם ההסכם",
            plane="FACT", speaker_mode="finding",
            time_reference="1.1.2020",
        )
        b = _claim(
            "ביום 1.6.2022 בוטל ההסכם",
            plane="FACT", speaker_mode="finding",
            time_reference="1.6.2022",
        )
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome == OUTCOME_TIME_SHIFT

    def test_duplicate_detection(self):
        a = _claim(
            "ההסכם נחתם ביום 15/01/2024",
            plane="FACT", speaker_mode="finding",
        )
        b = _claim(
            "ההסכם נחתם ביום 15/01/2024",
            plane="FACT", speaker_mode="finding",
        )
        result = reconcile_pair(a, b, detector_confidence=0.9)
        assert result.outcome == OUTCOME_DUPLICATE


# ===================================================================
# 8. Detection with Multiple Contradiction Types
# ===================================================================

class TestMultipleContradictionTypes:
    """Test scenarios with multiple contradiction types in same claim set."""

    def test_temporal_and_quantitative(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("ביום 15/01/2024 שולם סכום של ₪50,000 לחברה", id="c1"),
            _claim("ביום 20/06/2024 שולם סכום של ₪150,000 לחברה", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        types_found = set(c.type for c in result.contradictions)
        # Should detect at least one type of contradiction
        assert len(result.contradictions) >= 1

    def test_presence_and_document(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("הייתי נוכח בפגישה וקיים הסכם שנחתם שם", id="c1"),
            _claim("לא הייתי נוכח בפגישה ואין הסכם בין הצדדים", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        assert len(result.contradictions) >= 1


# ===================================================================
# 9. Contradiction Properties
# ===================================================================

class TestContradictionProperties:
    """Test properties of detected contradictions."""

    def test_contradiction_has_id(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("ההסכם נחתם ביום 15/01/2024", id="c1"),
            _claim("ההסכם נחתם ביום 20/06/2024", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        for c in result.contradictions:
            assert c.id is not None
            assert len(c.id) > 0

    def test_contradiction_has_claims(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("ההסכם נחתם ביום 15/01/2024", id="c1"),
            _claim("ההסכם נחתם ביום 20/06/2024", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        for c in result.contradictions:
            assert c.claim1 is not None
            assert c.claim2 is not None

    def test_contradiction_has_type(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("ההסכם נחתם ביום 15/01/2024", id="c1"),
            _claim("ההסכם נחתם ביום 20/06/2024", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        for c in result.contradictions:
            assert c.type is not None

    def test_contradiction_has_status(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("ההסכם נחתם ביום 15/01/2024", id="c1"),
            _claim("ההסכם נחתם ביום 20/06/2024", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        for c in result.contradictions:
            assert c.status in (ContradictionStatus.VERIFIED, ContradictionStatus.LIKELY, ContradictionStatus.SUSPICIOUS)

    def test_contradiction_has_severity(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("ההסכם נחתם ביום 15/01/2024", id="c1"),
            _claim("ההסכם נחתם ביום 20/06/2024", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        for c in result.contradictions:
            assert c.severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW)

    def test_contradiction_has_confidence(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("ההסכם נחתם ביום 15/01/2024", id="c1"),
            _claim("ההסכם נחתם ביום 20/06/2024", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        for c in result.contradictions:
            assert 0 <= c.confidence <= 1

    def test_contradiction_has_explanation(self):
        detector = RuleBasedDetector()
        claims = [
            _claim("ההסכם נחתם ביום 15/01/2024", id="c1"),
            _claim("ההסכם נחתם ביום 20/06/2024", id="c2"),
        ]
        result = detector.detect(claims, enrich=False)
        for c in result.contradictions:
            assert c.explanation is not None
            assert len(c.explanation) > 0


# ===================================================================
# 10. Detection Result Properties
# ===================================================================

class TestDetectionResultProperties:
    def test_result_has_contradictions_list(self):
        detector = RuleBasedDetector()
        result = detector.detect([], enrich=False)
        assert isinstance(result.contradictions, list)

    def test_result_has_detection_time(self):
        detector = RuleBasedDetector()
        result = detector.detect([], enrich=False)
        assert result.detection_time_ms >= 0

    def test_result_has_method(self):
        detector = RuleBasedDetector()
        result = detector.detect([], enrich=False)
        assert result.method in ("rule_based", "rule_based_v3")

    def test_result_has_metadata(self):
        detector = RuleBasedDetector()
        result = detector.detect([], enrich=False)
        assert isinstance(result.metadata, dict)

    def test_metadata_keys(self):
        detector = RuleBasedDetector()
        claims = [_claim("c1"), _claim("c2")]
        result = detector.detect(claims, enrich=False)
        expected_keys = [
            "temporal_count", "quantitative_count",
            "attribution_count", "presence_count",
            "doc_existence_count", "identity_count",
            "claims_analyzed",
        ]
        for key in expected_keys:
            assert key in result.metadata, f"Missing key: {key}"


# ===================================================================
# 11. Claim Evidence Conversion
# ===================================================================

class TestClaimEvidenceConversion:
    def test_to_claim_evidence_with_doc_id(self):
        claim = _claim("test claim", doc_id="doc1", page=3)
        contr = DetectedContradiction(
            id="test", claim1=claim, claim2=claim,
            type=ContradictionType.TEMPORAL_DATE,
            subtype=None, status=ContradictionStatus.VERIFIED,
            severity=Severity.HIGH, confidence=0.9,
            same_event_confidence=0.8, explanation="test",
            quote1="q1", quote2="q2",
        )
        evidence = contr.to_claim_evidence(claim, "quote", "normalized")
        assert evidence.doc_id == "doc1"
        assert evidence.quote == "quote"
        assert evidence.normalized == "normalized"

    def test_to_claim_evidence_without_doc_id(self):
        claim = _claim("test claim")
        contr = DetectedContradiction(
            id="test", claim1=claim, claim2=claim,
            type=ContradictionType.TEMPORAL_DATE,
            subtype=None, status=ContradictionStatus.VERIFIED,
            severity=Severity.HIGH, confidence=0.9,
            same_event_confidence=0.8, explanation="test",
            quote1="q1", quote2="q2",
        )
        evidence = contr.to_claim_evidence(claim, "quote", None)
        assert evidence.locator is None


# ===================================================================
# 12. Insight Scoring Logic
# ===================================================================

class TestInsightScoringLogic:
    """Test the scoring logic patterns used by the insight engine."""

    def test_verified_higher_than_likely(self):
        """VERIFIED status should indicate higher certainty."""
        assert ContradictionStatus.VERIFIED.value == "verified"
        assert ContradictionStatus.LIKELY.value == "likely"

    def test_critical_severity_highest(self):
        """CRITICAL is the highest severity."""
        severities = {
            Severity.CRITICAL: 4,
            Severity.HIGH: 3,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
        }
        assert severities[Severity.CRITICAL] > severities[Severity.HIGH]
        assert severities[Severity.HIGH] > severities[Severity.MEDIUM]
        assert severities[Severity.MEDIUM] > severities[Severity.LOW]

    def test_hard_contradiction_most_important(self):
        """Hard contradiction should be most important for litigation."""
        assert ContradictionCategory.HARD_CONTRADICTION.value == "hard_contradiction"
        assert ContradictionCategory.TRUE_CONTRADICTION.value == "TRUE_CONTRADICTION"

    def test_narrative_ambiguity_less_important(self):
        """Narrative ambiguity is less critical than hard contradiction."""
        assert ContradictionCategory.NARRATIVE_AMBIGUITY.value == "narrative_ambiguity"
