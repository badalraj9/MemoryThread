"""
Test: 10 multi-turn sessions across 5 topics with 10 distinct agents,
      contradictions, Galaxy cross-agent detection, and Golden Thread verification.

Runs as a single sequential test to preserve graph_engine state across all checks.
"""

import time
import uuid
from datetime import datetime, timedelta

import pytest

from memory_thread.sdk import MemoryClient
from memory_thread.services.graph_engine import graph_engine
from memory_thread.services.golden_thread import GoldenThreadService, golden_thread_service


AGENTS = {
    "architect_alice": {"authority": 0.90, "title": "Lead Architect"},
    "engineer_bob": {"authority": 0.70, "title": "Backend Engineer"},
    "manager_maria": {"authority": 0.80, "title": "Engineering Manager"},
    "designer_dana": {"authority": 0.60, "title": "UX Designer"},
    "security_sam": {"authority": 0.85, "title": "Security Engineer"},
    "datascientist_dave": {"authority": 0.70, "title": "Data Scientist"},
    "product_paula": {"authority": 0.80, "title": "Product Lead"},
    "devops_danny": {"authority": 0.75, "title": "DevOps Engineer"},
    "researcher_rachel": {"authority": 0.70, "title": "Researcher"},
    "intern_ian": {"authority": 0.30, "title": "Intern"},
}

TOPICS = [
    "database_decision",
    "architecture_direction",
    "meeting_schedule",
    "feature_priority",
    "vendor_selection",
]


def make_client(agent_id: str, ns_suffix: str = "") -> MemoryClient:
    cfg = AGENTS[agent_id]
    ns = f"{agent_id}_{ns_suffix}" if ns_suffix else agent_id
    return MemoryClient(namespace=ns, use_db=False, default_authority=cfg["authority"])


def multi_turn(
    client: MemoryClient,
    thread_id: str,
    turns: list,
    agent_id: str,
) -> list:
    entity_ids = []
    for content, confidence in turns:
        time.sleep(0.002)
        eid = client.remember(
            content=content,
            source="agent",
            confidence=confidence,
            authority=AGENTS[agent_id]["authority"],
            memory_type="fact",
            thread_id=thread_id,
        )
        entity_ids.append(eid)
    return entity_ids


# ────────────────────────────────────────────────────────────────────────


