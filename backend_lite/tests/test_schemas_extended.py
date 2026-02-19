"""
Extended Logical Tests — Schemas & Validation
===============================================

~60 tests covering:
- ContradictionType enum values
- ContradictionSubtype enum values
- ContradictionStatus enum values
- ContradictionCategory enum values
- Severity enum values
- LLMMode enum values
- AmbiguityExplanation pydantic model
- Enum value uniqueness
- Backward compatibility of legacy types
"""

import pytest
from backend_lite.schemas import (
    ContradictionType,
    ContradictionSubtype,
    ContradictionStatus,
    ContradictionCategory,
    Severity,
    LLMMode,
    AmbiguityExplanation,
)


# ===================================================================
# 1. ContradictionType Enum
# ===================================================================

class TestContradictionType:
    def test_tier1_temporal_date(self):
        assert ContradictionType.TEMPORAL_DATE.value == "temporal_date_conflict"

    def test_tier1_quant_amount(self):
        assert ContradictionType.QUANT_AMOUNT.value == "quant_amount_conflict"

    def test_tier1_actor_attribution(self):
        assert ContradictionType.ACTOR_ATTRIBUTION.value == "actor_attribution_conflict"

    def test_tier1_presence_participation(self):
        assert ContradictionType.PRESENCE_PARTICIPATION.value == "presence_participation_conflict"

    def test_tier1_document_existence(self):
        assert ContradictionType.DOCUMENT_EXISTENCE.value == "document_existence_conflict"

    def test_tier1_identity_basic(self):
        assert ContradictionType.IDENTITY_BASIC.value == "identity_basic_conflict"

    def test_tier2_timeline_sequence(self):
        assert ContradictionType.TIMELINE_SEQUENCE.value == "timeline_sequence_conflict"

    def test_tier2_location(self):
        assert ContradictionType.LOCATION.value == "location_conflict"

    def test_tier2_communication_channel(self):
        assert ContradictionType.COMMUNICATION_CHANNEL.value == "communication_channel_conflict"

    def test_tier2_party_position(self):
        assert ContradictionType.PARTY_POSITION.value == "party_position_conflict"

    def test_tier2_version(self):
        assert ContradictionType.VERSION.value == "version_conflict"

    def test_legacy_temporal(self):
        assert ContradictionType.TEMPORAL.value == "temporal_conflict"

    def test_legacy_quantitative(self):
        assert ContradictionType.QUANTITATIVE.value == "quantitative_conflict"

    def test_legacy_attribution(self):
        assert ContradictionType.ATTRIBUTION.value == "attribution_conflict"

    def test_legacy_factual(self):
        assert ContradictionType.FACTUAL.value == "factual_conflict"

    def test_legacy_witness(self):
        assert ContradictionType.WITNESS.value == "witness_conflict"

    def test_legacy_document(self):
        assert ContradictionType.DOCUMENT.value == "document_conflict"

    def test_all_values_unique(self):
        values = [t.value for t in ContradictionType]
        assert len(values) == len(set(values))

    def test_is_string_enum(self):
        assert isinstance(ContradictionType.TEMPORAL_DATE.value, str)
        assert isinstance(ContradictionType.TEMPORAL_DATE, str)


# ===================================================================
# 2. ContradictionSubtype Enum
# ===================================================================

