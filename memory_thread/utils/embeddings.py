"""
Embedding utilities for Memory Thread.

Uses sentence-transformers for semantic embeddings.
Falls back to mock embeddings if model unavailable.
"""

from typing import List, Tuple, Optional
from functools import lru_cache
import logging
import concurrent.futures

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

EMBEDDING_DIMENSION = 384

_model = None


def get_model():
    """Lazy load the sentence transformer model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            log.info("Loaded sentence transformer model")
        except Exception as e:
            log.warning(f"Could not load sentence transformer: {e}")
            _model = False
    return _model if _model else None


def normalize_text(text: str) -> str:
    """Normalize text for consistent embedding generation."""
    import unicodedata

    return unicodedata.normalize("NFKC", text.lower().strip())


@lru_cache(maxsize=512)
def generate_embeddings(texts: Tuple[str, ...]) -> List[List[float]]:
    """
    Generate embeddings for texts.
    Tries real model first, falls back to mock on failure.
    Normalizes text before encoding.
    """
    model = get_model()
    normalized = tuple(normalize_text(t) for t in texts)
    if model:
        try:
            return model.encode(list(normalized)).tolist()
        except Exception as e:
            log.warning(f"Real embedding failed: {e}")
    return _mock_embeddings(normalized)


def generate_embeddings_async(texts: Tuple[str, ...]) -> List[List[float]]:
    """Generate embeddings in a thread pool to avoid blocking."""
    model = get_model()
    if model:
        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(model.encode, list(texts))
                return future.result().tolist()
        except Exception as e:
            log.warning(f"Real embedding failed: {e}")

    return generate_embeddings(texts)


def _mock_embeddings(texts: Tuple[str, ...]) -> List[List[float]]:
    """Hash-based mock embeddings - fast, works offline."""
    dim = 384

    embeddings = []
    for text in texts:
        import hashlib

        hash_bytes = hashlib.md5(text.encode()).digest()

        embedding = []
        for i in range(dim):
            byte_val = hash_bytes[i % len(hash_bytes)]
            embedding.append((byte_val / 128.0) - 1.0)

        embeddings.append(embedding)

    return embeddings


def get_embedding_dimension() -> int:
    return EMBEDDING_DIMENSION


def embed_text(text: str) -> List[float]:
    return generate_embeddings((text,))[0]


def get_embedding(text: str) -> List[float]:
    return embed_text(text)
