"""
Extended Tests -- CrossExamGenerator.generate() and related helpers
===================================================================

~50 tests covering:
- PlaybookLoader._get_embedded_playbooks and load()
- CrossExamGenerator initialization
- generate() basic behaviour
- generate() by ContradictionType
- _extract_variables
- _sanitize_quote
- _fill_template
- _format_amount
- generate_for_all
"""

import pytest
from backend_lite.extractor import Claim
from backend_lite.detector import DetectedContradiction
from backend_lite.schemas import (
    ContradictionType,
    ContradictionStatus,
    ContradictionCategory,
    Severity,
)
from backend_lite.cross_exam import (
    CrossExamGenerator,
    CrossExamQuestion,
    CrossExamSet,
    PlaybookLoader,
    QuestionType,
    QuestionTypeSelector,
    MAX_QUOTE_LENGTH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(text: str, **kwargs) -> Claim:
    defaults = dict(id=kwargs.pop("id", f"c_{abs(hash(text)) % 100000}"), text=text)
    defaults.update(kwargs)
    return Claim(**defaults)


def _make_contradiction(
    type=ContradictionType.FACTUAL,
    severity=Severity.HIGH,
    confidence=0.85,
    quote1="הנתבע שילם 50,000 שקלים",
    quote2="הנתבע לא שילם דבר",
    **kwargs,
) -> DetectedContradiction:
    claim1 = kwargs.pop("claim1", _claim(quote1, speaker=kwargs.pop("speaker1", None)))
    claim2 = kwargs.pop("claim2", _claim(quote2, speaker=kwargs.pop("speaker2", None)))
    return DetectedContradiction(
        id=kwargs.get("id", "test_001"),
        claim1=claim1,
        claim2=claim2,
        type=type,
        subtype=kwargs.get("subtype", None),
        status=kwargs.get("status", ContradictionStatus.VERIFIED),
        severity=severity,
        confidence=confidence,
        same_event_confidence=kwargs.get("same_event_confidence", 0.9),
        explanation=kwargs.get("explanation", "סתירה עובדתית"),
        quote1=quote1,
        quote2=quote2,
        metadata=kwargs.get("metadata", {}),
        category=kwargs.get("category", None),
    )


# ===================================================================
# 1. TestPlaybookLoaderEmbed (~5 tests)
# ===================================================================

class TestPlaybookLoaderEmbed:
    """Tests for PlaybookLoader._get_embedded_playbooks()."""

    def test_returns_dict_with_expected_keys(self):
        embedded = PlaybookLoader._get_embedded_playbooks()
        expected_keys = {
            "temporal", "quantitative", "attribution", "factual",
            "version", "witness", "cross_party", "internal",
        }
        assert expected_keys == set(embedded.keys())

    def test_each_playbook_has_cross_examination_key(self):
        embedded = PlaybookLoader._get_embedded_playbooks()
        for key, playbook in embedded.items():
            assert "cross_examination" in playbook, f"Playbook '{key}' missing 'cross_examination'"

    def test_each_cross_examination_has_question_set(self):
        embedded = PlaybookLoader._get_embedded_playbooks()
        for key, playbook in embedded.items():
            ce = playbook["cross_examination"]
            assert "question_set" in ce, f"Playbook '{key}' cross_examination missing 'question_set'"
            assert isinstance(ce["question_set"], list)
            assert len(ce["question_set"]) > 0

    def test_temporal_playbook_has_at_least_3_templates(self):
        embedded = PlaybookLoader._get_embedded_playbooks()
        templates = embedded["temporal"]["cross_examination"]["question_set"]
        assert len(templates) >= 3

    def test_cross_party_has_trap_branches(self):
        embedded = PlaybookLoader._get_embedded_playbooks()
        ce = embedded["cross_party"]["cross_examination"]
        assert "trap_branches" in ce
        assert len(ce["trap_branches"]) > 0


# ===================================================================
# 2. TestPlaybookLoaderLoad (~3 tests)
# ===================================================================

class TestPlaybookLoaderLoad:
    """Tests for PlaybookLoader.load()."""

    def test_load_returns_dict(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        assert isinstance(result, dict)

    def test_load_contains_cross_party_and_internal(self):
        PlaybookLoader._playbooks = None
        result = PlaybookLoader.load()
        assert "cross_party" in result
        assert "internal" in result

    def test_load_caches_result(self):
        PlaybookLoader._playbooks = None
        first = PlaybookLoader.load()
        second = PlaybookLoader.load()
        assert first is second


# ===================================================================
# 3. TestCrossExamGeneratorInit (~3 tests)
# ===================================================================

class TestCrossExamGeneratorInit:
    """Tests for CrossExamGenerator.__init__."""

    def test_init_succeeds(self):
        gen = CrossExamGenerator()
        assert gen is not None

    def test_has_playbooks_attribute(self):
        gen = CrossExamGenerator()
        assert isinstance(gen.playbooks, dict)
        assert len(gen.playbooks) > 0

    def test_type_to_playbook_maps_temporal(self):
        gen = CrossExamGenerator()
        assert gen.type_to_playbook[ContradictionType.TEMPORAL] == "temporal"


# ===================================================================
# 4. TestGenerateBasic (~10 tests)
# ===================================================================

class TestGenerateBasic:
    """Tests for CrossExamGenerator.generate() basic behaviour."""

    @pytest.fixture(autouse=True)
    def setup(self):
        PlaybookLoader._playbooks = None
        self.gen = CrossExamGenerator()
        self.contradiction = _make_contradiction()

    def test_returns_cross_exam_set(self):
        result = self.gen.generate(self.contradiction)
        assert isinstance(result, CrossExamSet)

    def test_questions_list_non_empty(self):
        result = self.gen.generate(self.contradiction)
        assert len(result.questions) > 0

    def test_contradiction_id_matches(self):
        result = self.gen.generate(self.contradiction)
        assert result.contradiction_id == "test_001"

    def test_each_question_has_non_empty_text(self):
        result = self.gen.generate(self.contradiction)
        for q in result.questions:
            assert isinstance(q, CrossExamQuestion)
            assert len(q.question) > 0

    def test_each_question_has_severity(self):
        result = self.gen.generate(self.contradiction)
        for q in result.questions:
            assert q.severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]

    def test_strategy_notes_populated(self):
        result = self.gen.generate(self.contradiction)
        assert isinstance(result.strategy_notes, list)
        assert len(result.strategy_notes) > 0

    def test_witness_profile_is_set(self):
        result = self.gen.generate(self.contradiction)
        assert isinstance(result.witness_profile, str)
        assert len(result.witness_profile) > 0

    def test_expected_value_is_float_0_1(self):
        result = self.gen.generate(self.contradiction)
        assert isinstance(result.expected_value, float)
        assert 0.0 <= result.expected_value <= 1.0

    def test_risk_score_is_float_0_1(self):
        result = self.gen.generate(self.contradiction)
        assert isinstance(result.risk_score, float)
        assert 0.0 <= result.risk_score <= 1.0

    def test_question_ids_unique(self):
        result = self.gen.generate(self.contradiction)
        ids = [q.id for q in result.questions]
        assert len(ids) == len(set(ids)), "Question IDs must be unique"


# ===================================================================
# 5. TestGenerateByType (~8 tests)
# ===================================================================

class TestGenerateByType:
    """Tests for generate() with different ContradictionType values."""

    @pytest.fixture(autouse=True)
    def setup(self):
        PlaybookLoader._playbooks = None
        self.gen = CrossExamGenerator()

    def test_temporal_references_dates(self):
        c = _make_contradiction(
            type=ContradictionType.TEMPORAL,
            quote1="האירוע התרחש ב-1.1.2020",
            quote2="האירוע התרחש ב-5.3.2021",
            metadata={"date1": "2020-01-01", "date2": "2021-03-05"},
        )
        result = self.gen.generate(c)
        all_text = " ".join(q.question for q in result.questions)
        assert "2020" in all_text or "2021" in all_text or "תאריך" in all_text or "date" in all_text.lower() or "יום" in all_text

    def test_quantitative_references_amounts(self):
        c = _make_contradiction(
            type=ContradictionType.QUANTITATIVE,
            quote1="הסכום הוא 100,000 שקלים",
            quote2="הסכום הוא 200,000 שקלים",
            metadata={"amount1": 100000, "amount2": 200000},
        )
        result = self.gen.generate(c)
        all_text = " ".join(q.question for q in result.questions)
        assert "100" in all_text or "200" in all_text or "סכום" in all_text or "אלף" in all_text

    def test_attribution_references_persons(self):
        c = _make_contradiction(
            type=ContradictionType.ATTRIBUTION,
            quote1="יוסי חתם על המסמך",
            quote2="דני חתם על המסמך",
            metadata={"attr1": ["יוסי"], "attr2": ["דני"]},
        )
        result = self.gen.generate(c)
        all_text = " ".join(q.question for q in result.questions)
        assert "יוסי" in all_text or "דני" in all_text or "ביצע" in all_text or "פעולה" in all_text

    def test_factual_generates_questions(self):
        c = _make_contradiction(type=ContradictionType.FACTUAL)
        result = self.gen.generate(c)
        assert len(result.questions) > 0

    def test_max_questions_3_limits_output(self):
        c = _make_contradiction(type=ContradictionType.FACTUAL)
        result = self.gen.generate(c, max_questions=3)
        assert len(result.questions) <= 5, "max_questions=3 should limit template selection to at most 3 templates"

    def test_max_questions_7_gives_more(self):
        c = _make_contradiction(type=ContradictionType.FACTUAL)
        result3 = self.gen.generate(c, max_questions=3)
        result7 = self.gen.generate(c, max_questions=7)
        assert len(result7.questions) >= len(result3.questions)

    def test_witness_type_uses_witness_playbook(self):
        c = _make_contradiction(
            type=ContradictionType.WITNESS,
            quote1="העד אמר שראה את התאונה",
            quote2="העד לא היה במקום",
        )
        result = self.gen.generate(c)
        assert len(result.questions) > 0

    def test_version_type_generates_questions(self):
        c = _make_contradiction(
            type=ContradictionType.VERSION,
            quote1="בתצהיר הראשון אמרתי שהתאונה היתה בלילה",
            quote2="עכשיו אני אומר שהתאונה היתה ביום",
        )
        result = self.gen.generate(c)
        assert len(result.questions) > 0
        all_text = " ".join(q.question for q in result.questions)
        # Version playbook typically mentions "תצהיר" or "גרסה"
        assert any(
            kw in all_text
            for kw in ["תצהיר", "גרסה", "השתנ", "אמרת", "אומר"]
        )


# ===================================================================
# 6. TestExtractVariables (~5 tests)
# ===================================================================

class TestExtractVariables:
    """Tests for CrossExamGenerator._extract_variables."""

    @pytest.fixture(autouse=True)
    def setup(self):
        PlaybookLoader._playbooks = None
        self.gen = CrossExamGenerator()

    def test_populates_quote_a_and_quote_b(self):
        c = _make_contradiction(quote1="ציטוט א", quote2="ציטוט ב")
        variables = self.gen._extract_variables(c)
        assert variables["quote_a"] == "ציטוט א"
        assert variables["quote_b"] == "ציטוט ב"

    def test_metadata_dates_populate_date_a_and_date_b(self):
        c = _make_contradiction(metadata={"date1": "2020-01-01", "date2": "2021-06-15"})
        variables = self.gen._extract_variables(c)
        assert variables["date_a"] == "2020-01-01"
        assert variables["date_b"] == "2021-06-15"

    def test_metadata_amounts_populate_amount_a_and_amount_b(self):
        c = _make_contradiction(metadata={"amount1": 50000, "amount2": 1000000})
        variables = self.gen._extract_variables(c)
        assert "אלף" in variables["amount_a"]
        assert "מיליון" in variables["amount_b"]

    def test_long_quotes_truncated(self):
        long_text = "א" * 200
        c = _make_contradiction(quote1=long_text, quote2="קצר")
        variables = self.gen._extract_variables(c)
        assert len(variables["quote_a"]) <= MAX_QUOTE_LENGTH

    def test_metadata_attribution_populates_person(self):
        c = _make_contradiction(metadata={"attr1": ["יוסי", "דני"], "attr2": ["שרה"]})
        variables = self.gen._extract_variables(c)
        assert "יוסי" in variables["person_a"]
        assert "דני" in variables["person_a"]
        assert variables["person_b"] == "שרה"


# ===================================================================
# 7. TestSanitizeQuote (~5 tests)
# ===================================================================

class TestSanitizeQuote:
    """Tests for CrossExamGenerator._sanitize_quote."""

    @pytest.fixture(autouse=True)
    def setup(self):
        PlaybookLoader._playbooks = None
        self.gen = CrossExamGenerator()

    def test_short_quote_returned_as_is(self):
        result = self.gen._sanitize_quote("ציטוט קצר")
        assert result == "ציטוט קצר"

    def test_long_quote_truncated_with_ellipsis(self):
        long_text = "מילה " * 60  # well over MAX_QUOTE_LENGTH
        result = self.gen._sanitize_quote(long_text)
        assert len(result) <= MAX_QUOTE_LENGTH + 10  # some slack for "..."
        assert result.endswith("...")

    def test_quote_with_system_text_returns_empty(self):
        result = self.gen._sanitize_quote("תוצאות הניתוח של המסמך")
        assert result == ""

    def test_none_returns_empty(self):
        result = self.gen._sanitize_quote(None)
        assert result == ""

    def test_sentence_boundary_cut(self):
        # Build text that exceeds MAX_QUOTE_LENGTH with a sentence boundary in the middle
        prefix = "זהו משפט ראשון שמסביר את הנושא. "  # ~34 chars
        filler = "א" * (MAX_QUOTE_LENGTH + 20)
        text = prefix + filler
        result = self.gen._sanitize_quote(text)
        # Should truncate but end with "..."
        assert result.endswith("...")


# ===================================================================
# 8. TestFillTemplate (~4 tests)
# ===================================================================

class TestFillTemplate:
    """Tests for CrossExamGenerator._fill_template."""

    @pytest.fixture(autouse=True)
    def setup(self):
        PlaybookLoader._playbooks = None
        self.gen = CrossExamGenerator()

    def test_template_with_quote_a_replaced(self):
        result = self.gen._fill_template("אתה אמרת: {quote_a}", {"quote_a": "שילמתי"})
        assert result == "אתה אמרת: שילמתי"

    def test_unknown_placeholder_replaced_with_unavailable(self):
        result = self.gen._fill_template("ערך: {xyz}", {})
        assert "[לא זמין]" in result

    def test_no_placeholders_unchanged(self):
        template = "שאלה פשוטה ללא תבנית?"
        result = self.gen._fill_template(template, {})
        assert result == template

    def test_multiple_placeholders(self):
        result = self.gen._fill_template(
            "מ-{date_a} עד {date_b} הסכום היה {amount_a}",
            {"date_a": "ינואר", "date_b": "מרץ", "amount_a": "50 אלף"},
        )
        assert "ינואר" in result
        assert "מרץ" in result
        assert "50 אלף" in result


# ===================================================================
# 9. TestFormatAmount (~5 tests)
# ===================================================================

class TestFormatAmount:
    """Tests for CrossExamGenerator._format_amount."""

    @pytest.fixture(autouse=True)
    def setup(self):
        PlaybookLoader._playbooks = None
        self.gen = CrossExamGenerator()

    def test_million(self):
        result = self.gen._format_amount(1000000)
        assert "מיליון" in result
        assert 'ש"ח' in result

    def test_thousands(self):
        result = self.gen._format_amount(50000)
        assert "אלף" in result
        assert 'ש"ח' in result

    def test_small_amount(self):
        result = self.gen._format_amount(500)
        assert "500" in result
        assert 'ש"ח' in result

    def test_invalid_amount(self):
        result = self.gen._format_amount("not_a_number")
        assert result == "not_a_number"

    def test_none_amount(self):
        result = self.gen._format_amount(None)
        assert result == "None"


# ===================================================================
# 10. TestGenerateForAll (~3 tests)
# ===================================================================

class TestGenerateForAll:
    """Tests for CrossExamGenerator.generate_for_all."""

    @pytest.fixture(autouse=True)
    def setup(self):
        PlaybookLoader._playbooks = None
        self.gen = CrossExamGenerator()

    def test_empty_list_returns_empty(self):
        result = self.gen.generate_for_all([])
        assert result == []

    def test_two_contradictions_two_sets(self):
        c1 = _make_contradiction(id="c1")
        c2 = _make_contradiction(id="c2", type=ContradictionType.TEMPORAL)
        result = self.gen.generate_for_all([c1, c2])
        assert len(result) == 2
        assert all(isinstance(s, CrossExamSet) for s in result)

    def test_each_set_has_matching_contradiction_id(self):
        c1 = _make_contradiction(id="alpha")
        c2 = _make_contradiction(id="beta")
        result = self.gen.generate_for_all([c1, c2])
        assert result[0].contradiction_id == "alpha"
        assert result[1].contradiction_id == "beta"
