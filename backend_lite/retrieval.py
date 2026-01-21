"""
BM25 Retrieval Module for Case-RAG
===================================

Implements BM25 (Best Match 25) for candidate pair generation.
Used to find paragraphs that are likely to contradict each other.

Key Features:
- Hebrew text tokenization
- BM25 scoring with tunable parameters
- TF-IDF fallback
- Candidate pair generation for contradiction detection
"""

import math
import re
from collections import Counter
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass

from .models import Paragraph


@dataclass
class RetrievalResult:
    """Result from retrieval query"""
    paragraph_id: str
    doc_id: str
    text: str
    score: float
    paragraph_index: int


class HebrewTokenizer:
    """Simple Hebrew text tokenizer"""

    def __init__(self):
        # Hebrew stopwords (common words that don't add meaning)
        self.stopwords = {
            # Prepositions and particles
            'את', 'של', 'על', 'עם', 'אל', 'מן', 'כי', 'לא', 'גם', 'או', 'אם',
            'אך', 'אז', 'כן', 'רק', 'עד', 'בין', 'אחר', 'תחת', 'נגד', 'לפי',
            # Pronouns
            'הוא', 'היא', 'הם', 'הן', 'אני', 'אנחנו', 'אתה', 'את', 'אתם', 'אתן',
            # Demonstratives
            'זה', 'זו', 'זאת', 'אלה', 'אלו',
            # Quantifiers
            'כל', 'כך', 'עוד', 'יותר', 'פחות', 'הרבה', 'מעט', 'קצת',
            # Verbs (be)
            'היה', 'היתה', 'היו', 'יהיה', 'תהיה', 'להיות', 'הייתי', 'היינו',
            # Single-letter prefixes
            'ה', 'ו', 'ב', 'ל', 'מ', 'ש', 'כ',
            # Common legal filler words
            'לעניין', 'בעניין', 'ביחס', 'לגבי', 'בדבר', 'באשר',
        }

        # Legal terms to keep (high signal)
        self.legal_terms = {
            'חוזה', 'הסכם', 'תביעה', 'נתבע', 'תובע', 'עד', 'עדות', 'ראיה',
            'סכום', 'תשלום', 'חתימה', 'מסמך', 'תאריך', 'מועד', 'נזק',
            'פיצוי', 'הפרה', 'התחייבות', 'זכות', 'חובה', 'אחריות',
        }

    def tokenize(self, text: str) -> List[str]:
        """
        Tokenize Hebrew text.

        Args:
            text: Hebrew text to tokenize

        Returns:
            List of tokens (lowercased, stopwords removed)
        """
        # Normalize
        text = text.lower()

        # Remove punctuation except Hebrew letters and digits
        text = re.sub(r'[^\u0590-\u05FF\d\s]', ' ', text)

        # Split into tokens
        tokens = text.split()

        # Remove stopwords and short tokens
        tokens = [
            t for t in tokens
            if len(t) > 1 and t not in self.stopwords
        ]

        return tokens

    def tokenize_with_bigrams(self, text: str) -> List[str]:
        """Tokenize with bigrams for better phrase matching"""
        tokens = self.tokenize(text)

        # Add bigrams
        bigrams = [
            f"{tokens[i]}_{tokens[i+1]}"
            for i in range(len(tokens) - 1)
        ]

        return tokens + bigrams


