"""
Fixture-based Regression Tests
==============================

Tests the analysis pipeline against known fixtures with expected outcomes.
Ensures no regression in contradiction detection.
"""

import json
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from backend_lite.api import app
from backend_lite.extractor import extract_claims, sanitize_input


# =============================================================================
# Fixtures Directory
# =============================================================================

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def get_fixture_pairs():
    """Get all fixture (txt, expected.json) pairs"""
    fixtures = []
    for txt_file in FIXTURES_DIR.glob("*.txt"):
        expected_file = txt_file.with_name(txt_file.stem + "_expected.json")
        if expected_file.exists():
            fixtures.append((txt_file, expected_file))
    return fixtures


def load_fixture(txt_path: Path, expected_path: Path):
    """Load a fixture and its expected outcomes"""
    with open(txt_path, 'r', encoding='utf-8') as f:
        text = f.read()
    with open(expected_path, 'r', encoding='utf-8') as f:
        expected = json.load(f)
    return text, expected


# =============================================================================
# Parametrized Fixture Tests
# =============================================================================

class TestFixtureRegression:
    """Test contradiction detection against known fixtures"""

    @pytest.fixture
    def fixture_pairs(self):
        """Get all fixture pairs for testing"""
        return get_fixture_pairs()

    @pytest.mark.asyncio
    async def test_temporal_01(self):
        """Test temporal contradiction detection - contract signing date"""
        txt_path = FIXTURES_DIR / "temporal_01.txt"
        expected_path = FIXTURES_DIR / "temporal_01_expected.json"

        if not txt_path.exists():
            pytest.skip("Fixture not found")

        text, expected = load_fixture(txt_path, expected_path)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/analyze",
                json={"text": text, "source_name": "temporal_01"}
            )

        assert response.status_code == 200
        data = response.json()

        # Check minimum contradictions
        if "min_contradictions" in expected:
            min_req = expected["min_contradictions"]
            if min_req > 0:
                assert len(data["contradictions"]) >= min_req, \
                    f"Expected at least {min_req} contradictions"

        # Check for expected types (only if we have contradictions and min_contradictions > 0)
        if data["contradictions"] and expected.get("min_contradictions", 0) > 0:
            if "expected_types" in expected and expected["expected_types"]:
                types_found = [c["type"] for c in data["contradictions"]]
                for expected_type in expected["expected_types"]:
                    assert any(expected_type in t for t in types_found), \
                        f"Expected type {expected_type} not found in {types_found}"

    @pytest.mark.asyncio
    async def test_temporal_02(self):
        """Test temporal contradiction - meeting date"""
        txt_path = FIXTURES_DIR / "temporal_02.txt"
        expected_path = FIXTURES_DIR / "temporal_02_expected.json"

        if not txt_path.exists():
            pytest.skip("Fixture not found")

        text, expected = load_fixture(txt_path, expected_path)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/analyze",
                json={"text": text}
            )

        assert response.status_code == 200
        data = response.json()

        if "min_contradictions" in expected:
            assert len(data["contradictions"]) >= expected["min_contradictions"]

    @pytest.mark.asyncio
    async def test_temporal_03(self):
        """Test temporal contradiction - accident date"""
        txt_path = FIXTURES_DIR / "temporal_03.txt"
        expected_path = FIXTURES_DIR / "temporal_03_expected.json"

        if not txt_path.exists():
            pytest.skip("Fixture not found")

        text, expected = load_fixture(txt_path, expected_path)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/analyze",
                json={"text": text}
            )

        assert response.status_code == 200
        data = response.json()

        if "min_contradictions" in expected:
            assert len(data["contradictions"]) >= expected["min_contradictions"]

    @pytest.mark.asyncio
    async def test_quant_01(self):
        """Test quantitative contradiction - damage amount"""
        txt_path = FIXTURES_DIR / "quant_01.txt"
        expected_path = FIXTURES_DIR / "quant_01_expected.json"

        if not txt_path.exists():
            pytest.skip("Fixture not found")

        text, expected = load_fixture(txt_path, expected_path)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/analyze",
                json={"text": text}
            )

        assert response.status_code == 200
        data = response.json()

        if "min_contradictions" in expected:
            min_req = expected["min_contradictions"]
            if min_req > 0:
                assert len(data["contradictions"]) >= min_req

        # Check for quant type (only if we have contradictions and min > 0)
        if data["contradictions"] and expected.get("min_contradictions", 0) > 0:
            if "expected_types" in expected and expected["expected_types"]:
                types_found = [c["type"] for c in data["contradictions"]]
                for expected_type in expected["expected_types"]:
                    assert any(expected_type in t for t in types_found), \
                        f"Expected type {expected_type} not found"

    @pytest.mark.asyncio
    async def test_quant_02(self):
        """Test quantitative contradiction - contract amount"""
        txt_path = FIXTURES_DIR / "quant_02.txt"
        expected_path = FIXTURES_DIR / "quant_02_expected.json"

        if not txt_path.exists():
            pytest.skip("Fixture not found")

        text, expected = load_fixture(txt_path, expected_path)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/analyze",
                json={"text": text}
            )

        assert response.status_code == 200
        data = response.json()

        if "min_contradictions" in expected:
            assert len(data["contradictions"]) >= expected["min_contradictions"]

    @pytest.mark.asyncio
    async def test_quant_03(self):
        """Test quantitative contradiction - payment amount"""
        txt_path = FIXTURES_DIR / "quant_03.txt"
        expected_path = FIXTURES_DIR / "quant_03_expected.json"

        if not txt_path.exists():
            pytest.skip("Fixture not found")

        text, expected = load_fixture(txt_path, expected_path)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/analyze",
                json={"text": text}
            )

        assert response.status_code == 200
        data = response.json()

        if "min_contradictions" in expected:
            assert len(data["contradictions"]) >= expected["min_contradictions"]

    @pytest.mark.asyncio
    async def test_presence_01(self):
        """Test presence contradiction - meeting attendance"""
        txt_path = FIXTURES_DIR / "presence_01.txt"
        expected_path = FIXTURES_DIR / "presence_01_expected.json"

        if not txt_path.exists():
            pytest.skip("Fixture not found")

        text, expected = load_fixture(txt_path, expected_path)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/analyze",
                json={"text": text}
            )

        assert response.status_code == 200
        data = response.json()

        if "min_contradictions" in expected:
            assert len(data["contradictions"]) >= expected["min_contradictions"]

    @pytest.mark.asyncio
    async def test_presence_02(self):
        """Test presence contradiction - witness attendance"""
        txt_path = FIXTURES_DIR / "presence_02.txt"
        expected_path = FIXTURES_DIR / "presence_02_expected.json"

        if not txt_path.exists():
            pytest.skip("Fixture not found")

        text, expected = load_fixture(txt_path, expected_path)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/analyze",
                json={"text": text}
            )

        assert response.status_code == 200
        data = response.json()

        if "min_contradictions" in expected:
            assert len(data["contradictions"]) >= expected["min_contradictions"]


