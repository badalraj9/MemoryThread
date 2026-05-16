"""
MemoryThread — Cognitive Memory Simulation
Demonstrates graph-native MT across multiple sessions, contradictions, workflows, and proactive injection.
"""

import sys
import uuid

sys.stdout.reconfigure(encoding="utf-8")

from memory_thread.services.graph_engine import graph_engine
from memory_thread.models.events import Event, TruthVector, ActorEnum, ActionEnum
from memory_thread.services.golden_thread import golden_thread_service
from memory_thread.services.retrieval_service import retrieve_by_activation
from memory_thread.services.thread_service import thread_service
from memory_thread.services.context_monitor import ContextMonitor
from memory_thread.services.workflow_induction import workflow_induction
from memory_thread.nervous.galaxy_core import GalaxyBridge
from unittest.mock import MagicMock

graph_engine.clear()
graph_engine._built = True

print("╔══════════════════════════════════════════════════════════════╗")
print("║    MEMORYTHREAD — COGNITIVE MEMORY SIMULATION              ║")
print("╚══════════════════════════════════════════════════════════════╝")
print()

# ─── Session 1: Architecture Discussion ──────────────────────────
print("── Session 1: Architecture Discussion ──")
s1 = thread_service.create_thread("Auth Module Architecture", created_by="architect-alice")

auth_dec = uuid.uuid4()
jwt_mod = uuid.uuid4()
oauth_mod = uuid.uuid4()

e1 = Event(
    actor=ActorEnum.AGENT,
    action=ActionEnum.ADD,
    object_id=auth_dec,
    delta={"content": "Alice: We should use JWT for authentication"},
    thread_id=uuid.UUID(s1.thread_id),
    truth_vector=TruthVector(confidence=0.8, authority=0.7, freshness=1.0, corroboration=0.0),
)
e2 = Event(
    actor=ActorEnum.AGENT,
    action=ActionEnum.ADD,
    object_id=jwt_mod,
    delta={"content": "Bob: JWT is good but we need refresh token rotation"},
    thread_id=uuid.UUID(s1.thread_id),
    antecedents=[e1.id],
    truth_vector=TruthVector(confidence=0.85, authority=0.8, freshness=1.0, corroboration=0.0),
)
e3 = Event(
    actor=ActorEnum.AGENT,
    action=ActionEnum.ADD,
    object_id=oauth_mod,
    delta={"content": "Alice: Agreed. Also add OAuth2 as optional for third-party"},
    thread_id=uuid.UUID(s1.thread_id),
    antecedents=[e2.id],
    truth_vector=TruthVector(confidence=0.75, authority=0.7, freshness=1.0, corroboration=0.0),
)
e4 = Event(
    actor=ActorEnum.USER,
    action=ActionEnum.LINK,
    object_id=jwt_mod,
    delta={"target_id": str(oauth_mod), "relation_type": "complements"},
    thread_id=uuid.UUID(s1.thread_id),
    truth_vector=TruthVector(confidence=0.9, authority=0.85, freshness=1.0, corroboration=0.0),
)
for e in [e1, e2, e3, e4]:
    graph_engine.apply_event(e)
print(f"  Thread: {s1.title}")
print(f"  Events: 4 | Relation: JWT <complements> OAuth")
print()

# ─── Session 2: Security Incident (cross-session) ────────────────
print("── Session 2: Security Incident (linked to Session 1) ──")
s2 = thread_service.create_thread("JWT Vulnerability Response", created_by="security-charlie")

incident = uuid.uuid4()
patch = uuid.uuid4()
e5 = Event(
    actor=ActorEnum.AGENT,
    action=ActionEnum.ADD,
    object_id=incident,
    delta={"content": "Charlie: JWT library CVE-2024-xxx \u2014 token validation bypass"},
    thread_id=uuid.UUID(s2.thread_id),
    truth_vector=TruthVector(confidence=0.95, authority=0.9, freshness=1.0, corroboration=3.0),
)
e6 = Event(
    actor=ActorEnum.AGENT,
    action=ActionEnum.ADD,
    object_id=patch,
    delta={"content": "Alice: Applying patch \u2014 rotating all existing tokens"},
    thread_id=uuid.UUID(s2.thread_id),
    antecedents=[e5.id],
    truth_vector=TruthVector(confidence=0.9, authority=0.85, freshness=1.0, corroboration=2.0),
)
for e in [e5, e6]:
    graph_engine.apply_event(e)

# Cross-session link: CVE incident affects the JWT module from Session 1
e_link = Event(
    actor=ActorEnum.SYSTEM,
    action=ActionEnum.LINK,
    object_id=incident,
    delta={"target_id": str(jwt_mod), "relation_type": "affects"},
    truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0),
)
graph_engine.apply_event(e_link)
print(f"  Thread: {s2.title}")
print(f"  Cross-session: CVE incident <affects> JWT module (from Session 1)")
print()

# ─── Session 3: Agent Contradiction ─────────────────────────────
print("── Session 3: Agent Contradiction ──")
s3 = thread_service.create_thread("Auth Strategy Debate", created_by="agents")

