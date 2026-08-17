# CRITICAL — Recall/Startup Latency Investigation (handoff)

**Status:** Investigation complete. **Fixes IMPLEMENTED (this session):**
- **Deadlock fix:** `graph_engine._write_lock` changed `Lock` → `RLock()` (was hanging every `use_db=True` startup — `client.py:286` held the lock while `load_snapshot` re-acquired it). Verified: `test_graceful_degradation` + `test_postgres_integration` now pass.
- **Fix #1 / A — O(1) name→index map** (`graph_engine.py`): replaced the `Set` existence index with `self._vertex_index: Dict[str,int]` plus a lazy generation counter (`_graph_generation`/`_index_generation`) so lookups self-detect staleness after index-shifting ops (merge/load) instead of doing O(V) `vs.find` scans. All `vs.find(name=..).index` call sites in activation/get_neighbors/shortest_path/centrality/retrieval now route through `_vidx()`.
- **Fix #2 — hoisted name set** (`retrieval_service.retrieve_by_activation`): built once before the loop (confirmed present).
- **Fix #3 / B — content cache on entity vertex**: every `_apply` writes `cached_content`/`last_event_id`/`last_event_ts` onto the entity vertex; `content_resolver.resolve_content` reads O(1), falling back to O(E) scan only for legacy graphs. `load_snapshot` backfills old graphs via `_backfill_entity_content()`.
- **Fix #4 — worker self-heal (Defect A)** (`graph_worker.py`): if graph empty but events exist, cursor reset to NULL for full replay (confirmed present).
- **C — BM25-lite keyword index** (`client.py`): inverted index + BM25 ranking over `_memories`, replacing the O(M) full scan on the keyword-fallback path. Tokenization kept whitespace-delimited to preserve cross-namespace isolation semantics.
- **D — single-pass dual-namespace recall** (`client.py`): when global != project, one activation pass over both namespaces (was two full `_recall_impl` calls). Union + dedup by entity id, global memories weighted by `GLOBAL_AUTHORITY_WEIGHT`.

**Validation so far:** full suite green (75 passed, 2 skipped — the 2 skips are perf benchmarks needing `MT_RUN_PERF=1`). Fast graph-only recall benchmark shows the hot path dropped from O(V) to O(K) (~1000× at V=10k vs documented before-numbers). Namespace-tiering foundation added (see below), disabled by default.

**NEXT SESSION (plan):** see "Next Session Plan" section at the end of this file.

---

## TL;DR

1. `rebuild()` is **gone from the live path**, but the O(N²) cost was **moved, not eliminated** — it now lives in `AsyncGraphWorker.flush()` which runs synchronously at startup (server.py lifespan).
2. Per-recall latency **scales ~linearly with graph vertex count V**, because every recall performs multiple full-graph O(V) scans (`_resolve_seeds` ×2, `retrieve_by_activation` scoring loop), and **superlinearly** (O(K·(V+E))) once activation is non-trivial.
3. Keyword fallback is an **O(M) full `_memories` dict scan** — this is what fires on every recall when the graph is empty or has no seed match.
4. **Silent-failure edge (Defect A):** if the graph is empty/stale but the PG cursor is advanced, `flush()` does nothing and **all recall silently degrades to the keyword path**. Most dangerous of the findings.
5. The DB queries themselves are **indexed and fast** (<10ms, verified with EXPLAIN ANALYZE). The bottlenecks are in-memory (igraph) — the DB is not the problem.

---

## Findings (with anchors)

### Step 1 — `rebuild()` is dead code in the live path
- Only remaining references: docstring `graph_engine.py:56`, test `tests/test_postgres_integration.py:258`, docs.
- Live path: `client.py:286-291` (`load_snapshot` + mark built), `server.py:159-166` (worker `flush()` then `start()`).
- No debug endpoint / retry path / exception handler calls it. ✅ fix held.

