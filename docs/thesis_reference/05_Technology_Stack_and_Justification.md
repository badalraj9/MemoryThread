# Technology Stack and Justification

The choice of technology in **Memory Thread** is non-trivial. Every component was selected to solve a specific problem inherent to cognitive architectures.

## 1. ZeroMQ (The Nervous System)
*   **Role:** Inter-process communication.
*   **Why not HTTP?** HTTP adds millisecond-level overhead (headers, handshake) per request. For a "brain" processing 47k thoughts per second, this is unacceptable.
*   **Why not RabbitMQ?** RabbitMQ is a broker. It introduces a central point of failure and latency.
*   **Justification:** ZeroMQ allows "brokerless" messaging. The `DEALER` socket on the client talks directly to the `ROUTER` socket on the server over TCP or IPC (Inter-Process Communication). This mimics the direct synaptic connections of neurons.

## 2. The Slab Allocator (Memory Management)
*   **Role:** Buffering incoming requests.
*   **Why not standard Python Lists/Queues?** Python's `multiprocessing.Queue` uses pickling (serialization) which is CPU expensive and slow.
*   **Justification:** By using a pre-allocated block of shared memory (`multiprocessing.SharedMemory`) and slicing it into fixed-size "slabs," we eliminate the OS overhead of allocating/freeing memory for every single request. This is the same technique used by the Linux Kernel (SLAB allocator).

## 3. Qdrant (The Association Cortex)
*   **Role:** Vector Database.
*   **Why not pgvector?** While Postgres has vector extensions, Qdrant is built from the ground up for high-dimensional search with HNSW (Hierarchical Navigable Small World) indexing.
*   **Justification:** Qdrant supports "Payload Filtering" natively. This allows us to say "Find vectors near X, BUT only if `timestamp > Y` and `truth_score > 0.8`" efficiently.

## 4. Postgres (The Hippocampus)
*   **Role:** Event Store and Relational Source of Truth.
*   **Why not MongoDB?** Cognitive integrity requires strict schemas.
*   **Justification:**
    *   **JSONB:** Allows flexibility for the `delta` (payload) of events.
    *   **ACID Transactions:** Crucial for the `Timewarp` feature. When we rewrite history, it must be an all-or-nothing operation.
    *   **Reliability:** Postgres is the industry standard for "don't lose data."

## 5. Pydantic (The Validation Layer)
*   **Role:** Data Serialization and Type Checking.
*   **Justification:** In a system where data evolves (Phase 3 -> Phase 6), type safety is paramount. Pydantic ensures that a `TruthVector` always has exactly 4 float fields, preventing "bit rot" where data structures degrade over time.

## 6. FastAPI (The Interface)
*   **Role:** API Server.
*   **Justification:** Native support for asynchronous programming (`async/await`) allows the Gateway to handle thousands of concurrent connections while waiting for the Slab Allocator, without blocking threads.
