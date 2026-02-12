"""
Memory Thread Engine API.

FastAPI application with health monitoring and Prometheus metrics.
"""
import signal
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from typing import Dict, Any

from memory_thread.api.gateway import router as gateway_router
from memory_thread.api.routers import maintenance
from memory_thread.utils.health import get_health_checker
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# Metrics storage (in production, use prometheus_client properly)
_metrics = {
    "requests_total": 0,
    "requests_errors": 0,
    "events_processed": 0
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Manages startup and shutdown events.
    """
    # Startup
    log.info("Memory Thread Engine starting up...")
    
    # Perform initial health check
    try:
        checker = get_health_checker()
        status = checker.full_check()
        log.info(f"Initial health check: {status['status']}")
        for service, service_status in status.get('services', {}).items():
            if service_status.get('status') == 'healthy':
                log.info(f"  ✓ {service}: healthy ({service_status.get('latency_ms', '?')}ms)")
            else:
                log.warning(f"  ✗ {service}: {service_status.get('status')} - {service_status.get('error', 'unknown')}")
    except Exception as e:
        log.warning(f"Initial health check failed: {e}")
    
    yield
    
    # Shutdown
    log.info("Memory Thread Engine shutting down...")
    
    # Graceful cleanup
    try:
        from memory_thread.db.postgres_client import close_pool
        close_pool()
        log.info("Database connections closed")
    except Exception as e:
        log.warning(f"Error during shutdown: {e}")
    
    log.info("Shutdown complete")


app = FastAPI(
    title="Memory Thread Engine",
    version="0.4.0",
    description="""
## Memory Thread - Truth-Aware AI Memory System

Memory Thread is an event-sourced memory engine for AI agents that:
- **Stores** facts with explicit uncertainty (Truth Vectors)
- **Decays** memories naturally over time
- **Resolves** contradictions mathematically
- **Replays** to any point in history

### Key Concepts
- **Truth Vector**: (Confidence, Authority, Freshness, Corroboration)
- **Event Sourcing**: All state derived from immutable event log
- **Decay Curves**: Different memory types fade at different rates

### Quick Start
```python
from memory_thread.sdk import MemoryClient
mt = MemoryClient()
mt.remember("User prefers dark mode")
memories = mt.recall("user preferences")
```
    """,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "health", "description": "Health and monitoring endpoints"},
        {"name": "ingestion", "description": "Event ingestion endpoints"},
        {"name": "maintenance", "description": "Memory maintenance operations"},
    ],
    contact={
        "name": "Memory Thread",
        "url": "https://github.com/badalraj9/MemoryThread",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
)

app.include_router(gateway_router)
app.include_router(maintenance.router)


@app.get("/")
def root_health_check() -> Dict[str, str]:
    """Simple health check for load balancers."""
    return {"status": "active", "version": "0.4.0"}


@app.get("/health")
def detailed_health_check() -> Dict[str, Any]:
    """
    Detailed health check with service statuses.
    
    Returns:
        Comprehensive health status including:
        - Overall status (healthy/degraded/unhealthy)
        - Individual service statuses
        - Response latencies
    """
    checker = get_health_checker()
    return checker.full_check()


@app.get("/health/ready")
def readiness_check() -> Dict[str, Any]:
    """
    Kubernetes-style readiness probe.
    Returns 200 only if the service can accept traffic.
    """
    checker = get_health_checker()
    status = checker.full_check()
    
    if status["status"] == "unhealthy":
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=status)
    
    return {"ready": True, "status": status["status"]}


@app.get("/health/live")
def liveness_check() -> Dict[str, bool]:
    """
    Kubernetes-style liveness probe.
    Returns 200 if the process is running (even if degraded).
    """
    return {"alive": True}


@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics() -> str:
    """
    Prometheus-compatible metrics endpoint.
    
    Returns metrics in Prometheus exposition format.
    """
    try:
        from prometheus_client import generate_latest, REGISTRY, Counter, Gauge
        
        # Attempt to generate from prometheus_client if properly configured
        return generate_latest(REGISTRY).decode('utf-8')
    except Exception:
        # Fallback to simple metrics format
        lines = [
            "# HELP mt_requests_total Total requests processed",
            "# TYPE mt_requests_total counter",
            f"mt_requests_total {_metrics['requests_total']}",
            "",
            "# HELP mt_requests_errors Total request errors",
            "# TYPE mt_requests_errors counter",
            f"mt_requests_errors {_metrics['requests_errors']}",
            "",
            "# HELP mt_events_processed Total events processed",
            "# TYPE mt_events_processed counter",
            f"mt_events_processed {_metrics['events_processed']}",
            "",
            "# HELP mt_up Service up status",
            "# TYPE mt_up gauge",
            "mt_up 1",
        ]
        return "\n".join(lines)


@app.get("/version")
def get_version() -> Dict[str, str]:
    """Returns version and build information."""
    return {
        "version": "0.4.0",
        "name": "Memory Thread Engine",
        "api_version": "v1"
    }
