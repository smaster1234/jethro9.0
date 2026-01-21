"""
Tests for Case Management and Paragraph Chunking
=================================================

Tests for:
- Case CRUD operations
- Document CRUD operations
- Paragraph chunking and storage
- Evidence locators in output
- BM25 retrieval
"""

import pytest
import json
import tempfile
import os
from pathlib import Path

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi.testclient import TestClient
from backend_lite.api import app
from backend_lite.models import CaseDatabase, Paragraph, Document, Case, PartySide, DocumentType
from backend_lite.extractor import extract_claims, Claim
from backend_lite.retrieval import BM25Index, CandidatePairGenerator, generate_candidate_pairs


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def client():
    """Create test client"""
    # Use context manager so FastAPI startup/shutdown events run (DB init + demo seeding).
    with TestClient(app) as c:
        # API now requires auth; in tests we use the seeded demo super-admin user.
        c.headers.update({"X-User-Email": "david@demo.com"})
        yield c


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    db = CaseDatabase(db_path)
    yield db

    # Cleanup
    os.unlink(db_path)


@pytest.fixture
def sample_case(temp_db):
    """Create a sample case"""
    return temp_db.create_case(
        name="כהן נ' לוי",
        client_name="ישראל כהן",
        our_side=PartySide.PLAINTIFF,
        opponent_name="דוד לוי",
        court="שלום תל אביב",
        case_number="12345-01-24"
    )


@pytest.fixture
def sample_document_text():
    """Sample legal document text in Hebrew"""
    return """
1. הנתבע קיבל את הסכום ביום 15.3.2020 בסך 500,000 ש"ח.

2. התובע טוען כי ההסכם נחתם במשרדי החברה בתל אביב ביום 20.5.2021.

3. לפי העדות, הסכום שהועבר היה 350,000 שקלים בלבד.

4. המסמכים מראים כי החוזה נחתם בירושלים ולא בתל אביב.

5. העד מאשר כי היה נוכח בעת חתימת החוזה.
"""


# =============================================================================
# Case CRUD Tests
# =============================================================================

class TestCaseCRUD:
    """Tests for Case CRUD operations"""

    def test_create_case(self, temp_db):
        """Should create a case successfully"""
        case = temp_db.create_case(name="תיק בדיקה")

        assert case.id is not None
        assert case.name == "תיק בדיקה"
        assert case.our_side == PartySide.UNKNOWN

    def test_create_case_with_all_fields(self, temp_db):
        """Should create case with all fields"""
        case = temp_db.create_case(
            name="כהן נ' לוי",
            client_name="ישראל כהן",
            our_side=PartySide.PLAINTIFF,
            opponent_name="דוד לוי",
            court="שלום תל אביב",
            case_number="12345-01-24"
        )

        assert case.name == "כהן נ' לוי"
        assert case.client_name == "ישראל כהן"
        assert case.our_side == PartySide.PLAINTIFF
        assert case.opponent_name == "דוד לוי"
        assert case.court == "שלום תל אביב"
        assert case.case_number == "12345-01-24"

    def test_get_case_by_id(self, temp_db, sample_case):
        """Should retrieve case by ID"""
        retrieved = temp_db.get_case(sample_case.id)

        assert retrieved is not None
        assert retrieved.id == sample_case.id
        assert retrieved.name == sample_case.name

    def test_get_nonexistent_case(self, temp_db):
        """Should return None for nonexistent case"""
        result = temp_db.get_case("nonexistent-id")
        assert result is None

    def test_list_cases(self, temp_db):
        """Should list all cases"""
        temp_db.create_case(name="תיק 1")
        temp_db.create_case(name="תיק 2")
        temp_db.create_case(name="תיק 3")

        cases = temp_db.list_cases()
        assert len(cases) == 3


# =============================================================================
# Document CRUD Tests
# =============================================================================

