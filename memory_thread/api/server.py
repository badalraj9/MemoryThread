"""
Memory Thread REST API Server.

FastAPI-based REST API with automatic OpenAPI documentation.

Run:
    uvicorn memory_thread.api.server:app --reload

Docs:
    http://localhost:8000/docs (Swagger UI)
    http://localhost:8000/redoc (ReDoc)
"""

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime

from memory_thread.sdk import MemoryClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# ==============================================================================
# OpenTelemetry (Optional)
# ==============================================================================

try:
    from memory_thread.services.observability import init_telemetry, instrument_fastapi

    _otel_available = init_telemetry(service_name="memory-thread-api")
except ImportError:
    _otel_available = False
    log.info("OpenTelemetry not installed, running without tracing")

# ==============================================================================
# FastAPI App
# ==============================================================================

app = FastAPI(
    title="Memory Thread API",
    description="""
## Memory Thread - Cognitive Memory System

A truth-preserving, multi-agent memory layer for AI systems.

### Features
- **Remember/Recall**: Store and retrieve memories with truth scoring
- **Galaxy Schema**: OLAP-style cognitive queries (facts + beliefs)
- **Multi-Agent**: Per-agent belief dimensions

### Authentication
Use `X-Namespace` header to specify namespace (default: "default").
    """,
    version="1.0.0",
    contact={
        "name": "Memory Thread Team",
        "url": "https://github.com/badalraj/MemoryThread",
    },
    license_info={
        "name": "MIT",
    },
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instrument FastAPI with OpenTelemetry
if _otel_available:
    try:
        instrument_fastapi(app)
    except Exception as e:
        log.warning(f"FastAPI instrumentation failed: {e}")


# ==============================================================================
# Rate Limiter (Simple In-Memory)
# ==============================================================================

from collections import defaultdict
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimiter:
    """Simple in-memory rate limiter with sliding window."""

    def __init__(self, requests_per_minute: int = 100):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60
        self._requests: Dict[str, list] = defaultdict(list)

    def is_allowed(self, client_id: str) -> tuple[bool, int]:
        """
        Check if request is allowed.

        Returns:
            (allowed: bool, remaining: int)
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old requests
        self._requests[client_id] = [t for t in self._requests[client_id] if t > window_start]

        # Check limit
        current_count = len(self._requests[client_id])
        if current_count >= self.requests_per_minute:
            return False, 0

        # Record request
        self._requests[client_id].append(now)
        return True, self.requests_per_minute - current_count - 1

    def reset(self, client_id: str):
        """Reset rate limit for a client."""
        self._requests[client_id] = []


# Global rate limiter instance
rate_limiter = RateLimiter(requests_per_minute=100)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce rate limiting."""

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health check
        if request.url.path in ["/", "/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        # Get client ID from header or IP
        client_id = request.headers.get("X-API-Key") or request.client.host or "anonymous"

        allowed, remaining = rate_limiter.is_allowed(client_id)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Maximum {rate_limiter.requests_per_minute} requests per minute",
                    "retry_after_seconds": 60,
                },
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rate_limiter.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)


# ==============================================================================
# Request/Response Models
# ==============================================================================


class RememberRequest(BaseModel):
    """Request to store a memory."""

    content: str = Field(..., description="The content to remember")
    source: str = Field("agent", description="Source: 'user', 'agent', 'system'")
    confidence: float = Field(0.8, ge=0, le=1, description="Confidence level (0-1)")
    authority: float = Field(0.5, ge=0, le=1, description="Authority level (0-1)")
    memory_type: str = Field("fact", description="Type: 'fact', 'event', 'preference'")

    class Config:
        json_schema_extra = {
            "example": {
                "content": "User prefers dark mode",
                "source": "observation",
                "confidence": 0.9,
            }
        }


class RememberResponse(BaseModel):
    """Response after storing a memory."""

    entity_id: str
    message: str


class RecallRequest(BaseModel):
    """Request to recall memories."""

    query: str = Field(..., description="Search query")
    top_k: int = Field(5, ge=1, le=100, description="Max results to return")
    min_truth_score: float = Field(0.3, ge=0, le=1, description="Minimum truth score")


class MemoryItem(BaseModel):
    """A single memory item."""

    entity_id: str
    content: str
    truth_score: float
    confidence: float
    authority: float
    freshness: float
    source: str
    memory_type: str


class RecallResponse(BaseModel):
    """Response with recalled memories."""

    query: str
    total_found: int
    memories: List[MemoryItem]


class FactRequest(BaseModel):
    """Request to ingest a fact."""

    content: str = Field(..., description="Raw content to store")
    source_uri: Optional[str] = Field(None, description="Origin URI")
    content_type: str = Field("text", description="Type: 'text', 'code', 'log'")
    metadata: Optional[Dict[str, Any]] = None


class FactResponse(BaseModel):
    """Response after ingesting a fact."""

    fact_id: str
    message: str


class BeliefRequest(BaseModel):
    """Request to derive a belief from a fact."""

    fact_id: str = Field(..., description="Source fact ID")
    belief: str = Field(..., description="The belief/interpretation")
    agent_id: Optional[str] = Field(None, description="Agent ID (default: namespace)")
    confidence: float = Field(0.8, ge=0, le=1)
    authority: float = Field(0.5, ge=0, le=1)


class BeliefResponse(BaseModel):
    """Response after deriving a belief."""

    belief_id: str
    message: str


