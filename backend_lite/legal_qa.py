"""
Legal QA Engine — Extractive Question Answering for Hebrew Legal Text
=====================================================================

Uses HeBERT fine-tuned on Israeli Supreme Court verdicts for extractive QA:
- Extract specific facts from legal text (who, what, when, how much)
- Identify speakers, parties, and roles
- Pull structured data from unstructured legal prose

Model: shay681/HeBERT_finetuned_Legal_Clauses (96% F1 on legal clause QA)
Fallback: Regex-based extraction when model unavailable

Usage:
    from legal_qa import get_legal_qa, extract_facts

    qa = get_legal_qa()
    answer = qa.answer("מי הנתבע?", context_text)
    facts = qa.extract_legal_facts(claim_text)
"""

import re
import os
import logging
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# =============================================================================
# Model Availability Detection
# =============================================================================

_QA_MODEL_AVAILABLE = False
_qa_pipeline = None

# Allow disabling the QA model entirely for low-memory environments (e.g. Railway 512MB)
# Set DISABLE_QA_MODEL=1 to force regex-only mode and save ~500MB RAM.
_QA_MODEL_DISABLED = os.environ.get("DISABLE_QA_MODEL", "").strip() in ("1", "true", "yes")

if not _QA_MODEL_DISABLED:
    try:
        from transformers import pipeline as hf_pipeline
        import torch
        _QA_MODEL_AVAILABLE = True
    except ImportError:
        pass

# Model identifier — can be overridden via environment variable
LEGAL_QA_MODEL = os.environ.get(
    "LEGAL_QA_MODEL",
    "shay681/HeBERT_finetuned_Legal_Clauses"
)

# Minimum confidence for QA answers
QA_MIN_CONFIDENCE = float(os.environ.get("QA_MIN_CONFIDENCE", "0.15"))


# =============================================================================
# Data structures
# =============================================================================

@dataclass
class QAAnswer:
    """Result from a single QA query."""
    answer: str                   # Extracted answer text
    confidence: float             # Model confidence (0-1)
    start: int = 0                # Start char position in context
    end: int = 0                  # End char position in context
    method: str = "model"         # "model" or "regex"


@dataclass
class LegalFacts:
    """Structured facts extracted from a legal claim."""
    speaker: Optional[str] = None           # Who is making the claim
    speaker_role: Optional[str] = None      # Role: court/plaintiff/defendant/witness
    action: Optional[str] = None            # What happened (predicate)
    subject: Optional[str] = None           # Who did it
    object: Optional[str] = None            # To whom / what
    amount: Optional[str] = None            # Financial amount mentioned
    date: Optional[str] = None              # Date or time reference
    location: Optional[str] = None          # Place mentioned
    plane: Optional[str] = None             # FACT/LAW/OPINION/PROCEDURAL
    modality: Optional[str] = None          # certain/possible/obligation
    negation: bool = False                  # Is the claim negated
    confidence: float = 0.0                 # Overall extraction confidence
    raw_answers: Dict[str, QAAnswer] = field(default_factory=dict)


# =============================================================================
# Regex Fallback Patterns (Hebrew Legal Text)
# =============================================================================

# Speaker patterns: "לטענת X", "X טען כי", "X הצהיר/ה", "בעדותו של X"
_SPEAKER_PATTERNS = [
    re.compile(r'לטענת\s+([\u0590-\u05FF\s]{2,30}?)(?:[,.]|\s+כי)', re.UNICODE),
    re.compile(r'([\u0590-\u05FF]+(?:\s+[\u0590-\u05FF]+)?)\s+טען(?:ה)?\s+כי', re.UNICODE),
    re.compile(r'([\u0590-\u05FF]+(?:\s+[\u0590-\u05FF]+)?)\s+הצהיר(?:ה)?\s+כי', re.UNICODE),
    re.compile(r'([\u0590-\u05FF]+(?:\s+[\u0590-\u05FF]+)?)\s+העיד(?:ה)?\s+כי', re.UNICODE),
    re.compile(r'בעדות(?:ו|ה)\s+של\s+([\u0590-\u05FF\s]{2,30}?)\s', re.UNICODE),
    re.compile(r'(הנתבע(?:ת)?|התובע(?:ת)?|המשיב(?:ה)?|המערער(?:ת)?|העד(?:ה)?)\s+(?:טען|הצהיר|העיד|ציין)', re.UNICODE),
]