class TestContradictionSubtype:
    def test_temporal_subtypes(self):
        assert ContradictionSubtype.EXACT_DATE.value == "exact_date"
        assert ContradictionSubtype.MONTH_ONLY.value == "month_only"
        assert ContradictionSubtype.RANGE_OVERLAP.value == "range_overlap"
        assert ContradictionSubtype.RELATIVE_DATE.value == "relative_date"

    def test_quantitative_subtypes(self):
        assert ContradictionSubtype.CURRENCY.value == "currency"
        assert ContradictionSubtype.PERCENTAGE.value == "percentage"
        assert ContradictionSubtype.COUNT.value == "count"
        assert ContradictionSubtype.DURATION.value == "duration"

    def test_actor_subtypes(self):
        assert ContradictionSubtype.SENDER.value == "sender"
        assert ContradictionSubtype.DECISION_MAKER.value == "decision_maker"
        assert ContradictionSubtype.SIGNER.value == "signer"
        assert ContradictionSubtype.PAYER.value == "payer"
        assert ContradictionSubtype.RECEIVER.value == "receiver"

    def test_presence_subtypes(self):
        assert ContradictionSubtype.ATTENDED.value == "attended"
        assert ContradictionSubtype.SIGNED.value == "signed"
        assert ContradictionSubtype.PAID.value == "paid"
        assert ContradictionSubtype.DELIVERED.value == "delivered"
        assert ContradictionSubtype.RECEIVED.value == "received"

    def test_document_subtypes(self):
        assert ContradictionSubtype.CONTRACT_EXISTS.value == "contract_exists"
        assert ContradictionSubtype.NOTICE_SENT.value == "notice_sent"
        assert ContradictionSubtype.EMAIL_EXISTS.value == "email_exists"
        assert ContradictionSubtype.SIGNATURE_EXISTS.value == "signature_exists"

    def test_other_subtype(self):
        assert ContradictionSubtype.OTHER.value == "other"

    def test_all_values_unique(self):
        values = [s.value for s in ContradictionSubtype]
        assert len(values) == len(set(values))


# ===================================================================
# 3. ContradictionStatus Enum
# ===================================================================

class TestContradictionStatus:
    def test_verified(self):
        assert ContradictionStatus.VERIFIED.value == "verified"

    def test_likely(self):
        assert ContradictionStatus.LIKELY.value == "likely"

    def test_suspicious(self):
        assert ContradictionStatus.SUSPICIOUS.value == "suspicious"

    def test_all_values_unique(self):
        values = [s.value for s in ContradictionStatus]
        assert len(values) == len(set(values))

    def test_count(self):
        assert len(list(ContradictionStatus)) == 3


# ===================================================================
# 4. ContradictionCategory Enum
# ===================================================================

class TestContradictionCategory:
    def test_v1_hard_contradiction(self):
        assert ContradictionCategory.HARD_CONTRADICTION.value == "hard_contradiction"

    def test_v1_logical_inconsistency(self):
        assert ContradictionCategory.LOGICAL_INCONSISTENCY.value == "logical_inconsistency"

    def test_v1_narrative_ambiguity(self):
        assert ContradictionCategory.NARRATIVE_AMBIGUITY.value == "narrative_ambiguity"

    def test_v1_rhetorical_shift(self):
        assert ContradictionCategory.RHETORICAL_SHIFT.value == "rhetorical_shift"

    def test_v2_true_contradiction(self):
        assert ContradictionCategory.TRUE_CONTRADICTION.value == "TRUE_CONTRADICTION"

    def test_v2_apparent_tension(self):
        assert ContradictionCategory.APPARENT_TENSION_RESOLVABLE.value == "APPARENT_TENSION_RESOLVABLE"

    def test_v2_disagreement(self):
        assert ContradictionCategory.DISAGREEMENT_BETWEEN_PARTIES.value == "DISAGREEMENT_BETWEEN_PARTIES"

    def test_v2_role_mismatch(self):
        assert ContradictionCategory.ROLE_OR_ATTRIBUTION_MISMATCH.value == "ROLE_OR_ATTRIBUTION_MISMATCH"

    def test_v2_plane_mismatch(self):
        assert ContradictionCategory.PLANE_MISMATCH.value == "PLANE_MISMATCH"

    def test_v2_time_shift(self):
        assert ContradictionCategory.TIME_OR_STAGE_SHIFT.value == "TIME_OR_STAGE_SHIFT"

    def test_v2_ambiguity(self):
        assert ContradictionCategory.AMBIGUITY_OR_VAGUENESS.value == "AMBIGUITY_OR_VAGUENESS"

    def test_v2_insufficient_context(self):
        assert ContradictionCategory.INSUFFICIENT_CONTEXT.value == "INSUFFICIENT_CONTEXT"

    def test_v2_duplicate(self):
        assert ContradictionCategory.DUPLICATE_OR_RESTATEMENT.value == "DUPLICATE_OR_RESTATEMENT"

    def test_all_values_unique(self):
        values = [c.value for c in ContradictionCategory]
        assert len(values) == len(set(values))

    def test_total_count(self):
        assert len(list(ContradictionCategory)) == 13  # 4 V1 + 9 V2


