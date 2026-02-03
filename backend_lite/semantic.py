"""
Semantic Similarity Engine for Hebrew Legal Text
=================================================

Dual-strategy semantic engine:

1. **Legal-HeBERT** (primary, when torch+transformers installed):
   - BERT model trained on 3.7GB of Israeli legal text
   - Understands Hebrew legal semantics natively
   - Contextual embeddings: "לא קיבל" ≠ "קיבל" (unlike TF-IDF)
   - 512-token context window
   - Models: avichr/Legal-heBERT (from scratch) or avichr/Legal-heBERT_ft (fine-tuned)

2. **TF-IDF + Character N-grams** (fallback, zero dependencies):
   - Character n-grams (3-5) handle Hebrew morphological variants
   - No semantic understanding, only surface pattern matching
   - Always available

Strategy selection is automatic:
- If transformers+torch are installed → Legal-HeBERT (with TF-IDF pre-filter for speed)
- Otherwise → TF-IDF only

Usage:
    from semantic import SemanticEngine

    engine = SemanticEngine()
    engine.index_claims(claims)
    score = engine.relatedness(claim_a, claim_b)
"""

import math
import re
import os
import logging
import hashlib
from typing import List, Dict, Tuple, Optional, Set
from collections import Counter, defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# =============================================================================
# Legal-HeBERT Availability Detection
# =============================================================================

_HEBERT_AVAILABLE = False
_hebert_model = None
_hebert_tokenizer = None

# Model choices (from HuggingFace):
# - avichr/Legal-heBERT: trained from scratch on legal corpus
# - avichr/Legal-heBERT_ft: fine-tuned HeBERT on legal corpus
LEGAL_HEBERT_MODEL = os.environ.get(
    "LEGAL_HEBERT_MODEL", "avichr/Legal-heBERT"
)

try:
    import torch
    from transformers import AutoTokenizer, AutoModel
    _HEBERT_AVAILABLE = True
    logger.info("Legal-HeBERT available (torch + transformers installed)")
except ImportError:
    logger.info("Legal-HeBERT not available — using TF-IDF fallback. "
                "Install: pip install transformers torch")


def _load_hebert():
    """Lazy-load the Legal-HeBERT model and tokenizer."""
    global _hebert_model, _hebert_tokenizer

    if _hebert_model is not None:
        return _hebert_model, _hebert_tokenizer

    if not _HEBERT_AVAILABLE:
        return None, None

    try:
        logger.info("Loading Legal-HeBERT model: %s", LEGAL_HEBERT_MODEL)
        _hebert_tokenizer = AutoTokenizer.from_pretrained(LEGAL_HEBERT_MODEL)
        _hebert_model = AutoModel.from_pretrained(LEGAL_HEBERT_MODEL)
        _hebert_model.eval()  # Set to evaluation mode (no dropout)

        # Move to GPU if available
        if torch.cuda.is_available():
            _hebert_model = _hebert_model.cuda()
            logger.info("Legal-HeBERT loaded on GPU")
        else:
            logger.info("Legal-HeBERT loaded on CPU")

        return _hebert_model, _hebert_tokenizer

    except Exception as e:
        logger.warning("Failed to load Legal-HeBERT: %s — falling back to TF-IDF", e)
        return None, None


