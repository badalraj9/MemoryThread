# API Reference

Memory Thread Engine REST API documentation.

**Base URL:** `http://localhost:8000`

---

## Health & Monitoring

### `GET /`

Quick health check for load balancers.

**Response:**

```json
{
  "status": "active",
  "version": "0.4.0"
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
  "timestamp": "2025-01-24T10:00:00Z"
}
```

**Status Values:**

- `healthy` — All services operational
- `degraded` — Some services down, but functional
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
  "version": "0.4.0",
  "name": "Memory Thread Engine",
  "api_version": "v1"
}
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

Ingest a batch of events into the memory system.

**Request:**

```json
{
  "producer_id": "agent-001",
  "events": [
    {
      "content": "User prefers dark mode",
      "timestamp": "2025-01-24T10:00:00Z"
    },
    {
      "content": "User lives in Mumbai",
      "timestamp": "2025-01-24T10:01:00Z"
    }
  ]
}
```

**Response (200):**

```json
{
  "status": "accepted",
  "count": 2
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

Get duplicate entity merge proposals.

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

Approve and execute a merge proposal.

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

Dashboard metrics for system health.

**Response:**

```json
{
  "entities_count": 1000,
  "duplicates_detected": 5,
  "pruning_candidates": 20,
  "average_freshness": 0.88
}
```

---

## Error Responses

All endpoints may return:

| Status | Meaning                                               |
| ------ | ----------------------------------------------------- |
| `400`  | Bad request (invalid JSON)                            |
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

Currently no rate limiting is enforced. Use the `/control/throttle` endpoint to implement client-side adaptive throttling based on system pressure.

---

## Authentication

Currently no authentication required. For production, implement JWT or API key authentication.