class TestDocumentCRUD:
    """Tests for Document CRUD operations"""

    def test_add_document(self, temp_db, sample_case, sample_document_text):
        """Should add document to case"""
        doc = temp_db.add_document(
            case_id=sample_case.id,
            name="כתב תביעה",
            text=sample_document_text,
            doc_type=DocumentType.COMPLAINT
        )

        assert doc.id is not None
        assert doc.case_id == sample_case.id
        assert doc.name == "כתב תביעה"
        assert doc.doc_type == DocumentType.COMPLAINT
        assert doc.text_hash is not None

    def test_get_document(self, temp_db, sample_case, sample_document_text):
        """Should retrieve document by ID"""
        doc = temp_db.add_document(
            case_id=sample_case.id,
            name="תצהיר",
            text=sample_document_text
        )

        retrieved = temp_db.get_document(doc.id)
        assert retrieved is not None
        assert retrieved.extracted_text == sample_document_text

    def test_get_case_documents(self, temp_db, sample_case):
        """Should list all documents in case"""
        temp_db.add_document(case_id=sample_case.id, name="מסמך 1", text="טקסט 1")
        temp_db.add_document(case_id=sample_case.id, name="מסמך 2", text="טקסט 2")

        docs = temp_db.get_case_documents(sample_case.id)
        assert len(docs) == 2

    def test_document_text_hash(self, temp_db, sample_case):
        """Same text should produce same hash"""
        doc1 = temp_db.add_document(
            case_id=sample_case.id,
            name="מסמך 1",
            text="טקסט זהה"
        )
        doc2 = temp_db.add_document(
            case_id=sample_case.id,
            name="מסמך 2",
            text="טקסט זהה"
        )

        assert doc1.text_hash == doc2.text_hash


# =============================================================================
# Paragraph Tests
# =============================================================================

class TestParagraphOperations:
    """Tests for paragraph chunking and storage"""

    def test_add_paragraphs(self, temp_db, sample_case):
        """Should add paragraphs for a document"""
        doc = temp_db.add_document(
            case_id=sample_case.id,
            name="מסמך",
            text="טקסט כלשהו"
        )

        paragraphs = [
            Paragraph(
                id=Paragraph.compute_id(doc.id, 0, "פסקה ראשונה"),
                doc_id=doc.id,
                case_id=sample_case.id,
                paragraph_index=0,
                text="פסקה ראשונה",
                char_start=0,
                char_end=10
            ),
            Paragraph(
                id=Paragraph.compute_id(doc.id, 1, "פסקה שנייה"),
                doc_id=doc.id,
                case_id=sample_case.id,
                paragraph_index=1,
                text="פסקה שנייה",
                char_start=11,
                char_end=20
            )
        ]

        result = temp_db.add_paragraphs(doc.id, sample_case.id, paragraphs)
        assert len(result) == 2

    def test_get_document_paragraphs(self, temp_db, sample_case):
        """Should retrieve paragraphs for a document"""
        doc = temp_db.add_document(
            case_id=sample_case.id,
            name="מסמך",
            text="טקסט"
        )

        paragraphs = [
            Paragraph(
                id=Paragraph.compute_id(doc.id, i, f"פסקה {i}"),
                doc_id=doc.id,
                case_id=sample_case.id,
                paragraph_index=i,
                text=f"פסקה {i}"
            )
            for i in range(3)
        ]
        temp_db.add_paragraphs(doc.id, sample_case.id, paragraphs)

        retrieved = temp_db.get_document_paragraphs(doc.id)
        assert len(retrieved) == 3
        assert retrieved[0].paragraph_index == 0
        assert retrieved[2].paragraph_index == 2

    def test_paragraph_stable_id(self):
        """Same content should produce same ID"""
        id1 = Paragraph.compute_id("doc1", 0, "טקסט זהה")
        id2 = Paragraph.compute_id("doc1", 0, "טקסט זהה")
        id3 = Paragraph.compute_id("doc1", 0, "טקסט שונה")

        assert id1 == id2
        assert id1 != id3

    def test_paragraph_id_includes_position(self):
        """Different positions should produce different IDs"""
        id1 = Paragraph.compute_id("doc1", 0, "טקסט זהה")
        id2 = Paragraph.compute_id("doc1", 1, "טקסט זהה")

        assert id1 != id2


# =============================================================================
# Claim Extractor Tests with Locators
# =============================================================================

