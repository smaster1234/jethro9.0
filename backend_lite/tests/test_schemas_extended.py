"""
Extended Tests — Schemas, Claim Enricher, Candidate Filter
============================================================

Real logic tests for:
- AmbiguityExplanation pydantic model (kept from original)
- Basic enum behavior (2-3 sanity checks)
- claim_enricher.py: all detection/enrichment functions (~80 tests)
- candidate_filter.py: hard filters, clustering, pair generation (~40 tests)

Total: ~130 tests exercising actual Hebrew legal text processing logic.
"""

import pytest
from backend_lite.schemas import (
    ContradictionType,
    ContradictionCategory,
    Severity,
    AmbiguityExplanation,
)
from backend_lite.extractor import (
    Claim,
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
)
from backend_lite.claim_enricher import (
    _detect_speaker,
    _detect_plane,
    _detect_time_reference,
    _detect_modality,
    _detect_scope,
    _extract_entities,
    _detect_negation,
    _normalize_for_comparison,
    resolve_entities,
    enrich_claims,
    _sentence_spans,
    _context_window,
    _extract_headings,
    _nearest_heading,
    _extract_speaker_role_from_match,
)
from backend_lite.candidate_filter import (
    passes_hard_filters,
    _entity_overlap,
    _plane_compatible,
    _word_overlap,
    cluster_claims,
    generate_candidate_pairs,
    _strong_subject_overlap,
)


# ---------------------------------------------------------------------------
# Helper: create a Claim with sensible defaults for testing
# ---------------------------------------------------------------------------

def _make_claim(
    text="טקסט לדוגמה",
    *,
    id=None,
    plane=None,
    speaker_mode=None,
    speaker_role=None,
    entities=None,
    subject=None,
    doc_id=None,
    char_start=None,
    char_end=None,
    negation=False,
    modality=None,
    scope_quantifiers=None,
    time_reference=None,
    normalized_claim=None,
    confidence_extraction=1.0,
):
    import uuid as _uuid
    return Claim(
        id=id or str(_uuid.uuid4())[:8],
        text=text,
        plane=plane,
        speaker_mode=speaker_mode,
        speaker_role=speaker_role,
        entities=entities or [],
        subject=subject,
        doc_id=doc_id,
        char_start=char_start,
        char_end=char_end,
        negation=negation,
        modality=modality,
        scope_quantifiers=scope_quantifiers,
        time_reference=time_reference,
        normalized_claim=normalized_claim,
        confidence_extraction=confidence_extraction,
    )


# ===================================================================
# 1. AmbiguityExplanation Pydantic Model (kept — real tests)
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
# 2. Basic Enum Behavior (minimal sanity)
# ===================================================================

class TestEnumBasicBehavior:
    def test_contradiction_type_is_str_enum(self):
        """ContradictionType members are usable as plain strings."""
        assert isinstance(ContradictionType.TEMPORAL_DATE, str)
        assert ContradictionType.TEMPORAL_DATE == "temporal_date_conflict"

    def test_all_contradiction_type_values_unique(self):
        values = [t.value for t in ContradictionType]
        assert len(values) == len(set(values))

    def test_severity_ordering_by_name(self):
        """Severity enum has four levels."""
        names = [s.name for s in Severity]
        assert "CRITICAL" in names
        assert "LOW" in names
        assert len(names) == 4


# ===================================================================
# 3. Claim Enricher — _detect_speaker
# ===================================================================

