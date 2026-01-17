from typing import List, Tuple
from functools import lru_cache
EMBEDDING_DIMENSION = 1536
@lru_cache(maxsize=128)
def generate_embeddings(texts: Tuple[str]) -> List[List[float]]:
    return [[0.0] * EMBEDDING_DIMENSION for _ in texts]
