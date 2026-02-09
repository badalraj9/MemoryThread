# Memory Thread: Architecture Specification

**Version 2.0** | **Date: February 2026**

---

## Abstract

Memory Thread (MT) is a **truth-preserving cognitive memory system** designed for multi-agent AI environments. Unlike traditional vector databases that treat all data as equally valid, MT maintains explicit **truth vectors** (confidence, authority, freshness, corroboration) for every memory, enabling agents to reason about the reliability of their knowledge. The system is **autonomous** — during chat interactions, MT automatically remembers, extracts entities, detects contradictions, and builds context without explicit user commands.

---

## 1. Introduction

### 1.1 Problem Statement

Current AI memory systems suffer from three critical limitations:

1. **Truth Agnosticism**: No distinction between high-confidence facts and uncertain beliefs
2. **Temporal Blindness**: No decay model for outdated information
3. **Source Opacity**: No provenance tracking for multi-agent scenarios

### 1.2 Solution Overview

MT addresses these limitations through:

- **Truth Maintenance System (TMS)**: Explicit truth vectors for all memories
- **Galaxy Schema**: OLAP-style cognitive queries across belief dimensions
- **Event Sourcing**: Complete audit trail with time-travel capabilities
- **Write-Ahead Logging**: Crash-proof persistence guarantees
- **Autonomous Chat**: Auto-remember, entity extraction, contradiction detection

---

## 2. Theoretical Foundations

### 2.1 Truth Vectors

Each memory is associated with a **truth vector** $T = (c, a, f, r)$ where:

| Component     | Symbol | Range  | Description                  |
| ------------- | ------ | ------ | ---------------------------- |
| Confidence    | $c$    | [0, 1] | Certainty in the information |
| Authority     | $a$    | [0, 1] | Source credibility           |
| Freshness     | $f$    | [0, 1] | Temporal relevance (decays)  |
| Corroboration | $r$    | [0, ∞) | Independent confirmations    |

The composite **truth score** is computed as:

$$
\text{truth\_score} = 0.4c + 0.35a + 0.25f + 0.1 \cdot \log(1 + r)
$$

### 2.2 Decay Model

Freshness decays exponentially over time:

$$
f(t) = f_0 \cdot e^{-\lambda t}
$$

Where:

- $f_0$ = initial freshness (1.0)
- $\lambda$ = decay rate (configurable per memory type)
- $t$ = time since creation

### 2.3 Galaxy Schema (OLAP for Cognition)

Inspired by data warehouse star schemas, the Galaxy Schema separates:

| Layer | Name          | Purpose                                    |
| ----- | ------------- | ------------------------------------------ |
| L0    | Fact Store    | Immutable, content-addressed raw data      |
| L1    | Belief Store  | Agent-specific interpretations             |
| L2    | Query Engine  | OLAP operations (SLICE, DICE, DRILL, ROLL) |
| L3    | SDK Interface | Unified access layer                       |

---

## 3. System Architecture

### 3.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Memory Thread                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │   REST API  │  │  Python SDK │  │     CLI (Typer+Rich)    │ │
│  │  (FastAPI)  │  │MemoryClient │  │  RBAC-gated, mt command │ │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘ │
│         └────────────────┼─────────────────────┘               │
│                          ▼                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Core Services                          │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────────────┐  │  │
│  │  │   TMS   │  │ Galaxy  │  │ Decay / │  │   Access   │  │  │
│  │  │ Service │  │ Schema  │  │ Prune   │  │  Control   │  │  │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬───────┘  │  │
│  └───────┼────────────┼────────────┼─────────────┼──────────┘  │
│          ▼            ▼            ▼             ▼              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                  Persistence Layer                        │  │
│  │  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌───────────┐  │  │
│  │  │   WAL   │  │PostgreSQL│  │ Qdrant  │  │  SQLite   │  │  │
│  │  │(fsync)  │  │ (Events) │  │(Vectors)│  │(Fallback) │  │  │
│  │  └─────────┘  └──────────┘  └─────────┘  └───────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Autonomous Chat Flow

The primary interaction mode. When a user chats, MT performs all operations automatically:

```
User Message
    │
    ├─1─▶ remember(message, source="user")
    │       ├── WAL pre-write (crash safety)
    │       ├── Create TruthVector (c=0.8, a=1.0, f=1.0, r=0)
    │       ├── Entity extraction (NER)
    │       ├── Relation inference
    │       ├── Persist to DB + index in Qdrant
    │       └── WAL commit
    │
    ├─2─▶ check_contradiction(message)
    │       └── Flag if user previously said something conflicting
    │
    ├─3─▶ build_context()
    │       └── Aggregate ALL stored memories into context window
    │
    ├─4─▶ generate_response(context + message)
    │       └── Local LLM or Cloud API (Groq/OpenRouter)
    │
    └─5─▶ remember(response, source="agent")
            └── Store agent response with lower authority (0.5)
```

### 3.3 Data Flow (Write Path)

```
User Input
    │
    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  remember() │────▶│ WAL.append  │────▶│   fsync()   │
└─────────────┘     └─────────────┘     └─────────────┘
    │
    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ TMS.create  │────▶│ Event Store │────▶│  Qdrant     │
│   Event     │     │ (Postgres)  │     │ (Embed)     │
└─────────────┘     └─────────────┘     └─────────────┘
    │
    ▼
┌─────────────┐
│ WAL.commit  │  ← Only after successful processing
└─────────────┘
```

---

## 4. Fault Tolerance

### 4.1 Write-Ahead Logging (WAL)

MT employs a WAL to guarantee durability:

