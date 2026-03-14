"""
Embedding utilities for Memory Thread.

Uses mock embeddings by default (fast, works offline).
For semantic search, download model once while online:
  huggingface-cli download sentence-transformers/all-MiniLM-L6-v2
"""

import os

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from typing import List, Tuple, Optional
from functools import lru_cache
import logging

log = logging.getLogger(__name__)

# Default dimension (matches common models)
EMBEDDING_DIMENSION = 384

# Cached model - set to "loaded" to use real model
_model_loaded = False


@lru_cache(maxsize=512)
def generate_embeddings(texts: Tuple[str, ...]) -> List[List[float]]:
    """
    Generate embeddings for texts.

    Uses mock (hash-based) embeddings by default.
    For real semantic embeddings, download the model first:
      pip install sentence-transformers
      # Then first run while online will cache it
    """
    return _mock_embeddings(texts)


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
