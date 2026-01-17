from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    POSTGRES_USER: str = os.environ.get("POSTGRES_USER", "user")
    POSTGRES_PASSWORD: str = os.environ.get("POSTGRES_PASSWORD", "password")
    POSTGRES_SERVER: str = os.environ.get("POSTGRES_SERVER", "localhost")
    POSTGRES_PORT: int = int(os.environ.get("POSTGRES_PORT", 5432))
    POSTGRES_DB: str = os.environ.get("POSTGRES_DB", "memory_thread_db")
    QDRANT_HOST: str = os.environ.get("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.environ.get("QDRANT_PORT", 6333))

    # Graph
    MAX_EDGES_PER_NODE: int = 12

    # Retrieval Scoring
    SCORE_WEIGHT_VECTOR: float = 0.5
    SCORE_WEIGHT_KEYWORD: float = 0.2
    SCORE_WEIGHT_GRAPH: float = 0.15
    SCORE_WEIGHT_IMPORTANCE: float = 0.1
    SCORE_WEIGHT_RECENCY: float = 0.05

settings = Settings()
