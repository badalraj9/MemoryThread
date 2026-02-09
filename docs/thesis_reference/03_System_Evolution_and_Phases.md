# System Evolution and Phases

The development of **Memory Thread** followed a "Cognitive Roadmap," where each phase added a distinct layer of intelligence to the system. This mirrors the biological evolution of a brain: starting with storage, then truth, then relationships, and finally autonomy.

## Phase 1-2: The Foundation (Storage & Retrieval)

- **Goal:** Basic memory storage and retrieval.
- **Solution:**
  - In-memory state management with dictionary-based entity tracking.
  - PostgreSQL for persistent event storage.
  - Qdrant for vector-based semantic search.
- **Result:** A functional memory system that could store and retrieve information.

## Phase 3: The Truth Layer (Event Sourcing)

- **Goal:** Distinguish between reliable and unreliable information.
- **Solution:**
  - **Truth Maintenance System (TMS):** Every memory carries a 4-dimensional truth vector $(C, A, F, R)$.
  - **Event Sourcing:** All state changes recorded as immutable events. Current state derived deterministically.
  - **State Derivation:** Pure function $S_{t+1} = f(S_t, E)$ with delta patches.
- **Result:** The system can now reason about the reliability of its knowledge.

## Phase 4: The Galaxy Schema (Multi-Agent Cognition)

- **Goal:** Support multiple AI agents with different perspectives on the same facts.
- **Solution:**
  - **Galaxy Schema:** A 3-layer OLAP architecture:
    - Layer 0 (Facts): Immutable, content-addressed raw data.
    - Layer 1 (Beliefs): Agent-specific interpretations with provenance.
    - Layer 2 (Queries): OLAP operations — SLICE, DICE, DRILL_DOWN, ROLL_UP.
  - **Conflict Detection:** Identifies when agents hold contradictory beliefs about the same fact.
- **Result:** True multi-agent memory — agents can disagree, and the system tracks the disagreement.

## Phase 5: Cognitive Maintenance (The Glial Cells)

- **Goal:** Keeping the memory healthy over long periods.
- **Solution:**
  - **Decay Engine:** Exponential freshness decay: $F(t) = F_0 \cdot e^{-\lambda t}$. Configurable rates per memory type.
  - **Pruning:** Memories below truth score threshold removed from active storage.
  - **Consolidation:** Repetitive events merged into summaries (e.g., 100 similar events → 1 summary).
  - **Contradiction Detection:** Automatic flagging when new information conflicts with existing memories.

## Phase 6: Reliability & Security

- **Goal:** Crash safety, access control, and production readiness.
- **Solution:**
  - **Write-Ahead Log (WAL):** Every operation pre-written with `fsync()`. Uncommitted entries recovered on startup.
  - **Graceful Degradation:** PostgreSQL → SQLite fallback. Qdrant → keyword search fallback. Cloud LLM → local SmolLM fallback.
  - **Pentagon RBAC:** Six clearance grades (E-CLASS → SSS-CLASS) with namespace-scoped access control.
  - **Vault & Client Registry:** Secure credential storage and API key management.
  - **Structured Logging:** `structlog` with context propagation for debugging.
  - **JSONB Indexing:** GIN/BTREE indices for fast memory queries.

## Phase 7: Autonomy & Intelligence (Current State)

- **Goal:** Make the system autonomous — users should think, not manage memory.
- **Solution:**
  - **Autonomous Chat:** `client.chat()` handles everything:
    1. Auto-remembers user messages and agent responses.
    2. Extracts entities and relations (NER).
    3. Detects contradictions against all stored memories.
    4. Builds context from relevant stored knowledge.
    5. Generates personalized responses via LLM.
  - **Multi-LLM Support:** Local SmolLM (offline), Groq (fast), OpenRouter (multi-model). Automatic fallback chain.
  - **Knowledge Graph:** Entity-relation graph extracted from natural language, enabling structured queries.
  - **CLI Redesign:** Autonomy-first interface where `mt` = chat. No explicit "remember" command — the system is a living cognitive entity, not a to-do list.