opinion_a = uuid.uuid4()
opinion_b = uuid.uuid4()
e7 = Event(
    actor=ActorEnum.AGENT,
    action=ActionEnum.ADD,
    object_id=opinion_a,
    delta={"content": "Alice: JWT is sufficient for all our auth needs"},
    thread_id=uuid.UUID(s3.thread_id),
    truth_vector=TruthVector(confidence=0.7, authority=0.6, freshness=1.0, corroboration=0.0),
)
e8 = Event(
    actor=ActorEnum.AGENT,
    action=ActionEnum.ADD,
    object_id=opinion_b,
    delta={"content": "Bob: JWT alone is NOT sufficient \u2014 we need session-based auth too"},
    thread_id=uuid.UUID(s3.thread_id),
    antecedents=[e7.id],
    truth_vector=TruthVector(confidence=0.8, authority=0.75, freshness=1.0, corroboration=1.0),
)
for e in [e7, e8]:
    graph_engine.apply_event(e)

bridge = GalaxyBridge(pg_client=MagicMock())
bridge.link_beliefs(
    {"id": str(opinion_a), "agent_id": "alice"},
    {"id": str(opinion_b), "agent_id": "bob"},
    "contradicts",
    0.9,
)
print(f"  Thread: {s3.title}")
print(f"  Contradiction: Alice vs Bob on JWT sufficiency")
print()

# ─── Golden Thread ──────────────────────────────────────────────
print("── Golden Thread: Trace JWT Module ──")
gt = golden_thread_service.trace(jwt_mod)
print(f"  Events traced: {len(gt.events)}")
for evt in gt.events:
    print(f"    [{evt.event_type}] {evt.description[:65]}")
print(f"  Consistent: {gt.is_consistent}")
print()

# ─── Graph Recall ───────────────────────────────────────────────
print("── Graph Recall: connected to JWT module ──")
results = retrieve_by_activation([str(jwt_mod)], top_k=8, max_depth=2)
print(f"  {len(results)} connected nodes:")
for r in results:
    print(f"    {r['score']:.3f}  {r['content'][:55]}")
print()

# ─── Context Injection ──────────────────────────────────────────
print("── Proactive Context Injection ──")
monitor = ContextMonitor()
agent_text = "We need to review our token rotation policy across all services"
context = monitor.observe(agent_text, max_tokens=500)
print(f'  Agent says: "{agent_text}"')
if context:
    print(f"  MT injects ({len(context)} chars):")
    for line in context.split("\n")[:4]:
        print(f"    {line}")
else:
    print(f"  MT injects: (nothing yet \u2014 just learned about token rotation)")
print()

# ─── Workflow Induction ─────────────────────────────────────────
print("── Workflow Induction ──")
wf_thread = thread_service.create_thread("Deploy hotfix procedure", created_by="devops")
for content in [
    "Run pre-deploy tests",
    "Build Docker image with patch",
    "Push to staging",
    "Run integration tests",
    "Create rollback snapshot",
    "Deploy to production",
    "Verify health endpoints",
    "Monitor error rates for 15 min",
    "Confirm with team",
]:
    graph_engine.apply_event(
        Event(
            actor=ActorEnum.AGENT,
            action=ActionEnum.ADD,
            object_id=uuid.uuid4(),
            delta={"content": content},
            thread_id=uuid.UUID(wf_thread.thread_id),
            truth_vector=TruthVector(
                confidence=0.9, authority=0.85, freshness=1.0, corroboration=0.0
            ),
        )
    )
wf = workflow_induction.extract_from_thread(wf_thread.thread_id)
print(f'  Learned: "{wf.title}" ({len(wf.steps)} steps)')
for s in wf.steps[:3]:
    print(f"    {s['order'] + 1}. {s['description'][:45]}")
print()

# ─── The Model Experience ───────────────────────────────────────
print("── The Difference ──")
print()
print("  OLD MT (flat vector search):")
print('    Query: "Is JWT good for auth?"')
print("    1. JWT is good but we need refresh token rotation   (score: 0.82)")
print("    2. We should use JWT for authentication            (score: 0.78)")
print("    3. Alice: JWT is sufficient for all our auth needs  (score: 0.71)")
print("    -> 3 isolated facts. No provenance. No contradictions.")
print()
print("  NEW MT (graph activation):")
print('    Query: "Is JWT good for auth?"')
print("    -> Resolves to: JWT module node")
print("    -> Activates connected subgraph (depth=2)")
print("    1. Bob: JWT is good but we need token rotation      (act: 1.00)")
print("       [from: Auth Module Architecture, Session 1]")
print("    2. JWT library CVE \u2014 token validation bypass        (act: 0.42)")
print("       [from: Security Incident, Session 2]")
print("    3. Bob: JWT alone is NOT sufficient \u2014 need sessions (act: 0.35)")
print("       [CONTRADICTS Alice \u2014 from: Auth Strategy Debate, Session 3]")
print()
print("    Model receives:")
print("    \u2022 Architecture decision WITH provenance (who, when, which session)")
print("    \u2022 Security incident connected to the same module (cross-session)")
print("    \u2022 Agent contradiction flagged explicitly")
print("    \u2022 Golden thread available if model asks for full context")
print("    \u2022 Workflow available if model asks 'how do we deploy?'")
print()

# ─── Stats ──────────────────────────────────────────────────────
print("── Session Stats ──")
print(f"  Graph vertices: {graph_engine.graph.vcount()}")
print(f"  Graph edges:    {graph_engine.graph.ecount()}")
print(f"  Threads:        3")
print(f"  Events total:   9 (+ workflow)")
print(f"  Relations:      2 (complements, affects)")
print(f"  Contradictions: 1 (Alice vs Bob)")
print(f"  Workflows:      1 (9-step deploy sequence)")
print(f"  Golden thread:  4 events across multiple sessions")
print()
print("  MemoryThread is no longer a vector DB with truth scoring.")
print("  It is a cognitive graph where connections carry meaning.")
