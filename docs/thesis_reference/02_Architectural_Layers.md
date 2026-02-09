# Architectural Layers: A Deep Dive

The **Memory Thread** architecture is designed as a layered cognitive system, separating concerns between interface, processing, access control, and persistence.

## 1. The Interface Layer (Interaction Points)

- **Location:** `memory_thread/cli.py`, `memory_thread/api/`

The system provides three interfaces for different use cases:

### CLI (Primary — Typer + Rich)

The autonomy-first CLI. `mt` with no arguments enters interactive chat where everything is auto-handled:

- Auto-remembering of user messages and agent responses
- Entity extraction and relation inference
- Contradiction detection against existing memories
- Context building from all stored knowledge

Commands are RBAC-gated by Pentagon clearance grades (E-CLASS → SSS-CLASS).

### REST API (FastAPI)

Authenticated endpoints for programmatic access. Bearer token authentication via the client registry. Full CRUD for memories, Galaxy Schema operations, and maintenance endpoints.

### Python SDK (`MemoryClient`)

Direct integration via `from memory_thread.sdk import MemoryClient`. The SDK is the foundation — both CLI and API are thin wrappers around it.

## 2. The Service Layer (The Brain)

- **Location:** `memory_thread/services/`
- **Role:** Processing, Logic, and Derivation.

This is where raw input is converted into "Meaning."

### Key Services:

1.  **TMSService (Truth Maintenance System):**
    - The core logic engine.
    - Calculates `TruthVector` scores: $S = 0.4C + 0.35A + 0.25F + 0.1 \ln(1 + R)$.
    - Decides if a new fact (Event) overrides an old fact (State).
    - _Code:_ `memory_thread/services/tms_service.py`

2.  **StateDerivationService:**
    - A pure function $S_{t+1} = f(S_t, E)$.
    - Applies `DeltaPatch` (JSON Diff) to entity states.
    - Handles arithmetic for numeric fields (e.g., `tree_count += 5`).

3.  **GalaxyQueryService:**
    - OLAP-style cognitive queries across belief dimensions.
    - SLICE (by source), DICE (multi-filter), DRILL_DOWN (to source fact), ROLL_UP (aggregate).
    - _Code:_ `memory_thread/services/galaxy_query.py`

4.  **DecayEngine:**
    - Exponential decay: $F_{new} = F_{old} \cdot e^{-\lambda t}$
    - Configurable decay rates per memory type.
    - _Code:_ `memory_thread/services/decay_engine.py`

5.  **EntityExtractor (NER):**
    - Extracts named entities and relations from natural language.
    - Builds structured relationships between concepts.
    - _Code:_ `memory_thread/services/ner.py`

## 3. The Access Control Layer

- **Location:** `memory_thread/services/access_control.py`, `memory_thread/vault.py`
- **Role:** Pentagon-grade RBAC enforcement.

### Components:

1.  **AccessControlService:**
    - Enforces grade-based command access (E-CLASS → SSS-CLASS).
    - Calculates write authority based on user grade and target namespace.
    - Filters read results by namespace clearance.

2.  **Vault:**
    - Stores API keys (Base64 encoded), PINs (SHA-256 hashed).
    - Per-user provider credentials for LLM services.
    - _Location:_ `~/.mt/vault.json`

3.  **Client Registry:**
    - Manages API keys for external consumers.
    - Issues `mt_sk_*` prefixed bearer tokens.

## 4. The Persistence Layer (The Hippocampus)

- **Location:** `memory_thread/db/`
- **Role:** Durable storage with crash safety.

We employ a **Hybrid Storage Strategy** with automatic fallback:

### A. Write-Ahead Log (WAL)

- **Role:** Crash-proof durability guarantee.
- **Protocol:** Pre-write → fsync → Process → Commit.
- **Recovery:** Uncommitted entries replayed on startup.

### B. The Event Log (PostgreSQL)

- **Table:** `events`
- **Role:** The absolute source of truth. An append-only log of every interaction.
- **Schema:** Immutable JSONB with GIN indices for fast queries.

### C. The Entity State (PostgreSQL)

- **Table:** `entity_state`
- **Role:** A cache of the "Now."
- **Schema:** `current_value` (JSONB) + `truth_vector`.
- **Logic:** This table can be deleted and fully rebuilt from the Event Log at any time (Replay).

### D. SQLite Fallback

- **Role:** Automatic fallback when PostgreSQL is unavailable.
- **Guarantees:** Same schema, same query interface, reduced scale.

### E. The Vector Store (Qdrant)

- **Collection:** `memories`
- **Role:** Associative memory — "Find me things _like_ this."
- **Fallback:** When Qdrant is unavailable, keyword search via PostgreSQL `websearch_to_tsquery`.

---

## 5. Data Structure Definitions

### 5.1 The Event Object

The atomic unit of memory.

- **ID:** UUID4 (Unique Identifier)
- **Timestamp:** UTC Datetime
- **Actor:** Enum (`USER`, `AGENT`, `SYSTEM`)
- **Action:** Enum (`ADD`, `UPDATE`, `REMOVE`, `OBSERVE`, `INFER`)
- **Object ID:** UUID (The entity being acted upon)
- **Delta:** JSON Dictionary (The change payload)
- **Truth Vector:** Embedded `TruthVector` object

### 5.2 The Truth Vector

The tensor of validity.

- **Confidence:** Float [0.0 - 1.0]
- **Authority:** Float [0.0 - 1.0]
- **Freshness:** Float [0.0 - 1.0]
- **Corroboration:** Float [0.0 - inf)
