# The Prime Rule: Cognitive Governance

> "MT only persists what can be replayed, audited, and justified without an LLM."

## 1. The Prime Rule (Non-Negotiable)

If something cannot survive deterministic replay, it does not belong in MT core storage.
Everything else is derived.

## 2. Two Ingestion Classes

MT enforces a strict separation between **Ontology (What Is)** and **Epistemology (What We Know)**.

### Class A: Canonical Truth (Facts)

These are external reality snapshots.

*   **Examples:** Source code, specs, logs, sensor dumps, user messages.
*   **Properties:** Immutable, Versioned, Content-Addressed, No "Cleaning".
*   **Constraint:** Must be ingestible without an LLM.

### Class B: Epistemic Artifacts (Beliefs)

These are interpretations, summaries, and conclusions derived from facts.

*   **Examples:** Code summaries, classifications, confidence scores, hypotheses.
*   **Properties:** Mutable, Decaying, Subjective, Contradictory.
*   **Constraint:** Must have explicit **Provenance**.

## 3. Forbidden Patterns (Poison Control)

The following must **NEVER** be persisted as Truth (Class A):

1.  **Embeddings as Truth:** Vectors are derived artifacts, not facts.
2.  **Chain-of-Thought:** Internal reasoning traces are transient runtime noise.
3.  **Unattributed Beliefs:** "The system thinks X" without an Agent ID and Source ID.
4.  **Confidence without Source:** A number without a derivation path is meaningless noise.

## 4. Enforcement Policy

The `SecureMemoryClient` enforces these rules at runtime:

| Violation | Action |
|-----------|--------|
| Belief stored as Fact | ❌ **Hard Error** |
| Missing `derived_from` on Belief | ❌ **Hard Error** |
| Fact with Confidence/Authority | ❌ **Hard Error** |
| Deprecated `remember()` usage | ⚠️ **Warning + Audit** |

## 5. Self-Observation

MT can ingest its own logs (e.g., `audit_ledger.jsonl`) as **Facts**.
MT must **never** treat its own previous outputs as canonical truth by default.
**Self-Observation ≠ Self-Belief.**
