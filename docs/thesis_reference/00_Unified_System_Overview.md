# Memory Thread: A Deterministic Cognitive Architecture

## Unified System Overview

### Abstract

**Memory Thread** is a production-grade cognitive memory system designed to solve the "amnesia" and "hallucination" problems in Large Language Models (LLMs). Unlike standard vector databases which provide only probabilistic retrieval, Memory Thread implements a **Truth Maintenance System (TMS)** based on **Event Sourcing**. It treats memory not as a static storage bin, but as a living, self-correcting temporal graph. The system is **autonomous** — during chat interactions, it automatically remembers, extracts entities, detects contradictions, and builds context without explicit user commands. The system is provably correct, detecting and resolving contradictions in real-time.

---

### 1. The Core Philosophy: "Memory is a Function of Time"

The central axiom of the project is that the "Current State" of any entity is simply the sum of all events that have happened to it, derived deterministically.

$$ State(t) = \sum\_{i=0}^{t} \text{Apply}(\text{Event}\_i) $$

This allows for:

- **Time Travel:** The system can rewind to any point in the past.
- **Auditability:** Every belief held by the AI can be traced back to the specific source events.
- **Self-Healing:** If a contradiction is found, the system re-evaluates the "Truth Score" of conflicting events to resolve the dissonance.
- **Autonomy:** Users interact via natural conversation; the system handles all memory management internally.

---

### 2. High-Level Architecture

The system is divided into four layers:

1.  **Interface Layer:**
    - **CLI (Typer + Rich):** RBAC-gated commands. `mt` with no args enters autonomous chat.
    - **REST API (FastAPI):** Authenticated endpoints for programmatic access.
    - **Python SDK (`MemoryClient`):** Direct integration for Python applications.
2.  **Core Services (The Brain):**
    - **TMS (Truth Maintenance):** Calculates the "Truth Vector" (Confidence, Authority, Freshness, Corroboration) for every fact.
    - **Galaxy Schema:** OLAP-style cognitive queries across belief dimensions (SLICE, DICE, DRILL_DOWN, ROLL_UP).
    - **Meta-Stability:** Checks for contradictions and flags "Cognitive Drift."
    - **Decay & Consolidation:** Temporal decay of freshness, consolidation of repetitive events.
3.  **Access Control:**
    - **Pentagon Classification:** Six clearance grades (E-CLASS → SSS-CLASS) controlling feature access.
    - **Vault:** Secure storage for API keys and credentials.
    - **Client Registry:** API key management for external consumers.
4.  **Persistence Layer (The Hippocampus):**
    - **PostgreSQL:** Stores the immutable Event Log + entity states (JSONB with GIN indices).
    - **SQLite:** Automatic fallback when PostgreSQL is unavailable.
    - **Qdrant:** Stores Semantic Vectors (Embeddings) for fuzzy retrieval.
    - **Write-Ahead Log (WAL):** Crash-safe persistence with fsync and recovery.

---

### 3. Key Innovations

#### The Truth Vector

We do not store binary "True/False." We store a tensor:

```json
"truth_vector": {
  "confidence": 0.95,
  "authority": 0.8,
  "freshness": 0.99,
  "corroboration": 0.1
}
```

This allows the system to handle conflicting information gracefully. If the User says "I am 30" (High Authority) and a Web Bio says "He is 29" (Low Authority), the TMS automatically prioritizes the User's statement.

#### Autonomous Memory Management

Unlike traditional memory systems requiring explicit "save" commands, MT's `chat()` function is fully autonomous:

1. Auto-remembers user messages and agent responses
2. Extracts entities and relations via NER
3. Detects contradictions against existing memories
4. Builds context from all stored knowledge
5. Generates personalized responses using local or cloud LLMs

#### The Galaxy Schema

Inspired by data warehouse star schemas, the Galaxy Schema enables multi-agent cognition. Multiple agents can hold different beliefs about the same fact, and OLAP-style queries can analyze these belief dimensions.

#### Write-Ahead Logging

MT uses a crash-proof WAL: every memory operation is pre-written to a durable log with `fsync()` before processing. On crash recovery, uncommitted entries are replayed automatically.

---

### 4. Roadmap & Current State

**Implemented:**

- **Phases 1-4:** Core storage, performance, and temporal correctness.
- **Phase 5 (Partial):** Decay engine, pruning, consolidation.
- **Phase 6 (Partial):** WAL, snapshot/replay, provenance tracking.
- **Phase 7 (Partial):** Entity/relation extraction, graph service.
- **Autonomy Layer:** Autonomous chat with auto-remembering.
- **Security Layer:** Pentagon-grade RBAC, vault, client registry.
- **Multi-LLM Support:** Local SmolLM, Groq, OpenRouter with fallback.

**Planned:**

- Setup wizard (`mt init`) and auto-migrations (`mt migrate`).
- Background scheduler for decay/consolidation.
- PyPI publishing and Docker Compose.
- Comprehensive test suite and CI/CD.

**Memory Thread** represents a shift from "Static Knowledge Bases" to "Living Cognitive Systems."
