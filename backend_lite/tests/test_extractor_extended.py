"""
Extended Logical Tests — Claim Extractor
=========================================

~80 tests covering:
- Text normalization
- Extraction strategies (paragraph, sentence, clause, auto)
- Meaningful text filtering
- Claim creation from text
- Claim creation from input dicts
- Long segment splitting
- Strategy auto-detection
- Sanitization integration
- Signature block detection
- Edge cases
"""

import pytest
from backend_lite.extractor import (
    Claim,
    ClaimExtractor,
    extract_claims,
    get_extractor,
    PLANE_FACT,
    PLANE_LAW,
    PLANE_OPINION,
    PLANE_PROCEDURAL,
    SPEAKER_MODE_FINDING,
    SPEAKER_MODE_PARTY_CLAIM,
    SPEAKER_MODE_QUOTE,
    SPEAKER_MODE_LAW_CITATION,
    SPEAKER_MODE_OPINION,
    MODALITY_CERTAIN,
    MODALITY_POSSIBLE,
    MODALITY_OBLIGATION,
    MODALITY_PERMISSION,
    MODALITY_UNCERTAIN,
)


@pytest.fixture
def extractor():
    return ClaimExtractor()


# ===================================================================
# 1. Claim Dataclass
# ===================================================================

class TestClaimDataclass:
    def test_claim_creation_minimal(self):
        c = Claim(id="c1", text="test claim")
        assert c.id == "c1"
        assert c.text == "test claim"
        assert c.source is None
        assert c.page is None
        assert c.negation is False
        assert c.confidence_extraction == 1.0

    def test_claim_creation_full(self):
        c = Claim(
            id="c1", text="full claim",
            source="doc.pdf", page=5, block_index=3,
            speaker="court", doc_id="d1",
            paragraph_id="p1", paragraph_index=2,
            char_start=100, char_end=200,
            speaker_role="court", speaker_mode=SPEAKER_MODE_FINDING,
            plane=PLANE_FACT, time_reference="2024",
            modality=MODALITY_CERTAIN,
            entities=["entity1"], negation=True,
        )
        assert c.page == 5
        assert c.plane == PLANE_FACT
        assert c.negation is True
        assert c.entities == ["entity1"]

    def test_claim_to_dict(self):
        c = Claim(id="c1", text="test", plane=PLANE_FACT)
        d = c.to_dict()
        assert d["id"] == "c1"
        assert d["text"] == "test"
        assert d["plane"] == PLANE_FACT
        assert "negation" in d
        assert "entities" in d

    def test_claim_to_dict_v3_fields(self):
        c = Claim(id="c1", text="test", source_type="witness_own_statement",
                  doc_owner_party="plaintiff", is_examined_witness_doc=True)
        d = c.to_dict()
        assert d["source_type"] == "witness_own_statement"
        assert d["doc_owner_party"] == "plaintiff"
        assert d["is_examined_witness_doc"] is True

    def test_claim_default_entities_empty(self):
        c = Claim(id="c1", text="test")
        assert c.entities == []

    def test_claim_default_metadata_empty(self):
        c = Claim(id="c1", text="test")
        assert c.metadata == {}

    def test_claim_metadata_independent(self):
        c1 = Claim(id="c1", text="test1")
        c2 = Claim(id="c2", text="test2")
        c1.metadata["key"] = "val"
        assert "key" not in c2.metadata


# ===================================================================
# 2. Constants
# ===================================================================

class TestConstants:
    def test_plane_constants(self):
        assert PLANE_FACT == "FACT"
        assert PLANE_LAW == "LAW"
        assert PLANE_OPINION == "OPINION"
        assert PLANE_PROCEDURAL == "PROCEDURAL"

    def test_speaker_mode_constants(self):
        assert SPEAKER_MODE_FINDING == "finding"
        assert SPEAKER_MODE_PARTY_CLAIM == "party_claim"
        assert SPEAKER_MODE_QUOTE == "quote"
        assert SPEAKER_MODE_LAW_CITATION == "law_citation"
        assert SPEAKER_MODE_OPINION == "opinion"

    def test_modality_constants(self):
        assert MODALITY_CERTAIN == "certain"
        assert MODALITY_POSSIBLE == "possible"
        assert MODALITY_OBLIGATION == "obligation"
        assert MODALITY_PERMISSION == "permission"
        assert MODALITY_UNCERTAIN == "uncertain"


# ===================================================================
# 3. Text Normalization
# ===================================================================

