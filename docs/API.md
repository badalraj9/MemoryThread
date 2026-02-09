# API Reference

Memory Thread Engine REST API documentation.

**Base URL:** `http://localhost:8000`  
**Version:** `2.0.0`

---

## Authentication

All mutating endpoints require a Bearer token. Obtain tokens via the client registry:

```bash
# Register an API client (S-CLASS required)
mt clients create my-app

# Use the returned API key in requests
curl -H "Authorization: Bearer mt_sk_..." http://localhost:8000/memory/recall
```

**Header Format:**

```
Authorization: Bearer <api_key>
```

**Unauthenticated endpoints:** `/`, `/health`, `/health/ready`, `/health/live`, `/version`

---

## Health & Monitoring

### `GET /`

Quick health check for load balancers.

**Response:**

```json
{
  "status": "active",
  "version": "2.0.0"
}
```

---

### `GET /health`

Detailed health check with service statuses.

**Response:**

```json
{
  "status": "healthy",
  "services": {
    "postgres": {
      "status": "healthy",
      "latency_ms": 12
    },
    "qdrant": {
      "status": "healthy",
      "latency_ms": 5
    }
  },
  "memory_count": 1523,
  "wal_pending": 0,
  "timestamp": "2026-02-10T02:00:00Z"
}
```

**Status Values:**

- `healthy` — All services operational
- `degraded` — Some services down, but functional (using fallbacks)
- `unhealthy` — Critical services down

---

### `GET /health/ready`

Kubernetes-style readiness probe.

**Response (200):**

```json
{
  "ready": true,
  "status": "healthy"
}
```

**Response (503):** Service not ready to accept traffic.

---

### `GET /health/live`

Kubernetes-style liveness probe.

**Response:**

```json
{
  "alive": true
}
```

---

### `GET /metrics`

Prometheus-compatible metrics endpoint.

**Response (text/plain):**

```
# HELP mt_requests_total Total requests processed
# TYPE mt_requests_total counter
mt_requests_total 1234

# HELP mt_events_processed Total events processed
# TYPE mt_events_processed counter
mt_events_processed 567890

# HELP mt_truth_score_avg Average truth score
# TYPE mt_truth_score_avg gauge
mt_truth_score_avg 0.82

# HELP mt_up Service up status
# TYPE mt_up gauge
mt_up 1
```

---

### `GET /version`

Version and build information.

**Response:**

```json
{
  "version": "2.0.0",
  "name": "Memory Thread Engine",
  "api_version": "v2"
}
```

---

## Memory Operations

### `POST /memory/chat`

**Auth Required.** Autonomous chat — auto-remembers input, builds context, generates response.

**Request:**

```json
{
  "message": "My project deadline is March 15th",
  "system_prompt": "You are a helpful assistant with memory.",
  "use_local": false
}
```

**Response:**

```json
{
  "response": "I've noted that your project deadline is March 15th. Would you like me to help you plan the remaining milestones?",
  "memories_used": 12,
  "contradiction_detected": false
}
```

---

### `POST /memory/remember`

**Auth Required.** Explicitly store a memory with truth vector.

**Request:**

```json
{
  "content": "User prefers dark mode",
  "source": "agent",
  "confidence": 0.9,
  "authority": 0.5,
  "memory_type": "preference"
}
```

**Response:**

```json
{
  "entity_id": "550e8400-e29b-41d4-a716-446655440000",
  "truth_score": 0.72
}
```

---

### `POST /memory/recall`

**Auth Required.** Query stored memories with truth-ranked results.

**Request:**

```json
{
  "query": "project deadline",
  "top_k": 10,
  "min_truth_score": 0.3,
  "search_type": "hybrid"
}
```

**Response:**

```json
{
  "results": [
    {
      "entity_id": "550e8400-...",
      "content": "Project deadline is March 15th",
      "truth_score": 0.92,
      "memory_type": "fact",
      "created_at": "2026-02-10T02:00:00Z"
    }
  ],
  "total": 1
}
```

---

## Galaxy Schema

### `POST /galaxy/fact`

**Auth Required.** Ingest an immutable fact into Layer 0.