class TestDetectSpeaker:
    """Test Hebrew speaker/role detection from claim text."""

    def test_defendant_claim_with_letinat(self):
        role, mode = _detect_speaker("לטענת הנתבע, הוא שילם את כל החוב במועד")
        assert "defendant" in role
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_plaintiff_claim_with_taan(self):
        role, mode = _detect_speaker("התובע טען כי לא קיבל את הסחורה")
        assert "plaintiff" in role
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_quoted_text_hebrew_quotes(self):
        role, mode = _detect_speaker('הנתבע אמר "אני שילמתי הכל" בישיבת בית המשפט')
        assert mode == SPEAKER_MODE_QUOTE
        # role is None for quotes
        assert role is None

    def test_law_citation_case_number(self):
        role, mode = _detect_speaker('כפי שנקבע בע"א 1234/22 בפסקה 15')
        assert mode == SPEAKER_MODE_LAW_CITATION
        assert role is None

    def test_court_finding(self):
        role, mode = _detect_speaker("בית המשפט קובע כי התביעה מתקבלת")
        assert role == "court"
        assert mode == SPEAKER_MODE_FINDING

    def test_opinion_nire_ki(self):
        role, mode = _detect_speaker("נראה כי הנתבע לא עמד בנטל ההוכחה")
        assert mode == SPEAKER_MODE_OPINION

    def test_defendant_taan_ki(self):
        role, mode = _detect_speaker("הנתבע טען כי שילם את מלוא הסכום")
        assert role == "defendant"
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_expert_ledivre(self):
        role, mode = _detect_speaker("לדברי המומחה, הנזק עומד על מיליון שקלים")
        assert role is not None
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_counsel_ba_koach(self):
        # "בא כוח הנתבע טען" — _extract_speaker_role_from_match sees "נתבע"
        # in the matched text, so role is "defendant" (the party being represented).
        role, mode = _detect_speaker("בא כוח הנתבע טען כי התביעה התיישנה")
        assert role in ("defendant", "counsel")
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_plain_text_no_markers(self):
        role, mode = _detect_speaker("הסכום שולם בתאריך 15.1.2024")
        assert role is None
        assert mode is None

    def test_plaintiff_female_form_no_match(self):
        # "התובעת טענה" does NOT match any pattern because pattern[2] requires
        # "טען" (no feminine ה suffix) and pattern[3] requires "התובע" (no feminine ת).
        # This is a known gap in the regex patterns.
        role, mode = _detect_speaker("התובעת טענה כי לא קיבלה את המכתב")
        assert role is None
        assert mode is None

    def test_plaintiff_with_letinat(self):
        # Using "לטענת התובעת" which matches pattern[0]: לטענת\s+\S+
        role, mode = _detect_speaker("לטענת התובעת, לא קיבלה את המכתב")
        assert mode == SPEAKER_MODE_PARTY_CLAIM
        assert role is not None

    def test_witness_testified(self):
        role, mode = _detect_speaker("העד העיד כי ראה את התאונה מקרוב")
        assert role == "witness"
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_ruling_nifask_ki(self):
        role, mode = _detect_speaker("נפסק כי הנתבע ישלם פיצויים")
        assert mode == SPEAKER_MODE_FINDING

    def test_letinat_hatovea(self):
        role, mode = _detect_speaker("לטענת התובע, ההסכם הופר על ידי הנתבע")
        assert "plaintiff" in role
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_nitan_litoan(self):
        role, mode = _detect_speaker("ניתן לטעון כי ההסכם בטל")
        assert mode == SPEAKER_MODE_PARTY_CLAIM

    def test_lakhora(self):
        role, mode = _detect_speaker("לכאורה, הנתבע הפר את ההסכם")
        assert mode == SPEAKER_MODE_PARTY_CLAIM


# ===================================================================
# 4. Claim Enricher — _extract_speaker_role_from_match
# ===================================================================

class TestExtractSpeakerRole:
    def test_plaintiff_role(self):
        assert _extract_speaker_role_from_match("התובע טען") == "plaintiff"

    def test_defendant_role(self):
        assert _extract_speaker_role_from_match("הנתבע טען") == "defendant"

    def test_witness_role(self):
        assert _extract_speaker_role_from_match("העד העיד") == "witness"

    def test_counsel_role(self):
        # "בא כוח" alone triggers counsel, but "בא כוח הנתבע" contains "נתבע"
        # which is checked BEFORE "בא כוח" in _extract_speaker_role_from_match.
        assert _extract_speaker_role_from_match("בא כוח הנתבע טען") == "defendant"
        # Pure counsel text without a party name
        assert _extract_speaker_role_from_match("בא-כוח טען") == "counsel"

    def test_generic_party_role(self):
        # Text with no specific role keyword returns "party"
        assert _extract_speaker_role_from_match("לדברי הגורם") == "party"

    def test_appellant_maps_to_plaintiff(self):
        assert _extract_speaker_role_from_match("המערער טען") == "plaintiff"


# ===================================================================
# 5. Claim Enricher — _detect_plane
# ===================================================================

class TestDetectPlane:
    def test_law_section_reference(self):
        assert _detect_plane("סעיף 5 לחוק החוזים קובע את זכות הביטול") == PLANE_LAW

    def test_procedural_appeal_filed(self):
        assert _detect_plane("הוגש ערעור על פסק הדין") == PLANE_PROCEDURAL

    def test_opinion_nire_ki(self):
        assert _detect_plane("נראה כי ישנו קושי בעמדת הנתבע") == PLANE_OPINION

    def test_plain_fact(self):
        assert _detect_plane("הנתבע שילם סך של 50,000 שקלים ביום 15.1.2024") == PLANE_FACT

    def test_law_by_halacha(self):
        assert _detect_plane("על פי הלכת בית המשפט העליון בעניין כהן") == PLANE_LAW

    def test_procedural_hearing_date(self):
        assert _detect_plane("דיון מיום 15.1.2024 בפני כבוד השופט") == PLANE_PROCEDURAL

    def test_law_regulation(self):
        assert _detect_plane("תקנה 3 לתקנות סדר הדין האזרחי") == PLANE_LAW

    def test_opinion_safek(self):
        assert _detect_plane("ספק אם ניתן לקבל את הטענה") == PLANE_OPINION

    def test_procedural_dismissed(self):
        assert _detect_plane("נדחה הערעור על ההחלטה") == PLANE_PROCEDURAL

    def test_fact_payment(self):
        assert _detect_plane("התשלום בוצע בהעברה בנקאית") == PLANE_FACT