### Step 2 — AsyncGraphWorker cursor: no steady-state full replay, but 2 real defects
- Incremental query is correct and **indexed**: `WHERE timestamp > cursor OR (timestamp = cursor AND id > cursor)`. EXPLAIN ANALYZE on dirty DB → uses `idx_events_timestamp` + incremental sort, **~9ms**. Not a DB-scan issue.
- **Defect A (silent empty graph):** cursor lives in PG, graph lives in memory. If snapshot missing/stale (crash, manual graph reset) while cursor is advanced → `flush()` finds no new events → graph stays **empty** → every recall falls back to keyword. **Reproduced live**: after `graph_engine.clear()`, `flush()` took 25ms and built 0 vertices despite 4,242 events.
- **Defect B (first-run / NULL-cursor full replay):** `_process_batch` does `SELECT * FROM events ORDER BY timestamp, id LIMIT 1000` when cursor is NULL (graph_worker.py:130-134). First run replays the whole table; the igraph applies are O(N²) (see Fix #1). This is the old rebuild cost renamed.

### Step 3 & 5 — Where time actually goes (measured, medians)

| state | events | graph V | flush (startup) | seeds | retr | kw | e2e recall |
|---|---|---|---|---|---|---|---|
| **DIRTY** (live DB, ~50 test namespaces + orphans) | 4,242 | 8,484 | **4,163 ms** | 75 ms | 26 ms | 0.1 ms | **110 ms** |
| CLEAN | 2,000 | 4,000 | 982 ms | 34 ms | 12 ms | ~0 | 53 ms |
| CLEAN | 8,000 | 16,000 | **15,474 ms** | 159–267 ms | 43–75 ms | ~0 | 200–313 ms |

- **Startup is superlinear (O(N²))**: 2× events → ~3.7× flush time. Each apply costs `_apply` → `_vertex_exists` → `igraph.vs.find` = **linear scan** (measured `apply_event` = **2.385 ms avg at V=8,484**).
- **Seeds**: `_resolve_seeds` (client.py:758-799) runs **two** full `search_nodes` scans (graph_engine.py:683) + a `vs.find` per seed. ~10 µs/vertex.
- **Retrieve**: `retrieve_by_activation` (retrieval_service.py:104-107) **rebuilds `{v["name"] for v in graph.vs}` on every activated node** + `vs.find` + `_resolve_content`.

### Step 4 — N+1 / unindexed patterns (in-memory, not DB)
- `content_resolver.resolve_content` (content_resolver.py:24) scans **all edges O(E)** per scored entity — entity vertices never store content; content lives on event vertices (`_apply`). 37 ms at E=30k, per entity.
- `_recall_keyword` (client.py:855-892) is an **O(M) full `_memories` dict scan** — 524 ms at M=50k.
- The `{v["name"] for v in graph.vs}` O(V) set-build pattern also appears in: `thread_service.py:59,71`, `graph_engine.py:266,277`, `server.py` (via vs.find). Precomputing a name set once would help all of them.

### Write path (bonus finding)
- `_remember_direct` calls `graph_engine.apply_event(event)` **synchronously** (client.py:394-396) — so per-write latency also grows ~linearly with V (measured 2.385 ms at V=8,484).
- `recall()` runs `_recall_impl` **twice** when global namespace ≠ project namespace (client.py:624-634, default global) → 2× per-recall cost in production.

---

## Planned fixes — next session

### Fix #1 — O(1) vertex existence (highest leverage; kills O(N²) apply)
Replace `_vertex_exists` (`graph_engine.py:876-881`, currently `self.graph.vs.find(name=...)` linear scan) with a **maintained name → set/dict**.

**DANGER — every vertex mutation must stay in sync. Full audit:**

| location | operation | consequence for index |
|---|---|---|
| `graph_engine.py:719` | `add_vertex(event_id, ...)` in `_apply` | must register |
| `graph_engine.py:792` | `add_vertex(thread_id, ...)` in `_apply` | must register |
| `graph_engine.py:871` | `add_vertex(name, ...)` in `_ensure_node` | must register |
| `graph_engine.py:904` | `delete_vertices(sidx)` in `_merge_nodes` | must unregister (also **reindexes** all later vertices → name→index dict invalid; prefer a `Set[str]` for existence, or rebuild) |
| `graph_engine.py:296` | `clear()` replaces graph | reset set |
| `graph_engine.py:661` | `load_snapshot()` sets `self.graph = data["graph"]` | **rebuild set from `graph.vs["name"]`** |
| `graph_engine.py:267` | `add_vertex(tid,...)` in `rebuild()` (threads) | must register (test-only path but keep correct) |
| `workflow_induction.py:96,109` | `graph_engine.graph.add_vertex(...)` **direct, bypasses `_ensure_node`** | must register or switch to a helper |
| `thread_service.py:60` | `graph_engine.graph.add_vertex(...)` **direct** | must register or switch to a helper |
| `contradiction_worker.py:189` | `add_edge(event_id, entity_id, ...)` | endpoints pre-exist (both created from events) — verify, no new vertices |
| `galaxy_core.py:107-112` | `_ensure_node(...)` | ✅ already centralized |
| tests: `test_graph_export.py:10-28` | direct `add_vertex` | test-only; tests use their own `GraphEngine` instances |

Recommended shape: `self._vertex_names: Set[str]` used by `_vertex_exists`; a tiny `_register(name)`/`_unregister(name)` helper called at each site. Keep `vs.find` where the actual **index** is needed (activation, get_neighbors, etc.) unless you also maintain name→index and rebuild after `_merge_nodes`.

### Fix #4 — worker self-heal on Defect A (silent empty graph)
In `AsyncGraphWorker` (`graph_worker.py`): before reading the cursor in `_process_batch` (or at `flush()`/`start()`), if `graph_engine.graph.vcount() == 0` **and** the events table has rows, **reset `ingestion_cursor.last_event_id` to NULL** so the worker replays from the beginning.
- Anchors: `_ensure_cursor_table` (graph_worker.py:50-63), `_process_batch` (111-171), `flush` (78-81).
- One cheap query: `SELECT EXISTS(SELECT 1 FROM events LIMIT 1)`.
- Guards against the "crash after cursor advanced, before snapshot saved" window.

### Fix #2 — hoist vertex-name set out of the retrieve loop
In `retrieve_by_activation` (retrieval_service.py:104-107): build `names = set(graph_engine.graph.vs["name"])` **once** before the loop; replace the per-iteration `{v["name"] for v in graph.vs}` comprehension with a membership check. Optionally pair with Fix #1's name set.
- Measured impact (this exact loop, K=100 fixed): 215 ms @ V=1k → **4,938 ms @ V=20k** — real, not theoretical.

### Fix #3 — DEFERRED (structural)
Cache content on entity vertices (or store `last_event_id`/latest-content on the entity vertex) so `resolve_content` stops doing the O(E) edge scan per entity. Changes where data lives — do once #1/#2/#4 are re-benchmarked and stable.

---

## Benchmark methodology (recreate exactly for before/after)

The bench scripts were **deleted** during session-1 cleanup. Recreate from this spec:

1. **`_recall_bench.py`** (in-memory apply + recall scaling): populate module-level `graph_engine` via direct `_apply` (bypass lock+event bus for speed); sizes `[500, 1000, 2000]`; query `"signal relay"`; seed content `f"signal relay protocol channel {i} alpha bravo"`; single `MemoryClient(namespace="bench_ns", use_db=False)` with `_get_global_namespace` monkeypatched to `self.namespace` (avoid double-impl).
2. **`_pg_compare.py`** (PG stage breakdown): for each DB, reset `ingestion_cursor.last_event_id = NULL`, delete `.mt/graph.pkl`, `graph_engine.clear()`, then `MemoryClient(ns, use_db=True)` → `AsyncGraphWorker.flush()` → time `_resolve_seeds`, `activation`, `retrieve_by_activation`, `_recall_keyword`, `recall()`.
   - Dirty: `memory_thread_db`, ns `architect_alice`, query `"PostgreSQL"` (real content).
   - Clean: scratch DB `memory_thread_clean` bulk-seeded via `executemany` INSERT into `events` only (recall path reads only events/graph), ns `clean_ns`, content `f"PostgreSQL best for services and JSONB support benchmark topic {i}"`.
3. **`_micro_bench.py`** (isolated complexity classes):
   - A) `retrieve_by_activation` at fixed K=50 seeds / max_depth=1, n∈[500,2000,5000,10000] (fanout=2 dense graph) → shows O(K·(V+E)).
   - C) `resolve_content` on one entity, same sizes → O(E).
   - B) `_recall_keyword` with `_memories` size ∈[1k,5k,10k,50k] → O(M).

