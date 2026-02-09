# Technology Stack and Justification

The choice of technology in **Memory Thread** is non-trivial. Every component was selected to solve a specific problem inherent to cognitive architectures.

## 1. PostgreSQL (The Hippocampus)

- **Role:** Event Store, Entity State, and Relational Source of Truth.
- **Why not MongoDB?** Cognitive integrity requires strict schemas and ACID transactions.
- **Justification:**
  - **JSONB:** Allows flexibility for the `delta` (payload) of events while maintaining query performance via GIN indices.
  - **ACID Transactions:** Crucial for replay and state derivation. When we rewrite history, it must be an all-or-nothing operation.
  - **GIN Indices:** `CREATE INDEX ON entity_state USING gin (current_value jsonb_path_ops)` for sub-millisecond JSONB queries.
  - **Reliability:** Postgres is the industry standard for "don't lose data."

## 2. SQLite (The Fallback Brain)

- **Role:** Automatic fallback when PostgreSQL is unavailable.
- **Why SQLite?** Zero-configuration, embedded, file-based. No server process needed.
- **Justification:** A cognitive system should not become amnesiac just because a database server is down. SQLite provides identical schema with reduced scale, enabling local-only mode for development and edge deployment.

## 3. Qdrant (The Association Cortex)

- **Role:** Vector Database for semantic search.
- **Why not pgvector?** While Postgres has vector extensions, Qdrant is built from the ground up for high-dimensional search with HNSW (Hierarchical Navigable Small World) indexing.
- **Justification:** Qdrant supports "Payload Filtering" natively. This allows us to say "Find vectors near X, BUT only if `timestamp > Y` and `truth_score > 0.8`" efficiently.
- **Fallback:** When Qdrant is unavailable, MT falls back to PostgreSQL `websearch_to_tsquery` keyword search. Degraded but functional.

## 4. Write-Ahead Log (The Safety Net)

- **Role:** Crash-proof durability guarantee.
- **Why a custom WAL?** PostgreSQL has its own WAL, but we need application-level durability that spans multiple storage backends (Postgres + Qdrant).
- **Justification:**
  - Pre-write → `fsync()` → Process → Commit. If the system crashes between pre-write and commit, uncommitted entries are replayed on startup.
  - This ensures no memory is ever lost, even during power failures or process crashes.

## 5. Pydantic (The Validation Layer)

- **Role:** Data Serialization and Type Checking.
- **Justification:** In a system where data evolves across phases, type safety is paramount. Pydantic ensures that a `TruthVector` always has exactly 4 float fields, preventing "bit rot" where data structures degrade over time.

## 6. FastAPI (The Interface)

- **Role:** REST API Server.
- **Justification:** Native support for asynchronous programming (`async/await`) allows the API to handle concurrent requests while waiting for database operations. Automatic OpenAPI documentation provides self-documenting endpoints.

## 7. Typer + Rich (The CLI)

- **Role:** Command-line interface for direct user interaction.
- **Why not Textual?** Textual provides a full TUI but adds complexity for a system that is primarily autonomous. Typer provides clean command parsing; Rich provides beautiful terminal output.
- **Justification:** The CLI defaults to interactive chat (`mt` with no arguments). Commands are RBAC-gated, and Rich panels/tables provide clear, scannable output for inspection commands.

## 8. Sentence-Transformers (The Encoding Layer)

- **Role:** Text-to-vector embedding generation.
- **Model:** `all-MiniLM-L6-v2` (384 dimensions).
- **Justification:** Lightweight, fast, runs locally without GPU. Produces high-quality embeddings for semantic search. No external API dependency for core functionality.

## 9. Multi-LLM Architecture

- **Role:** Response generation during autonomous chat.
- **Providers:**
  - **SmolLM (135M):** Local, offline, default. No API keys needed.
  - **Groq:** Fast cloud inference via Groq SDK. Low latency.
  - **OpenRouter:** Multi-model access (GPT-4, Claude, Mixtral, etc.).
- **Justification:** A cognitive system should not depend on a single cloud provider. The fallback chain (Groq → OpenRouter → local) ensures MT always works, even offline.

## 10. structlog (The Observability Layer)

- **Role:** Structured logging with context propagation.
- **Justification:** Traditional logging (`print` or `logging`) produces unstructured text. `structlog` produces structured JSON logs with context variables (user_id, namespace, operation), enabling debugging of complex multi-step cognitive operations.