# ===================================================================
# 6. Claim Enricher — _detect_time_reference
# ===================================================================

class TestDetectTimeReference:
    def test_date_with_slashes(self):
        ref = _detect_time_reference("התשלום בוצע ב-15/01/2024 לחשבון הבנק")
        assert ref is not None
        assert "15" in ref or "01" in ref or "2024" in ref

    def test_hebrew_month_name(self):
        ref = _detect_time_reference("בינואר 2024 נחתם ההסכם בין הצדדים")
        assert ref is not None
        assert "2024" in ref

    def test_bayom_with_number(self):
        # The TIME_PATTERN for "ביום" matches "ביום\s+\d" which grabs "ביום 1"
        # (only the first digit). The match is still not None.
        ref = _detect_time_reference("ביום 15 לחודש נעשתה הפגישה")
        assert ref is not None
        assert ref.startswith("ביום")

    def test_year_shnat(self):
        ref = _detect_time_reference("האירוע התרחש בשנת 2020 לאחר חתימת ההסכם")
        assert ref is not None
        assert "2020" in ref

    def test_relative_time_achar_miken(self):
        ref = _detect_time_reference("לאחר מכן, הנתבע פנה למשטרה")
        assert ref is not None

    def test_no_time_reference(self):
        ref = _detect_time_reference("הנתבע שילם את הסכום המלא")
        assert ref is None

    def test_date_with_dots(self):
        ref = _detect_time_reference("מיום 3.5.2023 ההסכם נכנס לתוקף")
        assert ref is not None

    def test_date_with_dashes(self):
        ref = _detect_time_reference("נכון ל-15-01-2024 היתרה עמדה על אפס")
        assert ref is not None


# ===================================================================
# 7. Claim Enricher — _detect_modality
# ===================================================================

class TestDetectModality:
    def test_obligation_chayav(self):
        assert _detect_modality("הנתבע חייב לשלם את הסכום") == MODALITY_OBLIGATION

    def test_permission_rashai(self):
        assert _detect_modality("התובע רשאי להגיש בקשה נוספת") == MODALITY_PERMISSION

    def test_possibility_yitakhen(self):
        assert _detect_modality("ייתכן שהיה ויתור מכללא") == MODALITY_POSSIBLE

    def test_certain_plain_text(self):
        assert _detect_modality("הנתבע שילם 50,000 שקלים") == MODALITY_CERTAIN

    def test_obligation_alav(self):
        assert _detect_modality("עליו לשלם את ההוצאות תוך 30 יום") == MODALITY_OBLIGATION

    def test_permission_mutar(self):
        assert _detect_modality("מותר להעתיק את המסמך לצורך עיון") == MODALITY_PERMISSION

    def test_possibility_asui(self):
        assert _detect_modality("הנתבע עשוי לטעון שלא קיבל הודעה") == MODALITY_POSSIBLE

    def test_possibility_knarae(self):
        assert _detect_modality("כנראה הסכום שולם באיחור") == MODALITY_POSSIBLE


# ===================================================================
# 8. Claim Enricher — _detect_scope
# ===================================================================

class TestDetectScope:
    def test_scope_all_kol(self):
        assert _detect_scope("כל הצדדים הסכימו לתנאי ההסכם") == "all"

    def test_scope_part_chelek(self):
        assert _detect_scope("חלק מהסכום הושב לתובע") == "part"

    def test_scope_conditional_im(self):
        assert _detect_scope("אם יתקבל הערעור, יבוטל פסק הדין") == "conditional"

    def test_scope_conditional_bitnai(self):
        assert _detect_scope("בתנאי שישולם הסכום תוך 30 יום") == "conditional"

    def test_scope_none_plain_text(self):
        assert _detect_scope("הנתבע שילם את הסכום") is None

    def test_scope_conditional_takes_priority(self):
        # "conditional" is checked first in the code, so it should take priority
        assert _detect_scope("אם כל הצדדים יסכימו") == "conditional"


# ===================================================================
# 9. Claim Enricher — _extract_entities
# ===================================================================

