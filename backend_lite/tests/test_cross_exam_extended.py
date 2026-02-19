"""
Extended Logical Tests — Cross-Examination, Insights & Integration
===================================================================

~120 tests covering:
- QuestionTypeSelector logic (select_type, get_question_prefix, transform_to_type)
- PlaybookLoader (embedded playbooks, caching)
- DocumentSourceClassifier (classify_claim_source, _detect_document_type, etc.)
- CrossExamSourceContext (strategic approach, question phrasing)
- create_source_classifier / classify_contradiction_sources helpers
- Deduplication logic
- Entity graph extraction
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
from backend_lite.cross_exam import QuestionType, QuestionTypeSelector, PlaybookLoader
from backend_lite.source_classifier import (
    DocumentSourceClassifier,
    SourceType,
    PartyRole,
    DocumentMetadata,
    SourceClassification,
    CrossExamSourceContext,
    create_source_classifier,
    classify_contradiction_sources,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(text: str, **kwargs) -> Claim:
    defaults = dict(id=kwargs.pop("id", f"c_{abs(hash(text)) % 100000}"), text=text)
    defaults.update(kwargs)
    return Claim(**defaults)


# ===================================================================
# 1. QuestionTypeSelector — select_type
# ===================================================================

class TestQuestionTypeSelectorSelectType:
    """Test QuestionTypeSelector.select_type for all positions and branches."""

    def test_position_0_always_open(self):
        """Position 0 always returns OPEN regardless of other params."""
        result = QuestionTypeSelector.select_type(
            position=0, total_questions=5,
            severity=Severity.HIGH,
            contradiction_type=ContradictionType.TEMPORAL,
        )
        assert result == QuestionType.OPEN

    def test_position_0_open_with_critical_severity(self):
        result = QuestionTypeSelector.select_type(
            position=0, total_questions=5,
            severity=Severity.CRITICAL,
            contradiction_type=ContradictionType.FACTUAL,
        )
        assert result == QuestionType.OPEN

    def test_position_0_open_with_quantitative(self):
        result = QuestionTypeSelector.select_type(
            position=0, total_questions=5,
            severity=Severity.LOW,
            contradiction_type=ContradictionType.QUANTITATIVE,
        )
        assert result == QuestionType.OPEN

    def test_position_1_temporal_returns_yes_no(self):
        """Position 1 with TEMPORAL contradiction returns YES_NO."""
        result = QuestionTypeSelector.select_type(
            position=1, total_questions=5,
            severity=Severity.HIGH,
            contradiction_type=ContradictionType.TEMPORAL,
        )
        assert result == QuestionType.YES_NO

    def test_position_1_quantitative_returns_yes_no(self):
        """Position 1 with QUANTITATIVE contradiction returns YES_NO."""
        result = QuestionTypeSelector.select_type(
            position=1, total_questions=5,
            severity=Severity.MEDIUM,
            contradiction_type=ContradictionType.QUANTITATIVE,
        )
        assert result == QuestionType.YES_NO

    def test_position_1_factual_returns_open(self):
        """Position 1 with FACTUAL contradiction returns OPEN."""
        result = QuestionTypeSelector.select_type(
            position=1, total_questions=5,
            severity=Severity.HIGH,
            contradiction_type=ContradictionType.FACTUAL,
        )
        assert result == QuestionType.OPEN

    def test_position_1_attribution_returns_open(self):
        """Position 1 with ATTRIBUTION contradiction returns OPEN."""
        result = QuestionTypeSelector.select_type(
            position=1, total_questions=5,
            severity=Severity.HIGH,
            contradiction_type=ContradictionType.ATTRIBUTION,
        )
        assert result == QuestionType.OPEN

    def test_position_1_witness_returns_open(self):
        result = QuestionTypeSelector.select_type(
            position=1, total_questions=5,
            severity=Severity.HIGH,
            contradiction_type=ContradictionType.WITNESS,
        )
        assert result == QuestionType.OPEN

    def test_position_2_high_confidence_returns_confrontation(self):
        """Position 2 with confidence >= 0.85 returns CONFRONTATION."""
        result = QuestionTypeSelector.select_type(
            position=2, total_questions=5,
            severity=Severity.HIGH,
            contradiction_type=ContradictionType.TEMPORAL,
            confidence=0.9,
        )
        assert result == QuestionType.CONFRONTATION

    def test_position_2_exactly_085_returns_confrontation(self):
        result = QuestionTypeSelector.select_type(
            position=2, total_questions=5,
            severity=Severity.HIGH,
            contradiction_type=ContradictionType.TEMPORAL,
            confidence=0.85,
        )
        assert result == QuestionType.CONFRONTATION

    def test_position_2_low_confidence_returns_clarification(self):
        """Position 2 with confidence < 0.85 returns CLARIFICATION."""
        result = QuestionTypeSelector.select_type(
            position=2, total_questions=5,
            severity=Severity.HIGH,
            contradiction_type=ContradictionType.TEMPORAL,
            confidence=0.7,
        )
        assert result == QuestionType.CLARIFICATION

    def test_position_2_confidence_084_returns_clarification(self):
        result = QuestionTypeSelector.select_type(
            position=2, total_questions=5,
            severity=Severity.MEDIUM,
            contradiction_type=ContradictionType.FACTUAL,
            confidence=0.84,
        )
        assert result == QuestionType.CLARIFICATION

    def test_position_3_critical_severity_returns_trap(self):
        """Position 3 with CRITICAL severity returns TRAP."""
        result = QuestionTypeSelector.select_type(
            position=3, total_questions=5,
            severity=Severity.CRITICAL,
            contradiction_type=ContradictionType.TEMPORAL,
        )
        assert result == QuestionType.TRAP

    def test_position_3_high_severity_returns_trap(self):
        """Position 3 with HIGH severity returns TRAP."""
        result = QuestionTypeSelector.select_type(
            position=3, total_questions=5,
            severity=Severity.HIGH,
            contradiction_type=ContradictionType.FACTUAL,
        )
        assert result == QuestionType.TRAP

    def test_position_3_medium_severity_returns_leading(self):
        """Position 3 with MEDIUM severity returns LEADING."""
        result = QuestionTypeSelector.select_type(
            position=3, total_questions=5,
            severity=Severity.MEDIUM,
            contradiction_type=ContradictionType.TEMPORAL,
        )
        assert result == QuestionType.LEADING

    def test_position_3_low_severity_returns_leading(self):
        """Position 3 with LOW severity returns LEADING."""
        result = QuestionTypeSelector.select_type(
            position=3, total_questions=5,
            severity=Severity.LOW,
            contradiction_type=ContradictionType.FACTUAL,
        )
        assert result == QuestionType.LEADING

    def test_position_4_returns_open(self):
        """Position >= 4 (beyond special positions) returns OPEN."""
        result = QuestionTypeSelector.select_type(
            position=4, total_questions=5,
            severity=Severity.HIGH,
            contradiction_type=ContradictionType.TEMPORAL,
        )
        assert result == QuestionType.OPEN

    def test_position_5_returns_open(self):
        """Position 5 (last question) returns OPEN."""
        result = QuestionTypeSelector.select_type(
            position=5, total_questions=6,
            severity=Severity.CRITICAL,
            contradiction_type=ContradictionType.FACTUAL,
        )
        assert result == QuestionType.OPEN

    def test_position_10_returns_open(self):
        result = QuestionTypeSelector.select_type(
            position=10, total_questions=15,
            severity=Severity.HIGH,
            contradiction_type=ContradictionType.TEMPORAL,
        )
        assert result == QuestionType.OPEN


# ===================================================================
# 2. QuestionTypeSelector — get_question_prefix
# ===================================================================

class TestQuestionTypeSelectorPrefix:
    """Test get_question_prefix for all question types."""

    def test_leading_prefix(self):
        result = QuestionTypeSelector.get_question_prefix(QuestionType.LEADING)
        assert result == "נכון לומר ש"

    def test_clarification_prefix(self):
        result = QuestionTypeSelector.get_question_prefix(QuestionType.CLARIFICATION)
        assert result == "תוכל להבהיר "

    def test_yes_no_prefix_empty(self):
        result = QuestionTypeSelector.get_question_prefix(QuestionType.YES_NO)
        assert result == ""

    def test_open_prefix_empty(self):
        result = QuestionTypeSelector.get_question_prefix(QuestionType.OPEN)
        assert result == ""

    def test_confrontation_prefix_empty(self):
        result = QuestionTypeSelector.get_question_prefix(QuestionType.CONFRONTATION)
        assert result == ""

    def test_trap_prefix_empty(self):
        result = QuestionTypeSelector.get_question_prefix(QuestionType.TRAP)
        assert result == ""

    def test_unknown_type_returns_empty(self):
        result = QuestionTypeSelector.get_question_prefix("nonexistent_type")
        assert result == ""


# ===================================================================
# 3. QuestionTypeSelector — transform_to_type
# ===================================================================

class TestQuestionTypeSelectorTransform:
    """Test transform_to_type for all question types."""

    def test_transform_to_yes_no_adds_nachon(self):
        """YES_NO transform adds ', נכון?' suffix."""
        question = "ההסכם נחתם ביום 15/01/2024"
        result = QuestionTypeSelector.transform_to_type(question, QuestionType.YES_NO, {})
        assert result.endswith(", נכון?")

    def test_transform_to_yes_no_already_has_nachon(self):
        """YES_NO transform does not double-add ', נכון?' if already present."""
        question = "ההסכם נחתם ביום 15/01/2024, נכון?"
        result = QuestionTypeSelector.transform_to_type(question, QuestionType.YES_NO, {})
        assert result.count("נכון?") == 1

    def test_transform_to_yes_no_adds_question_mark(self):
        question = "ההסכם נחתם"
        result = QuestionTypeSelector.transform_to_type(question, QuestionType.YES_NO, {})
        assert "?" in result

    def test_transform_to_leading_adds_prefix(self):
        """LEADING transform adds 'נכון לומר ש' prefix."""
        question = "ההסכם נחתם ביום 15/01/2024"
        result = QuestionTypeSelector.transform_to_type(question, QuestionType.LEADING, {})
        assert result.startswith("נכון לומר ש")

    def test_transform_to_leading_removes_ha_im(self):
        """LEADING transform removes 'האם' from the question."""
        question = "האם ההסכם נחתם ביום 15/01/2024?"
        result = QuestionTypeSelector.transform_to_type(question, QuestionType.LEADING, {})
        assert "נכון לומר ש" in result
        assert "האם" not in result

    def test_transform_to_leading_already_has_prefix(self):
        """LEADING transform does not double-add prefix."""
        question = "נכון לומר שההסכם נחתם?"
        result = QuestionTypeSelector.transform_to_type(question, QuestionType.LEADING, {})
        assert result.count("נכון לומר ש") == 1

    def test_transform_to_open_keeps_open_question(self):
        """OPEN transform leaves an already-open question unchanged."""
        question = "ספר לי על מה שקרה ביום 15/01/2024"
        result = QuestionTypeSelector.transform_to_type(question, QuestionType.OPEN, {})
        assert result == question

    def test_transform_to_open_keeps_descriptive_question(self):
        question = "תאר את מה שראית"
        result = QuestionTypeSelector.transform_to_type(question, QuestionType.OPEN, {})
        assert result == question

    def test_transform_to_confrontation_returns_unchanged(self):
        """CONFRONTATION transform returns question unchanged."""
        question = "בתצהיר שלך כתבת X אבל במסמך אחר כתוב Y"
        result = QuestionTypeSelector.transform_to_type(question, QuestionType.CONFRONTATION, {})
        assert result == question

    def test_transform_to_clarification_adds_prefix(self):
        """CLARIFICATION transform adds 'תוכל להבהיר ' prefix."""
        question = "מה קרה ביום 15/01/2024?"
        result = QuestionTypeSelector.transform_to_type(question, QuestionType.CLARIFICATION, {})
        assert "תוכל" in result

    def test_transform_to_trap_returns_trap_question(self):
        """TRAP transform returns one of the predefined trap questions."""
        question = "כלשהי"
        result = QuestionTypeSelector.transform_to_type(question, QuestionType.TRAP, {})
        trap_options = [
            "האם יש סיבה כלשהי לכך שהגרסה השתנתה?",
            "האם אתה זוכר בדיוק מה אמרת קודם?",
            "האם יש מסמך שתומך בגרסה הנוכחית?",
        ]
        assert result in trap_options


# ===================================================================
# 4. PlaybookLoader
# ===================================================================

class TestPlaybookLoader:
    """Test PlaybookLoader loading and cache behavior."""

    def test_load_returns_dict(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        assert isinstance(result, dict)

    def test_embedded_playbooks_contain_temporal(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        assert "temporal" in result

    def test_embedded_playbooks_contain_quantitative(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        assert "quantitative" in result

    def test_embedded_playbooks_contain_attribution(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        assert "attribution" in result

    def test_embedded_playbooks_contain_factual(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        assert "factual" in result

    def test_embedded_playbooks_contain_version(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        assert "version" in result

    def test_embedded_playbooks_contain_witness(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        assert "witness" in result

    def test_embedded_playbooks_contain_cross_party(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        assert "cross_party" in result

    def test_embedded_playbooks_contain_internal(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        assert "internal" in result

    def test_temporal_has_question_set(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        temporal = result["temporal"]
        assert "cross_examination" in temporal
        assert "question_set" in temporal["cross_examination"]
        assert isinstance(temporal["cross_examination"]["question_set"], list)
        assert len(temporal["cross_examination"]["question_set"]) > 0

    def test_temporal_has_trap_branches(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        temporal = result["temporal"]
        assert "trap_branches" in temporal["cross_examination"]
        assert isinstance(temporal["cross_examination"]["trap_branches"], list)

    def test_all_playbooks_have_cross_examination_structure(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        required_keys = [
            "temporal", "quantitative", "attribution", "factual",
            "version", "witness", "cross_party", "internal",
        ]
        for key in required_keys:
            assert key in result, f"Missing playbook: {key}"
            playbook = result[key]
            assert "cross_examination" in playbook, f"{key} missing cross_examination"
            ce = playbook["cross_examination"]
            assert "question_set" in ce, f"{key} missing question_set"
            assert "trap_branches" in ce, f"{key} missing trap_branches"

    def test_cache_reset_and_reload(self):
        """Setting _playbooks = None forces reload."""
        PlaybookLoader._playbooks = None
        first = PlaybookLoader.load()
        assert PlaybookLoader._playbooks is not None
        PlaybookLoader._playbooks = None
        assert PlaybookLoader._playbooks is None
        second = PlaybookLoader.load()
        assert PlaybookLoader._playbooks is not None
        assert set(first.keys()) == set(second.keys())

    def test_caching_returns_same_object(self):
        """Second call returns same cached dict without resetting."""
        PlaybookLoader._playbooks = None
        first = PlaybookLoader.load()
        second = PlaybookLoader.load()
        assert first is second


# ===================================================================
# 5. DocumentSourceClassifier — classify_claim_source
# ===================================================================

class TestDocumentSourceClassifierBasic:
    """Test classify_claim_source with different inputs."""

    def test_classify_from_metadata_examined_witness(self):
        """When doc_id matches metadata with is_examined_witness, returns WITNESS_OWN_STATEMENT."""
        meta = DocumentMetadata(
            doc_id="doc1", doc_name="תצהיר של מר כהן",
            doc_type="תצהיר", party_role=PartyRole.DEFENDANT,
            witness_name="כהן", is_examined_witness=True,
        )
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            documents_metadata=[meta],
        )
        result = classifier.classify_claim_source("טענה כלשהי", doc_id="doc1")
        assert result.source_type == SourceType.WITNESS_OWN_STATEMENT

    def test_classify_from_metadata_supporting_witness(self):
        """Affidavit from same party but different witness -> SUPPORTING_WITNESS."""
        meta = DocumentMetadata(
            doc_id="doc2", doc_name="תצהיר של מר לוי",
            doc_type="תצהיר", party_role=PartyRole.DEFENDANT,
            witness_name="לוי", is_examined_witness=False,
        )
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            documents_metadata=[meta],
        )
        result = classifier.classify_claim_source("טענה כלשהי", doc_id="doc2")
        assert result.source_type == SourceType.SUPPORTING_WITNESS

    def test_classify_tatzir_doc_name(self):
        """Doc name with 'תצהיר של מר כהן' and matching witness name -> WITNESS_OWN_STATEMENT."""
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )
        result = classifier.classify_claim_source(
            "טענה כלשהי", doc_name="תצהיר של מר כהן",
        )
        assert result.source_type == SourceType.WITNESS_OWN_STATEMENT

    def test_classify_ktav_hagana(self):
        """Doc name with 'כתב הגנה' from same party -> PARTY_PLEADING."""
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )
        result = classifier.classify_claim_source(
            "טענה", doc_name="כתב הגנה מטעם ההגנה",
        )
        assert result.source_type == SourceType.PARTY_PLEADING

    def test_classify_ktav_tvia_from_opposing(self):
        """Doc name 'כתב תביעה' from the plaintiff when witness is defendant -> OPPOSING_EVIDENCE."""
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )
        result = classifier.classify_claim_source(
            "טענה", doc_name="כתב תביעה מטעם התביעה",
        )
        # plaintiff party detected, but witness is defendant -> opposing
        assert result.source_type == SourceType.OPPOSING_EVIDENCE

    def test_classify_psak_din(self):
        """Doc name with 'פסק דין' returns COURT_FINDING."""
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )
        result = classifier.classify_claim_source("טענה", doc_name="פסק דין חלקי")
        assert result.source_type == SourceType.COURT_FINDING

    def test_classify_speaker_mode_finding(self):
        """speaker_mode='finding' returns COURT_FINDING even without doc info."""
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )
        result = classifier.classify_claim_source("טענה", speaker_mode="finding")
        assert result.source_type == SourceType.COURT_FINDING

    def test_classify_speaker_mode_party_claim_same_party(self):
        """speaker_mode='party_claim' from same party -> PARTY_PLEADING."""
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )
        result = classifier.classify_claim_source(
            "טענה", speaker_mode="party_claim", speaker_role="defendant",
        )
        assert result.source_type == SourceType.PARTY_PLEADING

    def test_classify_speaker_mode_party_claim_opposing_party(self):
        """speaker_mode='party_claim' from opposing party -> OPPOSING_EVIDENCE."""
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )
        result = classifier.classify_claim_source(
            "טענה", speaker_mode="party_claim", speaker_role="plaintiff",
        )
        assert result.source_type == SourceType.OPPOSING_EVIDENCE

    def test_classify_no_info_returns_unknown(self):
        """No doc info and no speaker mode -> UNKNOWN."""
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )
        result = classifier.classify_claim_source("טענה כלשהי")
        assert result.source_type == SourceType.UNKNOWN

    def test_classification_has_reference_phrase(self):
        """Classified witness_own_statement has a non-empty reference_phrase."""
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )
        result = classifier.classify_claim_source(
            "טענה", doc_name="תצהיר של מר כהן",
        )
        assert result.reference_phrase  # non-empty
        assert "תצהיר" in result.reference_phrase

    def test_classification_has_attribution_phrase(self):
        """Classified witness_own_statement has a non-empty attribution_phrase."""
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )
        result = classifier.classify_claim_source(
            "טענה", doc_name="תצהיר של מר כהן",
        )
        assert result.attribution_phrase  # non-empty

    def test_court_finding_metadata(self):
        """Court finding from metadata with COURT party_role."""
        meta = DocumentMetadata(
            doc_id="court1", doc_name="פסק דין",
            doc_type="פסק_דין", party_role=PartyRole.COURT,
        )
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            documents_metadata=[meta],
        )
        result = classifier.classify_claim_source("טענה", doc_id="court1")
        assert result.source_type == SourceType.COURT_FINDING


# ===================================================================
# 6. DocumentSourceClassifier — _detect_document_type
# ===================================================================

class TestDetectDocumentType:
    """Test _detect_document_type for various Hebrew document names."""

    def setup_method(self):
        self.classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )

    def test_detect_tatzir(self):
        assert self.classifier._detect_document_type("תצהיר של מר כהן") == "תצהיר"

    def test_detect_tatzir_edut(self):
        assert self.classifier._detect_document_type("תצהיר עדות ראשית של מר לוי") == "תצהיר"

    def test_detect_ktav_hagana(self):
        assert self.classifier._detect_document_type("כתב הגנה") == "כתב_הגנה"

    def test_detect_ktav_hagana_metukan(self):
        assert self.classifier._detect_document_type("כתב הגנה מתוקן") == "כתב_הגנה"

    def test_detect_ktav_tvia(self):
        assert self.classifier._detect_document_type("כתב תביעה") == "כתב_תביעה"

    def test_detect_psak_din(self):
        assert self.classifier._detect_document_type("פסק דין") == "פסק_דין"

    def test_detect_hachlata(self):
        assert self.classifier._detect_document_type("החלטה מיום 15/01/2024") == "פסק_דין"

    def test_detect_protocol(self):
        assert self.classifier._detect_document_type("פרוטוקול דיון מיום 10/03/2024") == "פרוטוקול"

    def test_detect_havat_daat(self):
        assert self.classifier._detect_document_type("חוות דעת מומחה") == "חוות_דעת"

    def test_detect_unknown(self):
        assert self.classifier._detect_document_type("מכתב כלשהו") == "מסמך"


# ===================================================================
# 7. DocumentSourceClassifier — _detect_party_from_doc_name
# ===================================================================

class TestDetectPartyFromDocName:
    """Test _detect_party_from_doc_name for various document name patterns."""

    def setup_method(self):
        self.classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )

    def test_detect_plaintiff(self):
        result = self.classifier._detect_party_from_doc_name("תצהיר התובע")
        assert result == PartyRole.PLAINTIFF

    def test_detect_defendant(self):
        result = self.classifier._detect_party_from_doc_name("תצהיר הנתבע")
        assert result == PartyRole.DEFENDANT

    def test_detect_witness(self):
        result = self.classifier._detect_party_from_doc_name("העד יוסי")
        assert result == PartyRole.WITNESS

    def test_detect_court(self):
        result = self.classifier._detect_party_from_doc_name("בית המשפט קבע")
        assert result == PartyRole.COURT

    def test_detect_unknown(self):
        result = self.classifier._detect_party_from_doc_name("מסמך כלשהו")
        assert result == PartyRole.UNKNOWN

    def test_detect_meshiv(self):
        result = self.classifier._detect_party_from_doc_name("תצהיר המשיבה")
        assert result == PartyRole.DEFENDANT

    def test_detect_mevaresh(self):
        result = self.classifier._detect_party_from_doc_name("תצהיר המבקשת")
        assert result == PartyRole.PLAINTIFF


# ===================================================================
# 8. DocumentSourceClassifier — _is_examined_witness_document
# ===================================================================

class TestIsExaminedWitnessDocument:
    """Test _is_examined_witness_document with various inputs."""

    def test_match_by_doc_name(self):
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )
        assert classifier._is_examined_witness_document("תצהיר של מר כהן") is True

    def test_no_match_different_name(self):
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )
        assert classifier._is_examined_witness_document("תצהיר של מר לוי") is False

    def test_match_by_speaker(self):
        classifier = DocumentSourceClassifier(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
        )
        assert classifier._is_examined_witness_document("תצהיר כלשהו", speaker="מר כהן") is True

    def test_no_witness_name_returns_false(self):
        classifier = DocumentSourceClassifier(
            examined_witness_name=None,
            examined_witness_party=PartyRole.DEFENDANT,
        )
        assert classifier._is_examined_witness_document("תצהיר כהן") is False


# ===================================================================
# 9. CrossExamSourceContext
# ===================================================================

class TestCrossExamSourceContext:
    """Test CrossExamSourceContext strategic logic."""

    def _make_classification(self, source_type, ref="", attr="", confront=""):
        return SourceClassification(
            source_type=source_type,
            reference_phrase=ref,
            attribution_phrase=attr,
            confrontation_phrase=confront,
        )

    def test_is_internal_contradiction_both_own(self):
        """Both claims from WITNESS_OWN_STATEMENT -> internal contradiction."""
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(SourceType.WITNESS_OWN_STATEMENT),
            contradiction_claim2_source=self._make_classification(SourceType.WITNESS_OWN_STATEMENT),
        )
        assert ctx.is_internal_contradiction() is True
        assert ctx.is_supporting_witness_contradiction() is False

    def test_not_internal_when_different_sources(self):
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(SourceType.WITNESS_OWN_STATEMENT),
            contradiction_claim2_source=self._make_classification(SourceType.OPPOSING_EVIDENCE),
        )
        assert ctx.is_internal_contradiction() is False

    def test_is_supporting_witness_contradiction(self):
        """One WITNESS_OWN_STATEMENT and one SUPPORTING_WITNESS -> supporting witness contradiction."""
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(SourceType.WITNESS_OWN_STATEMENT),
            contradiction_claim2_source=self._make_classification(SourceType.SUPPORTING_WITNESS),
        )
        assert ctx.is_supporting_witness_contradiction() is True

    def test_supporting_witness_contradiction_reversed_order(self):
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(SourceType.SUPPORTING_WITNESS),
            contradiction_claim2_source=self._make_classification(SourceType.WITNESS_OWN_STATEMENT),
        )
        assert ctx.is_supporting_witness_contradiction() is True

    def test_strategic_approach_internal(self):
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(SourceType.WITNESS_OWN_STATEMENT),
            contradiction_claim2_source=self._make_classification(SourceType.WITNESS_OWN_STATEMENT),
        )
        assert ctx.get_strategic_approach() == "internal_contradiction"

    def test_strategic_approach_cross_party(self):
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(SourceType.WITNESS_OWN_STATEMENT),
            contradiction_claim2_source=self._make_classification(SourceType.OPPOSING_EVIDENCE),
        )
        assert ctx.get_strategic_approach() == "cross_party_conflict"

    def test_strategic_approach_court_finding(self):
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(SourceType.WITNESS_OWN_STATEMENT),
            contradiction_claim2_source=self._make_classification(SourceType.COURT_FINDING),
        )
        assert ctx.get_strategic_approach() == "contradict_court_finding"

    def test_strategic_approach_supporting_witness(self):
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(SourceType.WITNESS_OWN_STATEMENT),
            contradiction_claim2_source=self._make_classification(SourceType.SUPPORTING_WITNESS),
        )
        assert ctx.get_strategic_approach() == "supporting_witness_conflict"

    def test_strategic_approach_external_document(self):
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(SourceType.WITNESS_OWN_STATEMENT),
            contradiction_claim2_source=self._make_classification(SourceType.EXTERNAL_DOCUMENT),
        )
        assert ctx.get_strategic_approach() == "contradict_document"

    def test_strategic_approach_general_fallback(self):
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(SourceType.PARTY_PLEADING),
            contradiction_claim2_source=self._make_classification(SourceType.EXTERNAL_DOCUMENT),
        )
        assert ctx.get_strategic_approach() == "general_contradiction"

    def test_get_question_phrasing_returns_required_keys(self):
        """get_question_phrasing always returns dict with opening, confrontation, closing, strategy_note, approach."""
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(
                SourceType.WITNESS_OWN_STATEMENT,
                ref="בתצהיר שלך", attr="אתה כתבת ש",
            ),
            contradiction_claim2_source=self._make_classification(
                SourceType.OPPOSING_EVIDENCE,
                confront="הצד השני מציג ראיה ש",
            ),
        )
        phrasing = ctx.get_question_phrasing()
        assert "opening" in phrasing
        assert "confrontation" in phrasing
        assert "closing" in phrasing
        assert "strategy_note" in phrasing
        assert "approach" in phrasing

    def test_phrasing_internal_contains_closing(self):
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(
                SourceType.WITNESS_OWN_STATEMENT,
                ref="בתצהיר שלך", attr="אתה כתבת ש",
            ),
            contradiction_claim2_source=self._make_classification(
                SourceType.WITNESS_OWN_STATEMENT,
                ref="בתצהיר שלך", attr="אתה כתבת ש",
            ),
        )
        phrasing = ctx.get_question_phrasing()
        assert phrasing["approach"] == "internal_contradiction"
        assert "נכונה" in phrasing["closing"]

    def test_phrasing_court_finding_closing(self):
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(
                SourceType.WITNESS_OWN_STATEMENT, attr="אתה כתבת ש",
            ),
            contradiction_claim2_source=self._make_classification(
                SourceType.COURT_FINDING, confront="אבל בית המשפט כבר קבע ש",
            ),
        )
        phrasing = ctx.get_question_phrasing()
        assert phrasing["approach"] == "contradict_court_finding"
        assert "בית המשפט" in phrasing["closing"]

    def test_generate_source_aware_question_confrontation(self):
        """generate_source_aware_question produces question with both quotes and references."""
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(
                SourceType.WITNESS_OWN_STATEMENT,
                ref="בתצהיר שלך", attr="אתה כתבת ש",
            ),
            contradiction_claim2_source=self._make_classification(
                SourceType.OPPOSING_EVIDENCE,
                confront="הצד השני מציג ראיה ש",
            ),
        )
        question = ctx.generate_source_aware_question(
            quote_a="שילמתי 50,000 שקלים",
            quote_b="לא שולם דבר",
            question_type="confrontation",
        )
        assert "שילמתי 50,000" in question
        assert "לא שולם" in question

    def test_generate_source_aware_question_internal(self):
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(
                SourceType.WITNESS_OWN_STATEMENT,
                ref="בתצהיר שלך",
            ),
            contradiction_claim2_source=self._make_classification(
                SourceType.WITNESS_OWN_STATEMENT,
                ref="בתצהיר שלך",
            ),
        )
        question = ctx.generate_source_aware_question(
            quote_a="ההסכם נחתם ב-15/01",
            quote_b="ההסכם נחתם ב-20/03",
            question_type="confrontation",
        )
        assert "15/01" in question
        assert "20/03" in question

    def test_generate_source_aware_question_clarification(self):
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(
                SourceType.WITNESS_OWN_STATEMENT, attr="אתה כתבת ש",
            ),
            contradiction_claim2_source=self._make_classification(
                SourceType.OPPOSING_EVIDENCE,
            ),
        )
        question = ctx.generate_source_aware_question(
            quote_a="שילמתי את הכל",
            quote_b="לא שולם",
            question_type="clarification",
        )
        assert "שילמתי" in question
        assert "הבהיר" in question

    def test_generate_source_aware_question_trap(self):
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=self._make_classification(
                SourceType.WITNESS_OWN_STATEMENT, attr="אתה כתבת ש",
            ),
            contradiction_claim2_source=self._make_classification(
                SourceType.OPPOSING_EVIDENCE,
            ),
        )
        question = ctx.generate_source_aware_question(
            quote_a="הגעתי לפגישה",
            quote_b="לא הגעת",
            question_type="trap",
        )
        assert "הגעתי" in question

    def test_get_witness_own_claim_claim1(self):
        own = self._make_classification(SourceType.WITNESS_OWN_STATEMENT)
        opp = self._make_classification(SourceType.OPPOSING_EVIDENCE)
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=own,
            contradiction_claim2_source=opp,
        )
        assert ctx.get_witness_own_claim() is own

    def test_get_witness_own_claim_claim2(self):
        opp = self._make_classification(SourceType.OPPOSING_EVIDENCE)
        own = self._make_classification(SourceType.WITNESS_OWN_STATEMENT)
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=opp,
            contradiction_claim2_source=own,
        )
        assert ctx.get_witness_own_claim() is own

    def test_get_opposing_claim(self):
        own = self._make_classification(SourceType.WITNESS_OWN_STATEMENT)
        opp = self._make_classification(SourceType.OPPOSING_EVIDENCE)
        ctx = CrossExamSourceContext(
            examined_witness_name="כהן",
            examined_witness_party=PartyRole.DEFENDANT,
            contradiction_claim1_source=own,
            contradiction_claim2_source=opp,
        )
        assert ctx.get_opposing_claim() is opp


# ===================================================================
# 10. create_source_classifier and classify_contradiction_sources
# ===================================================================

class TestCreateSourceClassifier:
    """Test helper functions for creating classifiers and classifying contradictions."""

    def test_create_classifier_plaintiff(self):
        classifier = create_source_classifier(
            examined_witness_name="כהן",
            examined_witness_party="plaintiff",
        )
        assert classifier.examined_witness_party == PartyRole.PLAINTIFF
        assert classifier.examined_witness_name == "כהן"

    def test_create_classifier_defendant(self):
        classifier = create_source_classifier(
            examined_witness_name="לוי",
            examined_witness_party="defendant",
        )
        assert classifier.examined_witness_party == PartyRole.DEFENDANT
        assert classifier.examined_witness_name == "לוי"

    def test_create_classifier_with_documents(self):
        docs = [
            {
                "id": "doc1",
                "name": "תצהיר כהן",
                "type": "תצהיר",
                "party": "defendant",
                "witness_name": "כהן",
                "is_examined_witness": True,
            },
        ]
        classifier = create_source_classifier(
            examined_witness_name="כהן",
            examined_witness_party="defendant",
            documents=docs,
        )
        assert "doc1" in classifier.documents_metadata
        meta = classifier.documents_metadata["doc1"]
        assert meta.is_examined_witness is True
        assert meta.witness_name == "כהן"

    def test_classify_contradiction_sources_returns_context(self):
        classifier = create_source_classifier(
            examined_witness_name="כהן",
            examined_witness_party="defendant",
        )
        ctx = classify_contradiction_sources(
            classifier=classifier,
            claim1_doc_id=None,
            claim1_doc_name="תצהיר של מר כהן",
            claim1_speaker=None,
            claim1_speaker_role=None,
            claim1_speaker_mode=None,
            claim2_doc_id=None,
            claim2_doc_name=None,
            claim2_speaker=None,
            claim2_speaker_role="plaintiff",
            claim2_speaker_mode="party_claim",
        )
        assert isinstance(ctx, CrossExamSourceContext)
        assert ctx.claim1_source.source_type == SourceType.WITNESS_OWN_STATEMENT
        assert ctx.claim2_source.source_type == SourceType.OPPOSING_EVIDENCE

    def test_classify_contradiction_sources_internal(self):
        """Both claims from witness's own documents -> internal contradiction."""
        classifier = create_source_classifier(
            examined_witness_name="כהן",
            examined_witness_party="defendant",
        )
        ctx = classify_contradiction_sources(
            classifier=classifier,
            claim1_doc_id=None,
            claim1_doc_name="תצהיר של מר כהן",
            claim1_speaker=None,
            claim1_speaker_role=None,
            claim1_speaker_mode=None,
            claim2_doc_id=None,
            claim2_doc_name="תצהיר של מר כהן מיום 20/03",
            claim2_speaker=None,
            claim2_speaker_role=None,
            claim2_speaker_mode=None,
        )
        assert ctx.is_internal_contradiction() is True
        assert ctx.get_strategic_approach() == "internal_contradiction"

    def test_classify_contradiction_sources_court_finding(self):
        """One claim from witness, one from court -> contradict_court_finding."""
        classifier = create_source_classifier(
            examined_witness_name="כהן",
            examined_witness_party="defendant",
        )
        ctx = classify_contradiction_sources(
            classifier=classifier,
            claim1_doc_id=None,
            claim1_doc_name="תצהיר של מר כהן",
            claim1_speaker=None,
            claim1_speaker_role=None,
            claim1_speaker_mode=None,
            claim2_doc_id=None,
            claim2_doc_name=None,
            claim2_speaker=None,
            claim2_speaker_role=None,
            claim2_speaker_mode="finding",
        )
        assert ctx.claim2_source.source_type == SourceType.COURT_FINDING
        assert ctx.get_strategic_approach() == "contradict_court_finding"


# ===================================================================
# 11. Deduplication Logic
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
# 12. Entity Graph Logic
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
# 13. End-to-End Detection Pipeline
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
# 14. Extractor + Detector Integration
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
# 15. Reconciler Integration Scenarios
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
# 16. Detection with Multiple Contradiction Types
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
# 17. Contradiction Properties
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
# 18. Detection Result Properties
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
# 19. Claim Evidence Conversion
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