class TestClaimExtractorLocators:
    """Tests for claim extraction with locator support"""

    def test_extract_claims_basic(self):
        """Should extract claims from text"""
        text = """
        1. החוזה נחתם ביום 15.3.2020.
        2. הסכום שהועבר היה 500,000 ש"ח.
        """
        claims = extract_claims(text, source_name="תצהיר")

        assert len(claims) >= 2
        assert all(isinstance(c, Claim) for c in claims)

    def test_extract_claims_with_doc_id(self):
        """Should include doc_id in claims"""
        claims = extract_claims(
            text="טקסט עם תוכן מספיק לטענה אחת לפחות",
            source_name="מסמך",
            doc_id="doc_123"
        )

        assert len(claims) >= 1
        assert claims[0].doc_id == "doc_123"

    def test_extract_claims_with_paragraph_id(self):
        """Should include paragraph_id in claims"""
        claims = extract_claims(
            text="טקסט עם תוכן מספיק לטענה אחת לפחות",
            source_name="מסמך",
            doc_id="doc_123",
            paragraph_id="para_456"
        )

        assert len(claims) >= 1
        assert claims[0].paragraph_id == "para_456"

    def test_extract_claims_with_char_offset(self):
        """Should add char_offset to positions"""
        claims = extract_claims(
            text="טקסט עם תוכן מספיק לטענה אחת לפחות",
            source_name="מסמך",
            char_offset=100
        )

        assert len(claims) >= 1
        # char_start should be offset by 100
        assert claims[0].char_start is not None
        assert claims[0].char_start >= 100

    def test_claim_to_dict_includes_locators(self):
        """to_dict should include locator fields"""
        claims = extract_claims(
            text="טקסט עם תוכן מספיק לטענה אחת לפחות",
            source_name="מסמך",
            doc_id="doc_123",
            paragraph_id="para_456",
            paragraph_index=5
        )

        claim_dict = claims[0].to_dict()
        assert "doc_id" in claim_dict
        assert "paragraph_id" in claim_dict
        assert "paragraph_index" in claim_dict
        assert "char_start" in claim_dict
        assert "char_end" in claim_dict


# =============================================================================
# BM25 Retrieval Tests
# =============================================================================

class TestBM25Retrieval:
    """Tests for BM25 retrieval module"""

    def test_bm25_index_add_paragraph(self):
        """Should add paragraph to index"""
        index = BM25Index()
        para = Paragraph(
            id="p1",
            doc_id="d1",
            case_id="c1",
            paragraph_index=0,
            text="החוזה נחתם ביום 15.3.2020"
        )

        index.add_paragraph(para)
        assert index.n_docs == 1

    def test_bm25_search(self):
        """Should search and find relevant paragraphs"""
        index = BM25Index()

        paragraphs = [
            Paragraph(id="p1", doc_id="d1", case_id="c1", paragraph_index=0,
                     text="החוזה נחתם ביום 15.3.2020 במשרדי החברה"),
            Paragraph(id="p2", doc_id="d1", case_id="c1", paragraph_index=1,
                     text="הסכום שהועבר היה 500,000 שקלים"),
            Paragraph(id="p3", doc_id="d2", case_id="c1", paragraph_index=0,
                     text="החוזה נחתם ביום 20.5.2021 בירושלים"),
        ]

        index.add_paragraphs(paragraphs)

        results = index.search("חוזה נחתם", top_k=2)
        assert len(results) == 2
        # First result should be most relevant
        assert results[0].score >= results[1].score

    def test_bm25_find_similar(self):
        """Should find similar paragraphs from different documents"""
        index = BM25Index()

        paragraphs = [
            Paragraph(id="p1", doc_id="d1", case_id="c1", paragraph_index=0,
                     text="החוזה נחתם ביום 15.3.2020"),
            Paragraph(id="p2", doc_id="d2", case_id="c1", paragraph_index=0,
                     text="החוזה נחתם ביום 20.5.2021"),
            Paragraph(id="p3", doc_id="d3", case_id="c1", paragraph_index=0,
                     text="הסכום היה 500,000 שקלים"),
        ]

        index.add_paragraphs(paragraphs)

        # Find similar to p1 (should find p2, not p3)
        similar = index.find_similar_paragraphs(paragraphs[0], top_k=2)
        assert len(similar) >= 1
        # p2 should be more similar than p3
        assert similar[0].paragraph_id == "p2"

    def test_candidate_pair_generator(self):
        """Should generate candidate pairs for contradiction detection"""
        paragraphs = [
            Paragraph(id="p1", doc_id="d1", case_id="c1", paragraph_index=0,
                     text="החוזה נחתם ביום 15.3.2020"),
            Paragraph(id="p2", doc_id="d2", case_id="c1", paragraph_index=0,
                     text="החוזה נחתם ביום 20.5.2021"),
        ]

        candidates = generate_candidate_pairs(paragraphs, top_k=2)

        assert len(candidates) >= 1
        # Should be a tuple of (para1, para2, score)
        para1, para2, score = candidates[0]
        assert para1.id != para2.id
        assert score > 0


