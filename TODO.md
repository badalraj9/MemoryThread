# Memory Thread — Roadmap

> **Status legend:** `[ ]` planned · `[/]` in progress · `[x]` done

---

## ✅ Completed

- [x] Core SDK — remember, recall, chat with auto-entity extraction
- [x] Truth Management System — truth vectors, state derivation, decay
- [x] Galaxy Schema — 3-layer fact → belief → agent (OLAP queries)
- [x] Persistence — PostgreSQL + SQLite fallback + Qdrant vector search
- [x] Write-Ahead Log — crash-safe persistence (sync + async)
- [x] RBAC — Pentagon-grade access control with vault & client registry
- [x] REST API — FastAPI server with auth middleware
- [x] CLI — Typer + Rich, RBAC-tiered, autonomy-first design
- [x] LLM Integration — local SmolLM + Groq + OpenRouter
- [x] Structured Logging — structlog with context variables
- [x] JSONB Indexing — GIN/BTREE indices migration script

---

## 🔲 Priority 1 — System Bootstrap

These make MT installable and runnable by anyone.

- [ ] **`mt init` — Setup wizard**
  - Interactive first-run: create `.env`, test DB connection, create tables
  - `mt init --minimal` for SQLite-only mode (no Postgres/Qdrant)
  - Generate default namespace, create first API key

- [ ] **`mt migrate` — Auto-migrations**
  - Scan `migrations/` folder, track applied versions in DB
  - `mt migrate --status` to show pending
  - Run `001_add_gin_indices.sql` and future migrations automatically

- [ ] **`mt serve` — Start API server from CLI**
  - Wraps `uvicorn memory_thread.api.server:app`
  - `--host`, `--port`, `--workers` flags
  - Auto-recovery: call WAL `recover()` on startup

---

## 🔲 Priority 2 — Reliability

These prevent data loss and ensure uptime.

- [ ] **WAL auto-recovery on startup**
  - Call `wal.recover()` when `MemoryClient` initializes
  - Log recovered entries, replay uncommitted operations

- [ ] **Graceful shutdown**
  - SIGTERM/SIGINT handler: flush WAL, close DB pools, stop workers
  - Prevent data loss during restarts

- [ ] **Background scheduler**
  - Periodic tasks: decay (hourly), consolidation (daily), WAL compaction (hourly)
  - Lightweight — use `asyncio` tasks, not Celery
  - `mt scheduler start` / `mt scheduler status`

- [ ] **Health endpoint**
  - `GET /health` — returns DB status, Qdrant status, memory count, WAL size
  - For load balancers, Docker health checks, monitoring

---

## 🔲 Priority 3 — Correctness

These ensure the system behaves correctly at scale.

- [ ] **Tests**
  - Unit tests for SDK: remember, recall, chat, contradiction, decay
  - Unit tests for TMS: truth vector scoring, state derivation
  - Integration tests: PostgreSQL + Qdrant end-to-end
  - CLI tests: command output, RBAC gating
  - Target: 80%+ coverage

- [ ] **Namespace isolation audit**
  - Verify ALL queries filter by namespace
  - Qdrant searches, PostgreSQL queries, in-memory cache
  - Multi-tenant safety guarantee

- [ ] **Full async API**
  - Replace remaining sync `psycopg2` calls with `asyncpg`
  - Replace sync Qdrant with `AsyncQdrantClient` in API paths
  - Ensure event loop is never blocked

---

## 🔲 Priority 4 — Distribution

These let others install and use MT.

- [ ] **PyPI publish**
  - `pyproject.toml` is ready — publish to PyPI
  - `pip install memory-thread` should work
  - `pip install memory-thread[full]` for all extras

- [ ] **Docker Compose**
  - `docker-compose.yml` with: MT API, PostgreSQL, Qdrant
  - Single `docker compose up` to run everything
  - Volume mounts for data persistence

- [ ] **CI/CD pipeline**
  - GitHub Actions: lint, test, type-check on PR
  - Auto-publish to PyPI on tagged release
  - Docker image build + push

---

## 🔲 Priority 5 — Observability

Nice-to-have for production monitoring.

- [ ] **OpenTelemetry integration**
  - Instrument SDK methods with spans
  - Trace: remember → WAL → persist → index
  - Export to Jaeger/Grafana

- [ ] **API rate limiting**
  - Per-client rate limits based on role/authority
  - 429 responses with retry-after headers

- [ ] **Documentation site**
  - MkDocs or Docusaurus
  - SDK reference, CLI reference, architecture guide
  - Deploy to GitHub Pages

---

## Notes

- **MT is autonomous** — it auto-remembers during `chat()`, extracts entities, detects contradictions. The CLI reflects this: `mt` with no args = chat.
- **RBAC grades:** E-CLASS (guest) → C-CLASS (employee) → B-CLASS (developer) → A-CLASS (researcher) → S-CLASS (executive) → SSS-CLASS (godfather)
- **Env vars:** `MT_ROLE`, `MT_USER`, `MT_NAMESPACE` control identity