# Role patterns
_ROLE_INDICATORS = {
    'court': re.compile(r'(?:בית\s*ה?משפט|השופט(?:ת)?|קבע\s+כי|נקבע\s+כי|פסק\s+כי)', re.UNICODE),
    'plaintiff': re.compile(r'(?:התובע(?:ת)?|העותר(?:ת)?|המבקש(?:ת)?)', re.UNICODE),
    'defendant': re.compile(r'(?:הנתבע(?:ת)?|המשיב(?:ה)?|המערער(?:ת)?)', re.UNICODE),
    'witness': re.compile(r'(?:העד(?:ה)?|המומח(?:ית)?|המצהיר(?:ה)?)', re.UNICODE),
    'counsel': re.compile(r'(?:עו"ד|ב"כ|פרקליט(?:ה)?)', re.UNICODE),
}

# Amount patterns: NNN,NNN ש"ח / NNN ₪
_AMOUNT_PATTERN = re.compile(
    r'([\d,]+(?:\.\d+)?)\s*(?:ש"ח|₪|שקל(?:ים)?|אלף|מיליון)',
    re.UNICODE
)

# Date patterns
_DATE_PATTERN = re.compile(
    r'(\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}\s+ב?[א-ת]+\s+\d{4})',
    re.UNICODE
)

# Negation markers
_NEGATION_PATTERN = re.compile(
    r'(?:^|\s)(?:לא|אין|אינ(?:ו|ה|ם|ן)|מעולם\s+לא|אי[\s\-]|בלתי|ללא|טרם|לפני\s+ש)',
    re.UNICODE
)

# Plane indicators
_PLANE_INDICATORS = {
    'LAW': re.compile(r'(?:סעיף|חוק|תקנ(?:ה|ות)|פקוד(?:ה|ת)|צו|הוראת|דין|הלכ(?:ה|ת))', re.UNICODE),
    'OPINION': re.compile(r'(?:לדעת(?:י|נו)?|סבור(?:ה)?|נראה\s+(?:לי|כי)|ייתכן|אפשר\s+כי|דומה\s+כי)', re.UNICODE),
    'PROCEDURAL': re.compile(r'(?:הוגש(?:ה)?|נקבע\s+דיון|מועד|ישיבה|הוחלט|נדחה|התקבל(?:ה)?)', re.UNICODE),
    'FACT': re.compile(r'(?:בתאריך|ביום|בפועל|למעשה|בפגישה|נחתם|שולם|הועבר|נמסר)', re.UNICODE),
}

# Modality indicators
_MODALITY_INDICATORS = {
    'certain': re.compile(r'(?:בוודאות|בהחלט|ללא\s+ספק|ברור\s+כי|הוכח\s+כי)', re.UNICODE),
    'possible': re.compile(r'(?:ייתכן|אפשר|עשוי|עלול|סביר\s+כי)', re.UNICODE),
    'obligation': re.compile(r'(?:חייב|חובה|נדרש|מחויב|עליו)', re.UNICODE),
    'permission': re.compile(r'(?:רשאי|מותר|ניתן\s+ל|הותר)', re.UNICODE),
}

# Structured QA questions for fact extraction (Hebrew)
_LEGAL_QA_QUESTIONS = {
    'speaker': "מי טוען או מצהיר?",
    'subject': "מי ביצע את הפעולה?",
    'action': "מה נעשה או מה קרה?",
    'object': "על מי או על מה מדובר?",
    'amount': "מה הסכום?",
    'date': "מתי זה קרה?",
    'location': "היכן זה קרה?",
}


# =============================================================================
# Legal QA Engine
# =============================================================================