class TestExtractEntities:
    def test_plaintiff_entity(self):
        entities = _extract_entities("התובע הגיש תביעה בסך מיליון שקלים")
        assert "התובע" in entities

    def test_law_reference_entity(self):
        entities = _extract_entities("בהתאם לסעיף 5 לחוק החוזים")
        assert any("סעיף 5" in e for e in entities)

    def test_organization_entity(self):
        entities = _extract_entities("חברת אלפא הפרה את ההסכם עם הנתבע")
        assert any("חברת אלפא" in e for e in entities)

    def test_multiple_party_entities(self):
        entities = _extract_entities("הנתבע והתובע חתמו על ההסכם")
        assert "הנתבע" in entities
        assert "התובע" in entities

    def test_bank_entity(self):
        entities = _extract_entities("בנק לאומי סירב לכבד את השיק")
        assert any("בנק לאומי" in e for e in entities)

    def test_expert_entity(self):
        # The ENTITY_PERSON_ROLE pattern has "המומח" (without final ה) in its
        # alternation group, so the entity extracted is "המומח" not "המומחה".
        entities = _extract_entities("המומחה קבע כי הנזק עומד על מיליון שקלים")
        assert any("מומח" in e for e in entities)

    def test_law_section_with_subsection(self):
        entities = _extract_entities("סעיף 12(א) לחוק קובע חובת גילוי")
        assert any("סעיף 12" in e for e in entities)

    def test_no_entities_in_generic_text(self):
        entities = _extract_entities("הסכום שולם במלואו ובמועד")
        assert len(entities) == 0


# ===================================================================
# 10. Claim Enricher — _detect_negation
# ===================================================================

class TestDetectNegation:
    def test_lo_shilam(self):
        assert _detect_negation("הנתבע לא שילם את החוב") is True

    def test_eino_maskim(self):
        assert _detect_negation("הנתבע אינו מסכים לתנאים") is True

    def test_lelo_haskama(self):
        assert _detect_negation("ההסכם נחתם ללא הסכמת התובע") is True

    def test_positive_assertion(self):
        assert _detect_negation("הנתבע שילם את כל הסכום") is False

    def test_meolam_lo(self):
        assert _detect_negation("הנתבע מעולם לא הגיע לפגישה") is True

    def test_ein_no_subject(self):
        assert _detect_negation("אין ראיות לטענת התובע") is True


# ===================================================================
# 11. Claim Enricher — _normalize_for_comparison
# ===================================================================

class TestNormalizeForComparison:
    def test_strip_and_lowercase(self):
        result = _normalize_for_comparison("  Hello World  ")
        assert result == "hello world"

    def test_punctuation_removed(self):
        result = _normalize_for_comparison("הנתבע שילם, לכאורה, את הסכום.")
        # Punctuation replaced with spaces, then collapsed
        assert "," not in result
        assert "." not in result

    def test_multiple_spaces_collapsed(self):
        result = _normalize_for_comparison("הנתבע    שילם     את    הכל")
        assert "  " not in result
        assert "הנתבע שילם את הכל" == result

    def test_hebrew_text_preserved(self):
        result = _normalize_for_comparison("הנתבע שילם")
        assert "הנתבע" in result
        assert "שילם" in result

    def test_empty_string(self):
        result = _normalize_for_comparison("")
        assert result == ""


# ===================================================================
# 12. Claim Enricher — resolve_entities
# ===================================================================

class TestResolveEntities:
    def test_mashiv_normalized_to_nitba(self):
        claim = _make_claim(entities=["המשיב"])
        result = resolve_entities([claim])
        assert "הנתבע" in result[0].entities

    def test_meareer_normalized_to_toveea(self):
        claim = _make_claim(entities=["המערער"])
        result = resolve_entities([claim])
        assert "התובע" in result[0].entities

    def test_multiple_claims_consistent(self):
        c1 = _make_claim(entities=["המשיב", "חברת אלפא"])
        c2 = _make_claim(entities=["המשיב"])
        results = resolve_entities([c1, c2])
        assert results[0].entities[0] == results[1].entities[0]
        assert results[0].entities[0] == "הנתבע"

    def test_non_alias_unchanged(self):
        claim = _make_claim(entities=["המומחה", "חברת אלפא"])
        result = resolve_entities([claim])
        assert "המומחה" in result[0].entities
        assert "חברת אלפא" in result[0].entities

    def test_deduplication_after_normalization(self):
        # Both "המשיב" and "הנתבע" should deduplicate to single "הנתבע"
        claim = _make_claim(entities=["המשיב", "הנתבע"])
        result = resolve_entities([claim])
        assert result[0].entities.count("הנתבע") == 1


# ===================================================================
# 13. Claim Enricher — _sentence_spans, _context_window, headings
# ===================================================================