**Request:**

```json
{
  "content": "auth_service.py handles JWT token parsing",
  "source_uri": "file://src/auth_service.py"
}
```

**Response:**

```json
{
  "fact_id": "fact-uuid",
  "status": "ingested"
}
```

---

### `POST /galaxy/belief`

**Auth Required.** Derive a belief from a fact (Layer 1).

**Request:**

```json
{
  "fact_id": "fact-uuid",
  "belief": "Legacy OAuth implementation; potential vulnerability",
  "agent_id": "security-bot",
  "confidence": 0.7
}
```

**Response:**

```json
{
  "belief_id": "belief-uuid",
  "status": "derived"
}
```

---

### `GET /galaxy/conflicts`

**Auth Required.** Get conflicting beliefs across agents.

**Response:**

```json
[
  {
    "fact_id": "fact-uuid",
    "beliefs": [
      {
        "agent": "coder-bot",
        "belief": "JWT handling is secure",
        "confidence": 0.9
      },
      {
        "agent": "security-bot",
        "belief": "Legacy OAuth is vulnerable",
        "confidence": 0.7
      }
    ]
  }
]
```

---

## Event Ingestion

### `POST /register`

Register a producer (client) with the engine.

**Request:**

```json
{
  "producer_id": "agent-001",
  "type": "python",
  "version": "1.0.0"
}
```

**Response:**

```json
{
  "status": "ok",
  "throttle": 0.1
}
```

- `throttle`: Current system pressure (0.0-1.0). High values indicate backpressure.

---

### `POST /ingest`

**Auth Required.** Ingest a batch of events into the memory system.

**Request:**

```json
{
  "producer_id": "agent-001",
  "events": [
    {
      "content": "User prefers dark mode",
      "timestamp": "2026-02-10T10:00:00Z"
    }
  ]
}
```

**Response (200):**

```json
{
  "status": "accepted",
  "count": 1
}
```

**Response (503):** System overloaded, backpressure active.

---

### `GET /control/throttle`

Get current system pressure for adaptive ingestion.

**Response:**

```json
{
  "pressure": 0.15
}
```

- `pressure < 0.5`: Safe to send at full speed
- `pressure 0.5-0.9`: Slow down ingestion
- `pressure > 0.9`: System overloaded, expect 503s

---

## Maintenance

### `GET /maintenance/proposals`

**Auth Required.** Get duplicate entity merge proposals.

**Response:**

```json
[
  {
    "source_entity": { "id": "...", "name": "J. Smith" },
    "target_entity": { "id": "...", "name": "John Smith" },
    "confidence": 0.92,
    "reason": "95% embedding similarity + same email"
  }
]
```

---

### `POST /maintenance/approve/merge`

**Auth Required.** Approve and execute a merge proposal.

**Request:**

```json
{
  "source_entity": { "id": "uuid-1" },
  "target_entity": { "id": "uuid-2" },
  "confidence": 0.92
}
```

**Response:**

```json
{
  "status": "merged",
  "source": "uuid-1",
  "target": "uuid-2"
}
```

---

### `GET /maintenance/health/stats`

**Auth Required.** Dashboard metrics for system health.

**Response:**

```json
{
  "entities_count": 1000,
  "duplicates_detected": 5,
  "pruning_candidates": 20,
  "average_freshness": 0.88,
  "wal_entries": 42,
  "health_score": 0.95
}
```

---

## Error Responses

All endpoints may return:

| Status | Meaning                                               |
| ------ | ----------------------------------------------------- |
| `400`  | Bad request (invalid JSON)                            |
| `401`  | Unauthorized (missing or invalid API key)             |
| `403`  | Forbidden (insufficient RBAC clearance)               |
| `500`  | Internal server error                                 |
| `503`  | Service unavailable (overloaded or dependencies down) |

**Error Format:**

```json
{
  "detail": "Error message here"
}
```

---

## Rate Limiting

Rate limiting is enforced per API key based on the client's associated RBAC role. Exceeding limits returns `429 Too Many Requests` with a `Retry-After` header.

Use the `/control/throttle` endpoint for client-side adaptive throttling based on system pressure.