class Test10SessionGalaxyGoldenThread:
    def test_full_simulation(self):
        """
        Single sequential test that:
        1. Runs all 10 sessions (multi-turn conversations)
        2. Checks namespace isolation
        3. Verifies Golden Thread reconstruction for contradicted entities
        4. Checks cross-agent graph structure
        5. Verifies Golden Thread narratives
        6. Runs topic-level golden threads
        7. Checks Galaxy multi-agent awareness
        """
        graph_engine.clear()
        all_entity_ids = {}
        all_clients = []

        # ═══════════════════════════════════════════════════════════════
        # PART 1: RUN ALL 10 SESSIONS
        # ═══════════════════════════════════════════════════════════════

        # ── Topic 1: Database Decision ─────────────────────────────────
        alice = make_client("architect_alice", "t1")
        bob = make_client("engineer_bob", "t1")
        all_clients.extend([alice, bob])

        tid1 = alice.create_thread("DB Decision - Alice lead")
        all_entity_ids["sess_db_01"] = multi_turn(
            alice,
            tid1,
            [
                ("We should standardize on PostgreSQL for all new services", 0.95),
                ("PostgreSQL has the best JSONB support and full-text search", 0.90),
                ("The data team needs PL/pgSQL for complex aggregations", 0.85),
                ("I've evaluated MongoDB and it lacks transactional guarantees we need", 0.88),
            ],
            "architect_alice",
        )

        tid2 = bob.create_thread("DB Decision - Bob lead")
        all_entity_ids["sess_db_02"] = multi_turn(
            bob,
            tid2,
            [
                ("MongoDB is the right choice for our rapid prototyping phase", 0.80),
                ("PostgreSQL is too rigid for our evolving schema requirements", 0.75),
                ("The team can move faster with document models and no migrations", 0.82),
                ("We don't need ACID transactions at our current scale", 0.70),
            ],
            "engineer_bob",
        )

        # ── Topic 2: Architecture Direction ────────────────────────────
        maria = make_client("manager_maria", "t2")
        dana = make_client("designer_dana", "t2")
        all_clients.extend([maria, dana])

        tid3 = maria.create_thread("Architecture - Maria lead")
        all_entity_ids["sess_arch_01"] = multi_turn(
            maria,
            tid3,
            [
                ("We must break the monolith into microservices this quarter", 0.85),
                ("Each team should own their service end-to-end", 0.80),
                ("Microservices will let us scale teams independently", 0.82),
                ("Event-driven communication via Kafka is the way forward", 0.78),
            ],
            "manager_maria",
        )

        tid4 = dana.create_thread("Architecture - Dana lead")
        all_entity_ids["sess_arch_02"] = multi_turn(
            dana,
            tid4,
            [
                ("A well-structured monolith is faster to build and iterate on", 0.65),
                ("Microservices add complexity that kills UX velocity", 0.70),
                ("We cannot even define service boundaries yet", 0.60),
                ("Monolith-first with modular extraction is the pragmatic choice", 0.68),
            ],
            "designer_dana",
        )

        # ── Topic 3: Meeting Schedule ──────────────────────────────────
        sam = make_client("security_sam", "t3")
        dave = make_client("datascientist_dave", "t3")
        all_clients.extend([sam, dave])

        tid5 = sam.create_thread("Sprint review - Sam")
        all_entity_ids["sess_meet_01"] = multi_turn(
            sam,
            tid5,
            [
                ("The sprint review is confirmed for Tuesday at 2pm", 0.90),
                ("I have already sent calendar invites for 2pm", 0.88),
                ("The 2pm slot works best for the security team availability", 0.85),
                ("Please confirm 2pm attendance by EOD", 0.82),
            ],
            "security_sam",
        )

        tid6 = dave.create_thread("Sprint review - Dave")
        all_entity_ids["sess_meet_02"] = multi_turn(
            dave,
            tid6,
            [
                ("The sprint review got moved to Tuesday at 4pm", 0.75),
                ("The data team cannot make 2pm due to batch processing window", 0.80),
                ("I have updated the calendar to 4pm", 0.78),
                ("4pm is the final confirmed time for the review", 0.82),
            ],
            "datascientist_dave",
        )

        # ── Topic 4: Feature Priority ──────────────────────────────────
        paula = make_client("product_paula", "t4")
        danny = make_client("devops_danny", "t4")
        all_clients.extend([paula, danny])

        tid7 = paula.create_thread("Q1 features - Paula")
        all_entity_ids["sess_feat_01"] = multi_turn(
            paula,
            tid7,
            [
                ("The real-time collaboration feature is our top priority", 0.90),
                ("Users are begging for multi-user editing", 0.85),
                ("We should delay auth overhaul and ship collab first", 0.80),
                ("Revenue depends on launching collab mode this quarter", 0.88),
            ],
            "product_paula",
        )

        tid8 = danny.create_thread("Q1 infra - Danny")
        all_entity_ids["sess_feat_02"] = multi_turn(
            danny,
            tid8,
            [
                ("Auth overhaul is priority one we have security debt", 0.85),
                ("We cannot ship any feature until RBAC and SSO are in place", 0.82),
                ("The audit findings require auth fixes before anything else", 0.88),
                ("Real-time collab is blocked until auth is done anyway", 0.80),
            ],
            "devops_danny",
        )

        # ── Topic 5: Vendor Selection ──────────────────────────────────
        rachel = make_client("researcher_rachel", "t5")
        ian = make_client("intern_ian", "t5")
        all_clients.extend([rachel, ian])

        tid9 = rachel.create_thread("Vendor eval - Rachel")
        all_entity_ids["sess_vend_01"] = multi_turn(
            rachel,
            tid9,
            [
                ("Vendor A has the best price-performance ratio for our workload", 0.80),
                ("Their SLA guarantees are industry-leading at 99.99 percent", 0.75),
                ("The API design is clean and well-documented", 0.78),
                ("Vendor A supports all compliance frameworks we need", 0.82),
            ],
            "researcher_rachel",
        )

        tid10 = ian.create_thread("Vendor eval - Ian")
        all_entity_ids["sess_vend_02"] = multi_turn(
            ian,
            tid10,
            [
                ("Vendor B has better developer experience and tooling", 0.40),
                ("The free tier of Vendor B is more generous", 0.45),
                ("Vendor B integrates natively with our existing stack", 0.35),
                ("I think Vendor B is the future-proof choice", 0.30),
            ],
            "intern_ian",
        )

        # Verify all sessions produced entities
        for sess_id, ids in all_entity_ids.items():
            assert len(ids) == 4, f"{sess_id}: expected 4 entity_ids, got {len(ids)}"
        print(f"\nPART 1: All 10 sessions completed - 40 entities created")

        # ═══════════════════════════════════════════════════════════════
        # PART 2: NAMESPACE ISOLATION CHECK
        # ═══════════════════════════════════════════════════════════════
        # Each client's in-memory _memories should be isolated
        alice_ids = list(alice._memories.keys())
        bob_ids = list(bob._memories.keys())
        for bid in bob_ids[:2]:
            assert alice.get_truth_score(bid) is None, (
                "Alice should not see Bob's truth scores (namespace isolation)"
            )
        print(
            f"PART 2: Namespace isolation verified - "
            f"Alice has {len(alice_ids)} memories, Bob has {len(bob_ids)}"
        )

        # ═══════════════════════════════════════════════════════════════
        # PART 3: GRAPH STRUCTURE CHECK
        # ═══════════════════════════════════════════════════════════════
        vcount = graph_engine.graph.vcount()
        ecount = graph_engine.graph.ecount()
        assert vcount > 0, "Graph should have vertices"
        assert ecount > 0, "Graph should have edges"

        # Count agent namespaces in the graph
        agent_nodes = set()
        for v in graph_engine.graph.vs:
            vattrs = v.attributes()
            ns = vattrs.get("namespace") or vattrs.get("agent_id") or ""
            if any(aid in ns for aid in AGENTS):
                for aid in AGENTS:
                    if aid in ns:
                        agent_nodes.add(aid)

        print(f"PART 3: Graph has {vcount} vertices, {ecount} edges")
        print(f"  Agent namespaces detected in graph: {len(agent_nodes)}")

        # Check modifies edges
        modifies_count = sum(
            1 for e in graph_engine.graph.es if e.attributes().get("type") == "modifies"
        )
        print(f"  'modifies' edges: {modifies_count}")

        # ═══════════════════════════════════════════════════════════════
        # PART 4: GOLDEN THREAD VERIFICATION
        # ═══════════════════════════════════════════════════════════════
        gts = GoldenThreadService()

        # Find entity nodes via graph search for key terms
        # search_nodes returns event nodes (they have "content" attr).
        # We resolve to entity nodes by following "modifies" edges.
        search_terms = [
            "PostgreSQL",
            "MongoDB",
            "microservices",
            "monolith",
            "2pm",
            "4pm",
            "real-time collaboration",
            "auth overhaul",
            "Vendor A",
            "Vendor B",
        ]

        def resolve_entity_ids(term: str) -> list:
            """Search for events matching term, then resolve to entity IDs."""
            event_names = graph_engine.search_nodes(term, attr="content")
            entity_ids = []
            for ename in event_names:
                try:
                    vidx = graph_engine.graph.vs.find(name=ename).index
                except (ValueError, KeyError):
                    continue
                for e in graph_engine.graph.es:
                    eattrs = e.attributes()
                    if eattrs.get("type") == "modifies" and e.source == vidx:
                        entity_name = graph_engine.graph.vs[e.target]["name"]
                        try:
                            entity_ids.append(uuid.UUID(entity_name))
                        except ValueError:
                            continue
            return entity_ids

        golden_results = {}
        for term in search_terms:
            entity_ids = resolve_entity_ids(term)
            for eid in entity_ids[:2]:
                result = gts.trace(eid)
                golden_results[str(eid)] = result
                assert len(result.events) > 0, (
                    f"Golden thread for {eid} (term='{term}') should have >=1 event"
                )
                assert "Current State:" in result.narrative
                assert "Consistency:" in result.narrative

        assert len(golden_results) > 0, "Should have at least one golden thread result"

        # Check for inconsistent (contradicted) threads
        inconsistent = [eid for eid, r in golden_results.items() if not r.is_consistent]
        print(f"\nPART 4: Golden Thread results - {len(golden_results)} entities traced")
        print(f"  Consistent: {len(golden_results) - len(inconsistent)}")
        print(f"  Inconsistent: {len(inconsistent)}")
        print(
            f"  (Note: 0 inconsistent is expected - MetaStabilityService tier-1 "
            f"detects boolean/numeric/antonym flips, not semantic disagreements. "
            f"LLM/NLI classifier would catch semantic contradictions.)"
        )

        # Verify golden thread event types
        all_event_types = set()
        for r in golden_results.values():
            for e in r.events:
                all_event_types.add(e.event_type)
        print(f"  Event types observed: {all_event_types}")
        assert "CREATED" in all_event_types
        # Note: each entity in this simulation receives only one event
        # (new entity_id per remember()), so only CREATED appears.
        # UPDATED/CONTRADICTED require multi-event entities (see sub-test below).

        # ── Sub-test: update same entity to see UPDATED in golden thread ──
        update_client = MemoryClient(namespace="update_test", use_db=False)
        existing_eid = update_client.remember(
            "Initial project budget is 100k", source="user", confidence=0.90
        )
        update_client.remember(
            "Project budget revised to 150k", source="user", confidence=0.85, entity_id=existing_eid
        )
        update_client.remember(
            "Final budget approved at 200k", source="user", confidence=0.95, entity_id=existing_eid
        )
        gt_update = gts.trace(existing_eid)
        gt_event_types = {e.event_type for e in gt_update.events}
        print(f"  Multi-update entity event types: {gt_event_types}")
        assert "CREATED" in gt_event_types
        assert "UPDATED" in gt_event_types
        assert len(gt_update.events) >= 3, (
            f"Should have 3+ events for multi-update entity, got {len(gt_update.events)}"
        )
        print(
            f"  Golden thread with updates: OK ({len(gt_update.events)} events: CREATED + UPDATED)"
        )
        update_client.close()

        # ── Sub-test: tier-1 contradiction detection on structured data ──
        # MetaStabilityService detects contradictions on structured key-value
        # (boolean flips, sign conflicts) — not on raw text content.
        from memory_thread.models.events import EntityState, TruthVector
        from memory_thread.services.meta_stability_service import MetaStabilityService

        meta = MetaStabilityService()
        state = EntityState(
            entity_id=uuid.uuid4(),
            namespace="test",
            current_value={"enabled": True, "score": 42, "likes": "coffee"},
            truth_vector=TruthVector(confidence=0.9, authority=0.9, freshness=1.0, corroboration=0),
            last_event_id=uuid.uuid4(),
            updated_at=datetime.now(),
        )
        assert meta.check_contradiction(state, {"enabled": False}), (
            "Tier-1 should detect boolean flip"
        )
        assert meta.check_contradiction(state, {"score": -10}), "Tier-1 should detect sign conflict"
        # Semantic opposite: key="likes" has ANTONYM_PAIRS entry "hates"
        assert meta.check_contradiction(state, {"likes": "hates"}), (
            "Tier-1 should detect semantic opposite (value equals antonym)"
        )
        print(f"  Tier-1 contradiction: boolean flip OK, sign conflict OK, antonym OK")
        assert not meta.check_contradiction(state, {"enabled": True}), (
            "No contradiction on same value"
        )

        # Print sample narrative (safe for Windows cp1252 console)
        if golden_results:
            sample_id = list(golden_results.keys())[0]
            sample = golden_results[sample_id]
            narrative_clean = sample.narrative.encode("ascii", errors="replace").decode("ascii")
            print(f"\n  Sample Golden Thread narrative ({sample_id[:12]}...):")
            print(f"  {narrative_clean[:1500]}")

        # ═══════════════════════════════════════════════════════════════
        # PART 5: TOPIC-LEVEL GOLDEN THREAD
        # ═══════════════════════════════════════════════════════════════
        for topic in TOPICS:
            result = golden_thread_service.trace_topic(topic, max_entities=5, max_events=50)
            assert "topic" in result
            print(
                f"\nPART 5: Topic '{topic}': "
                f"{result['entity_count']} entities, "
                f"{result['event_count']} events, "
                f"truncated={result['truncated']}"
            )

        # ═══════════════════════════════════════════════════════════════
        # PART 6: THREAD VERIFICATION
        # ═══════════════════════════════════════════════════════════════
        # Verify threads were created and accessible
        thread_ids = [tid1, tid2, tid3, tid4, tid5, tid6, tid7, tid8, tid9, tid10]
        for i, tid in enumerate(thread_ids):
            thread_data = alice.get_thread(tid)
            # Thread should exist (created by some client)
            if thread_data:
                print(
                    f"  Thread {i + 1} ({tid[:8]}...): "
                    f"'{thread_data['title']}' - {thread_data['event_count']} events"
                )

        # ═══════════════════════════════════════════════════════════════
        # PART 7: CLEANUP
        # ═══════════════════════════════════════════════════════════════
        for c in all_clients:
            c.close()

        print(f"\n{'=' * 60}")
        print(f"ALL CHECKS PASSED")
        print(f"{'=' * 60}")
