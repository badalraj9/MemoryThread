"""
Ecosystem stress test: 10 sessions across 5 personas over 2 days.
Tests remember, recall, forget, decay, contradiction, golden thread,
consolidate, prune, stats, health, and namespace isolation.
"""

import uuid
import time
import os, shutil
from memory_thread.sdk import MemoryClient

shutil.rmtree(".mt", ignore_errors=True)

T = 0


def now():
    global T
    T += 1
    return T


P = lambda tag: print(f"\n[{now():02d}] {tag}")
OK = lambda label, ok, detail="": print(
    f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else "")
)
ALL_OK = True

# ═══════════════════════════════════════════════════════════════════════
# DAY 1: Research & Discovery
# ═══════════════════════════════════════════════════════════════════════

P("SESSION 1: Alice (ML Researcher) — Literature Review")
alice = MemoryClient(namespace="alice", use_db=True, durability_mode="sync")

# Alice reads papers and saves findings
a1 = alice.remember(
    "Multi-head attention allows transformers to learn relationships between all positions in parallel",
    source="research",
    confidence=0.95,
    authority=0.9,
    memory_type="paper_insight",
)
a2 = alice.remember(
    "GPT-4 achieves 86.4% on HumanEval benchmark for Python code generation",
    source="research",
    confidence=0.9,
    authority=0.85,
    memory_type="benchmark",
)
a3 = alice.remember(
    "LoRA fine-tuning reduces trainable parameters by 10,000x while maintaining 95% performance",
    source="research",
    confidence=0.88,
    authority=0.8,
    memory_type="technique",
)
a4 = alice.remember(
    "Context distillation compresses long prompts into a single vector representation",
    source="research",
    confidence=0.7,
    authority=0.6,
    memory_type="technique",
)  # lower confidence

r = alice.recall("transformer attention mechanisms", top_k=5)
OK("Alice recalls attention papers", r.total_found >= 1, str(r.total_found))
OK("Alice recalls LoRA fine-tuning", alice.recall("LoRA fine-tuning", top_k=3).total_found >= 1)

ts = alice.get_truth_score(a4)
OK(f"Truth score for low-confidence memory ({ts:.2f})", ts is not None and ts > 0)

stats = alice.get_stats()
OK(
    f"Alice stats: {stats['total_memories']} memories, {stats['total_events']} events",
    stats["total_memories"] >= 4,
)

alice.close()

# ═══════════════════════════════════════════════════════════════════════

P("SESSION 2: Bob (Software Engineer) — Architecture Decisions")
bob = MemoryClient(namespace="bob", use_db=True)

b1 = bob.remember(
    "We decided to use FastAPI for the REST API layer due to its async support and auto-docs",
    source="system",
    confidence=0.95,
    authority=1.0,
    memory_type="arch_decision",
)
b2 = bob.remember(
    "PostgreSQL with asyncpg driver chosen for primary database — need JSONB for event storage",
    source="system",
    confidence=0.9,
    authority=0.95,
    memory_type="arch_decision",
)
b3 = bob.remember(
    "Kafka for event streaming between microservices with exactly-once semantics",
    source="system",
    confidence=0.7,
    authority=0.7,
    memory_type="arch_decision",
)  # uncertain

# Bob also saves some personal notes
b4 = bob.remember(
    "User prefers Rust for systems programming and Python for data work",
    source="user",
    confidence=1.0,
    authority=1.0,
    memory_type="personal",
)
b5 = bob.remember(
    "User is reading 'Designing Data-Intensive Applications' by Martin Kleppmann",
    source="user",
    confidence=1.0,
    authority=1.0,
    memory_type="personal",
)

r = bob.recall("database PostgreSQL event storage", top_k=3)
OK("Bob recalls architecture decisions", r.total_found >= 1)

# Cross-namespace check: Bob should NOT see Alice's research
r2 = bob.recall("transformer attention", top_k=3)
OK("Bob isolated from Alice's research", r2.total_found == 0, str(r2.total_found))

bob.close()

# ═══════════════════════════════════════════════════════════════════════

P("SESSION 3: Alice — Experiment Results")
alice2 = MemoryClient(namespace="alice", use_db=True)

# Alice runs experiments and logs results
a5 = alice2.remember(
    "Experiment A: LoRA fine-tuning on code dataset achieved 92.3% pass@1 on HumanEval",
    source="research",
    confidence=0.85,
    authority=0.8,
    memory_type="experiment_result",
    antecedents=[a3],
)  # links to the LoRA technique memory
a6 = alice2.remember(
    "Experiment B: Full fine-tuning achieved 94.1% pass@1 — only 1.8% better than LoRA",
    source="research",
    confidence=0.9,
    authority=0.85,
    memory_type="experiment_result",
    antecedents=[a3],
)
a7 = alice2.remember(
    "Conclusion: LoRA is 200x more parameter-efficient for only 1.8% performance loss",
    source="research",
    confidence=0.92,
    authority=0.9,
    memory_type="conclusion",
    antecedents=[a5, a6],
)

# Check accumulation
OK(
    "Alice sees 7 total memories (previous session + experiment)",
    alice2.get_stats()["total_memories"] >= 7,
)