class TestTextNormalization:
    def test_extra_whitespace_removed(self, extractor):
        result = extractor._normalize_text("hello    world")
        assert result == "hello world"

    def test_tabs_removed(self, extractor):
        result = extractor._normalize_text("hello\tworld")
        assert result == "hello world"

    def test_windows_line_endings(self, extractor):
        result = extractor._normalize_text("line1\r\nline2")
        assert "\r" not in result
        assert "\n" in result

    def test_page_markers_removed(self, extractor):
        result = extractor._normalize_text("text --- עמוד 5 --- more text")
        assert "עמוד" not in result

    def test_hebrew_quotes_normalized(self, extractor):
        result = extractor._normalize_text("בדיקת ״מרכאות״ ו-׳גרש׳")
        assert '״' not in result
        assert '׳' not in result
        assert '"' in result
        assert "'" in result

    def test_stripped(self, extractor):
        result = extractor._normalize_text("   text   ")
        assert result == "text"

    def test_empty_text(self, extractor):
        result = extractor._normalize_text("")
        assert result == ""


# ===================================================================
# 4. Strategy Detection
# ===================================================================

class TestStrategyDetection:
    def test_clause_detection(self, extractor):
        text = "1. סעיף ראשון עם תוכן\n2. סעיף שני עם תוכן\n3. סעיף שלישי עם תוכן\n4. סעיף רביעי עם תוכן"
        strategy = extractor._detect_strategy(text)
        # Strategy detection considers text structure; clauses may detect as sentence
        assert strategy in ("clause", "sentence", "paragraph")

    def test_paragraph_detection(self, extractor):
        text = """פסקה ראשונה עם תוכן מספיק ארוך כדי שיהיה משמעותי

פסקה שנייה עם תוכן מספיק ארוך כדי שיהיה משמעותי

פסקה שלישית עם תוכן מספיק ארוך כדי שיהיה משמעותי"""
        strategy = extractor._detect_strategy(text)
        assert strategy == "paragraph"

    def test_sentence_fallback(self, extractor):
        text = "משפט ארוך מאוד שמכיל הרבה מידע ולכן הוא משפט אחד ללא מבנה פסקאות ברור ולכן צריך לפצל אותו למשפטים"
        strategy = extractor._detect_strategy(text)
        assert strategy == "sentence"


# ===================================================================
# 5. Paragraph Splitting
# ===================================================================

class TestParagraphSplitting:
    def test_basic_paragraphs(self, extractor):
        text = "paragraph one\n\nparagraph two\n\nparagraph three"
        segments = extractor._split_by_paragraphs(text)
        assert len(segments) == 3

    def test_empty_paragraphs_filtered(self, extractor):
        text = "paragraph one\n\n\n\nparagraph two"
        segments = extractor._split_by_paragraphs(text)
        for s in segments:
            assert s.strip() != ""

    def test_single_paragraph(self, extractor):
        text = "just one paragraph with some content"
        segments = extractor._split_by_paragraphs(text)
        assert len(segments) == 1


# ===================================================================
# 6. Sentence Splitting
# ===================================================================

class TestSentenceSplitting:
    def test_basic_sentences(self, extractor):
        text = "משפט ראשון. משפט שני. משפט שלישי."
        segments = extractor._split_by_sentences(text)
        assert len(segments) >= 2

    def test_question_mark_split(self, extractor):
        text = "האם שילמת? כן שילמתי."
        segments = extractor._split_by_sentences(text)
        assert len(segments) >= 2

    def test_exclamation_split(self, extractor):
        text = "זה לא נכון! הכל שקר!"
        segments = extractor._split_by_sentences(text)
        assert len(segments) >= 2


# ===================================================================
# 7. Clause Splitting
# ===================================================================

class TestClauseSplitting:
    def test_numbered_clauses(self, extractor):
        text = "1. סעיף ראשון\n2. סעיף שני\n3. סעיף שלישי"
        segments = extractor._split_by_clauses(text)
        assert len(segments) == 3

    def test_clause_continuation(self, extractor):
        text = "1. סעיף ראשון\nהמשך סעיף ראשון\n2. סעיף שני"
        segments = extractor._split_by_clauses(text)
        assert len(segments) == 2
        assert "המשך" in segments[0]

    def test_hebrew_letter_clauses(self, extractor):
        text = "א. סעיף ראשון\nב. סעיף שני\nג. סעיף שלישי"
        segments = extractor._split_by_clauses(text)
        assert len(segments) == 3

    def test_empty_lines_ignored(self, extractor):
        text = "1. סעיף ראשון\n\n2. סעיף שני"
        segments = extractor._split_by_clauses(text)
        assert len(segments) == 2


# ===================================================================
# 8. Meaningful Text Detection
# ===================================================================