class TestSentenceSpansAndContext:
    def test_sentence_spans_splits_on_periods(self):
        text = "משפט ראשון בעברית. משפט שני בעברית. משפט שלישי בעברית."
        spans = _sentence_spans(text)
        assert len(spans) >= 2

    def test_sentence_spans_skips_short(self):
        text = "אב. משפט שני ארוך מספיק להכנס."
        spans = _sentence_spans(text)
        # "אב" is <= 5 chars stripped so should be skipped
        for s, e in spans:
            assert len(text[s:e].strip()) > 5

    def test_context_window_before_and_after(self):
        full = "משפט ראשון לפני. משפט שני לפני. הטענה עצמה כאן. משפט אחרי. משפט אחרון."
        spans = _sentence_spans(full)
        claim_start = full.index("הטענה עצמה כאן")
        claim_end = claim_start + len("הטענה עצמה כאן")
        before, after = _context_window(full, claim_start, claim_end, spans)
        assert before is not None
        assert after is not None

    def test_extract_headings_finds_numbered(self):
        text = "1. כותרת ראשונה\nטקסט רגיל כאן\n2. כותרת שנייה\nטקסט נוסף"
        headings = _extract_headings(text)
        assert len(headings) >= 2

    def test_nearest_heading_returns_closest_before(self):
        headings = [(0, "פרק א"), (100, "פרק ב"), (200, "פרק ג")]
        assert _nearest_heading(headings, 150) == "פרק ב"
        assert _nearest_heading(headings, 50) == "פרק א"
        assert _nearest_heading(headings, 250) == "פרק ג"

    def test_nearest_heading_returns_none_before_first(self):
        headings = [(100, "פרק א")]
        assert _nearest_heading(headings, 50) is None


# ===================================================================
# 14. Claim Enricher — enrich_claims integration
# ===================================================================

class TestEnrichClaimsIntegration:
    def test_enrichment_sets_plane(self):
        claim = _make_claim(text="סעיף 5 לחוק החוזים קובע חובת תום לב")
        result = enrich_claims([claim])
        assert result[0].plane == PLANE_LAW

    def test_enrichment_sets_speaker_mode(self):
        claim = _make_claim(text="התובע טען כי שילם את מלוא הסכום")
        result = enrich_claims([claim])
        assert result[0].speaker_mode == SPEAKER_MODE_PARTY_CLAIM
        assert result[0].speaker_role == "plaintiff"

    def test_enrichment_sets_entities(self):
        claim = _make_claim(text="הנתבע חתם על ההסכם עם חברת אלפא")
        result = enrich_claims([claim])
        assert len(result[0].entities) >= 1
        assert "הנתבע" in result[0].entities

    def test_enrichment_with_full_text_gives_context(self):
        full_text = (
            "זהו פתיח ארוך מספיק כהקדמה לטקסט. "
            "הנתבע שילם 50000 שקלים ביום 15.1.2024. "
            "לאחר מכן הוגשה תביעה נוספת."
        )
        claim = _make_claim(
            text="הנתבע שילם 50000 שקלים ביום 15.1.2024",
            char_start=full_text.index("הנתבע שילם"),
            char_end=full_text.index("הנתבע שילם") + len("הנתבע שילם 50000 שקלים ביום 15.1.2024"),
        )
        result = enrich_claims([claim], full_text=full_text)
        # Context should be populated from surrounding sentences
        assert result[0].context_before is not None or result[0].context_after is not None

    def test_enrichment_sets_confidence(self):
        claim = _make_claim(
            text="הנתבע שילם סך של חמישים אלף שקלים במזומן לתובע",
            doc_id="doc1",
            char_start=0,
            char_end=50,
        )
        result = enrich_claims([claim])
        # Long text + doc_id + char_start → confidence should be 1.0
        assert result[0].confidence_extraction == 1.0

    def test_enrichment_sets_normalized_claim(self):
        claim = _make_claim(text="הנתבע שילם 50,000 ש\"ח.")
        result = enrich_claims([claim])
        assert result[0].normalized_claim is not None
        # Should be lowered, no punctuation
        assert "," not in result[0].normalized_claim
        assert "." not in result[0].normalized_claim

    def test_enrichment_sets_negation(self):
        claim = _make_claim(text="הנתבע לא שילם את הסכום שנדרש ממנו")
        result = enrich_claims([claim])
        assert result[0].negation is True

    def test_enrichment_sets_modality(self):
        claim = _make_claim(text="הנתבע חייב לשלם תוך שלושים יום")
        result = enrich_claims([claim])
        assert result[0].modality == MODALITY_OBLIGATION


# ===================================================================
# 15. Candidate Filter — passes_hard_filters
# ===================================================================

