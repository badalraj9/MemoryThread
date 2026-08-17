# Strategy 3: Staged Log Rebuild — Bulk Ingestion Plan

## What's dead right

- **Sequence ID** — UUID-based cursor is broken, full stop. The current `SELECT * FROM events ORDER BY timestamp` works for 5K events, fails at 100K. `BIGSERIAL` with an index-scan cursor is the cheapest, highest-impact change. Schema diff: one column + one index.

- **Structural-only graph** — This is the actual scaling ceiling, not rebuild speed. Storing full conversation text in igraph vertex attributes guarantees OOM past ~100K events. Keeping only `entity_id` + `sequence_id` in the graph, with content fetched via `SELECT ... WHERE id IN (...)` from PG, is the right direction. But it touches every graph consumer — `search_nodes()`, `recall()`, `golden_thread.trace()`, `context_monitor.observe()` — so it needs a careful rollout.

## Implementation

### Worker: `memory_thread/nervous/graph_worker.py`

Reads from the existing `events` table (not a new table), parses `truth_vector` from JSONB, reconstructs Pydantic `Event` objects, and replays them through `graph_engine._apply()`.

```python
class AsyncGraphWorker:
    """Background thread: replay PG events into igraph asynchronously."""

    def __init__(self, pg, batch_size=1000, poll_interval=1.0):
        self.pg = pg
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self._ensure_cursor_table()
        self._ensure_influence_table()
```

- Cursor: `ingestion_cursor` table tracks `last_event_id UUID`. Worker queries `WHERE timestamp > cursor_timestamp OR (timestamp = cursor_timestamp AND id > cursor_id) ORDER BY timestamp, id`.
- `_apply()` is idempotent — replaying already-applied events is a no-op (vertex existence check).
- No 5-second MVCC buffer — unnecessary given idempotent writes and single-threaded per-client.
- `galaxy_influence_matrix` table created on worker init.

### Schema additions required

```sql
-- Cursor tracking (created by worker on init)
CREATE TABLE IF NOT EXISTS ingestion_cursor (
    system_key VARCHAR(100) PRIMARY KEY,
    last_event_id UUID,
    last_processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Multi-agent trust matrix (created by worker on init)
CREATE TABLE IF NOT EXISTS galaxy_influence_matrix (
    requesting_namespace VARCHAR(255) NOT NULL,
    observed_namespace VARCHAR(255) NOT NULL,
    trust_weight FLOAT NOT NULL CHECK (trust_weight >= 0.0 AND trust_weight <= 1.0),
    PRIMARY KEY (requesting_namespace, observed_namespace)
);
```

No changes to the existing `events` table. No `sequence_id` required for initial deployment — cursor works on `(timestamp, id)`.

## Execution order

1. **Deploy worker** — `AsyncGraphWorker` can run alongside the existing sync path. `_apply()` is idempotent, so double-apply is safe (wasted CPU, no corruption).
2. **Strip graph apply from sync path** — once worker is stable, remove `graph_engine.apply_event()` from `remember()`. Worker becomes sole graph writer.
3. **Add `sequence_id BIGSERIAL`** — optimizes cursor query from index-scan on `(timestamp, id)` to integer comparison on `(sequence_id)`. Worker switches cursor after migration.
4. **Strip heavy attributes from igraph** — move content fetch to PG `SELECT ... WHERE id IN (...)`. Touches `search_nodes()`, `recall()`, `golden_thread.trace()`, `context_monitor.observe()`.
5. **Move ContradictionWorker + EnrichmentPipeline** — extract into the async worker loop so they process events as they're replayed, not detached from the graph.

## Remaining work

### 1. Strip full rebuild from startup (highest impact)
`client.py:274` calls `graph_engine.rebuild(self._pg)` — a `SELECT * FROM events ORDER BY timestamp` that replays every row. On accumulated PG data this takes minutes. Fix:
- Keep `load_snapshot()` for fast boot
- Remove `rebuild()` fallback — let `AsyncGraphWorker` catch up incrementally from cursor
- The graph is still populated by sync `_apply()` in `remember()`, so no test breakage

### 2. Remove `contradiction_audit.batch_id NOT NULL`
Migration 12 (`runner.py:261`) creates `batch_id UUID NOT NULL` with no default. The `ContradictionWorker` inserts rows without providing `batch_id`, causing `column "batch_id" does not exist` errors on every contradiction check. Fix: add `DEFAULT gen_random_uuid()` or make nullable.

### 3. Wire `AsyncGraphWorker` into server/bootstrap
The worker class is fully implemented at `memory_thread/nervous/graph_worker.py` (cursor table, influence table, batch replay, daemon thread loop) but never started. Needs:
- Start call in server bootstrap or app init
- Stop call in shutdown
- Worker reads from `events` table, uses `ingestion_cursor` for position tracking

### 4. Strip sync `_apply()` from `remember()` (after worker is live in prod)
Once the worker is proven stable, remove `graph_engine.apply_event(event)` from `_remember_direct()`. Breaks PG tests that expect immediate consistency — add `worker.flush()` or `time.sleep(0.1)` in test fixtures. Enables true async write path.

### 5. Add `sequence_id BIGSERIAL` to `events` table
Optimizes worker cursor from `ORDER BY (timestamp, id)` index-scan to integer comparison. One-column migration. Worker switches cursor query after migration is applied.

### 6. Strip heavy content attributes from igraph vertices
Conversation text stored in igraph vertex attributes guarantees OOM past ~100K events. Keep only `entity_id` (UUID) in graph, fetch content via `SELECT ... WHERE id IN (...)`. Touches `search_nodes()`, `recall()`, `golden_thread.trace()`, `context_monitor.observe()` — needs careful rollout.

### 7. Move `ContradictionWorker` + `EnrichmentPipeline` into worker loop
Currently these run detached from the graph replay. Processing them inside the worker's batch loop ensures they fire on each event as it's applied, not on a separate schedule.

## Design decisions

- **`truth_vector` is JSONB** — worker parses it back to `TruthVector` on read. No schema change needed.
- **Cursor uses `(timestamp, id)`** — works without schema migration. `ORDER BY timestamp, id` is deterministic even for same-timestamp events.
- **Double-apply is safe** — `_apply()` checks `_vertex_exists()` before creating any node. Redundant work but no data corruption.
- **Sync `_apply()` kept in `remember()` for now** — avoids breaking PG tests. Worker re-applies same events (idempotent, wasted CPU). To be stripped after worker is proven in production.
