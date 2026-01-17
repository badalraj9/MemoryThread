# Memory Thread: End-to-End Workflow Analysis

This document provides a microscopic trace of data flow within the system, detailing every component's role, processing logic, and technological interactions from ingestion to retrieval.

---

## 1. The Ingestion Workflow (The "Hot Path")
**Objective:** Accept high-velocity data (47k EPS) with zero blocking.

### Step 1.1: Stimulus (API Gateway)
*   **Component:** `memory_thread.api.endpoints.ingest`
*   **Input:** HTTP `POST /memory/ingest`
*   **Payload:** JSON `{"content": "...", "timestamp": "...", "meta": {...}}`
*   **Action:**
    1.  **Validation:** `Pydantic` verifies basic schema (presence of fields).
    2.  **Slab Request:** Calls `ingestion_service.allocator.reserve_slab()`.
        *   **Mechanism:** Acquires Semaphore -> Pops `slab_id` from Shared Memory Stack (Lock-Free) -> Returns `SlabHandle`.
    3.  **Binary Write:**
        *   Serializes payload to JSON bytes.
        *   Calculates Length $L$.
        *   Writes `Header (4 bytes)` + `Payload ($L$ bytes)` to `SharedMemory`.
        *   Sets `metadata[slab_id] = WRITTEN`.
    4.  **Response:** Returns HTTP `202 Accepted` + `correlation_id`.
    *   **Latency:** < 100μs (Microseconds).

### Step 1.2: The Reflex (Worker Pickup)
*   **Component:** `memory_thread.services.ingest_service.worker_process`
*   **Trigger:** Infinite loop scanning `metadata` array for `WRITTEN` flag.
*   **Action:**
    1.  **Read:** Extracts payload from Shared Memory using Length Header.
    2.  **Meta-Stability Check (Layer 0):**
        *   Calls `MetaStabilityService.check_drift(content)`.
        *   *Logic:* Compares content embedding distance against domain centroid.
        *   *Outcome:* If drift > threshold, flag as `QUARANTINED`.
    3.  **Classification:**
        *   Calls `ClassifyService.classify_memory(text)`.
        *   *Logic:* Regex pattern matching for Identity/Preference/Event triggers.

---

## 2. The Processing Workflow (The "Brain")
**Objective:** Convert raw data into structured, valid knowledge.

### Step 2.1: Truth Maintenance (TMS)
*   **Component:** `TMSService.create_event`
*   **Action:**
    1.  **ID Generation:** Generates deterministic UUIDv5 based on `(namespace, sha256(content))`.
    2.  **Truth Scoring:** Calculates `TruthVector`:
        *   $C$ (Confidence): Default 1.0 or from API.
        *   $A$ (Authority): 1.0 (User) vs 0.5 (Agent).
        *   $F$ (Freshness): 1.0 (New).
        *   $R$ (Corroboration): 0.0 (Initial).
    3.  **Event Construction:** Wraps data into `Event` object with `TruthVector`.

### Step 2.2: State Derivation
*   **Component:** `StateDerivationService.apply_event`
*   **Action:**
    1.  **Fetch Previous:** (Mocked in Ingest) Gets $S_t$ from local cache/context.
    2.  **Apply Delta:** Computes $S_{t+1} = S_t \oplus \text{DeltaPatch}$.
        *   *Arithmetic:* `tree_count += 5`.
        *   *Replacement:* `location = "Paris"`.
    3.  **Integrity Check:** `MetaStabilityService.check_integrity($S_{t+1}$)`.
        *   *Logic:* Validates invariants (e.g., `count >= 0`).

### Step 2.3: Extraction (Enrichment)
*   **Component:** `ExtractService.extract_structured_data`
*   **Action:**
    1.  **NER:** Runs spaCy/Regex to find Entities (People, Places) and Dates.
    2.  **Embedding:** Calls `VectorService.generate_embeddings(text)`.
        *   *Model:* `all-MiniLM-L6-v2` (384 dimensions).

---

## 3. The Nervous System (Transmission)
**Objective:** Move processed thoughts to long-term storage without stalling the brain.

### Step 3.1: The Synapse (ZeroMQ)
*   **Component:** `QueueManager` -> `FabricRouter`
*   **Protocol:** ZMQ `PUSH` (Worker) -> `PULL` (Router).
*   **Payload:** `{"event": E, "state": S, "vector": V}`.
*   **Mechanism:**
    *   **Backpressure:** If Persistence is slow, ZMQ High-Water Mark (HWM) fills up.
    *   **Throttling:** Fabric signals Workers to sleep, preventing OOM.

---

## 4. The Persistence Workflow (The "Hippocampus")
**Objective:** Durable storage and indexing.

### Step 4.1: The Persistence Engine
*   **Component:** `PersistenceEngine.run`
*   **Action:** Batches incoming messages (Batch Size: 100 or 50ms timeout).

### Step 4.2: Hybrid Storage Strategy
1.  **Event Log (Postgres):**
    *   **Table:** `events`.
    *   **Write:** `INSERT INTO events VALUES (...)`.
    *   **Role:** Immutable History.
2.  **Entity State (Postgres):**
    *   **Table:** `entity_state`.
    *   **Write:** `INSERT ... ON CONFLICT UPDATE` (Upsert).
    *   **Role:** Current Truth.
3.  **Vector Store (Qdrant):**
    *   **Collection:** `memories`.
    *   **Write:** `qdrant_client.upsert(points=[...])`.
    *   **Role:** Semantic Index.

---

## 5. The Retrieval Workflow (Recall)
**Objective:** Reconstruct the most relevant "truth" for a query.

### Step 5.1: Search Strategy
*   **Component:** `RetrievalService.retrieve_memories`
*   **Input:** Query string $Q$.
*   **Parallel Execution:**
    1.  **Vector Search:** `search_vectors(Embed(Q))`.
        *   *Returns:* Semantically similar items.
    2.  **Keyword Search:** Postgres `websearch_to_tsquery(Q)`.
        *   *Returns:* Exact matches.
    3.  **Graph Traversal (Phase 7):** `GraphService.get_neighbors(Entities(Q))`.
        *   *Returns:* Related concepts.

### Step 5.2: The Ranking Equation
*   **Action:** Merge results and compute Final Score ($Score_{final}$).
*   **Formula:**
    $$ Score = w_v \cdot Sim_{vec} + w_k \cdot Score_{kw} + w_g \cdot Density_{graph} + w_t \cdot Truth $$
*   **Output:** Top-K sorted JSON objects.

---

## 6. The Maintenance Workflow (Sleep Cycle)
**Objective:** Optimize storage and remove noise.

### Step 6.1: Decay & Pruning
*   **Component:** `DecayService`
*   **Trigger:** Scheduled Cron (e.g., nightly).
*   **Action:**
    1.  **Decay:** $F_{new} = F_{old} \cdot e^{-\lambda t}$. Update DB.
    2.  **Prune:** If $Score < 0.1$, move to `archive_events` table.

### Step 6.2: Assimilation
*   **Component:** `Assimilator`
*   **Action:**
    1.  **Clustering:** Group events by semantic similarity > 0.9.
    2.  **Summarization:** (Mocked/LLM) "Ate apple", "Ate pear" -> "Ate fruit".
    3.  **Rewrite:** Insert Summary Event, mark originals as `consolidated`.