class BM25Index:
    """
    BM25 (Okapi BM25) index for paragraph retrieval.

    BM25 scoring: score = IDF * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl/avgdl))

    Parameters:
    - k1: Term frequency saturation (default 1.5)
    - b: Length normalization (default 0.75)
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.tokenizer = HebrewTokenizer()

        # Index structures
        self.doc_freqs: Dict[str, int] = {}  # term -> doc frequency
        self.doc_lengths: Dict[str, int] = {}  # doc_id -> length
        self.doc_tokens: Dict[str, List[str]] = {}  # doc_id -> tokens
        self.doc_tf: Dict[str, Counter] = {}  # doc_id -> term frequencies
        self.paragraphs: Dict[str, Paragraph] = {}  # para_id -> Paragraph

        self.n_docs = 0
        self.avg_doc_length = 0.0

    def add_paragraph(self, paragraph: Paragraph):
        """Add a paragraph to the index"""
        tokens = self.tokenizer.tokenize(paragraph.text)

        if not tokens:
            return

        para_id = paragraph.id

        # Store paragraph
        self.paragraphs[para_id] = paragraph

        # Store tokens and compute TF
        self.doc_tokens[para_id] = tokens
        self.doc_tf[para_id] = Counter(tokens)
        self.doc_lengths[para_id] = len(tokens)

        # Update document frequencies
        unique_tokens = set(tokens)
        for token in unique_tokens:
            self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1

        # Update stats
        self.n_docs += 1
        total_length = sum(self.doc_lengths.values())
        self.avg_doc_length = total_length / self.n_docs

    def add_paragraphs(self, paragraphs: List[Paragraph]):
        """Add multiple paragraphs to the index"""
        for para in paragraphs:
            self.add_paragraph(para)

    def _idf(self, term: str) -> float:
        """Compute IDF (Inverse Document Frequency)"""
        df = self.doc_freqs.get(term, 0)
        if df == 0:
            return 0.0

        # IDF with smoothing
        return math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1.0)

    def _bm25_score(self, query_tokens: List[str], para_id: str) -> float:
        """Compute BM25 score for a paragraph"""
        if para_id not in self.doc_tf:
            return 0.0

        tf = self.doc_tf[para_id]
        dl = self.doc_lengths[para_id]
        avgdl = self.avg_doc_length

        score = 0.0
        for term in query_tokens:
            if term not in tf:
                continue

            term_tf = tf[term]
            idf = self._idf(term)

            # BM25 formula
            numerator = term_tf * (self.k1 + 1)
            denominator = term_tf + self.k1 * (1 - self.b + self.b * dl / avgdl)
            score += idf * numerator / denominator

        return score

    def search(
        self,
        query: str,
        top_k: int = 10,
        exclude_ids: Optional[Set[str]] = None
    ) -> List[RetrievalResult]:
        """
        Search for paragraphs matching the query.

        Args:
            query: Search query text
            top_k: Number of results to return
            exclude_ids: Paragraph IDs to exclude from results

        Returns:
            List of RetrievalResult objects sorted by score
        """
        query_tokens = self.tokenizer.tokenize(query)

        if not query_tokens:
            return []

        exclude_ids = exclude_ids or set()

        # Score all paragraphs
        scores = []
        for para_id in self.paragraphs:
            if para_id in exclude_ids:
                continue

            score = self._bm25_score(query_tokens, para_id)
            if score > 0:
                scores.append((para_id, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        # Return top_k results
        results = []
        for para_id, score in scores[:top_k]:
            para = self.paragraphs[para_id]
            results.append(RetrievalResult(
                paragraph_id=para_id,
                doc_id=para.doc_id,
                text=para.text,
                score=score,
                paragraph_index=para.paragraph_index
            ))

        return results

    def find_similar_paragraphs(
        self,
        paragraph: Paragraph,
        top_k: int = 5,
        min_score: float = 0.1
    ) -> List[RetrievalResult]:
        """
        Find paragraphs similar to the given one.

        Excludes paragraphs from the same document for cross-document comparison.

        Args:
            paragraph: Source paragraph
            top_k: Number of results
            min_score: Minimum BM25 score threshold

        Returns:
            List of similar paragraphs from other documents
        """
        # Get all paragraph IDs from the same document
        same_doc_ids = {
            pid for pid, para in self.paragraphs.items()
            if para.doc_id == paragraph.doc_id
        }

        results = self.search(
            query=paragraph.text,
            top_k=top_k * 2,  # Get more, then filter
            exclude_ids=same_doc_ids
        )

        # Filter by minimum score
        results = [r for r in results if r.score >= min_score]

        return results[:top_k]


class CandidatePairGenerator:
    """
    Generate candidate paragraph pairs for contradiction detection.

    Uses BM25 to find paragraphs that discuss similar topics,
    which are more likely to contain contradictions.
    """

    def __init__(self, top_k: int = 8, min_score: float = 0.1):
        self.top_k = top_k
        self.min_score = min_score
        self.index = BM25Index()

    def build_index(self, paragraphs: List[Paragraph]):
        """Build BM25 index from paragraphs"""
        self.index = BM25Index()
        self.index.add_paragraphs(paragraphs)

    def generate_candidates(
        self,
        paragraphs: List[Paragraph],
        cross_document_only: bool = True
    ) -> List[Tuple[Paragraph, Paragraph, float]]:
        """
        Generate candidate paragraph pairs for contradiction detection.

        Args:
            paragraphs: All paragraphs to consider
            cross_document_only: If True, only pair paragraphs from different documents

        Returns:
            List of (para1, para2, similarity_score) tuples
        """
        # Build index if needed
        if self.index.n_docs != len(paragraphs):
            self.build_index(paragraphs)

        candidates = []
        seen_pairs = set()

        for para in paragraphs:
            # Find similar paragraphs
            if cross_document_only:
                similar = self.index.find_similar_paragraphs(
                    paragraph=para,
                    top_k=self.top_k,
                    min_score=self.min_score
                )
            else:
                similar = self.index.search(
                    query=para.text,
                    top_k=self.top_k,
                    exclude_ids={para.id}
                )

            for result in similar:
                # Create sorted pair ID to avoid duplicates
                pair_id = tuple(sorted([para.id, result.paragraph_id]))
                if pair_id in seen_pairs:
                    continue

                seen_pairs.add(pair_id)

                # Get the matching paragraph
                other_para = self.index.paragraphs.get(result.paragraph_id)
                if other_para:
                    candidates.append((para, other_para, result.score))

        # Sort by similarity score descending
        candidates.sort(key=lambda x: x[2], reverse=True)

        return candidates


# Singleton instance
_generator: Optional[CandidatePairGenerator] = None


def get_candidate_generator(top_k: int = 8) -> CandidatePairGenerator:
    """Get singleton candidate pair generator"""
    global _generator
    if _generator is None or _generator.top_k != top_k:
        _generator = CandidatePairGenerator(top_k=top_k)
    return _generator


def generate_candidate_pairs(
    paragraphs: List[Paragraph],
    top_k: int = 8,
    cross_document_only: bool = True
) -> List[Tuple[Paragraph, Paragraph, float]]:
    """
    Convenience function to generate candidate pairs.

    Args:
        paragraphs: All paragraphs in the case
        top_k: Number of similar paragraphs to consider per paragraph
        cross_document_only: Only pair paragraphs from different documents

    Returns:
        List of (para1, para2, similarity_score) tuples
    """
    generator = get_candidate_generator(top_k)
    generator.build_index(paragraphs)
    return generator.generate_candidates(
        paragraphs=paragraphs,
        cross_document_only=cross_document_only
    )
