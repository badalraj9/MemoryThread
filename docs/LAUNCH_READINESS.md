# Memory Thread — Launch Readiness & Action Plan

> **Status**: Core functionality complete. Preparing for MVP launch.
> **Last Updated**: 2026-03-14

---

## 1. Current State

### ✅ Completed Features

| Feature | Status | Notes |
|---------|--------|-------|
| SDK (`MemoryClient`) | ✅ Done | `remember()`, `recall()`, `chat()` with entity extraction |
| Truth Management System | ✅ Done | Truth vectors, state derivation, decay |
| Galaxy Schema | ✅ Done | 3-layer fact → belief → agent OLAP queries |
| PostgreSQL + SQLite | ✅ Done | With fallback chain |
| Qdrant Vector Search | ✅ Done | Async client ready |
| Write-Ahead Log (WAL) | ✅ Done | Sync + async implementation |
| REST API (FastAPI) | ✅ Done | With rate limiting, CORS, OpenAPI docs |
| CLI (Typer + Rich) | ✅ Done | Full-featured command interface |
| LLM Integration | ✅ Done | Groq, OpenRouter, local (Ollama) |
| Structured Logging | ✅ Done | structlog with context |
| Tests | ✅ Done | 80 tests, core ones passing |

### ⚠️ Known Issues

| Issue | Severity | Fix |
|-------|----------|-----|
| `test_phase_4_logic.py` import error | Medium | `ReplayService` moved to separate module |
| Pydantic deprecation warnings | Low | `class Config` → `ConfigDict` |
| FastAPI `on_event` deprecation | Low | Migrate to lifespan handlers |

---

## 2. RBAC Remnant Cleanup

RBAC was removed but remnants exist in:

### Files Requiring Cleanup

| File | Line Range | Action |
|------|------------|--------|
| `memory_thread/cli.py` | 7, 11-16, 61-102, 106-1020 | **Remove** Grade system and `_require()` decorators |
| `memory_thread/api/server.py` | 51, 54, 278-313 | Remove API key auth references |
| `memory_thread/api/gateway.py` | Check for auth middleware | Remove if present |

### Cleanup Command (Reference)

```bash
# After cleanup, verify CLI works:
python -c "from memory_thread.cli import app; print('CLI loads OK')"
```

---

## 3. What's Missing (Priority Order)

### 🔴 Priority 1 — Required for Launch

| Item | Description | Effort |
|------|-------------|--------|
| **`mt init`** | Setup wizard: create `.env`, test DB, create tables, generate namespace | Medium |
| **`mt serve`** | Start API server: wraps `uvicorn`, supports `--host`, `--port`, `--workers` | Low |
| **`mt migrate`** | Auto-run migrations from `migrations/` folder | Medium |
| **Docker Compose** | Single-command startup: MT API + PostgreSQL + Qdrant | Medium |

### 🟡 Priority 2 — Reliability

| Item | Description | Effort |
|------|-------------|--------|
| **WAL Recovery** | Call `wal.recover()` on startup, log recovered entries | Low |
| **Graceful Shutdown** | SIGTERM/SIGINT: flush WAL, close DB pools | Medium |
| **Health Endpoint** | Already exists at `/health` | Done |

### 🟡 Priority 3 — Verification

| Item | Description | Effort |
|------|-------------|--------|
| **Namespace Isolation** | Audit all queries filter by namespace | Medium |
| **Full Async API** | Replace remaining sync psycopg2 with asyncpg | Medium |

### 🟢 Priority 4 — Nice to Have

| Item | Description | Effort |
|------|-------------|--------|
| **Background Scheduler** | Periodic: decay (hourly), consolidation (daily) | Medium |
| **PyPI Publish** | `pip install memory-thread` | Low |
| **CI/CD** | GitHub Actions: lint, test, publish | Medium |

---

## 4. Recommended Approach

### Phase 1: Cleanup (Day 1)

1. **Remove RBAC remnants**
   - Clean `cli.py` Grade system
   - Clean `server.py` API key auth
   - Verify CLI loads without errors

2. **Fix test import error**
   - Move or import `ReplayService` correctly

### Phase 2: Core Launch Features (Day 2-3)

1. **`mt init` command**
   ```python
   # Expected behavior:
   mt init                    # Interactive wizard
   mt init --minimal          # SQLite-only mode
   ```
   
2. **`mt serve` command**
   ```python
   # Expected behavior:
   mt serve                   # Start on default 0.0.0.0:8000
   mt serve --host 127.0.0.1 --port 9000 --workers 4
   ```

3. **Docker Compose**
   ```yaml
   # docker-compose.yml
   services:
     mt-api:
       build: .
       ports:
         - "8000:8000"
     postgres:
       image: postgres:15
     qdrant:
       image: qdrant/qdrant
   ```

### Phase 3: Reliability (Day 4-5)

1. WAL auto-recovery on startup
2. Graceful shutdown handlers
3. Namespace isolation audit

---

## 5. Quick Wins (Low Effort)

| Task | Files | Action |
|------|-------|--------|
| Fix Pydantic deprecation | `models/entity.py` | Use `model_config = ConfigDict(...)` |
| Fix FastAPI deprecation | `api/gateway.py` | Use `lifespan` context manager |
| Verify health endpoint | `api/server.py` | Already exists, test it |

---

## 6. Success Criteria for Launch

- [ ] `mt init` creates working environment
- [ ] `mt serve` starts API without manual setup
- [ ] `docker compose up` runs full stack
- [ ] CLI commands work without RBAC
- [ ] All core tests pass
- [ ] No deprecation warnings in normal operation

---

## 7. Immediate Next Steps

1. **Remove RBAC from CLI** — Most urgent cleanup
2. **Add `mt init` and `mt serve`** — Core UX requirement
3. **Add Docker Compose** — Easy deployment
4. **Fix test imports** — Clean test suite
5. **Verify everything works** — End-to-end test

---

*Document generated for Memory Thread v1.0.0 launch assessment.*