"""
Tests for Claim Results Mapping
================================

Tests for:
- ClaimOutput generation
- ClaimResult computation
- claim->contradiction mapping
- Status calculation logic
"""

import pytest
from pathlib import Path

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi.testclient import TestClient
from backend_lite.api import (
    app,
    build_claim_outputs,
    compute_claim_results,
)
from backend_lite.schemas import (
    ClaimOutput,
    ClaimResult,
    ClaimStatus,
    ClaimFeatures,
    ContradictionOutput,
    ContradictionStatus,
    ContradictionType,
    Severity,
    ClaimEvidence,
    Locator,
)
from backend_lite.extractor import Claim


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def sample_claims():
    """Sample claims for testing"""
    return [
        Claim(id="claim_1", text="החוזה נחתם ביום 15.3.2020", source="תצהיר תובע", doc_id="doc_1"),
        Claim(id="claim_2", text="החוזה נחתם ביום 20.5.2021", source="תצהיר נתבע", doc_id="doc_2"),
        Claim(id="claim_3", text="הסכום היה 500,000 שקלים", source="תצהיר תובע", doc_id="doc_1"),
        Claim(id="claim_4", text="הסכום היה 350,000 שקלים", source="תצהיר נתבע", doc_id="doc_2"),
        Claim(id="claim_5", text="הפגישה התקיימה בתל אביב", source="תצהיר עד", doc_id="doc_3"),
    ]


@pytest.fixture
def sample_claims_data():
    """Sample claims data dict for testing"""
    return [
        {"id": "claim_1", "text": "החוזה נחתם ביום 15.3.2020", "source": "תצהיר תובע", "doc_id": "doc_1"},
        {"id": "claim_2", "text": "החוזה נחתם ביום 20.5.2021", "source": "תצהיר נתבע", "doc_id": "doc_2"},
        {"id": "claim_3", "text": "הסכום היה 500,000 שקלים", "source": "תצהיר תובע", "doc_id": "doc_1"},
        {"id": "claim_4", "text": "הסכום היה 350,000 שקלים", "source": "תצהיר נתבע", "doc_id": "doc_2"},
        {"id": "claim_5", "text": "הפגישה התקיימה בתל אביב", "source": "תצהיר עד", "doc_id": "doc_3"},
    ]


@pytest.fixture
def sample_contradictions():
    """Sample contradictions for testing"""
    return [
        ContradictionOutput(
            id="contr_1",
            type=ContradictionType.TEMPORAL_DATE,
            status=ContradictionStatus.VERIFIED,
            severity=Severity.HIGH,
            confidence=0.95,
            claim1=ClaimEvidence(claim_id="claim_1", quote="15.3.2020"),
            claim2=ClaimEvidence(claim_id="claim_2", quote="20.5.2021"),
            claim1_id="claim_1",
            claim2_id="claim_2",
            explanation="סתירה בתאריך חתימת החוזה"
        ),
        ContradictionOutput(
            id="contr_2",
            type=ContradictionType.QUANT_AMOUNT,
            status=ContradictionStatus.LIKELY,
            severity=Severity.MEDIUM,
            confidence=0.8,
            claim1=ClaimEvidence(claim_id="claim_3", quote="500,000 שקלים"),
            claim2=ClaimEvidence(claim_id="claim_4", quote="350,000 שקלים"),
            claim1_id="claim_3",
            claim2_id="claim_4",
            explanation="סתירה בסכום"
        ),
    ]


# =============================================================================
# ClaimOutput Tests
# =============================================================================

