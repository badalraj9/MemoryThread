from pydantic_settings import BaseSettings
from typing import ClassVar, Optional
from urllib.parse import urlparse, parse_qs
import os
from pathlib import Path

# Load .env file if exists
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv

    load_dotenv(_env_path)


def _parse_mt_url(url: str) -> tuple:
    """Parse MT_URL and return (host, port, namespace)."""
    if not url:
        return None, None, None

    parsed = urlparse(url)

    if parsed.scheme != "mt":
        return None, None, None

    host = parsed.hostname or "localhost"
    port = parsed.port or 8000
    path = parsed.path.strip("/")
    namespace = path if path else "default"

    return host, port, namespace


class Settings(BaseSettings):
    # Primary connection method - MT_URL
    MT_URL: str = os.environ.get("MT_URL", "")

    # Parsed from MT_URL (if set)
    MT_HOST: Optional[str] = None
    MT_PORT: Optional[int] = None
    MT_NAMESPACE: str = "default"

    # Legacy/fallback - individual connection vars (used if MT_URL not set)
    POSTGRES_USER: str = "user"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "memory_thread_db"
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # API Key (from MT_URL query param or env)
    MT_API_KEY: str = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Parse MT_URL if set
        if self.MT_URL:
            host, port, namespace = _parse_mt_url(self.MT_URL)
            if host:
                self.MT_HOST = host
                self.MT_PORT = port
                self.MT_NAMESPACE = namespace

                # Also set legacy vars from MT_URL for compatibility
                self.POSTGRES_SERVER = host
                self.QDRANT_HOST = host

        # Get API key from MT_URL query or env
        if self.MT_URL:
            parsed = urlparse(self.MT_URL)
            query_params = parse_qs(parsed.query)
            api_key = query_params.get("api_key", [None])[0]
            if api_key:
                self.MT_API_KEY = api_key

    # Legacy env var compatibility
    class Config:
        env_file = ".env"
        extra = "ignore"

    # Graph
    MAX_EDGES_PER_NODE: int = 12

    # Retrieval Scoring Weights
    # Controls how different signals contribute to memory retrieval scores
    # Valid range: 0.0 to 1.0 for each
    SCORE_WEIGHT_VECTOR: float = 0.5  # Semantic similarity from Qdrant
    SCORE_WEIGHT_KEYWORD: float = 0.2  # Keyword matching
    SCORE_WEIGHT_GRAPH: float = 0.15  # Graph relationship strength
    SCORE_WEIGHT_IMPORTANCE: float = 0.1  # User-specified importance
    SCORE_WEIGHT_RECENCY: float = 0.05  # Temporal freshness

    # TMS Truth Vector Weights
    # Controls how components combine into the final truth score
    # Valid range: 0.0 to 2.0 (higher = more influence)
    TMS_WEIGHT_CONFIDENCE: float = 1.0  # Certainty in the information
    TMS_WEIGHT_AUTHORITY: float = 1.2  # Source credibility (user=1.0, agent=0.5)
    TMS_WEIGHT_FRESHNESS: float = 0.8  # Temporal relevance (decays over time)
    TMS_WEIGHT_CORROBORATION: float = 0.6  # Independent confirmations

    # Drift Detection
    # Cosine distance threshold for semantic drift detection
    # If new content differs from domain centroid by more than this, flag drift
    DRIFT_THRESHOLD: float = 0.3

    # Integrity Rules
    # Configurable constraints for entity state validation
    # Each rule: {field: {"min": X, "max": Y}}
    INTEGRITY_RULES: ClassVar = {
        "tree_count": {"min": 0},
        "age": {"min": 0, "max": 150},
        "confidence": {"min": 0.0, "max": 1.0},
    }

    # Embedding Configuration
    EMBEDDING_DIMENSION: int = 1536
    EMBEDDING_DISTANCE: str = "Cosine"

    # ZMQ Configuration
    ZMQ_FABRIC_ADDRESS: str = "ipc://fabric_router"
    ZMQ_PERSISTENCE_ADDRESS: str = "ipc://persistence_pipe"

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC: str = "memory_events"

    # Performance Tuning
    SLAB_COUNT: int = 128
    SLAB_SIZE: int = 65536

    # Benchmark Configuration
    BENCHMARK_TARGET_EPS: int = 50000
    BENCHMARK_DURATION_SEC: int = 5
    BENCHMARK_NUM_PRODUCERS: int = 4
    BENCHMARK_ADDRESS: str = "tcp://127.0.0.1:5555"

    # Database Pool Configuration
    DB_POOL_MIN_CONN: int = 2
    DB_POOL_MAX_CONN: int = 10

    # Retry Configuration
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_WAIT_SECONDS: float = 1.0
    RETRY_WAIT_MAX_SECONDS: float = 10.0

    # Namespace Configuration
    # Directory paths for MT configuration
    MT_GLOBAL_DIR: str = os.path.expanduser("~/.mt/")  # User-level global config
    MT_PROJECT_DIR: str = ".mt/"  # Project-level config (relative to project root)

    # Namespace Authority Weights
    # Weight applied to global namespace memories during recall merge
    GLOBAL_AUTHORITY_WEIGHT: float = 0.8


settings = Settings()