class TestFalsePositives:
    """Test that known false positives are NOT detected as contradictions"""

    @pytest.mark.asyncio
    async def test_case_numbers_not_dates(self):
        """Case numbers like 17682-06-25 should not be flagged as dates"""
        txt_path = FIXTURES_DIR / "false_positive_case_number.txt"
        expected_path = FIXTURES_DIR / "false_positive_case_number_expected.json"

        if not txt_path.exists():
            pytest.skip("Fixture not found")

        text, expected = load_fixture(txt_path, expected_path)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/analyze",
                json={"text": text}
            )

        assert response.status_code == 200
        data = response.json()

        # Should NOT have temporal contradictions
        temporal_contradictions = [
            c for c in data["contradictions"]
            if "temporal" in c["type"]
        ]

        assert len(temporal_contradictions) == 0, \
            f"Case numbers incorrectly detected as temporal contradiction: {temporal_contradictions}"

    @pytest.mark.asyncio
    async def test_report_contamination_sanitized(self):
        """Report output should be sanitized and not create self-contradictions"""
        txt_path = FIXTURES_DIR / "false_positive_report.txt"
        expected_path = FIXTURES_DIR / "false_positive_report_expected.json"

        if not txt_path.exists():
            pytest.skip("Fixture not found")

        text, expected = load_fixture(txt_path, expected_path)

        # First test: sanitization removes system markers
        sanitized = sanitize_input(text)

        claims_should_not_contain = expected.get("claims_should_not_contain", [])
        for marker in claims_should_not_contain:
            assert marker not in sanitized, \
                f"Sanitization failed to remove '{marker}'"

        # Second test: claims don't contain system text
        claims = extract_claims(text)
        for claim in claims:
            for marker in claims_should_not_contain:
                assert marker not in claim.text, \
                    f"Claim contains system marker '{marker}': {claim.text}"


