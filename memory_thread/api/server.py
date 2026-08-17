"""
Memory Thread REST API Server.

FastAPI-based REST API with automatic OpenAPI documentation.

Run:
    uvicorn memory_thread.api.server:app --reload

Docs:
    http://localhost:8000/docs (Swagger UI)
    http://localhost:8000/redoc (ReDoc)
"""

import logging
import sys
import os
import secrets
from collections import defaultdict
import time

# Suppress noisy third-party logs
for _lib in ["httpx", "httpcore", "urllib3", "sqlalchemy", "psycopg2"]:
    logging.getLogger(_lib).setLevel(logging.WARNING)

# Set MT logs to INFO
logging.getLogger("memory_thread").setLevel(logging.INFO)

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime
from contextlib import asynccontextmanager

security = HTTPBearer(auto_error=False)


async def verify_token(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> Optional[str]:
    api_key = os.environ.get("MT_API_KEY", "")
    if not api_key:
        return None  # No key configured = no auth required
    if creds is None or not secrets.compare_digest(creds.credentials, api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return creds.credentials


from memory_thread.sdk import MemoryClient
from memory_thread.utils.logger import get_logger
from memory_thread.config.settings import settings

log = get_logger(__name__)

# ==============================================================================
# Request Logging Middleware
# ==============================================================================


class RequestLoggingMiddleware:
    """Middleware to log requests with timing using Rich."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Only log API requests, not health/docs
        path = scope.get("path", "")
        if (
            path.startswith("/memory")
            or path.startswith("/galaxy")
            or path in ["/stats", "/health"]
        ):
            # Get method and start time
            method = scope.get("method", "GET")
            start_time = time.perf_counter()

            # Get namespace from headers
            headers = dict(scope.get("headers", []))
            namespace = headers.get(b"x-namespace", b"default").decode()

            # Process request
            await self.app(scope, receive, send)

            # Calculate duration
            duration = (time.perf_counter() - start_time) * 1000

            # Get status code
            status_code = 200
            for item in scope.get("extensions", {}).get("http.response.start", []):
                if isinstance(item, tuple) and len(item) >= 2:
                    status_code = item[1].get("status_code", 200)

            # Format log message
            status_str = f"{status_code}"
            duration_str = f"{duration:>5.0f}ms"

            if status_code >= 500:
                status_str = f"[red]{status_code}[/red]"
            elif status_code >= 400:
                status_str = f"[yellow]{status_code}[/yellow]"
            else:
                status_str = f"[green]{status_code}[/green]"

            # Pad method and path for alignment
            method_padded = f"{method:<6}"
            path_padded = f"{path:<30}"

            # Print formatted log
            print(
                f"  {method_padded}  {path_padded}  {status_str}  {duration_str:<6}  [{namespace}]"
            )

        else:
            await self.app(scope, receive, send)


# ==============================================================================
# Startup / Shutdown
# ==============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    # Startup
    print()

    # Check PostgreSQL and bootstrap AsyncGraphWorker
    postgres_status = "unavailable"
    postgres_latency = None
    _graph_worker = None
    try:
        from memory_thread.db.postgres_client import PostgresClient
        from memory_thread.nervous.graph_worker import AsyncGraphWorker

        pg = PostgresClient()
        start = time.perf_counter()
        with pg.get_cursor() as cur:
            cur.execute("SELECT 1")
        postgres_latency = int((time.perf_counter() - start) * 1000)
        postgres_status = "healthy"

        # Bootstrap graph worker. Replay mode is configurable (Fix #2):
        #   sync      — block startup until all backlog is replayed (old behaviour)
        #   background— start the worker and accept traffic immediately; the graph
        #               fills in as replay runs (default; avoids cold-start stalls
        #               on very large events tables)
        #   skip      — no replay (test environments); also honours legacy
        #               MT_SKIP_GRAPH_FLUSH=1.
        _graph_worker = AsyncGraphWorker(pg)
        replay_mode = os.environ.get("MT_GRAPH_REPLAY", "background").lower()
        if replay_mode == "skip" or os.environ.get("MT_SKIP_GRAPH_FLUSH") == "1":
            log.info("AsyncGraphWorker replay skipped (MT_GRAPH_REPLAY=skip)")
        elif replay_mode == "sync":
            flush_start = time.perf_counter()
            _graph_worker.flush()
            flush_ms = int((time.perf_counter() - flush_start) * 1000)
            log.info("AsyncGraphWorker initial flush complete (%dms)", flush_ms)
            _graph_worker.start()
        else:
            _graph_worker.start()
            log.info("AsyncGraphWorker replaying in background (server ready immediately)")
        global _graph_worker_ref
        _graph_worker_ref = _graph_worker

    except Exception as e:
        log.warning("AsyncGraphWorker could not start (Postgres unavailable?): %s", e)
        postgres_status = "unavailable"

    # Check API auth
    api_key = os.environ.get("MT_API_KEY", "")
    auth_status = "unset — all endpoints open"

    # Print service status
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="green")
    table.add_column(style="cyan")
    table.add_column(style="dim")

    if postgres_latency:
        table.add_row("✓ PostgreSQL", "healthy", f"({postgres_latency}ms)")
    else:
        table.add_row("✗ PostgreSQL", postgres_status, "")

    if not api_key:
        table.add_row("⚠ Auth", "MT_API_KEY", "unset — no auth on any endpoint")
    else:
        table.add_row("✓ Auth", "MT_API_KEY", "configured")

    print(table)
    print()

    yield

    # Shutdown
    print("\n[yellow]Shutting down...[/yellow]")
    # Stop the graph worker before closing clients
    if _graph_worker is not None:
        try:
            _graph_worker.stop()
        except Exception as e:
            log.warning("Error stopping AsyncGraphWorker: %s", e)
    # Close all cached MemoryClient instances (shuts down enrichment pipelines + WAL)
    for namespace, client in list(_client_cache.items()):
        try:
            client.close()
            log.info("Closed MemoryClient for namespace '%s'", namespace)
        except Exception as e:
            log.warning("Error closing MemoryClient for '%s': %s", namespace, e)
    _client_cache.clear()


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
    lifespan=lifespan,
)

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("MT_ALLOWED_ORIGINS", "").split(",")
    if os.environ.get("MT_ALLOWED_ORIGINS")
    else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Namespace", "X-API-Key"],
)

from memory_thread.api.routers import maintenance as maintenance_router

app.include_router(maintenance_router.router)


# ==============================================================================
# Rate Limiter (Simple In-Memory)
# ==============================================================================

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
        now = time.time()
        window_start = now - self.window_seconds
        self._requests[client_id] = [t for t in self._requests[client_id] if t > window_start]
        current_count = len(self._requests[client_id])
        if current_count >= self.requests_per_minute:
            return False, 0
        self._requests[client_id].append(now)
        return True, self.requests_per_minute - current_count - 1

    def reset(self, client_id: str):
        self._requests[client_id] = []


rate_limiter = RateLimiter(requests_per_minute=100)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/", "/health", "/docs", "/redoc", "/openapi.json", "/stats"]:
            return await call_next(request)

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


app.add_middleware(RateLimitMiddleware)


# ==============================================================================
# Request/Response Models
# ==============================================================================


class RememberRequest(BaseModel):
    content: str = Field(..., description="The content to remember")
    source: str = Field("agent", description="Source: 'user', 'agent', 'system'")
    confidence: float = Field(0.8, ge=0, le=1, description="Confidence level (0-1)")
    authority: float = Field(0.5, ge=0, le=1, description="Authority level (0-1)")
    memory_type: str = Field("fact", description="Type: 'fact', 'event', 'preference'")
    namespace: Optional[str] = Field(None, description="Namespace override")

    class Config:
        json_schema_extra = {
            "example": {
                "content": "User prefers dark mode",
                "source": "observation",
                "confidence": 0.9,
            }
        }


class RememberResponse(BaseModel):
    entity_id: str
    message: str


class RecallRequest(BaseModel):
    query: str = Field(..., description="Search query")
    top_k: int = Field(5, ge=1, le=100, description="Max results to return")
    min_truth_score: float = Field(0.3, ge=0, le=1, description="Minimum truth score")
    namespace: Optional[str] = Field(None, description="Namespace override")


class MemoryItem(BaseModel):
    entity_id: str
    content: str
    truth_score: float
    confidence: float
    authority: float
    freshness: float
    source: str
    memory_type: str


class RecallResponse(BaseModel):
    query: str
    total_found: int
    memories: List[MemoryItem]


class FactRequest(BaseModel):
    content: str = Field(..., description="Raw content to store")
    source_uri: Optional[str] = Field(None, description="Origin URI")
    content_type: str = Field("text", description="Type: 'text', 'code', 'log'")
    metadata: Optional[Dict[str, Any]] = None


class FactResponse(BaseModel):
    fact_id: str
    message: str


class BeliefRequest(BaseModel):
    fact_id: str = Field(..., description="Source fact ID")
    belief: str = Field(..., description="The belief/interpretation")
    agent_id: Optional[str] = Field(None, description="Agent ID (default: namespace)")
    confidence: float = Field(0.8, ge=0, le=1)
    authority: float = Field(0.5, ge=0, le=1)


class BeliefResponse(BaseModel):
    belief_id: str
    message: str


class GalaxyQueryRequest(BaseModel):
    operation: str = Field(..., description="SLICE, DICE, DRILL_DOWN, ROLL_UP, SEARCH")
    source_uri: Optional[str] = None
    agent_id: Optional[str] = None
    min_authority: Optional[float] = None
    min_confidence: Optional[float] = None
    query: Optional[str] = None
    belief_id: Optional[str] = None
    top_k: int = Field(10, ge=1, le=100)


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    postgres_connected: bool = False


class GraphSearchRequest(BaseModel):
    query: str = Field(..., description="Search text")
    attr: str = Field("content", description="Vertex attribute to search")
    namespace: Optional[str] = Field(None, description="Filter by namespace")


class GraphPathsRequest(BaseModel):
    source: str = Field(..., description="Source entity ID")
    target: str = Field(..., description="Target entity ID")
    max_hops: int = Field(5, ge=1, le=20, description="Max path length")


class GraphActivationRequest(BaseModel):
    seeds: List[str] = Field(..., min_length=1, description="Seed node IDs to activate from")
    max_depth: int = Field(3, ge=1, le=10, description="Max traversal depth")
    decay_per_hop: float = Field(0.5, ge=0.0, le=1.0, description="Activation decay per hop")
    truth_threshold: float = Field(0.0, ge=0.0, le=1.0, description="Minimum activation threshold")


# ==============================================================================
# Dependencies
# ==============================================================================

_client_cache: dict = {}

# Reference to the running AsyncGraphWorker, exposed for readiness/metrics probes.
_graph_worker_ref = None


def get_client(
    x_namespace: str = Header("default", alias="X-Namespace"),
    namespace_override: Optional[str] = None,
) -> MemoryClient:
    namespace = namespace_override or x_namespace

    if namespace not in _client_cache:
        use_db = os.environ.get("MT_USE_DB_FALSE") != "1"
        _client_cache[namespace] = MemoryClient(
            namespace=namespace, use_db=use_db, default_authority=0.5
        )
    return _client_cache[namespace]


# ==============================================================================
# Routes
# ==============================================================================


@app.get("/", tags=["Health"])
async def root():
    return {"message": "Memory Thread API", "docs": "/docs"}


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    from memory_thread.utils.health import get_health_checker

    checker = get_health_checker()
    result = checker.full_check()

    postgres_connected = result.get("services", {}).get("postgres", {}).get("status") == "healthy"

    return HealthResponse(
        status=result.get("status", "degraded"),
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0",
        postgres_connected=postgres_connected,
    )


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """Kubernetes readiness probe — 200 only if service can accept traffic."""
    from memory_thread.utils.health import get_health_checker

    checker = get_health_checker()
    result = checker.full_check()
    pg_ok = result.get("services", {}).get("postgres", {}).get("status") == "healthy"

    if not pg_ok:
        raise HTTPException(status_code=503, detail="PostgreSQL not available")

    # Optionally gate on initial graph replay completion (Fix #2). Off by default
    # so startup is fast; enable with MT_WAIT_REPLAY_READY=1 for strict readiness.
    if os.environ.get("MT_WAIT_REPLAY_READY") == "1" and _graph_worker_ref is not None:
        if not _graph_worker_ref.is_initial_replay_done():
            raise HTTPException(status_code=503, detail="Graph replay still in progress")
    return {"ready": True, "status": "healthy"}


@app.get("/health/live", tags=["Health"])
async def liveness_check():
    """Kubernetes liveness probe — 200 if process is running."""
    return {"alive": True}


_metrics_store = {"requests_total": 0, "requests_errors": 0, "events_processed": 0}


@app.get("/metrics", response_class=PlainTextResponse, tags=["Health"])
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint."""
    from memory_thread.services.metrics import get_metrics

    lines = [
        "# HELP mt_requests_total Total requests processed",
        "# TYPE mt_requests_total counter",
        f"mt_requests_total {_metrics_store['requests_total']}",
        "",
        "# HELP mt_requests_errors Total request errors",
        "# TYPE mt_requests_errors counter",
        f"mt_requests_errors {_metrics_store['requests_errors']}",
        "",
        "# HELP mt_events_processed Total events processed",
        "# TYPE mt_events_processed counter",
        f"mt_events_processed {_metrics_store['events_processed']}",
        "",
        "# HELP mt_up Service up status",
        "# TYPE mt_up gauge",
        "mt_up 1",
    ]

    # Append in-process operational metrics (replay + recall health).
    for name, data in get_metrics().items():
        if "avg" in data:
            lines.append(f"# TYPE mt_{name} histogram")
            lines.append(f"mt_{name}_count {data['count']}")
            lines.append(f"mt_{name}_sum {round(data['sum'], 3)}")
            lines.append(f"mt_{name}_max {round(data['max'], 3)}")
        else:
            lines.append(f"# TYPE mt_{name} counter")
            lines.append(f"mt_{name} {data['count']}")
        lines.append("")

    try:
        from prometheus_client import generate_latest, REGISTRY

        # If the prometheus client is available, prepend its registry too.
        return generate_latest(REGISTRY).decode("utf-8") + "\n".join(lines)
    except Exception:
        return "\n".join(lines)


@app.get("/version", tags=["Health"])
async def get_version():
    """Returns version and build information."""
    return {"version": "1.0.0", "name": "Memory Thread API", "api_version": "v1"}


@app.post(
    "/memory/remember",
    response_model=RememberResponse,
    tags=["Memory"],
    dependencies=[Depends(verify_token)],
)
async def remember(request: RememberRequest):
    try:
        namespace = request.namespace or "default"
        client = get_client(namespace_override=namespace)

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


@app.post(
    "/memory/recall",
    response_model=RecallResponse,
    tags=["Memory"],
    dependencies=[Depends(verify_token)],
)
async def recall(request: RecallRequest):
    try:
        namespace = request.namespace or "default"
        client = get_client(namespace_override=namespace)

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


@app.post("/memory/check_contradiction", tags=["Memory"], dependencies=[Depends(verify_token)])
async def check_contradiction(request: RecallRequest):
    try:
        namespace = request.namespace or "default"
        client = get_client(namespace_override=namespace)

        result = client.check_contradiction(request.query)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats", dependencies=[Depends(verify_token)])
async def get_stats(namespace: str = "default"):
    """Get Memory Thread stats."""
    try:
        client = get_client(namespace_override=namespace)
        stats = client.get_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/memory/{entity_id}", tags=["Memory"], dependencies=[Depends(verify_token)])
async def forget_memory(entity_id: str, client: MemoryClient = Depends(get_client)):
    """Delete a memory by entity_id."""
    try:
        import uuid

        result = client.forget(uuid.UUID(entity_id))
        return {"success": result, "entity_id": entity_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memory/{entity_id}/golden-thread", tags=["Memory"], dependencies=[Depends(verify_token)])
async def get_golden_thread(entity_id: str, client: MemoryClient = Depends(get_client)):
    """
    Get the complete causal chain for a memory.
    Shows every event that shaped this memory from creation to now.
    """
    try:
        import uuid as _uuid

        result = client.get_golden_thread(_uuid.UUID(entity_id))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid entity_id: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/galaxy/fact",
    response_model=FactResponse,
    tags=["Galaxy"],
    dependencies=[Depends(verify_token)],
)
async def ingest_fact(request: FactRequest, client: MemoryClient = Depends(get_client)):
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


@app.post(
    "/galaxy/belief",
    response_model=BeliefResponse,
    tags=["Galaxy"],
    dependencies=[Depends(verify_token)],
)
async def derive_belief(request: BeliefRequest, client: MemoryClient = Depends(get_client)):
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


@app.post("/galaxy/query", tags=["Galaxy"], dependencies=[Depends(verify_token)])
async def query_galaxy(request: GalaxyQueryRequest, client: MemoryClient = Depends(get_client)):
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


@app.get("/galaxy/stats", tags=["Galaxy"], dependencies=[Depends(verify_token)])
async def galaxy_stats(client: MemoryClient = Depends(get_client)):
    try:
        return client.galaxy_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/galaxy/conflicts", tags=["Galaxy"], dependencies=[Depends(verify_token)])
async def galaxy_conflicts(client: MemoryClient = Depends(get_client)):
    try:
        return {"conflicts": client.get_galaxy_conflicts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# Graph Endpoints
# ==============================================================================

GRAPH_TAG = "Graph"


@app.get("/graph", tags=[GRAPH_TAG], dependencies=[Depends(verify_token)])
async def get_graph(namespace: Optional[str] = None):
    """Export the full cognitive graph with positions, communities, and centralities."""
    try:
        from memory_thread.services.graph_engine import graph_engine

        return graph_engine.export_graph_json(namespace=namespace)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph/stats", tags=[GRAPH_TAG], dependencies=[Depends(verify_token)])
async def get_graph_stats(namespace: Optional[str] = None):
    """Graph-level statistics: node/edge counts, community count, density."""
    try:
        from memory_thread.services.graph_engine import graph_engine

        export = graph_engine.export_graph_json(namespace=namespace)
        nodes = export["nodes"]
        edges = export["edges"]
        n = len(nodes)
        e = len(edges)
        max_possible = n * (n - 1) / 2 if n > 1 else 1
        return {
            "node_count": n,
            "edge_count": e,
            "community_count": export["metadata"]["community_count"],
            "density": round(e / max_possible, 6) if max_possible > 0 else 0.0,
            "avg_centrality": round(sum(node["centrality"] for node in nodes) / n, 4)
            if n > 0
            else 0.0,
            "avg_pagerank": round(sum(node["pagerank"] for node in nodes) / n, 6) if n > 0 else 0.0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/graph/search", tags=[GRAPH_TAG], dependencies=[Depends(verify_token)])
async def search_graph(request: GraphSearchRequest):
    """Fuzzy search nodes by content."""
    try:
        from memory_thread.services.graph_engine import graph_engine

        results = graph_engine.search_nodes(request.query, attr=request.attr)
        if request.namespace:
            results = [
                n
                for n in results
                if graph_engine.graph.vs.find(name=n).attributes().get("namespace")
                == request.namespace
            ]
        enriched = []
        for node_id in results[:50]:
            try:
                v = graph_engine.graph.vs.find(name=node_id)
                attrs = v.attributes()
                enriched.append(
                    {
                        "id": node_id,
                        "content": attrs.get("content", ""),
                        "type": attrs.get("type", ""),
                        "namespace": attrs.get("namespace", ""),
                        "truth_confidence": attrs.get("truth_confidence", 0.5),
                    }
                )
            except (ValueError, KeyError):
                pass
        return {"query": request.query, "total": len(results), "results": enriched}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/graph/paths", tags=[GRAPH_TAG], dependencies=[Depends(verify_token)])
async def find_path(request: GraphPathsRequest):
    """Shortest path between two entities in the cognitive graph."""
    try:
        from memory_thread.services.graph_engine import graph_engine

        path = graph_engine.shortest_path(request.source, request.target)
        if not path:
            return {"found": False, "path": [], "length": 0}
        return {
            "found": True,
            "path": path,
            "length": len(path) - 1,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/graph/activation", tags=[GRAPH_TAG], dependencies=[Depends(verify_token)])
async def spreading_activation(request: GraphActivationRequest):
    """Run spreading activation from seed nodes and return the activation map."""
    try:
        from memory_thread.services.graph_engine import graph_engine

        result = graph_engine.activation(
            seeds=request.seeds,
            max_depth=request.max_depth,
            decay_per_hop=request.decay_per_hop,
            truth_threshold=request.truth_threshold,
        )
        sorted_results = sorted(result.items(), key=lambda x: -x[1])
        return {
            "seeds": request.seeds,
            "activation_map": {k: v for k, v in sorted_results},
            "total_activated": len(result),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# SSE Event Stream
# ==============================================================================


@app.get("/events", tags=["Events"])
def event_stream():
    """SSE endpoint — streams graph mutations, WAL commits, and health deltas to connected clients."""
    from memory_thread.services.event_bus import event_bus
    import queue

    q = event_bus.subscribe()
    try:
        while True:
            try:
                msg = q.get(timeout=30)
                yield f"data: {msg}\n\n"
            except queue.Empty:
                yield ": keepalive\n\n"
    except GeneratorExit:
        pass
    finally:
        event_bus.unsubscribe(q)


# ==============================================================================
# Main
# ==============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
