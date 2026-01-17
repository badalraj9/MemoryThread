# Contributing to Memory Thread

Thank you for your interest in Memory Thread.

This project is not a typical CRUD application; it is a reference architecture for persistent, uncertainty-aware reasoning systems. We welcome contributions that align with our core philosophy: **Correctness > Cleverness**.

## Philosophy

Memory Thread is designed to be the "Hippocampus" for AI agents. It prioritizes:
1.  **Deterministic History:** The past is immutable.
2.  **Explicit Uncertainty:** "I don't know" is a valid state.
3.  **Provable Correctness:** State must be a mathematical function of events.

We reject contributions that:
*   Introduce non-deterministic behavior (except where explicitly modeled as Aleatoric uncertainty).
*   Add features without corresponding "Golden Trace" verification.
*   Increase latency beyond the 20ms read budget without strong justification.

## Getting Started

### Prerequisites
*   Python 3.10+
*   PostgreSQL 14+ (with `pg_trgm` extension)
*   Qdrant (Vector Database)
*   Redis (for Hot State Cache)
*   ZeroMQ / Kafka (depending on deployment scale)

### Installation
1.  Clone the repository:
    ```bash
    git clone https://github.com/your-org/memory-thread.git
    cd memory-thread
    ```
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Set up environment:
    ```bash
    cp .env.example .env
    # Configure your DB connection strings
    ```

## Development Workflow

### 1. Issues First
Please open an Issue before submitting a Pull Request (PR), especially for architectural changes. Discussing the design beforehand saves everyone time.

### 2. Branching Strategy
*   `main`: The stable production branch.
*   `backend-core`: The active development branch for the core engine.
*   `feature/your-feature`: Your working branch.

### 3. Testing is Mandatory
We use a rigorous testing methodology.
*   **Unit Tests:** `pytest tests/`
*   **Golden Traces:** Run `python benchmarks/test_phase_6_integration.py`. This replays 100+ scenarios to ensure the timeline remains consistent.
*   **Performance:** If you touch the ingestion path, run `benchmarks/benchmark_phase_4_1.py` to verify EPS throughput.

### 4. Submission Checklist
*   [ ] Logic is covered by tests.
*   [ ] "Golden Trace" verification passes.
*   [ ] Type hints are strictly enforced (Pydantic models).
*   [ ] Documentation in `docs/` is updated if architectural assumptions change.

## Architecture Reference

Before contributing to the core logic, please read:
*   `docs/thesis_reference/00_Unified_System_Overview.md`: High-level concepts.
*   `docs/thesis_reference/07_End_to_End_Workflow.md`: Detailed data flow.

## Code Style

*   We follow PEP 8.
*   Use `Black` for formatting.
*   Docstrings should explain *why*, not just *what*.

## Community

We are building a tool for serious systems engineers and researchers. Please keep discussions professional and focused on technical excellence. See `CODE_OF_CONDUCT.md` for details.
