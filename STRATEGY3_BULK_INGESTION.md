# Strategy 3: Staged Log Rebuild — Bulk Ingestion Plan

## What's dead right

- **Sequence ID** — UUID-based cursor is broken, full stop. The current `SELECT * FROM events ORDER BY timestamp` works for 5K events, fails at 100K. `BIGSERIAL` with an index-scan cursor is the cheapest, highest-impact change. Schema diff: one column + one index.

- **Structural-only graph** — This is the actual scaling ceiling, not rebuild speed. Storing full conversation text in igraph vertex attributes guarantees OOM past ~100K events. Keeping only `entity_id` + `sequence_id` in the graph, with content fetched via `SELECT ... WHERE id IN (...)` from PG, is the right direction. But it touches every graph consumer — `search_nodes()`, `recall()`, `golden_thread.trace()`, `context_monitor.observe()` — so it needs a careful rollout.

## What I'd push back on

- **5-second MVCC buffer** — Correct in theory, but over-engineering for this system. The current write path is single-threaded per-client. Two clients writing concurrently *could* interleave, but `remember()` does `ON CONFLICT (id) DO NOTHING` and `_apply()` is idempotent via `_vertex_exists()`. The buffer adds 5s of latency per cycle for a race that practically never triggers in an append-only ledger. I'd skip it unless you see evidence of the bug in production.

- **The ContradictionWorker and EnrichmentPipeline** — Currently started as daemon threads in `MemoryClient.__init__`. If the async worker is the sole graph writer, these need to move there too, or they become orphans writing to a stale graph. It's manageable but worth calling out.

## What's missing

- **Crash recovery + cursor atomicity** — If the worker crashes *between* `_apply()` batches and `UPDATE ingestion_cursor`, replaying the batch is safe (idempotent). But the cursor update needs to be in the same transaction as... well, there's no PG-side transaction for the graph since it's in-memory. A simple fix: write `last_sequence_id` after every N events within the batch, not just at the end. That way crash replay overlaps at most N events instead of 5000.

## Verdict

**Strategy 3 is the right call.** If I were sequencing the work:

1. Add `sequence_id BIGSERIAL` to `events` table + `ingestion_cursor` table (1-2 hours, no code change to existing paths)
2. Strip heavy attributes from igraph vertices, move content fetch to PG (bigger refactor, 2-3 days)
3. Extract `ContradictionWorker` + `EnrichmentPipeline` into the async worker
4. Make the write path thin (skip graph apply on `remember()`)
