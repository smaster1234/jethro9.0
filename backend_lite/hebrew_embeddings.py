"""
Hebrew Legal Embeddings (Legal-heBERT)
======================================

Provides dense vector embeddings for Hebrew legal text using
the avichr/Legal-heBERT model from HuggingFace.

Features:
- Lazy model loading (only loads when first used)
- Mean pooling for sentence-level embeddings
- Cosine similarity computation
- Batch embedding support
- Thread-safe singleton
"""

import os
import logging
import threading
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Model configuration
DEFAULT_MODEL_NAME = "avichr/Legal-heBERT"
EMBEDDING_DIM = 768  # BERT base hidden size
MAX_LENGTH = 512  # Max token length for BERT


class LegalHeBERTEmbedder:
    """
    Hebrew legal text embedder using Legal-heBERT.

    Loads avichr/Legal-heBERT from HuggingFace and provides
    dense vector embeddings for Hebrew legal text.

    Usage:
        embedder = get_embedder()
        vec = embedder.embed("טענת התובע כי החוזה הופר")
        sim = embedder.similarity("טענה א", "טענה ב")
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self.model_name = model_name
        self._model = None
        self._tokenizer = None
        self._lock = threading.Lock()
        self._loaded = False
        self._load_error: Optional[str] = None

    def _load_model(self):
        """Lazy-load the model and tokenizer"""
        if self._loaded:
            return
        if self._load_error:
            return

        with self._lock:
            if self._loaded:
                return

            try:
                import torch
                from transformers import AutoModel, AutoTokenizer

                cache_dir = os.environ.get(
                    "TRANSFORMERS_CACHE",
                    os.environ.get("HF_HOME", None)
                )

                logger.info(f"Loading Legal-heBERT model: {self.model_name}")

                self._tokenizer = AutoTokenizer.from_pretrained(
                    self.model_name,
                    cache_dir=cache_dir
                )
                self._model = AutoModel.from_pretrained(
                    self.model_name,
                    cache_dir=cache_dir
                )
                self._model.eval()  # Set to inference mode

                self._loaded = True
                logger.info(f"Legal-heBERT loaded successfully ({EMBEDDING_DIM}d embeddings)")

            except Exception as e:
                self._load_error = str(e)
                logger.error(f"Failed to load Legal-heBERT: {e}")

    @property
    def is_available(self) -> bool:
        """Check if the model is loaded and available"""
        if not self._loaded and not self._load_error:
            self._load_model()
        return self._loaded

    def embed(self, text: str) -> Optional[np.ndarray]:
        """
        Generate embedding for a single text.

        Args:
            text: Hebrew text to embed

        Returns:
            numpy array of shape (768,) or None if model unavailable
        """
        if not self.is_available:
            return None

        import torch

        # Tokenize
        inputs = self._tokenizer(
            text,
            return_tensors="pt",
            max_length=MAX_LENGTH,
            truncation=True,
            padding=True
        )

        # Generate embeddings
        with torch.no_grad():
            outputs = self._model(**inputs)

        # Mean pooling over token embeddings (excluding padding)
        attention_mask = inputs["attention_mask"]
        token_embeddings = outputs.last_hidden_state

        # Expand mask to match embedding dimensions
        mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()

        # Sum embeddings and divide by mask sum
        sum_embeddings = torch.sum(token_embeddings * mask_expanded, dim=1)
        sum_mask = torch.clamp(mask_expanded.sum(dim=1), min=1e-9)
        mean_pooled = sum_embeddings / sum_mask

        # Normalize to unit vector
        embedding = mean_pooled[0].numpy()
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> Optional[np.ndarray]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of Hebrew texts to embed
            batch_size: Number of texts to process at once

        Returns:
            numpy array of shape (n_texts, 768) or None if model unavailable
        """
        if not self.is_available:
            return None

        if not texts:
            return np.array([])

        import torch

        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            inputs = self._tokenizer(
                batch,
                return_tensors="pt",
                max_length=MAX_LENGTH,
                truncation=True,
                padding=True
            )

            with torch.no_grad():
                outputs = self._model(**inputs)

            attention_mask = inputs["attention_mask"]
            token_embeddings = outputs.last_hidden_state
            mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
            sum_embeddings = torch.sum(token_embeddings * mask_expanded, dim=1)
            sum_mask = torch.clamp(mask_expanded.sum(dim=1), min=1e-9)
            mean_pooled = sum_embeddings / sum_mask

            # Normalize each embedding
            batch_np = mean_pooled.numpy()
            norms = np.linalg.norm(batch_np, axis=1, keepdims=True)
            norms = np.maximum(norms, 1e-9)
            batch_np = batch_np / norms

            all_embeddings.append(batch_np)

        return np.vstack(all_embeddings)

    def similarity(self, text1: str, text2: str) -> float:
        """
        Compute cosine similarity between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Cosine similarity score (0.0 to 1.0), or 0.5 if model unavailable
        """
        emb1 = self.embed(text1)
        emb2 = self.embed(text2)

        if emb1 is None or emb2 is None:
            return 0.5  # Uncertain fallback

        # Cosine similarity (already normalized, so just dot product)
        sim = float(np.dot(emb1, emb2))

        # Clamp to [0, 1] range
        return max(0.0, min(1.0, sim))

    def similarity_matrix(self, texts: List[str]) -> Optional[np.ndarray]:
        """
        Compute pairwise similarity matrix for a list of texts.

        Args:
            texts: List of texts

        Returns:
            numpy array of shape (n, n) with cosine similarities
        """
        embeddings = self.embed_batch(texts)
        if embeddings is None:
            return None

        # Cosine similarity matrix (embeddings are already normalized)
        return np.dot(embeddings, embeddings.T)

    def find_similar(
        self,
        query: str,
        candidates: List[str],
        top_k: int = 5,
        min_similarity: float = 0.3
    ) -> List[Tuple[int, float]]:
        """
        Find most similar candidates to query.

        Args:
            query: Query text
            candidates: List of candidate texts
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold

        Returns:
            List of (index, similarity) tuples, sorted by similarity descending
        """
        query_emb = self.embed(query)
        if query_emb is None:
            return []

        candidate_embs = self.embed_batch(candidates)
        if candidate_embs is None:
            return []

        # Compute similarities
        similarities = np.dot(candidate_embs, query_emb)

        # Filter and sort
        results = [
            (i, float(sim))
            for i, sim in enumerate(similarities)
            if sim >= min_similarity
        ]
        results.sort(key=lambda x: x[1], reverse=True)

        return results[:top_k]


# Singleton
_embedder: Optional[LegalHeBERTEmbedder] = None
_embedder_lock = threading.Lock()


def get_embedder(model_name: str = DEFAULT_MODEL_NAME) -> LegalHeBERTEmbedder:
    """Get singleton embedder instance"""
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                _embedder = LegalHeBERTEmbedder(model_name)
    return _embedder


def is_hebert_available() -> bool:
    """Check if Legal-heBERT is available without forcing load"""
    try:
        import transformers  # noqa: F401
        import torch  # noqa: F401
        return True
    except ImportError:
        return False
