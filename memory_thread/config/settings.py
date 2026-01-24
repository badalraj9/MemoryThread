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

    # TMS Truth Vector Weights
    TMS_WEIGHT_CONFIDENCE: float = 1.0
    TMS_WEIGHT_AUTHORITY: float = 1.2
    TMS_WEIGHT_FRESHNESS: float = 0.8
    TMS_WEIGHT_CORROBORATION: float = 0.6

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

settings = Settings()
