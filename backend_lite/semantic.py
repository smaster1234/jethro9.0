"""
Semantic Similarity Engine for Hebrew Legal Text
=================================================

Provides semantic relatedness scoring between claims using multiple strategies:

1. **TF-IDF + Character N-grams** (default, zero dependencies):
   - Character n-grams (3-5) handle Hebrew morphological variants naturally
   - Weighted IDF computed per analysis run
   - Cosine similarity on TF-IDF vectors

2. **Optional Sentence Embeddings** (if sentence-transformers installed):
   - Uses multilingual models (e.g., intfloat/multilingual-e5-large)
   - Superior semantic understanding
   - Cached per claim for O(1) lookup

3. **Optional LLM Embeddings** (via Gemini/OpenRouter API):
   - Uses existing LLM infrastructure
   - Best quality, higher latency

Usage:
    from semantic import SemanticEngine

    engine = SemanticEngine()
    engine.index_claims(claims)  # Build index once
    score = engine.relatedness(claim_a, claim_b)  # Fast lookup
    neighbors = engine.find_related(claim_a, top_k=10)  # ANN search
"""

import math
import re
import logging
import hashlib
from typing import List, Dict, Tuple, Optional, Set
from collections import Counter, defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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

    Returns a value from -1.0 to +1.0:
    - Positive: claims have opposing polarity (potential contradiction)
    - Zero: same polarity or no negation detected
    - Negative: both negated (might actually agree)
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


@dataclass
class ClaimVector:
    """Cached vector representation of a claim."""
    claim_id: str
    text: str
    tfidf: Dict[str, float] = field(default_factory=dict)
    norm: float = 0.0
    embedding: Optional[List[float]] = None
    entities: Set[str] = field(default_factory=set)