class TestBuildClaimOutputs:
    """Tests for build_claim_outputs function"""

    def test_basic_claim_output(self, sample_claims, sample_claims_data):
        """Should build basic claim outputs"""
        outputs = build_claim_outputs(sample_claims, sample_claims_data)

        assert len(outputs) == 5
        assert all(isinstance(o, ClaimOutput) for o in outputs)

    def test_claim_output_has_id_and_text(self, sample_claims, sample_claims_data):
        """Claim outputs should have id and text"""
        outputs = build_claim_outputs(sample_claims, sample_claims_data)

        for output in outputs:
            assert output.id is not None
            assert output.text is not None
            assert len(output.text) > 0

    def test_claim_output_has_doc_info(self, sample_claims, sample_claims_data):
        """Claim outputs should have doc info"""
        outputs = build_claim_outputs(sample_claims, sample_claims_data)

        for output in outputs:
            assert output.doc_id is not None or output.doc_name is not None

    def test_claim_output_locator_from_claim(self):
        """Claim output should include locator from claim"""
        claims = [
            Claim(
                id="claim_1",
                text="טקסט",
                source="מסמך",
                doc_id="doc_1",
                paragraph_index=3,
                char_start=100,
                char_end=150
            )
        ]
        claims_data = [{"id": "claim_1", "text": "טקסט", "source": "מסמך"}]

        outputs = build_claim_outputs(claims, claims_data)

        assert len(outputs) == 1
        assert outputs[0].locator is not None
        assert outputs[0].locator.doc_id == "doc_1"
        assert outputs[0].locator.paragraph == 3
        assert outputs[0].locator.char_start == 100
        assert outputs[0].locator.char_end == 150


# =============================================================================
# ClaimResult Tests
# =============================================================================

class TestComputeClaimResults:
    """Tests for compute_claim_results function"""

    def test_no_contradictions_all_no_issues(self, sample_claims):
        """Claims with no contradictions should be no_issues"""
        results = compute_claim_results(sample_claims, [])

        assert len(results) == 5
        assert all(r.status == ClaimStatus.NO_ISSUES for r in results)
        assert all(r.contradiction_count == 0 for r in results)

    def test_verified_contradiction_status(self, sample_claims, sample_contradictions):
        """Claims with verified contradiction should have verified status"""
        results = compute_claim_results(sample_claims, sample_contradictions)

        # claim_1 and claim_2 have verified contradiction
        result_1 = next(r for r in results if r.claim_id == "claim_1")
        result_2 = next(r for r in results if r.claim_id == "claim_2")

        assert result_1.status == ClaimStatus.VERIFIED_CONTRADICTION
        assert result_2.status == ClaimStatus.VERIFIED_CONTRADICTION

    def test_likely_contradiction_status(self, sample_claims, sample_contradictions):
        """Claims with likely contradiction should have potential status"""
        results = compute_claim_results(sample_claims, sample_contradictions)

        # claim_3 and claim_4 have likely contradiction
        result_3 = next(r for r in results if r.claim_id == "claim_3")
        result_4 = next(r for r in results if r.claim_id == "claim_4")

        assert result_3.status == ClaimStatus.POTENTIAL_CONTRADICTION
        assert result_4.status == ClaimStatus.POTENTIAL_CONTRADICTION

    def test_no_contradiction_claim_stays_no_issues(self, sample_claims, sample_contradictions):
        """Claims without contradictions should remain no_issues"""
        results = compute_claim_results(sample_claims, sample_contradictions)

        # claim_5 has no contradictions
        result_5 = next(r for r in results if r.claim_id == "claim_5")

        assert result_5.status == ClaimStatus.NO_ISSUES
        assert result_5.contradiction_count == 0

    def test_contradiction_count(self, sample_claims, sample_contradictions):
        """Should count contradictions correctly"""
        results = compute_claim_results(sample_claims, sample_contradictions)

        # claim_1 has 1 contradiction
        result_1 = next(r for r in results if r.claim_id == "claim_1")
        assert result_1.contradiction_count == 1

    def test_max_severity(self, sample_claims, sample_contradictions):
        """Should track max severity"""
        results = compute_claim_results(sample_claims, sample_contradictions)

        # claim_1 has high severity contradiction
        result_1 = next(r for r in results if r.claim_id == "claim_1")
        assert result_1.max_severity == Severity.HIGH

        # claim_3 has medium severity contradiction
        result_3 = next(r for r in results if r.claim_id == "claim_3")
        assert result_3.max_severity == Severity.MEDIUM

    def test_types_tracked(self, sample_claims, sample_contradictions):
        """Should track contradiction types"""
        results = compute_claim_results(sample_claims, sample_contradictions)

        result_1 = next(r for r in results if r.claim_id == "claim_1")
        assert ContradictionType.TEMPORAL_DATE in result_1.types

        result_3 = next(r for r in results if r.claim_id == "claim_3")
        assert ContradictionType.QUANT_AMOUNT in result_3.types

    def test_top_contradiction_ids(self, sample_claims, sample_contradictions):
        """Should track top contradiction IDs"""
        results = compute_claim_results(sample_claims, sample_contradictions)

        result_1 = next(r for r in results if r.claim_id == "claim_1")
        assert "contr_1" in result_1.top_contradiction_ids


