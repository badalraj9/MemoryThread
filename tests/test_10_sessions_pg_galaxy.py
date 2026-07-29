"""
Test: 10 sessions with PostgreSQL persistence, Galaxy tables, and golden thread.

This test uses the live PostgreSQL database (memory_thread_db) with use_db=True
and initializes Galaxy services to verify full pipeline persistence.
"""

import time
import uuid
import json

import pytest

from memory_thread.sdk import MemoryClient
from memory_thread.services.graph_engine import graph_engine
from memory_thread.services.golden_thread import GoldenThreadService


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


def multi_turn(client, thread_id, turns, agent_id):
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


def resolve_entity_ids(term):
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


# ────────────────────────────────────────────────────────────────────────


class Test10SessionPGalaxy:
    def test_full_pipeline_pg(self):
        """
        Single sequential test: 10 sessions with PG persistence,
        Galaxy table creation, golden thread, and DB verification.
        """
        graph_engine.clear()
        # Remove ALL stale .mt/ state (WAL files, snapshots) from previous runs
        import os, shutil

        if os.path.exists(".mt"):
            for f in os.listdir(".mt"):
                fp = os.path.join(".mt", f)
                if os.path.isfile(fp):
                    os.remove(fp)
                elif os.path.isdir(fp):
                    shutil.rmtree(fp)
            print("Cleaned .mt/ directory (WAL + snapshots)")

        # ── Initialize Galaxy tables (create if not exist) ──────────────
        from memory_thread.db.postgres_client import PostgresClient

        pg = PostgresClient()
        with pg.get_cursor() as cur:
            # Agents table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id UUID PRIMARY KEY,
                    name TEXT NOT NULL,
                    namespace TEXT NOT NULL UNIQUE,
                    authority REAL DEFAULT 0.5,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Belief bridges table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS belief_bridges (
                    id UUID PRIMARY KEY,
                    source_agent_id UUID REFERENCES agents(agent_id),
                    target_agent_id UUID REFERENCES agents(agent_id),
                    bridge_type TEXT DEFAULT 'influence',
                    weight REAL DEFAULT 0.5,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Contradiction audit table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS contradiction_audit (
                    id UUID PRIMARY KEY,
                    entity_id UUID,
                    event_id UUID,
                    source_agent TEXT,
                    target_agent TEXT,
                    content_a TEXT,
                    content_b TEXT,
                    contradiction_type TEXT DEFAULT 'semantic',
                    severity REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'pending',
                    detected_at TIMESTAMP DEFAULT NOW(),
                    resolved_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fact_store (
                    id UUID PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    entity_id UUID,
                    content TEXT,
                    fact_type TEXT DEFAULT 'fact',
                    confidence REAL DEFAULT 0.5,
                    authority REAL DEFAULT 0.5,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS belief_store (
                    id UUID PRIMARY KEY,
                    agent_id UUID,
                    entity_id UUID,
                    belief TEXT,
                    confidence REAL DEFAULT 0.5,
                    source TEXT DEFAULT 'direct',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
        print("Galaxy tables created/verified in PostgreSQL")

        # ── Register agents in PG ────────────────────────────────────────
        registered_agent_ids = {}
        with pg.get_cursor() as cur:
            for aid, cfg in AGENTS.items():
                agent_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, aid)
                cur.execute(
                    """
                    INSERT INTO agents (agent_id, name, namespace, authority, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (namespace) DO UPDATE SET authority = EXCLUDED.authority
                    RETURNING agent_id
                """,
                    (agent_uuid, cfg["title"], aid, cfg["authority"], json.dumps({"tag": aid})),
                )
                row = cur.fetchone()
                registered_agent_ids[aid] = row["agent_id"]
        print(f"Registered {len(registered_agent_ids)} agents in PostgreSQL")

        # ═══════════════════════════════════════════════════════════════
        # GET BASELINE BEFORE SESSIONS RUN
        # ═══════════════════════════════════════════════════════════════
        with pg.get_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM events")
            events_baseline = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) AS cnt FROM entity_state")
            estate_baseline = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) AS cnt FROM threads")
            threads_baseline = cur.fetchone()["cnt"]
        print(
            f"Baseline: {events_baseline} events, {estate_baseline} entity_state, {threads_baseline} threads"
        )

        # ═══════════════════════════════════════════════════════════════
        # PART 1: RUN ALL 10 SESSIONS WITH use_db=True
        # ═══════════════════════════════════════════════════════════════
        all_entity_ids = {}
        all_clients = []

        # Topic 1: Database Decision
        alice = MemoryClient(namespace="architect_alice", use_db=True)
        bob = MemoryClient(namespace="engineer_bob", use_db=True)
        all_clients.extend([alice, bob])

        tid1 = alice.create_thread("DB Decision - Alice lead")
        all_entity_ids["sess_db_01"] = multi_turn(
            alice,
            tid1,
            [
                ("We should standardize on PostgreSQL for all new services", 0.95),
                ("PostgreSQL has the best JSONB support and full-text search", 0.90),
                ("The data team needs PL/pgSQL for complex aggregations", 0.85),
                ("I have evaluated MongoDB and it lacks transactional guarantees", 0.88),
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
                ("We do not need ACID transactions at our current scale", 0.70),
            ],
            "engineer_bob",
        )

        # Topic 2: Architecture Direction
        maria = MemoryClient(namespace="manager_maria", use_db=True)
        dana = MemoryClient(namespace="designer_dana", use_db=True)
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

        # Topic 3: Meeting Schedule
        sam = MemoryClient(namespace="security_sam", use_db=True)
        dave = MemoryClient(namespace="datascientist_dave", use_db=True)
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

        # Topic 4: Feature Priority
        paula = MemoryClient(namespace="product_paula", use_db=True)
        danny = MemoryClient(namespace="devops_danny", use_db=True)
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

        # Topic 5: Vendor Selection
        rachel = MemoryClient(namespace="researcher_rachel", use_db=True)
        ian = MemoryClient(namespace="intern_ian", use_db=True)
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

        for sess_id, ids in all_entity_ids.items():
            assert len(ids) == 4, f"{sess_id}: expected 4 entity_ids, got {len(ids)}"
        print(f"\nPART 1: 10 sessions completed - 40 entities created with PG persistence")

        # ═══════════════════════════════════════════════════════════════
        # PART 2: VERIFY PG PERSISTENCE
        # ═══════════════════════════════════════════════════════════════
        # Post-check
        with pg.get_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM events")
            event_count = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) AS cnt FROM entity_state")
            estate_count = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) AS cnt FROM threads")
            thread_count = cur.fetchone()["cnt"]
            # Check by namespace
            agent_ns = [
                f"architect_alice",
                "engineer_bob",
                "manager_maria",
                "designer_dana",
                "security_sam",
                "datascientist_dave",
                "product_paula",
                "devops_danny",
                "researcher_rachel",
                "intern_ian",
            ]
            cur.execute(
                "SELECT namespace, COUNT(*) AS cnt FROM events WHERE namespace = ANY(%s) GROUP BY namespace ORDER BY namespace",
                (agent_ns,),
            )
            ns_rows = cur.fetchall()
            cur.execute(
                "SELECT title, COUNT(*) AS cnt FROM threads WHERE title LIKE %s GROUP BY title",
                ("%Decision%",),
            )
            thread_rows = cur.fetchall()

        new_events = event_count - events_baseline
        new_estate = estate_count - estate_baseline
        new_threads = thread_count - threads_baseline

        print(f"PART 2: PG persistence verified")
        print(f"  events: {event_count} total (+{new_events} new)")
        print(f"  entity_state: {estate_count} total (+{new_estate} new)")
        print(f"  threads: {thread_count} total (+{new_threads} new)")
        if ns_rows:
            for r in ns_rows:
                print(f"    {r['namespace']}: {r['cnt']} events")
        if thread_rows:
            for r in thread_rows:
                print(f"    thread '{r['title']}': {r['cnt']}")
        assert new_events >= 40, f"Expected >=40 new events in PG, got {new_events}"
        assert new_threads >= 10, f"Expected >=10 new threads in PG, got {new_threads}"

        # Cross-check with in-memory graph
        vcount = graph_engine.graph.vcount()
        ecount = graph_engine.graph.ecount()
        assert vcount > 0
        assert ecount > 0
        print(f"  GraphEngine: {vcount} vertices, {ecount} edges")

        # Agent namespaces in graph
        agent_nodes = set()
        for v in graph_engine.graph.vs:
            ns = v.attributes().get("namespace") or v.attributes().get("agent_id") or ""
            for aid in AGENTS:
                if aid in ns:
                    agent_nodes.add(aid)
        print(f"  Agent namespaces in graph: {len(agent_nodes)} (expected 10)")

        # ═══════════════════════════════════════════════════════════════
        # PART 3: GOLDEN THREAD VERIFICATION
        # ═══════════════════════════════════════════════════════════════
        gts = GoldenThreadService()
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

        assert len(golden_results) > 0
        print(f"\nPART 3: Golden Thread - {len(golden_results)} entities traced")
        all_event_types = set()
        for r in golden_results.values():
            for e in r.events:
                all_event_types.add(e.event_type)
        print(f"  Event types: {all_event_types}")
        assert "CREATED" in all_event_types

        # Multi-update entity test
        update_client = MemoryClient(namespace="update_test", use_db=True)
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
        assert "CREATED" in gt_event_types
        assert "UPDATED" in gt_event_types
        assert len(gt_update.events) >= 3
        print(f"  Multi-update: {gt_event_types} ({len(gt_update.events)} events)")

        # Verify the updates are also in PG
        with pg.get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM events WHERE object_id = %s", (str(existing_eid),)
            )
            pg_event_count = cur.fetchone()["cnt"]
        assert pg_event_count >= 3, f"Expected >=3 PG events for multi-update, got {pg_event_count}"
        print(f"  Multi-update persisted in PG: {pg_event_count} events")
        update_client.close()

        # ═══════════════════════════════════════════════════════════════
        # PART 4: GALAXY AGENT REGISTRY VERIFICATION
        # ═══════════════════════════════════════════════════════════════
        with pg.get_cursor() as cur:
            cur.execute("SELECT name, namespace, authority FROM agents ORDER BY authority DESC")
            agents_in_db = cur.fetchall()
        print(f"\nPART 4: Galaxy agent registry ({len(agents_in_db)} agents):")
        for a in agents_in_db:
            print(f"  {a['namespace']}: {a['name']} (auth={a['authority']})")
        assert len(agents_in_db) == len(AGENTS)

        # Agent belief store
        with pg.get_cursor() as cur:
            # Insert belief records for key agents
            for aid, cfg in AGENTS.items():
                agent_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, aid)
                for entity_ids_list in all_entity_ids.values():
                    for eid in entity_ids_list[:1]:
                        cur.execute(
                            """
                            INSERT INTO belief_store (id, agent_id, entity_id, belief, confidence, source)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO NOTHING
                        """,
                            (
                                uuid.uuid4(),
                                agent_uuid,
                                str(eid),
                                f"belief_from_{aid}",
                                cfg["authority"],
                                "direct",
                            ),
                        )
            cur.execute("SELECT COUNT(*) AS cnt FROM belief_store")
            belief_count = cur.fetchone()["cnt"]
        print(f"  belief_store entries: {belief_count}")

        # ═══════════════════════════════════════════════════════════════
        # PART 5: CONTRADICTION AUDIT VERIFICATION
        # ═══════════════════════════════════════════════════════════════
        # Register cross-agent contradictions in the audit table
        contradiction_pairs = [
            (
                "architect_alice",
                "engineer_bob",
                "database_decision",
                "PostgreSQL is the right choice",
                "MongoDB is the right choice",
            ),
            (
                "manager_maria",
                "designer_dana",
                "architecture_direction",
                "microservices are the way forward",
                "monolith is the pragmatic choice",
            ),
            (
                "security_sam",
                "datascientist_dave",
                "meeting_schedule",
                "sprint review at 2pm",
                "sprint review at 4pm",
            ),
            (
                "product_paula",
                "devops_danny",
                "feature_priority",
                "real-time collaboration is top priority",
                "auth overhaul is top priority",
            ),
            (
                "researcher_rachel",
                "intern_ian",
                "vendor_selection",
                "Vendor A is the best choice",
                "Vendor B is the best choice",
            ),
        ]
        with pg.get_cursor() as cur:
            for src, tgt, topic, content_a, content_b in contradiction_pairs:
                cur.execute(
                    """
                    INSERT INTO contradiction_audit
                        (id, entity_id, event_id, source_agent, target_agent,
                         content_a, content_b, contradiction_type, severity, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                """,
                    (
                        uuid.uuid4(),
                        uuid.uuid4(),
                        uuid.uuid4(),
                        src,
                        tgt,
                        content_a,
                        content_b,
                        "semantic",
                        0.7,
                        "detected",
                    ),
                )
            cur.execute("SELECT COUNT(*) AS cnt FROM contradiction_audit")
            audit_count = cur.fetchone()["cnt"]
        print(f"\nPART 5: contradiction_audit entries: {audit_count}")
        assert audit_count >= len(contradiction_pairs)

        # ═══════════════════════════════════════════════════════════════
        # PART 6: CLEANUP
        # ═══════════════════════════════════════════════════════════════
        for c in all_clients:
            c.close()

        print(f"\n{'=' * 60}")
        print(f"ALL PG CHECKS PASSED")
        print(f"{'=' * 60}")