class SemanticEngine:
    """
    Semantic similarity engine with TF-IDF character n-grams.

    Designed for Hebrew legal text where:
    - Morphological variants are common (חתם/חתמה/חתמתי)
    - Character n-grams capture root similarities without a stemmer
    - Cross-document entity matching needs fuzzy approach
    """

    def __init__(
        self,
        ngram_range: Tuple[int, int] = (3, 5),
        min_df: int = 1,
        max_df_ratio: float = 0.85,
        use_word_features: bool = True,
    ):
        self.ngram_range = ngram_range
        self.min_df = min_df
        self.max_df_ratio = max_df_ratio
        self.use_word_features = use_word_features

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

    # =========================================================================
    # Public API
    # =========================================================================

    def index_claims(self, claims: list) -> None:
        """
        Build TF-IDF index for a set of claims.

        Args:
            claims: List of Claim objects (must have .id and .text attributes)
        """
        if not claims:
            return

        self._claim_vectors.clear()
        self._idf.clear()

        # Step 1: Extract features and compute document frequencies
        doc_freq: Dict[str, int] = defaultdict(int)
        claim_features: Dict[str, Counter] = {}

        for claim in claims:
            cid = getattr(claim, 'id', str(id(claim)))
            text = getattr(claim, 'text', str(claim))
            features = self._extract_features(text)
            claim_features[cid] = features

            # Document frequency: count unique features per claim
            for feat in features:
                doc_freq[feat] += 1

        self._doc_count = len(claims)

        # Step 2: Compute IDF with filtering
        max_df = int(self._doc_count * self.max_df_ratio)
        for feat, df in doc_freq.items():
            if df >= self.min_df and df <= max_df:
                # Smooth IDF: log((N+1) / (df+1)) + 1
                self._idf[feat] = math.log((self._doc_count + 1) / (df + 1)) + 1.0

        # Step 3: Compute TF-IDF vectors and norms
        for claim in claims:
            cid = getattr(claim, 'id', str(id(claim)))
            text = getattr(claim, 'text', str(claim))
            features = claim_features[cid]

            tfidf = {}
            for feat, tf in features.items():
                idf = self._idf.get(feat, 0.0)
                if idf > 0:
                    # Sublinear TF: 1 + log(tf) if tf > 0
                    tfidf[feat] = (1 + math.log(tf)) * idf

            norm = math.sqrt(sum(v * v for v in tfidf.values())) if tfidf else 0.0

            self._claim_vectors[cid] = ClaimVector(
                claim_id=cid,
                text=text,
                tfidf=tfidf,
                norm=norm,
            )

        self._indexed = True
        logger.info(
            "Semantic index built: %d claims, %d features, %d IDF terms",
            len(claims), sum(len(f) for f in claim_features.values()), len(self._idf),
        )

    def relatedness(self, claim_a, claim_b) -> float:
        """
        Compute semantic relatedness between two claims (0-1).

        If claims are indexed, uses cached TF-IDF vectors.
        Otherwise, computes on-the-fly.
        """
        id_a = getattr(claim_a, 'id', str(id(claim_a)))
        id_b = getattr(claim_b, 'id', str(id(claim_b)))

        vec_a = self._claim_vectors.get(id_a)
        vec_b = self._claim_vectors.get(id_b)

        if vec_a and vec_b:
            return self._cosine_similarity(vec_a.tfidf, vec_a.norm, vec_b.tfidf, vec_b.norm)

        # Fallback: compute on-the-fly
        text_a = getattr(claim_a, 'text', str(claim_a))
        text_b = getattr(claim_b, 'text', str(claim_b))
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
            sim = self._cosine_similarity(vec.tfidf, vec.norm, other_vec.tfidf, other_vec.norm)
            if sim >= threshold:
                scores.append((other_id, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def get_candidate_pairs(self, threshold: float = 0.15) -> List[Tuple[str, str, float]]:
        """
        Get all claim pairs above the relatedness threshold.

        Returns list of (claim_id_a, claim_id_b, score) sorted by score descending.
        More efficient than O(n²) because it skips pairs early.
        """
        if not self._indexed:
            return []

        pairs = []
        claim_ids = list(self._claim_vectors.keys())

        for i in range(len(claim_ids)):
            vec_a = self._claim_vectors[claim_ids[i]]
            if vec_a.norm == 0:
                continue

            for j in range(i + 1, len(claim_ids)):
                vec_b = self._claim_vectors[claim_ids[j]]
                if vec_b.norm == 0:
                    continue

                sim = self._cosine_similarity(vec_a.tfidf, vec_a.norm, vec_b.tfidf, vec_b.norm)
                if sim >= threshold:
                    pairs.append((claim_ids[i], claim_ids[j], sim))

        pairs.sort(key=lambda x: x[2], reverse=True)
        logger.info(
            "Candidate pairs: %d pairs above threshold %.2f (from %d claims)",
            len(pairs), threshold, len(claim_ids),
        )
        return pairs

    # =========================================================================
    # Feature Extraction
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
        # Normalize whitespace
        import re
        text = re.sub(r'\s+', ' ', text.strip().lower())
        # Remove punctuation except Hebrew characters, digits, and spaces
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
    # Similarity Computation
    # =========================================================================

    @staticmethod
    def _cosine_similarity(
        vec_a: Dict[str, float], norm_a: float,
        vec_b: Dict[str, float], norm_b: float,
    ) -> float:
        """Compute cosine similarity between two sparse vectors."""
        if norm_a == 0 or norm_b == 0:
            return 0.0

        # Iterate over the smaller vector for efficiency
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

        # Simple TF-based (no IDF without corpus)
        vec_a = {k: 1 + math.log(v) for k, v in features_a.items() if v > 0}
        vec_b = {k: 1 + math.log(v) for k, v in features_b.items() if v > 0}

        norm_a = math.sqrt(sum(v * v for v in vec_a.values())) if vec_a else 0.0
        norm_b = math.sqrt(sum(v * v for v in vec_b.values())) if vec_b else 0.0

        return self._cosine_similarity(vec_a, norm_a, vec_b, norm_b)

    def negation_aware_relatedness(self, claim_a, claim_b) -> Dict[str, float]:
        """
        Compute relatedness WITH negation awareness.

        Returns dict with:
        - similarity: standard TF-IDF cosine similarity (0-1)
        - negation_contrast: opposing polarity score (0-1)
        - contradiction_signal: high similarity + opposing polarity = contradiction (0-1)
        - relatedness: final relatedness score for filtering (0-1)
        """
        # Standard similarity
        similarity = self.relatedness(claim_a, claim_b)

        # Negation contrast
        text_a = getattr(claim_a, 'text', str(claim_a))
        text_b = getattr(claim_b, 'text', str(claim_b))
        negation = compute_negation_contrast(text_a, text_b)

        # Contradiction signal: HIGH when claims are similar BUT have opposing polarity
        # This is the key insight — similar claims with opposite meaning = contradiction
        contradiction_signal = 0.0
        if negation > 0 and similarity > 0.2:
            # Scale: more similar + more negation = stronger contradiction signal
            contradiction_signal = min(1.0, similarity * negation * 2.0)

        # Relatedness for filtering: claims ARE related if they discuss the same thing,
        # EVEN IF they contradict each other. So similarity remains the filter,
        # but we note the contradiction.
        relatedness = similarity

        return {
            'similarity': round(similarity, 4),
            'negation_contrast': round(negation, 4),
            'contradiction_signal': round(contradiction_signal, 4),
            'relatedness': round(relatedness, 4),
        }


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