class TestPassesHardFilters:
    def test_fact_fact_shared_entity_passes(self):
        a = _make_claim(
            text="הנתבע שילם 50000 שקלים",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע"],
        )
        b = _make_claim(
            text="הנתבע לא שילם דבר",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע"],
        )
        assert passes_hard_filters(a, b) is True

    def test_fact_fact_no_overlap_fails(self):
        a = _make_claim(
            text="התובע הגיש מסמכים",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["התובע"],
        )
        b = _make_claim(
            text="המומחה בדק את הנכס",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["המומחה"],
        )
        assert passes_hard_filters(a, b) is False

    def test_fact_law_plane_mismatch_fails(self):
        a = _make_claim(
            text="הנתבע שילם 50000 שקלים",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע"],
        )
        b = _make_claim(
            text="סעיף 5 לחוק קובע חובה על הנתבע",
            plane=PLANE_LAW,
            speaker_mode=SPEAKER_MODE_LAW_CITATION,
            entities=["הנתבע"],
        )
        assert passes_hard_filters(a, b) is False

    def test_both_party_claim_fails(self):
        a = _make_claim(
            text="לטענת התובע הוא שילם",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM,
            speaker_role="plaintiff",
            entities=["התובע"],
        )
        b = _make_claim(
            text="לטענת הנתבע, התובע לא שילם",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM,
            speaker_role="defendant",
            entities=["התובע"],
        )
        assert passes_hard_filters(a, b) is False

    def test_missing_speaker_mode_fact_fact_strong_overlap_passes(self):
        """P0 fallback: missing speaker_mode but FACT/FACT with strong overlap."""
        a = _make_claim(
            text="חברת אלפא שילמה 500000 שקלים בהעברה לבנק מזרחי",
            plane=PLANE_FACT,
            speaker_mode=None,
            entities=["חברת אלפא", "בנק מזרחי"],
        )
        b = _make_claim(
            text="חברת אלפא לא שילמה דבר לבנק מזרחי",
            plane=PLANE_FACT,
            speaker_mode=None,
            entities=["חברת אלפא", "בנק מזרחי"],
        )
        assert passes_hard_filters(a, b) is True

    def test_missing_speaker_mode_no_strong_overlap_fails(self):
        a = _make_claim(
            text="הנתבע שילם",
            plane=PLANE_FACT,
            speaker_mode=None,
            entities=["הנתבע"],
        )
        b = _make_claim(
            text="התובע דרש",
            plane=PLANE_FACT,
            speaker_mode=None,
            entities=["התובע"],
        )
        assert passes_hard_filters(a, b) is False

    def test_law_law_shared_entity_passes(self):
        a = _make_claim(
            text="סעיף 5 לחוק החוזים מחייב גילוי מלא",
            plane=PLANE_LAW,
            speaker_mode=SPEAKER_MODE_LAW_CITATION,
            entities=["סעיף 5"],
        )
        b = _make_claim(
            text="סעיף 5 לחוק החוזים אינו מחייב גילוי",
            plane=PLANE_LAW,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["סעיף 5"],
        )
        assert passes_hard_filters(a, b) is True

    def test_opinion_opinion_incompatible(self):
        a = _make_claim(
            text="נראה כי הנתבע צודק",
            plane=PLANE_OPINION,
            speaker_mode=SPEAKER_MODE_OPINION,
            entities=["הנתבע"],
        )
        b = _make_claim(
            text="ייתכן שהנתבע טועה",
            plane=PLANE_OPINION,
            speaker_mode=SPEAKER_MODE_OPINION,
            entities=["הנתבע"],
        )
        assert passes_hard_filters(a, b) is False

    def test_finding_vs_party_claim_passes(self):
        """A court finding vs a single party claim should pass filters."""
        a = _make_claim(
            text="בית המשפט קובע כי הנתבע שילם",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע"],
        )
        b = _make_claim(
            text="לטענת התובע, הנתבע לא שילם",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM,
            entities=["הנתבע"],
        )
        assert passes_hard_filters(a, b) is True

    def test_missing_plane_fails(self):
        a = _make_claim(
            text="הנתבע שילם",
            plane=None,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע"],
        )
        b = _make_claim(
            text="הנתבע לא שילם",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע"],
        )
        assert passes_hard_filters(a, b) is False

    def test_same_party_claim_both_plaintiff_fails(self):
        """Two party claims from the same side are also filtered."""
        a = _make_claim(
            text="לטענת התובע, שילם הכל",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM,
            speaker_role="plaintiff",
            entities=["התובע"],
        )
        b = _make_claim(
            text="התובע טען כי הכסף הועבר",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_PARTY_CLAIM,
            speaker_role="plaintiff",
            entities=["התובע"],
        )
        assert passes_hard_filters(a, b) is False

    def test_quote_vs_finding_passes(self):
        a = _make_claim(
            text='הנתבע אמר "שילמתי הכל"',
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_QUOTE,
            entities=["הנתבע"],
        )
        b = _make_claim(
            text="בית המשפט מצא כי הנתבע לא שילם",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע"],
        )
        assert passes_hard_filters(a, b) is True