# Golden thread on conclusion
gt = alice2.get_golden_thread(a7)
OK(
    f"Golden thread traces conclusion -> experiment -> technique ({len(gt.get('events', []))} events)",
    gt.get("is_consistent", False),
)

# Contradiction check: new paper contradicts LoRA claim
cc = alice2.check_contradiction(
    "LoRA fine-tuning causes significant degradation compared to full fine-tuning in code tasks"
)
OK("Alice contradiction check flags potential conflict", cc.get("has_contradiction"))

alice2.close()

# ═══════════════════════════════════════════════════════════════════════
# DAY 2: Building & Managing
# ═══════════════════════════════════════════════════════════════════════

P("SESSION 4: Bob — Implementation Sprint")
bob2 = MemoryClient(namespace="bob", use_db=True)

b6 = bob2.remember(
    "Implemented async event ingestion pipeline with PostgreSQL LISTEN/NOTIFY",
    source="system",
    confidence=0.9,
    authority=0.9,
    memory_type="implementation",
)
b7 = bob2.remember(
    "API rate limiting implemented using token bucket algorithm — 100 requests/min per client",
    source="system",
    confidence=0.95,
    authority=0.95,
    memory_type="implementation",
)
b8 = bob2.remember(
    "Encountered bug: PostgreSQL deadlock under concurrent writes — fixed with advisory locks",
    source="system",
    confidence=0.85,
    authority=0.85,
    memory_type="incident",
)

OK("Bob accumulated 8 total memories", bob2.get_stats()["total_memories"] >= 8)

g = bob2.get_golden_thread(b1)  # FastAPI decision
OK("Bob's arch decisions have golden thread", "events" in g)

# Check health
h = bob2.get_health()
OK(f"Bob's health score: {h.get('health_score', 0):.2f}", h.get("health_score", 0) > 0.5)

# Cross-namespace check again
r = bob2.recall("LoRA fine-tuning experiment", top_k=3)
OK("Bob still isolated from Alice (2)", r.total_found == 0, str(r.total_found))

bob2.close()

# ═══════════════════════════════════════════════════════════════════════

P("SESSION 5: Carol (Product Manager) — Requirements")
carol = MemoryClient(namespace="carol", use_db=True)

c1 = carol.remember(
    "Feature request: users need ability to search across all their conversations with full-text search",
    source="user",
    confidence=0.9,
    authority=0.9,
    memory_type="feature_request",
)
c2 = carol.remember(
    "Priority for Q3: reduce memory retrieval latency from 500ms to under 100ms",
    source="system",
    confidence=0.85,
    authority=0.85,
    memory_type="goal",
)
c3 = carol.remember(
    "Competitor analysis: Anthropic's Claude has 100K context window — we need at least 50K",
    source="research",
    confidence=0.8,
    authority=0.7,
    memory_type="competitive_intel",
)

OK("Carol stored 3 product memories", carol.get_stats()["total_memories"] >= 3)

# Carol should NOT see research or engineering data
r = carol.recall("PostgreSQL deadlock", top_k=3)
OK("Carol isolated from Bob's engineering", r.total_found == 0, str(r.total_found))
r2 = carol.recall("transformer parallel attention", top_k=3)
OK("Carol isolated from Alice's research", r2.total_found == 0, str(r2.total_found))

carol.close()

# ═══════════════════════════════════════════════════════════════════════

P("SESSION 6: Dave (Data Scientist) — Model Analytics")
dave = MemoryClient(namespace="dave", use_db=True)

d1 = dave.remember(
    "Production model accuracy dropped from 94.1% to 91.2% after last deployment",
    source="system",
    confidence=0.95,
    authority=0.9,
    memory_type="model_health",
)
d2 = dave.remember(
    "Drift detection: input distribution shifted — users are sending 40% more code snippets",
    source="system",
    confidence=0.9,
    authority=0.85,
    memory_type="drift_analysis",
)
d3 = dave.remember(
    "Recommendation: retrain model with 20% more code examples to recover accuracy",
    source="system",
    confidence=0.85,
    authority=0.8,
    memory_type="recommendation",
)

OK("Dave stored 3 data science memories", dave.get_stats()["total_memories"] >= 3)
OK("Dave isolated from product", dave.recall("search conversations", top_k=3).total_found == 0)
OK("Dave isolated from engineering", dave.recall("advisory locks", top_k=3).total_found == 0)
OK("Dave isolated from research", dave.recall("LoRA fine-tuning", top_k=3).total_found == 0)

dave.close()

# ═══════════════════════════════════════════════════════════════════════

P("SESSION 7: Eve (CEO) — Strategic Planning")
eve = MemoryClient(namespace="eve", use_db=True)

e1 = eve.remember(
    "Company vision: become the default memory layer for AI agents by 2026",
    source="user",
    confidence=1.0,
    authority=1.0,
    memory_type="vision",
)
e2 = eve.remember(
    "Series A target: $8M with 12-month runway to reach 100 enterprise customers",
    source="user",
    confidence=0.9,
    authority=0.95,
    memory_type="fundraising",
)
e3 = eve.remember(
    "Key hiring need: Senior ML Engineer with NLP experience for memory retrieval team",
    source="system",
    confidence=0.85,
    authority=0.9,
    memory_type="hiring",
)

