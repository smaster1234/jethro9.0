"""
Tests for API Contract
======================

Ensures the API always returns valid JSON with expected structure.
Tests both success and error cases.
"""

import pytest
import json
from pathlib import Path

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi.testclient import TestClient
from backend_lite.api import app
from backend_lite.schemas import AnalysisResponse, HealthResponse


# =============================================================================
# Test Client
# =============================================================================

@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def temporal_fixture():
    """Load temporal claims fixture"""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_claims_temporal.json"
    with open(fixture_path, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def quantitative_fixture():
    """Load quantitative claims fixture"""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_claims_quantitative.json"
    with open(fixture_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# =============================================================================
# Health Check Tests
# =============================================================================

class TestHealthEndpoint:
    """Tests for /health endpoint"""

    def test_health_returns_200(self, client):
        """Health check should return 200"""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_valid_json(self, client):
        """Health check should return valid JSON"""
        response = client.get("/health")
        data = response.json()

        assert "status" in data
        assert "version" in data
        assert "llm_mode" in data
        assert "timestamp" in data

    def test_health_status_healthy(self, client):
        """Health check should report healthy status"""
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"


# =============================================================================
# Analyze Text Endpoint Tests
# =============================================================================

class TestAnalyzeTextEndpoint:
    """Tests for POST /analyze endpoint"""

    def test_analyze_returns_200(self, client):
        """Analyze should return 200 for valid input"""
        response = client.post("/analyze", json={
            "text": "החוזה נחתם ב-15.3.2020. החוזה נחתם ב-20.5.2021."
        })
        assert response.status_code == 200

    def test_analyze_returns_valid_structure(self, client):
        """Analyze should return expected JSON structure"""
        response = client.post("/analyze", json={
            "text": "טקסט לבדיקה עם תוכן מספיק לניתוח של מספר טענות"
        })
        data = response.json()

        # Check top-level keys
        assert "contradictions" in data
        assert "cross_exam_questions" in data
        assert "metadata" in data

        # Check metadata structure
        metadata = data["metadata"]
        assert "mode" in metadata
        assert "rule_based_time_ms" in metadata
        assert "total_time_ms" in metadata
        assert "claims_count" in metadata
        assert "validation_flags" in metadata

    def test_analyze_empty_text_returns_error(self, client):
        """Analyze should return 400 for empty text"""
        response = client.post("/analyze", json={"text": ""})
        assert response.status_code == 400

    def test_analyze_empty_text_after_strip_returns_error(self, client):
        """Analyze should return 400 for whitespace-only text"""
        response = client.post("/analyze", json={"text": "   \n\t  "})
        assert response.status_code == 400

    def test_analyze_detects_temporal_contradiction(self, client):
        """Analyze should detect temporal contradiction"""
        response = client.post("/analyze", json={
            "text": """
            1. החוזה נחתם ביום 15.3.2020 במשרדי החברה.
            2. לאחר חתימת החוזה ב-20.5.2021 החלו העבודות.
            """
        })
        data = response.json()

        # Should detect contradiction
        contradictions = data["contradictions"]
        temporal = [c for c in contradictions if c["type"] == "temporal_date_conflict"]
        assert len(temporal) >= 1

    def test_analyze_always_returns_valid_json_on_error(self, client):
        """Even errors should return valid JSON with proper structure"""
        # This tests that internal errors don't break the response
        response = client.post("/analyze", json={
            "text": "טקסט קצר מאוד"  # Very short text
        })

        # Should still return valid JSON
        data = response.json()
        assert "contradictions" in data
        assert "metadata" in data


# =============================================================================
# Analyze Claims Endpoint Tests
# =============================================================================

class TestAnalyzeClaimsEndpoint:
    """Tests for POST /analyze_claims endpoint"""

    def test_analyze_claims_returns_200(self, client, temporal_fixture):
        """Analyze claims should return 200 for valid input"""
        response = client.post("/analyze_claims", json={
            "claims": temporal_fixture["claims"]
        })
        assert response.status_code == 200

    def test_analyze_claims_returns_valid_structure(self, client, temporal_fixture):
        """Analyze claims should return expected JSON structure"""
        response = client.post("/analyze_claims", json={
            "claims": temporal_fixture["claims"]
        })
        data = response.json()

        # Check top-level keys
        assert "contradictions" in data
        assert "cross_exam_questions" in data
        assert "metadata" in data

    def test_analyze_claims_detects_temporal(self, client, temporal_fixture):
        """Should detect temporal contradiction from fixture"""
        response = client.post("/analyze_claims", json={
            "claims": temporal_fixture["claims"]
        })
        data = response.json()

        contradictions = data["contradictions"]
        temporal = [c for c in contradictions if c["type"] == "temporal_date_conflict"]
        assert len(temporal) >= 1

    def test_analyze_claims_detects_quantitative(self, client, quantitative_fixture):
        """Should detect quantitative contradiction from fixture"""
        response = client.post("/analyze_claims", json={
            "claims": quantitative_fixture["claims"]
        })
        data = response.json()

        contradictions = data["contradictions"]
        quantitative = [c for c in contradictions if c["type"] == "quant_amount_conflict"]
        assert len(quantitative) >= 1

    def test_analyze_claims_generates_cross_exam(self, client, temporal_fixture):
        """Should generate cross-examination questions for contradictions"""
        response = client.post("/analyze_claims", json={
            "claims": temporal_fixture["claims"]
        })
        data = response.json()

        # If there are contradictions, should have cross-exam questions
        if data["contradictions"]:
            assert len(data["cross_exam_questions"]) > 0

    def test_analyze_claims_empty_list_returns_error(self, client):
        """Should return 400 for empty claims list"""
        response = client.post("/analyze_claims", json={"claims": []})
        assert response.status_code == 400


# =============================================================================
# Contradiction Output Structure Tests
# =============================================================================

class TestContradictionOutputStructure:
    """Tests for contradiction output structure"""

    def test_contradiction_has_required_fields(self, client, temporal_fixture):
        """Each contradiction should have all required fields"""
        response = client.post("/analyze_claims", json={
            "claims": temporal_fixture["claims"]
        })
        data = response.json()

        for contr in data["contradictions"]:
            assert "id" in contr
            assert "claim1_id" in contr
            assert "claim2_id" in contr
            assert "type" in contr
            assert "severity" in contr
            assert "confidence" in contr
            assert "explanation" in contr
            assert "quote1" in contr
            assert "quote2" in contr

    def test_contradiction_type_is_valid(self, client, temporal_fixture):
        """Contradiction type should be a valid enum value"""
        response = client.post("/analyze_claims", json={
            "claims": temporal_fixture["claims"]
        })
        data = response.json()

        valid_types = [
            # Tier 1 types (new)
            "temporal_date_conflict",
            "quant_amount_conflict",
            "actor_attribution_conflict",
            "presence_participation_conflict",
            "document_existence_conflict",
            "identity_basic_conflict",
            # Tier 2 types
            "timeline_sequence_conflict",
            "location_conflict",
            "communication_channel_conflict",
            "party_position_conflict",
            "version_conflict",
            # Legacy types (backwards compatibility)
            "temporal_conflict",
            "quantitative_conflict",
            "attribution_conflict",
            "factual_conflict",
            "witness_conflict",
            "document_conflict"
        ]

        for contr in data["contradictions"]:
            assert contr["type"] in valid_types

    def test_contradiction_severity_is_valid(self, client, temporal_fixture):
        """Contradiction severity should be a valid enum value"""
        response = client.post("/analyze_claims", json={
            "claims": temporal_fixture["claims"]
        })
        data = response.json()

        valid_severities = ["critical", "high", "medium", "low"]

        for contr in data["contradictions"]:
            assert contr["severity"] in valid_severities

    def test_contradiction_confidence_in_range(self, client, temporal_fixture):
        """Contradiction confidence should be between 0 and 1"""
        response = client.post("/analyze_claims", json={
            "claims": temporal_fixture["claims"]
        })
        data = response.json()

        for contr in data["contradictions"]:
            assert 0.0 <= contr["confidence"] <= 1.0


# =============================================================================
# Cross-Exam Output Structure Tests
# =============================================================================

class TestCrossExamOutputStructure:
    """Tests for cross-examination output structure"""

    def test_cross_exam_has_required_fields(self, client, temporal_fixture):
        """Each cross-exam set should have required fields"""
        response = client.post("/analyze_claims", json={
            "claims": temporal_fixture["claims"]
        })
        data = response.json()

        for ce in data["cross_exam_questions"]:
            assert "contradiction_id" in ce
            assert "questions" in ce
            assert isinstance(ce["questions"], list)

    def test_cross_exam_question_has_required_fields(self, client, temporal_fixture):
        """Each question should have required fields"""
        response = client.post("/analyze_claims", json={
            "claims": temporal_fixture["claims"]
        })
        data = response.json()

        for ce in data["cross_exam_questions"]:
            for question in ce["questions"]:
                assert "id" in question
                assert "question" in question
                assert "purpose" in question
                assert "severity" in question


# =============================================================================
# Metadata Tests
# =============================================================================

class TestMetadataStructure:
    """Tests for metadata structure"""

    def test_metadata_timing_is_numeric(self, client, temporal_fixture):
        """Timing values should be numeric"""
        response = client.post("/analyze_claims", json={
            "claims": temporal_fixture["claims"]
        })
        data = response.json()
        metadata = data["metadata"]

        assert isinstance(metadata["rule_based_time_ms"], (int, float))
        assert isinstance(metadata["total_time_ms"], (int, float))

    def test_metadata_mode_is_valid(self, client, temporal_fixture):
        """Mode should be a valid LLM mode"""
        response = client.post("/analyze_claims", json={
            "claims": temporal_fixture["claims"]
        })
        data = response.json()
        metadata = data["metadata"]

        assert metadata["mode"] in ["none", "openrouter", "gemini"]

    def test_metadata_validation_flags_is_list(self, client, temporal_fixture):
        """Validation flags should be a list"""
        response = client.post("/analyze_claims", json={
            "claims": temporal_fixture["claims"]
        })
        data = response.json()
        metadata = data["metadata"]

        assert isinstance(metadata["validation_flags"], list)


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