# ===================================================================
# 16. Candidate Filter — _entity_overlap
# ===================================================================

class TestEntityOverlap:
    def test_shared_entity_true(self):
        a = _make_claim(entities=["הנתבע", "חברת אלפא"])
        b = _make_claim(entities=["הנתבע"])
        assert _entity_overlap(a, b) is True

    def test_no_shared_entity_false(self):
        a = _make_claim(entities=["התובע"])
        b = _make_claim(entities=["הנתבע"])
        assert _entity_overlap(a, b) is False

    def test_empty_entities_falls_back_to_word_overlap_similar(self):
        a = _make_claim(text="הנתבע שילם חמישים אלף שקלים", entities=[])
        b = _make_claim(text="הנתבע שילם חמישים אלף שקלים למרות שטען אחרת", entities=[])
        # Similar text → word overlap should be >= 0.15
        assert _entity_overlap(a, b) is True

    def test_empty_entities_falls_back_to_word_overlap_different(self):
        a = _make_claim(text="הנתבע שילם את הסכום", entities=[])
        b = _make_claim(text="המכונית נסעה למפעל ייצור בגליל", entities=[])
        result = _entity_overlap(a, b)
        # Very different texts — word overlap should be low
        assert result is False

    def test_one_empty_one_populated_fallback(self):
        a = _make_claim(text="הנתבע שילם חמישים אלף שקלים לחברה", entities=[])
        b = _make_claim(text="הנתבע שילם חמישים אלף שקלים לתובע", entities=["הנתבע"])
        # a has no entities → falls back to word overlap
        result = _entity_overlap(a, b)
        assert result is True


# ===================================================================
# 17. Candidate Filter — _plane_compatible
# ===================================================================

class TestPlaneCompatible:
    def test_fact_fact_compatible(self):
        a = _make_claim(plane=PLANE_FACT)
        b = _make_claim(plane=PLANE_FACT)
        assert _plane_compatible(a, b) is True

    def test_law_law_compatible(self):
        a = _make_claim(plane=PLANE_LAW)
        b = _make_claim(plane=PLANE_LAW)
        assert _plane_compatible(a, b) is True

    def test_fact_law_incompatible(self):
        a = _make_claim(plane=PLANE_FACT)
        b = _make_claim(plane=PLANE_LAW)
        assert _plane_compatible(a, b) is False

    def test_missing_plane_incompatible(self):
        a = _make_claim(plane=None)
        b = _make_claim(plane=PLANE_FACT)
        assert _plane_compatible(a, b) is False

    def test_opinion_opinion_incompatible(self):
        a = _make_claim(plane=PLANE_OPINION)
        b = _make_claim(plane=PLANE_OPINION)
        assert _plane_compatible(a, b) is False

    def test_procedural_procedural_incompatible(self):
        a = _make_claim(plane=PLANE_PROCEDURAL)
        b = _make_claim(plane=PLANE_PROCEDURAL)
        assert _plane_compatible(a, b) is False


# ===================================================================
# 18. Candidate Filter — _word_overlap
# ===================================================================

class TestWordOverlap:
    def test_similar_hebrew_texts_high_overlap(self):
        t1 = "הנתבע שילם חמישים אלף שקלים לתובע בהעברה בנקאית"
        t2 = "הנתבע שילם חמישים אלף שקלים ישירות לתובע"
        overlap = _word_overlap(t1, t2)
        assert overlap >= 0.5

    def test_different_texts_low_overlap(self):
        t1 = "הנתבע שילם את הסכום"
        t2 = "המכונית נסעה בכביש ראשי לעבר צפון הארץ"
        overlap = _word_overlap(t1, t2)
        assert overlap < 0.15

    def test_empty_texts_returns_half(self):
        # Both empty → no words extracted → returns 0.5
        assert _word_overlap("", "") == 0.5

    def test_identical_texts_full_overlap(self):
        t = "חברת אלפא שילמה למשיבים פיצויים בסכום ניכר"
        overlap = _word_overlap(t, t)
        assert overlap == 1.0


# ===================================================================
# 19. Candidate Filter — cluster_claims
# ===================================================================