class GalaxyQueryRequest(BaseModel):
    """Request for galaxy OLAP query."""

    operation: str = Field(..., description="SLICE, DICE, DRILL_DOWN, ROLL_UP, SEARCH")
    source_uri: Optional[str] = None
    agent_id: Optional[str] = None
    min_authority: Optional[float] = None
    min_confidence: Optional[float] = None
    query: Optional[str] = None
    belief_id: Optional[str] = None
    top_k: int = Field(10, ge=1, le=100)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: str
    version: str


# ==============================================================================
# Dependencies
# ==============================================================================


def get_client(
    x_namespace: str = Header("default", alias="X-Namespace"),
) -> MemoryClient:
    """Get or create a MemoryClient for the request."""
    return MemoryClient(namespace=x_namespace, use_db=False, default_authority=0.5)


# ==============================================================================
# Routes
# ==============================================================================


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint."""
    return {"message": "Memory Thread API", "docs": "/docs"}


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy", timestamp=datetime.utcnow().isoformat(), version="1.0.0"
    )


@app.post("/memory/remember", response_model=RememberResponse, tags=["Memory"])
async def remember(request: RememberRequest, client: MemoryClient = Depends(get_client)):
    """
    Store a memory with truth metadata.

    The memory is stored with confidence, authority, and freshness scores
    that combine into a truth score for ranking during recall.
    """
    try:
        entity_id = client.remember(
            content=request.content,
            source=request.source,
            confidence=request.confidence,
            authority=request.authority,
            memory_type=request.memory_type,
        )
        return RememberResponse(entity_id=str(entity_id), message="Memory stored successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/memory/recall", response_model=RecallResponse, tags=["Memory"])
async def recall(request: RecallRequest, client: MemoryClient = Depends(get_client)):
    """
    Recall memories relevant to a query.

    Uses semantic search when available, falls back to keyword matching.
    Results are ranked by truth score.
    """
    try:
        result = client.recall(
            query=request.query, top_k=request.top_k, min_truth_score=request.min_truth_score
        )

        memories = [
            MemoryItem(
                entity_id=str(m.entity_id),
                content=m.content,
                truth_score=m.truth_score,
                confidence=m.confidence,
                authority=m.authority,
                freshness=m.freshness,
                source=m.source,
                memory_type=m.memory_type,
            )
            for m in result.memories
        ]

        return RecallResponse(query=result.query, total_found=result.total_found, memories=memories)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/galaxy/fact", response_model=FactResponse, tags=["Galaxy"])
async def ingest_fact(request: FactRequest, client: MemoryClient = Depends(get_client)):
    """
    Ingest a raw fact into the Galaxy Schema.

    Facts are:
    - Immutable (stored once)
    - Content-addressed (deduplicated by hash)
    - The foundation for derived beliefs
    """
    try:
        fact_id = client.ingest_fact(
            content=request.content,
            source_uri=request.source_uri,
            content_type=request.content_type,
            metadata=request.metadata,
        )
        return FactResponse(fact_id=fact_id, message="Fact ingested successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/galaxy/belief", response_model=BeliefResponse, tags=["Galaxy"])
async def derive_belief(request: BeliefRequest, client: MemoryClient = Depends(get_client)):
    """
    Derive a belief from a fact.

    Beliefs are:
    - Agent-specific interpretations
    - Linked to source facts
    - Subject to decay and truth scoring
    """
    try:
        belief_id = client.derive_belief(
            fact_id=request.fact_id,
            belief=request.belief,
            agent_id=request.agent_id,
            confidence=request.confidence,
            authority=request.authority,
        )
        return BeliefResponse(belief_id=belief_id, message="Belief derived successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/galaxy/query", tags=["Galaxy"])
async def query_galaxy(request: GalaxyQueryRequest, client: MemoryClient = Depends(get_client)):
    """
    Execute OLAP-style query on the cognitive galaxy.

    Operations:
    - **SLICE**: Filter by source
    - **DICE**: Multi-dimensional filter
    - **DRILL_DOWN**: Navigate to source fact
    - **ROLL_UP**: Aggregate beliefs
    - **SEARCH**: Semantic search across beliefs
    """
    try:
        kwargs = {
            k: v
            for k, v in {
                "source_uri": request.source_uri,
                "agent_id": request.agent_id,
                "min_authority": request.min_authority,
                "min_confidence": request.min_confidence,
                "query": request.query,
                "belief_id": request.belief_id,
                "top_k": request.top_k,
            }.items()
            if v is not None
        }

        result = client.query_galaxy(request.operation, **kwargs)

        # Convert to serializable format
        if hasattr(result, "beliefs"):
            return {
                "operation": request.operation,
                "beliefs_count": len(result.beliefs),
                "facts_referenced": result.facts_referenced,
                "agents_involved": result.agents_involved,
                "beliefs": [b.to_dict() for b in result.beliefs[:20]],
            }

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/galaxy/stats", tags=["Galaxy"])
async def galaxy_stats(client: MemoryClient = Depends(get_client)):
    """Get Galaxy Schema statistics."""
    try:
        return client.galaxy_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/galaxy/conflicts", tags=["Galaxy"])
async def galaxy_conflicts(client: MemoryClient = Depends(get_client)):
    """Get conflicts across agent belief dimensions."""
    try:
        return {"conflicts": client.get_galaxy_conflicts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# Main
# ==============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