def _compute_hebert_embedding(text: str, max_length: int = 512) -> Optional[List[float]]:
    """
    Compute a sentence embedding using Legal-HeBERT.

    Uses mean pooling of the last hidden state (excluding [CLS] and [SEP]).
    Returns a list of floats (768-dimensional vector) or None on failure.
    """
    model, tokenizer = _load_hebert()
    if model is None or tokenizer is None:
        return None

    try:
        import torch

        # Tokenize with truncation for long claims
        inputs = tokenizer(
            text,
            return_tensors="pt",
            max_length=max_length,
            truncation=True,
            padding=True,
        )

        # Move to same device as model
        device = next(model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        # Forward pass without gradient computation
        with torch.no_grad():
            outputs = model(**inputs)

        # Mean pooling: average all token embeddings (excluding padding)
        attention_mask = inputs['attention_mask']
        hidden_state = outputs.last_hidden_state  # (1, seq_len, hidden_dim)

        # Expand mask to match hidden state dimensions
        mask_expanded = attention_mask.unsqueeze(-1).expand(hidden_state.size()).float()

        # Sum all token embeddings weighted by attention mask, then divide by mask sum
        sum_embeddings = torch.sum(hidden_state * mask_expanded, dim=1)
        sum_mask = torch.clamp(mask_expanded.sum(dim=1), min=1e-9)
        mean_pooled = sum_embeddings / sum_mask

        # Normalize to unit vector for cosine similarity
        normalized = torch.nn.functional.normalize(mean_pooled, p=2, dim=1)

        return normalized[0].cpu().tolist()

    except Exception as e:
        logger.warning("HeBERT embedding failed for text (len=%d): %s", len(text), e)
        return None


def _cosine_sim_vectors(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two dense float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


# =============================================================================
# Negation Detection for Hebrew Legal Text
# =============================================================================

# Hebrew negation markers that invert claim meaning
_NEGATION_MARKERS = re.compile(
    r'\b('
    r'לא|אין|איננו|איננה|אינו|אינה|אינם|אינן|'
    r'מעולם\s+לא|לעולם\s+לא|בשום\s+(?:אופן|מקרה|פנים)|'
    r'אף\s+(?:פעם|אחד)|ללא|בלי|טרם|'
    r'מכחיש|שולל|דוחה|מתנגד|חולק\s+על|'
    r'לא\s+(?:היה|היתה|היו|נעשה|נעשתה|בוצע|בוצעה|התקיים|התקיימה|סוכם|הוסכם)'
    r')\b',
    re.UNICODE,
)

# Patterns that explicitly indicate opposition/contradiction
_OPPOSITION_PATTERNS = re.compile(
    r'\b('
    r'בניגוד\s+ל|להיפך|לעומת\s+זאת|אך|אולם|אלא|'
    r'שונה\s+(?:מ|מן)|סותר|נוגד'
    r')\b',
    re.UNICODE,
)

# Antonym pairs common in Hebrew legal text
_LEGAL_ANTONYMS = [
    ('קיבל', 'לא קיבל'), ('שילם', 'לא שילם'), ('חתם', 'לא חתם'),
    ('נכח', 'לא נכח'), ('הסכים', 'לא הסכים'), ('אישר', 'לא אישר'),
    ('ידע', 'לא ידע'), ('ראה', 'לא ראה'), ('שמע', 'לא שמע'),
    ('קיבל', 'דחה'), ('הסכים', 'סירב'), ('אישר', 'דחה'),
    ('נוכח', 'נעדר'), ('הגיע', 'לא הגיע'), ('עבד', 'לא עבד'),
    ('פוטר', 'התפטר'), ('שכר', 'פיטר'),
    ('לפני', 'אחרי'), ('לפני', 'לאחר'),
    ('תובע', 'נתבע'),
]


def detect_negation_polarity(text: str) -> Tuple[bool, int]:
    """
    Detect negation in Hebrew text.

    Returns:
        (has_negation, negation_count)
    """
    negations = _NEGATION_MARKERS.findall(text)
    return (len(negations) > 0, len(negations))


def compute_negation_contrast(text_a: str, text_b: str) -> float:
    """
    Compute a negation contrast score between two claims.

    Returns a value from 0.0 to 1.0:
    - Positive: claims have opposing polarity (potential contradiction)
    - Zero: same polarity or no negation detected
    """
    neg_a, count_a = detect_negation_polarity(text_a)
    neg_b, count_b = detect_negation_polarity(text_b)

    # Check for antonym pairs
    antonym_found = False
    text_a_lower = text_a.lower() if text_a else ""
    text_b_lower = text_b.lower() if text_b else ""
    for word_a, word_b in _LEGAL_ANTONYMS:
        if (word_a in text_a_lower and word_b in text_b_lower) or \
           (word_b in text_a_lower and word_a in text_b_lower):
            antonym_found = True
            break

    # Opposing polarity: one negated, other not
    if neg_a != neg_b:
        score = 0.6
        if antonym_found:
            score = 0.85
        return score

    # Both have same polarity
    if antonym_found:
        return 0.5  # Antonyms detected even without clear negation

    # Both negated or both positive — no contrast
    return 0.0


# =============================================================================
# Claim Vector Storage
# =============================================================================

@dataclass
class ClaimVector:
    """Cached vector representation of a claim."""
    claim_id: str
    text: str
    tfidf: Dict[str, float] = field(default_factory=dict)
    norm: float = 0.0
    embedding: Optional[List[float]] = None
    entities: Set[str] = field(default_factory=set)


# =============================================================================
# Semantic Engine
# =============================================================================

class SemanticEngine:
    """
    Dual-strategy semantic similarity engine.

    Primary: Legal-HeBERT contextual embeddings (when available)
    Fallback: TF-IDF character n-grams (always available)

    The engine automatically selects the best available strategy.
    """

    def __init__(
        self,
        ngram_range: Tuple[int, int] = (3, 5),
        min_df: int = 1,
        max_df_ratio: float = 0.85,
        use_word_features: bool = True,
        force_tfidf: bool = False,
    ):
        self.ngram_range = ngram_range
        self.min_df = min_df
        self.max_df_ratio = max_df_ratio
        self.use_word_features = use_word_features

        # Strategy selection
        self._use_hebert = _HEBERT_AVAILABLE and not force_tfidf
        self._hebert_ready = False  # Set to True after first successful embedding

        # Index state
        self._claim_vectors: Dict[str, ClaimVector] = {}
        self._idf: Dict[str, float] = {}
        self._doc_count: int = 0
        self._indexed: bool = False

        # Hebrew stopwords (short function words)
        self._stopwords = {
            'את', 'של', 'על', 'עם', 'אל', 'מן', 'כי', 'גם', 'או', 'אם',
            'הוא', 'היא', 'הם', 'הן', 'אני', 'אנחנו', 'זה', 'זו', 'זאת',
            'כל', 'כך', 'רק', 'עוד', 'יותר',
        }

    @property
    def strategy(self) -> str:
        """Current active strategy."""
        if self._use_hebert and self._hebert_ready:
            return "Legal-HeBERT"
        return "TF-IDF"

    # =========================================================================
    # Public API
    # =========================================================================

    def index_claims(self, claims: list) -> None:
        """
        Build index for a set of claims.

        If Legal-HeBERT is available: computes dense embeddings + TF-IDF backup
        Otherwise: TF-IDF only
        """
        if not claims:
            return

        self._claim_vectors.clear()
        self._idf.clear()

        # Always build TF-IDF (fast, used as pre-filter even with HeBERT)
        self._build_tfidf_index(claims)

        # If HeBERT is available, compute embeddings
        if self._use_hebert:
            self._build_hebert_embeddings(claims)

        self._indexed = True
        logger.info(
            "Semantic index built: %d claims, strategy=%s",
            len(claims), self.strategy,
        )

    def relatedness(self, claim_a, claim_b) -> float:
        """
        Compute semantic relatedness between two claims (0-1).

        Uses HeBERT embeddings if available, falls back to TF-IDF.
        """
        id_a = getattr(claim_a, 'id', str(id(claim_a)))
        id_b = getattr(claim_b, 'id', str(id(claim_b)))

        vec_a = self._claim_vectors.get(id_a)
        vec_b = self._claim_vectors.get(id_b)

        # Strategy 1: HeBERT embeddings (best quality)
        if vec_a and vec_b and vec_a.embedding and vec_b.embedding:
            return _cosine_sim_vectors(vec_a.embedding, vec_b.embedding)

        # Strategy 2: TF-IDF (fallback)
        if vec_a and vec_b:
            return self._cosine_similarity(vec_a.tfidf, vec_a.norm, vec_b.tfidf, vec_b.norm)

        # Strategy 3: Ad-hoc computation for unindexed claims
        text_a = getattr(claim_a, 'text', str(claim_a))
        text_b = getattr(claim_b, 'text', str(claim_b))

        # Try HeBERT ad-hoc
        if self._use_hebert:
            emb_a = _compute_hebert_embedding(text_a)
            emb_b = _compute_hebert_embedding(text_b)
            if emb_a and emb_b:
                return _cosine_sim_vectors(emb_a, emb_b)

        # Final fallback: ad-hoc TF-IDF
        return self._compute_adhoc_similarity(text_a, text_b)

    def find_related(self, claim, top_k: int = 10, threshold: float = 0.15) -> List[Tuple[str, float]]:
        """
        Find the top-k most related claims to a given claim.

        Returns list of (claim_id, similarity_score) sorted by score descending.
        """
        cid = getattr(claim, 'id', str(id(claim)))
        vec = self._claim_vectors.get(cid)
        if not vec:
            return []

        scores = []
        for other_id, other_vec in self._claim_vectors.items():
            if other_id == cid:
                continue

            # Use HeBERT if available
            if vec.embedding and other_vec.embedding:
                sim = _cosine_sim_vectors(vec.embedding, other_vec.embedding)
            else:
                sim = self._cosine_similarity(vec.tfidf, vec.norm, other_vec.tfidf, other_vec.norm)

            if sim >= threshold:
                scores.append((other_id, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def get_candidate_pairs(self, threshold: float = 0.15) -> List[Tuple[str, str, float]]:
        """
        Get all claim pairs above the relatedness threshold.

        Uses TF-IDF as fast pre-filter, then refines with HeBERT if available.
        """
        if not self._indexed:
            return []

        pairs = []
        claim_ids = list(self._claim_vectors.keys())
        has_embeddings = self._hebert_ready

        # Pre-filter threshold for TF-IDF (lower than final to not miss pairs)
        tfidf_prefilter = threshold * 0.6 if has_embeddings else threshold

        for i in range(len(claim_ids)):
            vec_a = self._claim_vectors[claim_ids[i]]
            if vec_a.norm == 0 and not vec_a.embedding:
                continue

            for j in range(i + 1, len(claim_ids)):
                vec_b = self._claim_vectors[claim_ids[j]]
                if vec_b.norm == 0 and not vec_b.embedding:
                    continue

                # Fast TF-IDF pre-filter
                tfidf_sim = self._cosine_similarity(
                    vec_a.tfidf, vec_a.norm, vec_b.tfidf, vec_b.norm
                )
                if tfidf_sim < tfidf_prefilter:
                    continue

                # Refine with HeBERT if available
                if has_embeddings and vec_a.embedding and vec_b.embedding:
                    sim = _cosine_sim_vectors(vec_a.embedding, vec_b.embedding)
                else:
                    sim = tfidf_sim

                if sim >= threshold:
                    pairs.append((claim_ids[i], claim_ids[j], sim))

        pairs.sort(key=lambda x: x[2], reverse=True)
        logger.info(
            "Candidate pairs: %d pairs above threshold %.2f (from %d claims, strategy=%s)",
            len(pairs), threshold, len(claim_ids), self.strategy,
        )
        return pairs

    def negation_aware_relatedness(self, claim_a, claim_b) -> Dict[str, float]:
        """
        Compute relatedness WITH negation awareness.

        Returns dict with:
        - similarity: semantic similarity score (0-1)
        - negation_contrast: opposing polarity score (0-1)
        - contradiction_signal: high similarity + opposing polarity = contradiction (0-1)
        - relatedness: final relatedness score for filtering (0-1)
        """
        # Semantic similarity (HeBERT or TF-IDF)
        similarity = self.relatedness(claim_a, claim_b)

        # Negation contrast (always regex-based — fast and precise)
        text_a = getattr(claim_a, 'text', str(claim_a))
        text_b = getattr(claim_b, 'text', str(claim_b))
        negation = compute_negation_contrast(text_a, text_b)

        # Contradiction signal: HIGH when claims are similar BUT have opposing polarity
        contradiction_signal = 0.0
        if negation > 0 and similarity > 0.2:
            contradiction_signal = min(1.0, similarity * negation * 2.0)

        # Relatedness for filtering: claims ARE related if they discuss the same thing
        relatedness = similarity

        return {
            'similarity': round(similarity, 4),
            'negation_contrast': round(negation, 4),
            'contradiction_signal': round(contradiction_signal, 4),
            'relatedness': round(relatedness, 4),
        }

    # =========================================================================
    # Legal-HeBERT Embedding Index
    # =========================================================================

    def _build_hebert_embeddings(self, claims: list) -> None:
        """
        Compute Legal-HeBERT embeddings for all claims.

        Embeddings are stored in ClaimVector.embedding for O(1) lookup.
        If model fails to load, silently falls back to TF-IDF.
        """
        model, tokenizer = _load_hebert()
        if model is None:
            logger.warning("Legal-HeBERT not loaded — using TF-IDF only")
            self._use_hebert = False
            return

        success_count = 0
        fail_count = 0

        for claim in claims:
            cid = getattr(claim, 'id', str(id(claim)))
            text = getattr(claim, 'text', str(claim))

            embedding = _compute_hebert_embedding(text)
            if embedding:
                if cid in self._claim_vectors:
                    self._claim_vectors[cid].embedding = embedding
                success_count += 1
            else:
                fail_count += 1

        if success_count > 0:
            self._hebert_ready = True
            logger.info(
                "Legal-HeBERT embeddings: %d success, %d failed (%.0f%% coverage)",
                success_count, fail_count,
                100.0 * success_count / (success_count + fail_count),
            )
        else:
            logger.warning("All HeBERT embeddings failed — falling back to TF-IDF")
            self._use_hebert = False

    # =========================================================================
    # TF-IDF Index (Fallback / Pre-filter)
    # =========================================================================

    def _build_tfidf_index(self, claims: list) -> None:
        """Build TF-IDF index for all claims."""
        doc_freq: Dict[str, int] = defaultdict(int)
        claim_features: Dict[str, Counter] = {}

        for claim in claims:
            cid = getattr(claim, 'id', str(id(claim)))
            text = getattr(claim, 'text', str(claim))
            features = self._extract_features(text)
            claim_features[cid] = features

            for feat in features:
                doc_freq[feat] += 1

        self._doc_count = len(claims)

        # Compute IDF with filtering
        max_df = int(self._doc_count * self.max_df_ratio)
        for feat, df in doc_freq.items():
            if df >= self.min_df and df <= max_df:
                self._idf[feat] = math.log((self._doc_count + 1) / (df + 1)) + 1.0

        # Compute TF-IDF vectors and norms
        for claim in claims:
            cid = getattr(claim, 'id', str(id(claim)))
            text = getattr(claim, 'text', str(claim))
            features = claim_features[cid]

            tfidf = {}
            for feat, tf in features.items():
                idf = self._idf.get(feat, 0.0)
                if idf > 0:
                    tfidf[feat] = (1 + math.log(tf)) * idf

            norm = math.sqrt(sum(v * v for v in tfidf.values())) if tfidf else 0.0

            self._claim_vectors[cid] = ClaimVector(
                claim_id=cid,
                text=text,
                tfidf=tfidf,
                norm=norm,
            )

    # =========================================================================
    # Feature Extraction (TF-IDF)
    # =========================================================================

    def _extract_features(self, text: str) -> Counter:
        """
        Extract character n-gram and word features from text.

        Character n-grams naturally handle Hebrew morphological variants:
        - חתם, חתמה, חתמתי → share trigrams חתמ, תמה, etc.
        - 100,000 ש"ח and 100000 שקל → share numeric n-grams
        """
        features = Counter()
        cleaned = self._clean_text(text)

        # Character n-grams (the core feature)
        for n in range(self.ngram_range[0], self.ngram_range[1] + 1):
            for i in range(len(cleaned) - n + 1):
                ngram = cleaned[i:i + n]
                if not ngram.isspace():
                    features[f"c{n}:{ngram}"] += 1

        # Word features (supplementary)
        if self.use_word_features:
            words = self._get_meaningful_words(cleaned)
            for word in words:
                features[f"w:{word}"] += 1

        return features

    def _clean_text(self, text: str) -> str:
        """Clean text for feature extraction."""
        text = re.sub(r'\s+', ' ', text.strip().lower())
        text = re.sub(r'[^\w\s\u0590-\u05FF]', '', text)
        return text

    def _get_meaningful_words(self, text: str) -> List[str]:
        """Extract meaningful words (skip stopwords and short words)."""
        words = []
        for word in text.split():
            if len(word) >= 3 and word not in self._stopwords:
                words.append(word)
        return words

    # =========================================================================
    # Similarity Computation (TF-IDF)
    # =========================================================================

    @staticmethod
    def _cosine_similarity(
        vec_a: Dict[str, float], norm_a: float,
        vec_b: Dict[str, float], norm_b: float,
    ) -> float:
        """Compute cosine similarity between two sparse vectors."""
        if norm_a == 0 or norm_b == 0:
            return 0.0

        if len(vec_a) > len(vec_b):
            vec_a, vec_b = vec_b, vec_a
            norm_a, norm_b = norm_b, norm_a

        dot_product = 0.0
        for feat, val_a in vec_a.items():
            val_b = vec_b.get(feat, 0.0)
            if val_b > 0:
                dot_product += val_a * val_b

        return dot_product / (norm_a * norm_b)

    def _compute_adhoc_similarity(self, text_a: str, text_b: str) -> float:
        """Compute similarity without pre-built index."""
        features_a = self._extract_features(text_a)
        features_b = self._extract_features(text_b)

        vec_a = {k: 1 + math.log(v) for k, v in features_a.items() if v > 0}
        vec_b = {k: 1 + math.log(v) for k, v in features_b.items() if v > 0}

        norm_a = math.sqrt(sum(v * v for v in vec_a.values())) if vec_a else 0.0
        norm_b = math.sqrt(sum(v * v for v in vec_b.values())) if vec_b else 0.0

        return self._cosine_similarity(vec_a, norm_a, vec_b, norm_b)


# =============================================================================
# Singleton
# =============================================================================

_engine: Optional[SemanticEngine] = None


def get_semantic_engine() -> SemanticEngine:
    """Get singleton semantic engine."""
    global _engine
    if _engine is None:
        _engine = SemanticEngine()
    return _engine


def reset_semantic_engine() -> None:
    """Reset the singleton (for new analysis runs)."""
    global _engine
    _engine = None