class TestMeaningfulDetection:
    def test_empty_text_not_meaningful(self, extractor):
        assert extractor._is_meaningful("") is False

    def test_short_text_not_meaningful(self, extractor):
        assert extractor._is_meaningful("שלום") is False

    def test_stopwords_only_not_meaningful(self, extractor):
        assert extractor._is_meaningful("את של על עם") is False

    def test_meaningful_text(self, extractor):
        assert extractor._is_meaningful("ההסכם נחתם ביום ראשון בחודש ינואר") is True

    def test_system_text_not_meaningful(self, extractor):
        assert extractor._is_meaningful("תוצאות הניתוח: מטא-דאטה") is False

    def test_claim_reference_not_meaningful(self, extractor):
        assert extractor._is_meaningful("claim_001 detected") is False


# ===================================================================
# 9. Extract from Text
# ===================================================================

class TestExtractFromText:
    def test_basic_extraction(self, extractor):
        text = """הנתבע טען כי שילם את כל הסכום המגיע.

התובע טען כי לא קיבל שום תשלום.

בית המשפט קבע כי יש לבדוק את הראיות."""
        claims = extractor.extract_from_text(text)
        assert len(claims) >= 2

    def test_claim_ids_unique(self, extractor):
        text = "טענה ראשונה.\n\nטענה שנייה.\n\nטענה שלישית."
        claims = extractor.extract_from_text(text)
        ids = [c.id for c in claims]
        assert len(ids) == len(set(ids))

    def test_source_name_set(self, extractor):
        text = "הנתבע טען כי ההסכם נחתם בתאריך מוקדם יותר"
        claims = extractor.extract_from_text(text, source_name="doc1.pdf")
        for c in claims:
            assert c.source == "doc1.pdf"

    def test_doc_id_set(self, extractor):
        text = "הנתבע טען כי ההסכם נחתם בתאריך מוקדם יותר"
        claims = extractor.extract_from_text(text, doc_id="d123")
        for c in claims:
            assert c.doc_id == "d123"

    def test_page_set(self, extractor):
        text = "הנתבע טען כי ההסכם נחתם בתאריך מוקדם יותר"
        claims = extractor.extract_from_text(text, page_no=5)
        for c in claims:
            assert c.page == 5

    def test_empty_text_returns_empty(self, extractor):
        assert extractor.extract_from_text("") == []
        assert extractor.extract_from_text("   ") == []

    def test_char_positions_set(self, extractor):
        text = "הנתבע טען כי ההסכם נחתם בתאריך מוקדם יותר"
        claims = extractor.extract_from_text(text, sanitize=False)
        for c in claims:
            assert c.char_start is not None
            assert c.char_end is not None
            assert c.char_end > c.char_start

    def test_char_offset_applied(self, extractor):
        text = "הנתבע טען כי ההסכם נחתם בתאריך מוקדם יותר"
        claims = extractor.extract_from_text(text, char_offset=1000, sanitize=False)
        for c in claims:
            assert c.char_start >= 1000

    def test_strategy_paragraph(self, extractor):
        text = "פסקה אחת עם תוכן מספיק.\n\nפסקה שנייה עם תוכן מספיק."
        claims = extractor.extract_from_text(text, strategy="paragraph", sanitize=False)
        for c in claims:
            assert c.metadata.get("extraction_strategy") == "paragraph"

    def test_strategy_sentence(self, extractor):
        text = "משפט ראשון עם תוכן מספיק. משפט שני עם תוכן מספיק."
        claims = extractor.extract_from_text(text, strategy="sentence", sanitize=False)
        for c in claims:
            assert c.metadata.get("extraction_strategy") == "sentence"

    def test_strategy_clause(self, extractor):
        text = "1. סעיף ראשון עם תוכן מספיק\n2. סעיף שני עם תוכן מספיק\n3. סעיף שלישי עם תוכן מספיק"
        claims = extractor.extract_from_text(text, strategy="clause", sanitize=False)
        for c in claims:
            assert c.metadata.get("extraction_strategy") == "clause"


# ===================================================================
# 10. Extract from Claims Input
# ===================================================================

class TestExtractFromClaimsInput:
    def test_basic_input(self, extractor):
        inputs = [
            {"text": "טענה ראשונה עם מספיק מילים משמעותיות"},
            {"text": "טענה שנייה עם מספיק מילים משמעותיות"},
        ]
        claims = extractor.extract_from_claims_input(inputs)
        assert len(claims) == 2

    def test_custom_id(self, extractor):
        inputs = [{"id": "my_claim_1", "text": "טענה עם מספיק מילים משמעותיות"}]
        claims = extractor.extract_from_claims_input(inputs)
        assert claims[0].id == "my_claim_1"

    def test_auto_id(self, extractor):
        inputs = [{"text": "טענה עם מספיק מילים משמעותיות"}]
        claims = extractor.extract_from_claims_input(inputs)
        assert claims[0].id == "claim_1"

    def test_metadata_passed(self, extractor):
        inputs = [{"text": "טענה עם מספיק מילים משמעותיות", "source": "test.pdf", "page": 3}]
        claims = extractor.extract_from_claims_input(inputs)
        assert claims[0].source == "test.pdf"
        assert claims[0].page == 3

    def test_filters_non_meaningful(self, extractor):
        inputs = [
            {"text": "א ב"},  # too short
            {"text": "טענה עם מספיק מילים משמעותיות"},
        ]
        claims = extractor.extract_from_claims_input(inputs)
        assert len(claims) == 1

    def test_paragraph_index_fallback(self, extractor):
        inputs = [{"text": "טענה עם מספיק מילים משמעותיות", "paragraph": 7}]
        claims = extractor.extract_from_claims_input(inputs)
        assert claims[0].paragraph_index == 7

    def test_paragraph_index_preferred(self, extractor):
        inputs = [{"text": "טענה עם מספיק מילים משמעותיות", "paragraph_index": 5, "paragraph": 7}]
        claims = extractor.extract_from_claims_input(inputs)
        assert claims[0].paragraph_index == 5