class TestClusterClaims:
    def test_same_entity_same_cluster(self):
        c1 = _make_claim(text="הנתבע שילם", entities=["הנתבע"])
        c2 = _make_claim(text="הנתבע לא שילם", entities=["הנתבע"])
        clusters = cluster_claims([c1, c2])
        assert "entity:הנתבע" in clusters
        assert len(clusters["entity:הנתבע"]) == 2

    def test_different_entities_different_clusters(self):
        c1 = _make_claim(text="התובע הגיש", entities=["התובע"])
        c2 = _make_claim(text="המומחה קבע", entities=["המומחה"])
        clusters = cluster_claims([c1, c2])
        assert "entity:התובע" in clusters
        assert "entity:המומחה" in clusters
        assert c1 not in clusters.get("entity:המומחה", [])

    def test_no_entities_goes_to_unclustered(self):
        c1 = _make_claim(text="הסכום שולם", entities=[])
        clusters = cluster_claims([c1])
        assert "_unclustered" in clusters
        assert c1 in clusters["_unclustered"]

    def test_law_claim_gets_law_prefix_cluster(self):
        c1 = _make_claim(
            text="סעיף 5 לחוק קובע חובה",
            plane=PLANE_LAW,
            entities=["סעיף 5"],
        )
        clusters = cluster_claims([c1])
        assert "law:סעיף 5" in clusters

    def test_claim_in_multiple_clusters(self):
        c1 = _make_claim(
            text="הנתבע הפר את סעיף 5",
            plane=PLANE_LAW,
            entities=["הנתבע", "סעיף 5"],
        )
        clusters = cluster_claims([c1])
        assert "entity:הנתבע" in clusters
        assert "entity:סעיף 5" in clusters
        assert "law:סעיף 5" in clusters


# ===================================================================
# 20. Candidate Filter — generate_candidate_pairs
# ===================================================================

class TestGenerateCandidatePairs:
    def test_passing_pair_generates_candidate(self):
        a = _make_claim(
            id="c1",
            text="הנתבע שילם 50000 שקלים",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע"],
        )
        b = _make_claim(
            id="c2",
            text="הנתבע לא שילם כלום",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע"],
        )
        pairs = generate_candidate_pairs([a, b])
        assert len(pairs) >= 1
        ids_in_pairs = {(p[0].id, p[1].id) for p in pairs}
        assert ("c1", "c2") in ids_in_pairs or ("c2", "c1") in ids_in_pairs

    def test_failing_pair_no_candidate(self):
        a = _make_claim(
            id="c1",
            text="הנתבע שילם",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע"],
        )
        b = _make_claim(
            id="c2",
            text="סעיף 5 קובע",
            plane=PLANE_LAW,
            speaker_mode=SPEAKER_MODE_LAW_CITATION,
            entities=["סעיף 5"],
        )
        pairs = generate_candidate_pairs([a, b])
        assert len(pairs) == 0

    def test_returns_list_of_tuples(self):
        a = _make_claim(
            id="c1",
            text="הנתבע שילם",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע"],
        )
        b = _make_claim(
            id="c2",
            text="הנתבע חתם",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע"],
        )
        pairs = generate_candidate_pairs([a, b])
        assert isinstance(pairs, list)
        if pairs:
            assert isinstance(pairs[0], tuple)
            assert len(pairs[0]) == 2

    def test_no_duplicate_pairs(self):
        """Even if claims share multiple clusters, pairs should not duplicate."""
        a = _make_claim(
            id="c1",
            text="הנתבע הפר סעיף 5",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע", "סעיף 5"],
        )
        b = _make_claim(
            id="c2",
            text="הנתבע קיים סעיף 5",
            plane=PLANE_FACT,
            speaker_mode=SPEAKER_MODE_FINDING,
            entities=["הנתבע", "סעיף 5"],
        )
        pairs = generate_candidate_pairs([a, b])
        pair_keys = [(p[0].id, p[1].id) for p in pairs]
        assert len(pair_keys) == len(set(pair_keys))


# ===================================================================
# 21. Candidate Filter — _strong_subject_overlap
# ===================================================================

class TestStrongSubjectOverlap:
    def test_shared_unique_id_overlap(self):
        a = _make_claim(text="תיק 12345-01-22 נדון בבית המשפט", entities=[])
        b = _make_claim(text="בתיק 12345-01-22 ניתן פסק דין", entities=[])
        assert _strong_subject_overlap(a, b) is True

    def test_shared_strong_entities(self):
        a = _make_claim(entities=["חברת אלפא", "בנק מזרחי"])
        b = _make_claim(entities=["חברת אלפא", "בנק מזרחי"])
        assert _strong_subject_overlap(a, b) is True

    def test_only_weak_entities_no_overlap(self):
        a = _make_claim(entities=["התובע"])
        b = _make_claim(entities=["הנתבע"])
        assert _strong_subject_overlap(a, b) is False

    def test_no_entities_no_overlap(self):
        a = _make_claim(text="שילם כסף", entities=[])
        b = _make_claim(text="דרש פיצוי", entities=[])
        assert _strong_subject_overlap(a, b) is False