**Before numbers to beat:** see tables above; also micro A: 215→824→2,361→4,938 ms; C: 2.5→9.4→23.9→37.4 ms; B: 7.8→48.6→67.7→524 ms.

---

## Environment / state notes (what session-1 touched)

- **PostgreSQL 18 local** at `C:\Program Files\PostgreSQL\18`. Start: `pg_ctl start -D "C:\Program Files\PostgreSQL\18\data"` (or the `postgresql-x64-18` service, admin). Auth = `scram-sha-256`; superuser password is the **install-time** password, which differs from `.env` (postgres user / db `memory_thread_db` / host 127.0.0.1 / port 5432).
- **Live DB `memory_thread_db`**: 4,242 events across ~50 namespaces (dirty). `schema_version` = 12. `events` indexed: PK(id), timestamp, namespace, object_id, GIN(search_vector). `contradiction_audit` has 15 rows.
- **State changed by bench:** `ingestion_cursor.last_event_id` left **NULL** (fresh worker state — benign). `.mt/graph.pkl` rebuilt from live data on last run.
- Scratch DB `memory_thread_clean` **dropped** (recreate via spec above).
- **Latent migration-runner bug:** `runner.py` inserts into `schema_version` after migration 1, but `schema_version` is created by migration 7 → `run_migrations()` fails on a **fresh** DB. Workaround used: pre-create `schema_version(version_id INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ)` before running.