# ===================================================================
# 5. Severity Enum
# ===================================================================

class TestSeverity:
    def test_critical(self):
        assert Severity.CRITICAL.value == "critical"

    def test_high(self):
        assert Severity.HIGH.value == "high"

    def test_medium(self):
        assert Severity.MEDIUM.value == "medium"

    def test_low(self):
        assert Severity.LOW.value == "low"

    def test_all_values_unique(self):
        values = [s.value for s in Severity]
        assert len(values) == len(set(values))

    def test_count(self):
        assert len(list(Severity)) == 4


# ===================================================================
# 6. LLMMode Enum
# ===================================================================

class TestLLMMode:
    def test_none(self):
        assert LLMMode.NONE.value == "none"

    def test_openrouter(self):
        assert LLMMode.OPENROUTER.value == "openrouter"

    def test_openai(self):
        assert LLMMode.OPENAI.value == "openai"

    def test_gemini(self):
        assert LLMMode.GEMINI.value == "gemini"

    def test_deepseek(self):
        assert LLMMode.DEEPSEEK.value == "deepseek"

    def test_all_values_unique(self):
        values = [m.value for m in LLMMode]
        assert len(values) == len(set(values))

    def test_count(self):
        assert len(list(LLMMode)) == 5


# ===================================================================
# 7. AmbiguityExplanation Pydantic Model
# ===================================================================

class TestAmbiguityExplanation:
    def test_basic_creation(self):
        ae = AmbiguityExplanation(
            gap_description="תיאור הפער",
            why_not_contradiction="למה לא סתירה",
            litigation_importance="חשיבות ליטיגטיבית",
        )
        assert ae.gap_description == "תיאור הפער"
        assert ae.why_not_contradiction == "למה לא סתירה"
        assert ae.litigation_importance == "חשיבות ליטיגטיבית"

    def test_with_reconciliations(self):
        ae = AmbiguityExplanation(
            gap_description="gap",
            why_not_contradiction="reason",
            litigation_importance="important",
            possible_reconciliations=["option1", "option2"],
        )
        assert len(ae.possible_reconciliations) == 2

    def test_default_empty_reconciliations(self):
        ae = AmbiguityExplanation(
            gap_description="gap",
            why_not_contradiction="reason",
            litigation_importance="important",
        )
        assert ae.possible_reconciliations == []

    def test_serialization(self):
        ae = AmbiguityExplanation(
            gap_description="gap",
            why_not_contradiction="reason",
            litigation_importance="important",
            possible_reconciliations=["opt1"],
        )
        data = ae.model_dump()
        assert data["gap_description"] == "gap"
        assert data["possible_reconciliations"] == ["opt1"]


# ===================================================================
# 8. Enum String Behavior
# ===================================================================

class TestEnumStringBehavior:
    def test_contradiction_type_is_str(self):
        # ContradictionType inherits from str
        assert isinstance(ContradictionType.TEMPORAL_DATE, str)

    def test_contradiction_type_comparison(self):
        assert ContradictionType.TEMPORAL_DATE == "temporal_date_conflict"

    def test_severity_is_str(self):
        assert isinstance(Severity.HIGH, str)

    def test_severity_comparison(self):
        assert Severity.HIGH == "high"

    def test_status_is_str(self):
        assert isinstance(ContradictionStatus.VERIFIED, str)

    def test_status_comparison(self):
        assert ContradictionStatus.VERIFIED == "verified"

    def test_category_is_str(self):
        assert isinstance(ContradictionCategory.HARD_CONTRADICTION, str)