# =============================================================================
# API Endpoint Tests for Case Management
# =============================================================================

class TestCaseManagementAPI:
    """Tests for case management API endpoints"""

    def test_create_case_api(self, client):
        """Should create case via API"""
        response = client.post("/cases", json={
            "name": "תיק בדיקה",
            "client_name": "לקוח בדיקה"
        })

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["name"] == "תיק בדיקה"

    def test_list_cases_api(self, client):
        """Should list cases via API"""
        # Create a case first
        client.post("/cases", json={"name": "תיק 1"})

        response = client.get("/cases")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_add_document_api(self, client):
        """Should add document to case via upload API"""
        # Create case
        case_response = client.post("/cases", json={"name": "תיק בדיקה"})
        case_id = case_response.json()["id"]

        # Upload as a text file (new upload system)
        content = "טקסט ארוך מספיק עם תוכן משפטי לבדיקה של מערכת זיהוי סתירות"
        doc_response = client.post(
            f"/api/v1/cases/{case_id}/documents",
            files={"file": ("doc.txt", content.encode("utf-8"), "text/plain")},
            data={"metadata_json": "[]"},
        )

        assert doc_response.status_code == 200
        data = doc_response.json()
        assert "document_ids" in data
        assert len(data["document_ids"]) == 1

        # Document should be retrievable
        doc_id = data["document_ids"][0]
        details = client.get(f"/api/v1/documents/{doc_id}")
        assert details.status_code == 200
        assert details.json().get("extracted_text")

    def test_add_document_creates_paragraphs(self, client):
        """Adding document should create blocks/pages (snippetable source)"""
        # Create case
        case_response = client.post("/cases", json={"name": "תיק בדיקה"})
        case_id = case_response.json()["id"]

        # Upload document with multiple paragraphs
        doc_text = """
1. פסקה ראשונה עם תוכן מספיק ארוך מספיק כדי לעבור את הסף המינימלי של חמישים תווים לפסקה.

2. פסקה שנייה עם תוכן נוסף שגם הוא ארוך מספיק כדי לעבור את הסף המינימלי של חמישים תווים.

3. פסקה שלישית לבדיקה שגם היא צריכה להיות ארוכה מספיק כדי להיחשב כפסקה תקפה במערכת.
"""
        doc_response = client.post(
            f"/api/v1/cases/{case_id}/documents",
            files={"file": ("multi.txt", doc_text.encode("utf-8"), "text/plain")},
            data={"metadata_json": "[]"},
        )
        assert doc_response.status_code == 200
        doc_id = doc_response.json()["document_ids"][0]

        # Validate we have extracted text and can fetch a snippet (blocks/pages were created)
        details = client.get(f"/api/v1/documents/{doc_id}")
        assert details.status_code == 200
        assert len(details.json().get("extracted_text", "")) > 50

        snippet = client.get(f"/api/v1/documents/{doc_id}/snippet?page_no=1&block_index=0")
        assert snippet.status_code == 200
        assert snippet.json().get("text")


# =============================================================================
# Evidence Locator Tests
# =============================================================================

class TestEvidenceLocators:
    """Tests for evidence locators in contradiction output"""

    def test_contradiction_has_claim_evidence(self, client):
        """Contradictions should include claim evidence with locators"""
        # Create case with contradicting documents
        case_response = client.post("/cases", json={"name": "תיק סתירות"})
        case_id = case_response.json()["id"]

        # Add doc 1
        client.post(f"/cases/{case_id}/documents", json={
            "name": "תצהיר תובע",
            "extracted_text": "החוזה נחתם ביום 15.3.2020 במשרדי החברה בתל אביב"
        })

        # Add doc 2 with contradiction
        client.post(f"/cases/{case_id}/documents", json={
            "name": "תצהיר נתבע",
            "extracted_text": "החוזה נחתם ביום 20.5.2021 בירושלים ולא בתל אביב"
        })

        # Analyze
        analyze_response = client.post(f"/cases/{case_id}/analyze", json={})

        if analyze_response.status_code == 200:
            data = analyze_response.json()
            for contr in data.get("contradictions", []):
                # Should have claim1 and claim2 evidence
                assert "claim1" in contr
                assert "claim2" in contr
                # Evidence should have expected fields
                assert "claim_id" in contr["claim1"]
                assert "quote" in contr["claim1"]


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