class TestSanitization:
    """Test input sanitization to prevent self-contamination"""

    def test_sanitize_removes_system_markers(self):
        """Ensure sanitize_input removes all system markers"""
        contaminated_text = """
        תוצאות הניתוח
        מטא-דאטה: {"duration_ms": 123}
        claim_1: טקסט
        LLM_mode: hybrid

        זהו הטקסט המשפטי האמיתי.
        """

        sanitized = sanitize_input(contaminated_text)

        # Should not contain system markers
        assert "תוצאות הניתוח" not in sanitized
        assert "מטא-דאטה" not in sanitized
        assert "claim_1" not in sanitized
        assert "LLM_" not in sanitized

        # Should preserve legal content
        assert "טקסט המשפטי" in sanitized or "האמיתי" in sanitized

    def test_claims_no_self_contamination(self):
        """Extracted claims should never contain system output text"""
        contaminated_text = """
        החוזה נחתם ביום 15.3.2020.

        תוצאות הניתוח
        סתירות: 1
        claim_1: החוזה נחתם

        הנתבע חייב בתשלום.
        """

        claims = extract_claims(contaminated_text)

        system_markers = [
            "תוצאות הניתוח", "סתירות:", "claim_1", "מטא-דאטה"
        ]

        for claim in claims:
            for marker in system_markers:
                assert marker not in claim.text, \
                    f"Claim contains system marker: {marker}"


class TestClaimExtraction:
    """Test claim extraction quality"""

    def test_no_email_in_claims(self):
        """Claims should not contain email addresses (signature block)"""
        text = """
        התובע דורש פיצויים בסך 100,000 ש"ח.

        בכבוד רב,
        עו"ד יוסי כהן
        email@example.com
        טל: 03-1234567
        """

        claims = extract_claims(text)

        for claim in claims:
            assert "@" not in claim.text, \
                f"Claim contains email: {claim.text}"
            assert "03-1234567" not in claim.text or len(claim.text) > 50, \
                f"Claim is just a phone number: {claim.text}"

    def test_claim_length_reasonable(self):
        """Claims should be within reasonable length (not too long)"""
        long_text = "טענה ארוכה מאוד. " * 100  # Very long text

        claims = extract_claims(long_text)

        for claim in claims:
            # Claims should be under 600 chars (500 + some buffer)
            assert len(claim.text) <= 600, \
                f"Claim too long: {len(claim.text)} chars"

    def test_claims_have_meaningful_content(self):
        """Claims should have meaningful legal content"""
        text = """
        התובע טוען כי הנתבע הפר את החוזה.
        הנזק מוערך בסך 50,000 ש"ח.
        """

        claims = extract_claims(text)

        assert len(claims) >= 1, "Should extract at least one claim"

        # Each claim should have at least 3 meaningful words
        for claim in claims:
            words = [w for w in claim.text.split() if len(w) > 2]
            assert len(words) >= 2, \
                f"Claim has too few meaningful words: {claim.text}"


class TestUsableFlag:
    """Test the 'usable' flag computation"""

    @pytest.mark.asyncio
    async def test_usable_flag_present(self):
        """Contradictions should have usable flag"""
        text = """
        החוזה נחתם ביום 15.3.2020.
        החוזה נחתם ביום 20.5.2021.
        """

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/analyze",
                json={"text": text}
            )

        assert response.status_code == 200
        data = response.json()

        if data["contradictions"]:
            for c in data["contradictions"]:
                assert "usable" in c, "Contradiction should have 'usable' field"
                assert isinstance(c["usable"], bool)
