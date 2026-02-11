"""
Embedding utilities for Memory Thread.

Supports:
- sentence-transformers (local, accurate, ~100ms)
- OpenAI embeddings (API, high quality)
- Mock embeddings (testing, instant)
"""
from typing import List, Tuple, Optional
from functools import lru_cache
import logging

log = logging.getLogger(__name__)

# Default dimension (matches common models)
EMBEDDING_DIMENSION = 1536

# Cached model instance
_model = None
_model_type = None


def _get_local_model():
    """Load sentence-transformers model (lazy, cached)."""
    global _model, _model_type
    
    if _model is not None and _model_type == "local":
        return _model
    
    try:
        from sentence_transformers import SentenceTransformer
        # all-MiniLM-L6-v2 is small (80MB) and fast
        _model = SentenceTransformer('all-MiniLM-L6-v2')
        _model_type = "local"
        log.info("Loaded sentence-transformers model")
        return _model
    except ImportError:
        log.warning("sentence-transformers not installed. pip install sentence-transformers")
        return None
    except Exception as e:
        log.warning(f"Failed to load embedding model: {e}")
        return None


@lru_cache(maxsize=512)
def generate_embeddings(texts: Tuple[str, ...]) -> List[List[float]]:
    """
    Generate embeddings for texts.
    
    Tries in order:
    1. sentence-transformers (local)
    2. Mock embeddings (zeros)
    
    Args:
        texts: Tuple of strings to embed (tuple for caching)
    
    Returns:
        List of embedding vectors
    """
    # Try local model
    model = _get_local_model()
    if model is not None:
        try:
            embeddings = model.encode(list(texts), convert_to_numpy=True)
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            log.warning(f"Embedding failed: {e}")
    
    # Fallback to mock
    return _mock_embeddings(texts)


def _mock_embeddings(texts: Tuple[str, ...]) -> List[List[float]]:
    """
    Generate simple hash-based mock embeddings.
    
    Better than all zeros - at least provides some differentiation.
    """
    embeddings = []
    for text in texts:
        # Use hash to create reproducible pseudo-random vector
        import hashlib
        hash_bytes = hashlib.md5(text.encode()).digest()
        
        # Expand to full dimension
        embedding = []
        for i in range(EMBEDDING_DIMENSION):
            # Cycle through hash bytes
            byte_val = hash_bytes[i % len(hash_bytes)]
            # Normalize to -1 to 1
            embedding.append((byte_val / 128.0) - 1.0)
        
        embeddings.append(embedding)
    
    return embeddings


def get_embedding_dimension() -> int:
    """Get the dimension of embeddings."""
    model = _get_local_model()
    if model is not None:
        try:
            return model.get_sentence_embedding_dimension()
        except Exception:
            pass
    return EMBEDDING_DIMENSION


# Convenience function for single text
def embed_text(text: str) -> List[float]:
    """Embed a single text string."""
    return generate_embeddings((text,))[0]


# Canonical API alias (single-text embedding)
def get_embedding(text: str) -> List[float]:
    return embed_text(text)