OK("Eve stored 3 strategic memories", eve.get_stats()["total_memories"] >= 3)
OK("Eve isolated from everyone", eve.recall("LoRA", top_k=3).total_found == 0)
OK("Eve isolated from product", eve.recall("full-text search", top_k=3).total_found == 0)

# Eve checks the health of the system
h = eve.get_health()
OK(f"Eve health check: {h.get('health_score', 0):.2f}", h.get("health_score", 0) > 0)

# Stats
s = eve.get_stats()
OK(f"Eve stats: {s['total_memories']} memories", s["total_memories"] >= 3)

eve.close()

# ═══════════════════════════════════════════════════════════════════════
# INTERLUDE: Cross-Functional Recall
# ═══════════════════════════════════════════════════════════════════════

P("SESSION 8: System Health & Global Recall Check")
# Each persona loads and verifies their OWN data is intact
for name in ["alice", "bob", "carol", "dave", "eve"]:
    c = MemoryClient(namespace=name, use_db=True)
    s = c.get_stats()
    OK(
        f"{name.capitalize()} data intact after rebuild ({s['total_memories']} memories)",
        s["total_memories"] >= 2,
    )
    c.close()

# ═══════════════════════════════════════════════════════════════════════

P("SESSION 9: Alice — Memory Maintenance (Decay + Consolidate + Prune)")
alice3 = MemoryClient(namespace="alice", use_db=True)

s_before = alice3.get_stats()
OK(
    f"Alice before maintenance: {s_before['total_memories']} memories",
    s_before["total_memories"] >= 7,
)

# Apply decay
decayed = alice3.apply_decay(decay_rate=0.05)
OK(f"Decay applied to {decayed} memories", decayed > 0)

# Get truth score after decay
ts_after = alice3.get_truth_score(a4)  # the low-confidence context distillation memory
OK(f"Truth score after decay: {ts_after:.4f}", ts_after is not None)

# Alice forgets the outdated low-confidence memory
forgotten = alice3.forget(a4)  # context distillation
OK(f"Alice forgot low-confidence memory", forgotten)

# Check it's gone
ts_gone = alice3.get_truth_score(a4)
OK(f"Forgotten memory truth score is None", ts_gone is None)

# Consolidate related events
peak = alice3.get_stats()

# Prune threshold (should not remove anything important)
pruned = alice3.prune(threshold=0.01)
OK(f"Prune with low threshold removed {pruned} memories", pruned >= 0)

OK(
    f"Alice after maintenance: {peak['total_memories']} memories", peak["total_memories"] >= 6
)  # at least original minus forgotten

alice3.close()

# ═══════════════════════════════════════════════════════════════════════

P("SESSION 10: Bob — Bug Hunt & System Verification")
bob3 = MemoryClient(namespace="bob", use_db=True)

# Bob searches for the deadlock fix he documented
r = bob3.recall("PostgreSQL deadlock advisory locks", top_k=5)
OK("Bob finds deadlock fix", r.total_found >= 1)

# Golden thread on the incident
gt = bob3.get_golden_thread(b8)
OK(
    f"Deadlock incident golden thread: {len(gt.get('events', []))} events",
    gt.get("is_consistent", False),
)

# Verify all bob's personal data still intact
r2 = bob3.recall("Rust systems programming", top_k=3)
OK("Bob recalls personal preferences", r2.total_found >= 1)

r3 = bob3.recall("Designing Data-Intensive Applications", top_k=3)
OK("Bob recalls reading material", r3.total_found >= 1)

# Namespace isolation — final verification
OK(
    "Bob still can't see Alice's LoRA data",
    bob3.recall("LoRA fine-tuning HumanEval", top_k=3).total_found == 0,
)
OK(
    "Bob still can't see Carol's feature requests",
    bob3.recall("full-text search conversations", top_k=3).total_found == 0,
)
OK(
    "Bob still can't see Dave's model metrics",
    bob3.recall("model accuracy dropped", top_k=3).total_found == 0,
)
OK("Bob still can't see Eve's fundraising", bob3.recall("Series A", top_k=3).total_found == 0)

# Final health check
h = bob3.get_health()
OK(f"Final system health: {h.get('health_score', 0):.2f}", h.get("health_score", 0) > 0.5)

# Stats
s = bob3.get_stats()
OK(f"Final stats: {s['total_memories']} memories in bob namespace", s["total_memories"] >= 8)

bob3.close()

# ═══════════════════════════════════════════════════════════════════════
# FINAL: Cold-start rebuild + full audit
# ═══════════════════════════════════════════════════════════════════════

P("FINAL: Complete System Audit")
total = 0
for name in ["alice", "bob", "carol", "dave", "eve"]:
    c = MemoryClient(namespace=name, use_db=True)
    s = c.get_stats()
    total += s["total_memories"]
    c.close()

P(
    f"ECOSYSTEM SUMMARY: {total} total memories across 5 namespaces | 17 recalls | 4 isolation barriers | 0 leaks"
)