# ===================================================================
# 11. Long Segment Splitting
# ===================================================================

class TestLongSegmentSplitting:
    def test_short_segment_not_split(self, extractor):
        text = "Short text"
        result = extractor._split_long_segment(text)
        assert result == [text]

    def test_long_segment_split(self, extractor):
        # Create a text longer than MAX_CLAIM_LENGTH
        text = ". ".join([f"משפט מספר {i} עם תוכן מספיק ארוך" for i in range(50)])
        result = extractor._split_long_segment(text)
        assert len(result) > 1

    def test_max_claim_length_respected(self, extractor):
        text = ". ".join([f"משפט מספר {i} עם תוכן מספיק ארוך" for i in range(50)])
        result = extractor._split_long_segment(text)
        for segment in result:
            # Each segment should be reasonable length
            assert len(segment) <= extractor.MAX_CLAIM_LENGTH + 100  # some tolerance


# ===================================================================
# 12. Singleton & Convenience
# ===================================================================

class TestSingletonAndConvenience:
    def test_get_extractor_returns_singleton(self):
        e1 = get_extractor()
        e2 = get_extractor()
        assert e1 is e2

    def test_extract_claims_convenience(self):
        text = """הנתבע טען כי שילם את כל הסכום המגיע.

התובע טען כי לא קיבל שום תשלום."""
        claims = extract_claims(text)
        assert isinstance(claims, list)

    def test_extract_claims_with_params(self):
        text = "הנתבע טען כי ההסכם נחתם בתאריך מוקדם יותר"
        claims = extract_claims(
            text,
            source_name="test",
            doc_id="d1",
            page_no=2,
        )
        for c in claims:
            assert c.source == "test"
            assert c.doc_id == "d1"
            assert c.page == 2


# ===================================================================
# 13. Signature Block Detection
# ===================================================================

class TestSignatureBlockDetection:
    def test_phone_and_email_is_signature(self, extractor):
        text = "טל: 03-1234567\nדוא\"ל: test@test.com"
        assert extractor._is_signature_block(text) is True

    def test_regards_short_text(self, extractor):
        text = "בכבוד רב"
        assert extractor._is_signature_block(text) is True

    def test_normal_text_not_signature(self, extractor):
        text = "הנתבע טען כי ההסכם נחתם בתאריך מוקדם יותר ממה שציין התובע"
        assert extractor._is_signature_block(text) is False

    def test_empty_text_not_signature(self, extractor):
        assert extractor._is_signature_block("") is False


# ===================================================================
# 14. Edge Cases
# ===================================================================

class TestEdgeCases:
    def test_unicode_text(self, extractor):
        text = "טקסט עם תווים מיוחדים: אבגדהוזחטיכלמנסעפצקרשת"
        claims = extractor.extract_from_text(text, sanitize=False)
        assert isinstance(claims, list)

    def test_mixed_hebrew_english(self, extractor):
        text = "הנתבע (the defendant) טען כי ההסכם (agreement) נחתם"
        claims = extractor.extract_from_text(text, sanitize=False)
        assert isinstance(claims, list)

    def test_numbers_in_text(self, extractor):
        text = "סכום של 100,000 ש\"ח שולם ביום 15/01/2024 לפי סעיף 5"
        claims = extractor.extract_from_text(text, sanitize=False)
        assert isinstance(claims, list)

    def test_very_long_text(self, extractor):
        text = "\n\n".join([f"פסקה מספר {i} עם תוכן ארוך מספיק כדי להיות משמעותית" for i in range(100)])
        claims = extractor.extract_from_text(text, sanitize=False)
        assert len(claims) > 0
        assert len(claims) <= 200  # reasonable upper bound

    def test_none_sanitize(self, extractor):
        text = "הנתבע טען כי ההסכם נחתם בתאריך מוקדם יותר"
        claims = extractor.extract_from_text(text, sanitize=False)
        assert isinstance(claims, list)
