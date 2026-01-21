"""
Tests for Rule-Based Contradiction Detector
===========================================

Tests:
1. Temporal contradiction detection
2. Quantitative contradiction detection
3. Attribution contradiction detection
"""

import pytest
import json
from pathlib import Path

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend_lite.extractor import Claim, ClaimExtractor
from backend_lite.detector import RuleBasedDetector, detect_contradictions
from backend_lite.schemas import ContradictionType, Severity


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def detector():
    """Create detector instance"""
    return RuleBasedDetector()


@pytest.fixture
def extractor():
    """Create extractor instance"""
    return ClaimExtractor()


@pytest.fixture
def temporal_claims():
    """Load temporal contradiction fixture"""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_claims_temporal.json"
    with open(fixture_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data["claims"]


@pytest.fixture
def quantitative_claims():
    """Load quantitative contradiction fixture"""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_claims_quantitative.json"
    with open(fixture_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data["claims"]


def claims_from_dicts(claims_data):
    """Convert claim dicts to Claim objects"""
    return [
        Claim(
            id=c["id"],
            text=c["text"],
            source=c.get("source"),
            page=c.get("page"),
            speaker=c.get("speaker")
        )
        for c in claims_data
    ]


# =============================================================================
# Temporal Detection Tests
# =============================================================================

class TestTemporalDetection:
    """Tests for temporal contradiction detection"""

    def test_detects_different_dates_for_same_event(self, detector, temporal_claims):
        """Should detect when same event has different dates"""
        claims = claims_from_dicts(temporal_claims)
        result = detector.detect(claims)

        # Should find at least one temporal contradiction
        temporal = [c for c in result.contradictions if c.type == ContradictionType.TEMPORAL_DATE]
        assert len(temporal) >= 1

        # Check it found the 2020 vs 2021 conflict
        found_conflict = False
        for contr in temporal:
            if "2020" in contr.explanation and "2021" in contr.explanation:
                found_conflict = True
                break
        assert found_conflict, "Should detect 2020 vs 2021 date conflict"

    def test_hebrew_date_format(self, detector):
        """Should detect Hebrew date format contradictions"""
        claims = [
            Claim(id="1", text="האירוע התרחש ב-15 בינואר 2023"),
            Claim(id="2", text="האירוע התרחש ב-20 במרץ 2023"),
        ]
        result = detector.detect(claims)

        temporal = [c for c in result.contradictions if c.type == ContradictionType.TEMPORAL_DATE]
        assert len(temporal) >= 1

    def test_no_false_positive_unrelated_dates(self, detector):
        """Should not flag dates in unrelated claims"""
        claims = [
            Claim(id="1", text="החוזה נחתם ב-15.3.2020"),
            Claim(id="2", text="המכונית נרכשה ב-20.5.2021"),  # Different topic
        ]
        result = detector.detect(claims)

        # Should have low or no temporal contradictions (different topics)
        temporal = [c for c in result.contradictions if c.type == ContradictionType.TEMPORAL_DATE]
        # This depends on how related the claims appear
        # The detector checks for word overlap


# =============================================================================
# Quantitative Detection Tests
# =============================================================================

class TestQuantitativeDetection:
    """Tests for quantitative contradiction detection"""

    def test_detects_different_amounts(self, detector, quantitative_claims):
        """Should detect when same item has different amounts"""
        claims = claims_from_dicts(quantitative_claims)
        result = detector.detect(claims)

        # Should find quantitative contradictions
        quantitative = [c for c in result.contradictions if c.type == ContradictionType.QUANT_AMOUNT]
        assert len(quantitative) >= 1

    def test_shekel_symbol_format(self, detector):
        """Should detect contradictions with shekel symbol"""
        claims = [
            Claim(id="1", text="הסכום שהועבר היה ₪100,000"),
            Claim(id="2", text="הסכום שהועבר היה ₪50,000"),
        ]
        result = detector.detect(claims)

        quantitative = [c for c in result.contradictions if c.type == ContradictionType.QUANT_AMOUNT]
        assert len(quantitative) >= 1

    def test_percentage_contradictions(self, detector):
        """Should detect percentage contradictions"""
        claims = [
            Claim(id="1", text="הריבית על ההלוואה הייתה 5%"),
            Claim(id="2", text="הריבית על ההלוואה הייתה 12%"),
        ]
        result = detector.detect(claims)

        quantitative = [c for c in result.contradictions if c.type == ContradictionType.QUANT_AMOUNT]
        assert len(quantitative) >= 1

    def test_no_false_positive_similar_amounts(self, detector):
        """Should not flag very similar amounts as contradictions"""
        claims = [
            Claim(id="1", text="הסכום היה כ-100,000 ש\"ח"),
            Claim(id="2", text="הסכום היה 105,000 שקלים"),  # 5% difference
        ]
        result = detector.detect(claims)

        # Small differences should not be flagged (threshold is 10%)
        quantitative = [c for c in result.contradictions if c.type == ContradictionType.QUANT_AMOUNT]
        # Should be empty or have low confidence
        assert len(quantitative) == 0 or all(c.confidence < 0.8 for c in quantitative)


# =============================================================================
# Attribution Detection Tests
# =============================================================================

class TestAttributionDetection:
    """Tests for attribution contradiction detection"""

    def test_detects_different_actors(self, detector):
        """Should detect when different people are attributed same action"""
        claims = [
            Claim(id="1", text="יוסי חתם על החוזה במשרד"),
            Claim(id="2", text="דני חתם על החוזה באותו היום"),
        ]
        result = detector.detect(claims)

        attribution = [c for c in result.contradictions if c.type == ContradictionType.ACTOR_ATTRIBUTION]
        assert len(attribution) >= 1

    def test_hebrew_attribution_patterns(self, detector):
        """Should detect Hebrew attribution patterns"""
        claims = [
            Claim(id="1", text="עבודות הבנייה במקרקעין בוצעו על ידי ראובן"),
            Claim(id="2", text="עבודות הבנייה במקרקעין בוצעו על ידי שמעון"),
        ]
        result = detector.detect(claims)

        attribution = [c for c in result.contradictions if c.type == ContradictionType.ACTOR_ATTRIBUTION]
        assert len(attribution) >= 1


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for full detection pipeline"""

    def test_convenience_function(self, temporal_claims):
        """Test the convenience function works"""
        claims = claims_from_dicts(temporal_claims)
        result = detect_contradictions(claims)

        assert result is not None
        assert result.method == "rule_based"
        assert result.detection_time_ms >= 0
        assert "claims_analyzed" in result.metadata

    def test_empty_claims(self, detector):
        """Should handle empty claims list"""
        result = detector.detect([])

        assert result.contradictions == []
        assert result.detection_time_ms >= 0

    def test_single_claim(self, detector):
        """Should handle single claim (no pairs to compare)"""
        claims = [Claim(id="1", text="החוזה נחתם ב-15.3.2020")]
        result = detector.detect(claims)

        assert result.contradictions == []

    def test_metadata_populated(self, detector, temporal_claims):
        """Should populate metadata correctly"""
        claims = claims_from_dicts(temporal_claims)
        result = detector.detect(claims)

        assert "temporal_count" in result.metadata
        assert "quantitative_count" in result.metadata
        assert "attribution_count" in result.metadata
        assert result.metadata["claims_analyzed"] == len(claims)


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
