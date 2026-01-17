# Memory Thread

**A reference architecture and evolving system for persistent, uncertainty-aware reasoning.**

Memory Thread is a backend cognitive engine designed to serve as the "Hippocampus" for advanced AI agents. It replaces ephemeral context windows with a deterministic, event-sourced memory system that models truth as a vector, not a boolean.

---

## 🏗 What is this?

This is **not** a vector database wrapper.
This is **not** a chatbot.
This is **not** a "RAG" solution.

**Memory Thread is a Truth Maintenance System (TMS).**
It ingests raw sensory data, validates it for semantic drift, calculates a "Truth Score" based on confidence and corroboration, and maintains a strictly provable history of an entity's state over time.

### Core Capabilities
*   **Deterministic Replay:** Reconstruct the exact state of an entity at any point in the past ($t_{-k}$).
*   **Explicit Uncertainty:** Stores beliefs as 4D Truth Vectors: (Confidence, Authority, Freshness, Corroboration).
*   **High-Velocity Ingestion:** Capable of handling **47,000 Events Per Second** via a custom Slab Allocator and ZeroMQ fabric.
*   **Neurosymbolic Grounding:** Distinguishes between "Facts," "Hypotheses," and "Decisions."

---

## 📚 Deep Documentation

For a comprehensive understanding of the theory and architecture, refer to the **Thesis Reference**:

*   **[Unified System Overview](docs/thesis_reference/00_Unified_System_Overview.md)**: The executive summary and philosophy.
*   **[Architectural Layers](docs/thesis_reference/02_Architectural_Layers.md)**: Deep dive into the Nervous System, Brain, and Persistence layers.
*   **[End-to-End Workflow](docs/thesis_reference/07_End_to_End_Workflow.md)**: A microscopic trace of data from API to Storage.
*   **[Mathematical Specifications](docs/thesis_reference/06_Mathematical_Specifications.md)**: The algebra behind Truth Vectors and State Derivation.

---

## 🚀 Quick Start

### Prerequisites
*   Python 3.10+
*   PostgreSQL (Event Store)
*   Qdrant (Vector Store)

### Running the Engine
1.  **Install:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Start the API:**
    ```bash
    uvicorn memory_thread.api.main:app --host 0.0.0.0 --port 8000
    ```

3.  **Ingest a Memory:**
    ```bash
    curl -X POST http://localhost:8000/ingest \
      -H "Content-Type: application/json" \
      -d '{
        "producer_id": "agent-007",
        "events": [{
          "content": "The user prefers Python over JavaScript.",
          "timestamp": "2023-10-27T10:00:00Z"
        }]
      }'
    ```

### Running Benchmarks
To see the system under load:
```bash
# Run the 47k EPS Ingestion Benchmark
python benchmarks/benchmark_phase_4_1.py
```

---

## 🤝 Contributing

We welcome contributions from systems engineers and researchers interested in solving the "Cognitive Instability" problem in AI.

Please read **[CONTRIBUTING.md](CONTRIBUTING.md)** before submitting code. We prioritize correctness and architectural purity over feature count.

---

## 📜 License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.