# =============================================================================
# API Integration Tests
# =============================================================================

class TestClaimResultsAPI:
    """Tests for claims and claim_results in API response"""

    def test_analyze_returns_claims(self, client):
        """Analyze should return claims array"""
        response = client.post("/analyze", json={
            "text": "החוזה נחתם ביום 15.3.2020. הסכום היה 500,000 שקלים."
        })

        data = response.json()
        assert "claims" in data
        assert isinstance(data["claims"], list)

    def test_analyze_returns_claim_results(self, client):
        """Analyze should return claim_results array"""
        response = client.post("/analyze", json={
            "text": "החוזה נחתם ביום 15.3.2020. הסכום היה 500,000 שקלים."
        })

        data = response.json()
        assert "claim_results" in data
        assert isinstance(data["claim_results"], list)

    def test_claims_match_claim_results(self, client):
        """Each claim should have a corresponding claim_result"""
        response = client.post("/analyze", json={
            "text": """
            1. החוזה נחתם ביום 15.3.2020.
            2. החוזה נחתם ביום 20.5.2021.
            """
        })

        data = response.json()
        claim_ids = {c["id"] for c in data["claims"]}
        result_claim_ids = {r["claim_id"] for r in data["claim_results"]}

        assert claim_ids == result_claim_ids

    def test_claim_result_structure(self, client):
        """Claim results should have expected structure"""
        response = client.post("/analyze", json={
            "text": "החוזה נחתם ביום 15.3.2020. החוזה נחתם ביום 20.5.2021."
        })

        data = response.json()

        for result in data["claim_results"]:
            assert "claim_id" in result
            assert "status" in result
            assert "contradiction_count" in result
            assert "types" in result
            assert "top_contradiction_ids" in result

    def test_no_contradictions_all_no_issues(self, client):
        """When no contradictions, all claims should be no_issues"""
        response = client.post("/analyze", json={
            "text": "הפגישה התקיימה בתל אביב. מזג האוויר היה נעים."
        })

        data = response.json()

        # If no contradictions found, all results should be no_issues
        if len(data["contradictions"]) == 0:
            for result in data["claim_results"]:
                assert result["status"] == "no_issues"

    def test_claims_have_locator(self, client):
        """Claims should have locator info when available"""
        response = client.post("/analyze", json={
            "text": "החוזה נחתם ביום 15.3.2020 במשרדי החברה בתל אביב",
            "doc_id": "doc_test"
        })

        data = response.json()

        for claim in data["claims"]:
            # Locator can be null but key should exist
            assert "locator" in claim

    def test_error_returns_empty_claims(self, client):
        """On error, should return empty claims and claim_results"""
        response = client.post("/analyze", json={
            "text": ""  # Empty text causes error
        })

        # Should either be 400 or return empty arrays
        if response.status_code == 200:
            data = response.json()
            assert "claims" in data
            assert "claim_results" in data


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