---

## Session-1 leftovers to remove when convenient
- Nothing committed. `.gitignore`, `STRATEGY3_BULK_INGESTION.md`, `server.py`, `client.py`, `graph_engine.py`, `retrieval_service.py`, `tests/conftest.py` have pre-existing uncommitted edits from before this investigation (not ours).
- `memory_thread/nervous/graph_worker.py` is untracked (new file from earlier work) — it's live code now (server.py + client.py import it).

---

## NEXT SESSION PLAN (validating fixes + mem0 comparison)

### 1. Repeated 10-session run (reproduce the old multi-run slowdown)
- **Target:** `tests/test_10_sessions_galaxy_golden_thread.py` AND `tests/test_10_sessions_pg_galaxy.py`.
  - NOTE: despite "100 turns" in discussion, each of the 10 sessions is actually **4 turns (40 entities total)** — there is no 100-turns-per-session test today. The plan below runs the *whole 10-session suite* repeatedly, not one giant 100×10 run.
- **Procedure (10 runs, not all at once):** run the 10-session suite **10 times consecutively** against a NON-fresh DB (do NOT truncate `events` between runs) to reproduce the historically observed failure where the 2nd+ run took 400–600s to pass the first test.
  - The original cause was the O(N²) startup replay (linear `vs.find`/`_vertex_exists`) against an accumulating events table + Defect A (empty graph after `clear()` with advanced cursor). Both are now fixed (Fix #1 → O(N) replay; Fix #4 → self-heal).
  - **Success criterion:** run #2..#10 should be no slower than run #1 (no quadratic blowup). If it still degrades, the DB is accumulating unbounded — confirm whether the test truncates `events` between runs (it currently does NOT; recommend a scratch DB or truncation for CI hygiene).
- **Optional:** enable `GRAPH_NAMESPACE_BUDGET` during this run to also exercise the new namespace-tiering (RAM bounding) under repeated multi-namespace load.

### 2. Benchmark vs mem0 (retrieval quality + latency)
- Run the existing perf benchmarks with `MT_RUN_PERF=1` (`test_latency_profile.py`, `test_scale_ceiling.py`) and capture the "after" numbers (startup flush, seeds, retrieve, e2e recall at 1k/2k/8k/16k).
- Recreate the deleted micro-bench scripts from the "Benchmark methodology" spec (`_recall_bench.py`, `_pg_compare.py`, `_micro_bench.py`) and capture before/after for: A) `retrieve_by_activation` (K=50, fanout-2 dense graph, n∈[500,2000,5000,10000,20000]); B) `_recall_keyword` (BM25, `_memories` size ∈[1k,5k,10k,50k]); C) `resolve_content` (O(E)→O(1)).
- **mem0 comparison angle:** MT's graph traversal is exact (truth/contradiction/golden-thread) vs mem0's vector similarity. Benchmark both latency (sub-linear ANN for mem0, now O(K) for MT) and qualitative retrieval on the 10-session corpus (does MT return the contradicted entity / causal chain mem0 would miss?).
- Record all numbers in `reports/` for the packaging decision.

### 3. Packaging (deferred — last)
- Fix `setup.py` dependency mismatch: it lists `networkx` but the code requires `python-igraph` (align with `pyproject.toml`).
- Resolve uncommitted working-tree edits + deleted frontend files before tagging a release.

---

## SESSION-2 LEFTOVERS (implemented, uncommitted)
All fixes above are in the working tree but **not committed**. Files touched this session:
`memory_thread/services/graph_engine.py`, `memory_thread/services/retrieval_service.py`, `memory_thread/services/content_resolver.py`, `memory_thread/sdk/client.py`, `memory_thread/config/settings.py` (+ `bench_recall_after.py` throwaway benchmark at repo root). No commits made.