1. **Pre-write**: Event written to WAL with `fsync()`
2. **Process**: Event applied to memory stores
3. **Commit**: WAL entry marked committed

On crash recovery:

```python
uncommitted = wal.get_uncommitted()
for entry in uncommitted:
    replay(entry)  # Re-apply to stores
    wal.commit(entry.sequence)
```

### 4.2 Graceful Degradation

| Dependency | If Unavailable    | Fallback Behavior       |
| ---------- | ----------------- | ----------------------- |
| PostgreSQL | Skip DB persist   | SQLite file-based store |
| Qdrant     | Skip vector index | Keyword search          |
| Cloud LLM  | API unavailable   | Local SmolLM model      |
| Network    | API inaccessible  | Local-only mode         |

---

## 5. Security Model

### 5.1 RBAC Hierarchy (Pentagon Classification)

```
    SSS-CLASS (Godfather) ─── Nuclear: clear, rootkey, su, sudo
         │
    S-CLASS (Executive) ─── Operations: prune, audit, clients
         │
    A-CLASS (Researcher) ─── Maintenance: decay, consolidate, export, snapshot
         │
    B-CLASS (Developer) ─── Deep Inspection: galaxy, conflicts, provenance, agent, provider
         │
    C-CLASS (Employee) ─── Inspection: status, search, load
         │
    E-CLASS (Guest) ─── Chat only: mt, ask, whoami
```

### 5.2 Vault Storage

Sensitive data stored in `~/.mt/vault.json`:

- API keys: Base64 encoded (AES recommended for production)
- PINs: SHA-256 hashed
- Per-user provider credentials
- Client registry with API key management

### 5.3 Access Control Enforcement

- **CLI**: Commands gated by `MT_ROLE` environment variable
- **API**: Bearer token authentication via client registry
- **SDK**: `SecureMemoryClient` wraps `MemoryClient` with authority scoring

---

## 6. API Reference

### 6.1 Core SDK Methods

| Method                  | Signature                                  | Description         |
| ----------------------- | ------------------------------------------ | ------------------- |
| `chat()`                | `(message, system_prompt) → str`           | Autonomous chat     |
| `remember()`            | `(content, confidence, authority) → UUID`  | Store memory        |
| `recall()`              | `(query, top_k, min_truth) → RecallResult` | Retrieve memories   |
| `check_contradiction()` | `(content) → dict`                         | Detect conflicts    |
| `apply_decay()`         | `(rate) → int`                             | Decay freshness     |
| `consolidate()`         | `(entity_id, window_days) → int`           | Merge events        |
| `prune()`               | `(threshold) → int`                        | Remove low-truth    |
| `take_snapshot()`       | `(entity_id) → str`                        | Create checkpoint   |
| `get_provenance()`      | `(entity_id) → List[str]`                  | Event history chain |
| `ingest_fact()`         | `(content, source_uri) → fact_id`          | Galaxy L0           |
| `derive_belief()`       | `(fact_id, belief, agent_id) → belief_id`  | Galaxy L1           |
| `query_galaxy()`        | `(op, **kwargs) → QueryResult`             | OLAP query          |

### 6.2 REST Endpoints

| Method | Path               | Auth Required | Description    |
| ------ | ------------------ | ------------- | -------------- |
| POST   | `/memory/remember` | Yes           | Store memory   |
| POST   | `/memory/recall`   | Yes           | Query memories |
| POST   | `/memory/chat`     | Yes           | Chat with MT   |
| POST   | `/galaxy/fact`     | Yes           | Ingest fact    |
| POST   | `/galaxy/belief`   | Yes           | Derive belief  |
| GET    | `/health`          | No            | Health check   |
| GET    | `/version`         | No            | Version info   |

### 6.3 CLI Commands

See [COMMANDS.md](COMMANDS.md) for full CLI reference. Primary entry point:

```bash
# Install
pip install memory-thread[full]

# Chat (default)
mt

# One-shot
mt ask "What do you know about me?"
```

---

## 7. Performance Characteristics

| Operation        | Time Complexity | Space Complexity |
| ---------------- | --------------- | ---------------- |
| Remember         | O(1) amortized  | O(n)             |
| Recall (vector)  | O(log n)        | O(k)             |
| Recall (keyword) | O(n)            | O(k)             |
| Galaxy SLICE     | O(m)            | O(m)             |
| WAL append       | O(1)            | O(1)             |

Where:

- n = total memories
- k = top_k parameter
- m = matching beliefs

---

## 8. LLM Integration

MT supports multiple LLM providers with automatic fallback:

| Provider   | Model         | Usage                |
| ---------- | ------------- | -------------------- |
| Local      | SmolLM (135M) | Default, offline     |
| Groq       | llama/mixtral | Fast cloud inference |
| OpenRouter | Various       | Multi-model access   |

Provider selection via CLI: `mt provider use groq`

---

## 9. References

1. Doyle, J. (1979). A Truth Maintenance System. _Artificial Intelligence_, 12(3), 231-272.
2. de Kleer, J. (1986). An Assumption-based TMS. _Artificial Intelligence_, 28(2), 127-162.
3. Kimball, R., & Ross, M. (2013). _The Data Warehouse Toolkit_. Wiley.
4. Hellerstein, J.M., & Stonebraker, M. (2005). _Readings in Database Systems_. MIT Press.

---

## 10. Appendix: Installation

```bash
# Standard installation
pip install memory-thread

# With all components (CLI + vector search + PostgreSQL)
pip install memory-thread[full]

# Development
pip install -e .[dev]
pytest tests/
```

---

_Document generated for Memory Thread v2.0.0_