class LegalQA:
    """
    Extractive QA engine for Hebrew legal text.

    Primary: HeBERT fine-tuned on Supreme Court verdicts (when available)
    Fallback: Regex-based pattern matching (always available)
    """

    def __init__(self, force_regex: bool = False):
        self._use_model = _QA_MODEL_AVAILABLE and not force_regex
        self._model_loaded = False
        self._model_load_failed = False

    def _ensure_model(self) -> bool:
        """Lazy-load the QA model on first use."""
        global _qa_pipeline

        if not self._use_model or self._model_load_failed:
            return False

        if _qa_pipeline is not None:
            return True

        try:
            logger.info("Loading Legal QA model: %s", LEGAL_QA_MODEL)
            device = 0 if torch.cuda.is_available() else -1
            _qa_pipeline = hf_pipeline(
                "question-answering",
                model=LEGAL_QA_MODEL,
                tokenizer=LEGAL_QA_MODEL,
                device=device,
            )
            self._model_loaded = True
            logger.info("Legal QA model loaded successfully (device=%s)", "GPU" if device == 0 else "CPU")
            return True
        except Exception as e:
            logger.warning("Failed to load Legal QA model: %s — falling back to regex", e)
            self._model_load_failed = True
            self._use_model = False
            return False

    @property
    def strategy(self) -> str:
        """Return current strategy name."""
        if self._use_model and (self._model_loaded or not self._model_load_failed):
            return "HeBERT-QA"
        return "regex"

    def answer(self, question: str, context: str, min_confidence: float = None) -> Optional[QAAnswer]:
        """
        Answer a question given a context passage.

        Args:
            question: Question in Hebrew
            context: Legal text passage to search in
            min_confidence: Minimum confidence threshold (default: QA_MIN_CONFIDENCE)

        Returns:
            QAAnswer or None if no confident answer found
        """
        if not context or not question:
            return None

        if min_confidence is None:
            min_confidence = QA_MIN_CONFIDENCE

        # Try model first
        if self._ensure_model() and _qa_pipeline is not None:
            try:
                result = _qa_pipeline(
                    question=question,
                    context=context[:2048],  # Limit context length for BERT
                )
                if result and result.get('score', 0) >= min_confidence:
                    return QAAnswer(
                        answer=result['answer'].strip(),
                        confidence=result['score'],
                        start=result.get('start', 0),
                        end=result.get('end', 0),
                        method="model",
                    )
            except Exception as e:
                logger.debug("QA model inference failed: %s", e)

        return None

    def answer_batch(
        self, questions: List[Dict[str, str]], min_confidence: float = None
    ) -> Dict[str, Optional[QAAnswer]]:
        """
        Answer multiple questions against the same or different contexts.

        Args:
            questions: List of {"key": ..., "question": ..., "context": ...}

        Returns:
            Dict mapping key -> QAAnswer
        """
        results = {}
        for item in questions:
            key = item.get("key", "")
            results[key] = self.answer(
                question=item.get("question", ""),
                context=item.get("context", ""),
                min_confidence=min_confidence,
            )
        return results

    def extract_legal_facts(self, text: str) -> LegalFacts:
        """
        Extract structured legal facts from a claim text.

        Uses QA model when available, regex patterns as fallback/supplement.
        Both approaches are combined for maximum recall.

        Args:
            text: Hebrew legal claim text

        Returns:
            LegalFacts with extracted information
        """
        facts = LegalFacts()

        if not text or len(text) < 10:
            return facts

        # --- QA model extraction ---
        if self._ensure_model() and _qa_pipeline is not None:
            facts = self._extract_with_model(text, facts)

        # --- Regex extraction (fills gaps left by model) ---
        facts = self._extract_with_regex(text, facts)

        # Compute overall confidence
        filled = sum(1 for v in [
            facts.speaker, facts.action, facts.subject, facts.object,
            facts.amount, facts.date, facts.plane,
        ] if v is not None)
        facts.confidence = min(1.0, filled / 5.0)

        return facts

    def _extract_with_model(self, text: str, facts: LegalFacts) -> LegalFacts:
        """Extract facts using the QA model."""
        for field_name, question in _LEGAL_QA_QUESTIONS.items():
            try:
                result = self.answer(question, text, min_confidence=0.20)
                if result:
                    facts.raw_answers[field_name] = result
                    # Set the corresponding field
                    if field_name == 'speaker' and not facts.speaker:
                        facts.speaker = result.answer
                    elif field_name == 'subject' and not facts.subject:
                        facts.subject = result.answer
                    elif field_name == 'action' and not facts.action:
                        facts.action = result.answer
                    elif field_name == 'object' and not facts.object:
                        facts.object = result.answer
                    elif field_name == 'amount' and not facts.amount:
                        facts.amount = result.answer
                    elif field_name == 'date' and not facts.date:
                        facts.date = result.answer
                    elif field_name == 'location' and not facts.location:
                        facts.location = result.answer
            except Exception as e:
                logger.debug("QA extraction failed for %s: %s", field_name, e)

        return facts

    def _extract_with_regex(self, text: str, facts: LegalFacts) -> LegalFacts:
        """Extract facts using regex patterns (fills gaps from model)."""

        # Speaker
        if not facts.speaker:
            for pattern in _SPEAKER_PATTERNS:
                m = pattern.search(text)
                if m:
                    facts.speaker = m.group(1).strip()
                    break

        # Speaker role
        if not facts.speaker_role:
            for role, pattern in _ROLE_INDICATORS.items():
                if pattern.search(text):
                    facts.speaker_role = role
                    break

        # Amount
        if not facts.amount:
            m = _AMOUNT_PATTERN.search(text)
            if m:
                facts.amount = m.group(0)

        # Date
        if not facts.date:
            m = _DATE_PATTERN.search(text)
            if m:
                facts.date = m.group(1)

        # Negation
        facts.negation = bool(_NEGATION_PATTERN.search(text))

        # Plane (FACT/LAW/OPINION/PROCEDURAL)
        if not facts.plane:
            for plane_name, pattern in _PLANE_INDICATORS.items():
                if pattern.search(text):
                    facts.plane = plane_name
                    break
            if not facts.plane:
                facts.plane = "FACT"  # Default assumption

        # Modality
        if not facts.modality:
            for modality_name, pattern in _MODALITY_INDICATORS.items():
                if pattern.search(text):
                    facts.modality = modality_name
                    break
            if not facts.modality:
                facts.modality = "certain" if not facts.negation else "uncertain"

        return facts

    def extract_key_facts_for_contradiction(
        self,
        claim1_text: str,
        claim2_text: str,
    ) -> Dict[str, Any]:
        """
        Extract and compare key facts from two contradicting claims.

        Useful for cross-examination: identifies exactly WHAT differs
        between the two claims.

        Returns:
            Dict with:
            - facts1: LegalFacts for claim 1
            - facts2: LegalFacts for claim 2
            - differences: list of (field, val1, val2) tuples
            - contradiction_focus: the most likely focus of the contradiction
        """
        facts1 = self.extract_legal_facts(claim1_text)
        facts2 = self.extract_legal_facts(claim2_text)

        # Find differences
        differences = []
        for field_name in ['speaker', 'action', 'subject', 'object', 'amount', 'date', 'location']:
            v1 = getattr(facts1, field_name, None)
            v2 = getattr(facts2, field_name, None)
            if v1 and v2 and v1 != v2:
                differences.append((field_name, v1, v2))
            elif v1 and not v2:
                differences.append((field_name, v1, None))
            elif v2 and not v1:
                differences.append((field_name, None, v2))

        # Check negation flip
        if facts1.negation != facts2.negation:
            differences.append(('negation', facts1.negation, facts2.negation))

        # Determine contradiction focus
        focus = "general"
        if any(d[0] == 'amount' for d in differences):
            focus = "amount"
        elif any(d[0] == 'date' for d in differences):
            focus = "date"
        elif any(d[0] == 'negation' for d in differences):
            focus = "negation"
        elif any(d[0] == 'action' for d in differences):
            focus = "action"
        elif any(d[0] in ('subject', 'object') for d in differences):
            focus = "party"

        return {
            'facts1': facts1,
            'facts2': facts2,
            'differences': differences,
            'contradiction_focus': focus,
        }


# =============================================================================
# Singleton
# =============================================================================

_qa_engine: Optional[LegalQA] = None


def get_legal_qa() -> LegalQA:
    """Get singleton Legal QA engine."""
    global _qa_engine
    if _qa_engine is None:
        _qa_engine = LegalQA()
    return _qa_engine


def extract_facts(text: str) -> LegalFacts:
    """Convenience: extract legal facts from a claim."""
    return get_legal_qa().extract_legal_facts(text)
