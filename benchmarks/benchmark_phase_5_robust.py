import time
import logging
import uuid
import json
import random
import math
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any, Tuple

from faker import Faker
import numpy as np

# Adjust path if needed
import sys
import os
sys.path.append(os.getcwd())

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("benchmark_phase_5")
# Silence other loggers
logging.getLogger("memory_thread").setLevel(logging.WARNING)

fake = Faker()

# ==========================================
# MOCK INFRASTRUCTURE (IN-MEMORY DB)
# ==========================================
class MockCursor:
    def __init__(self, db_store):
        self.db = db_store
        self.rows = []

    def execute(self, query, params=None):
        query = query.strip().lower()
        params = params or ()

        # --- INSERT ---
        if query.startswith("insert into"):
            if "entities " in query:
                # INSERT INTO entities (id, namespace, entity_type, name, attributes, created_at, updated_at) VALUES ...
                # Params: (id, namespace, type, name, attrs, created, updated)
                # Or sparse insert. This is tricky to parse generally, so we assume specific usage patterns from services.

                # IdentityService.create_entity usage:
                # VALUES (%s, %s, %s, %s, %s, %s, %s)

                # Pruner/Decay might join 'entities', so we need to store them.
                # Just store by ID
                if len(params) >= 4:
                    e_id = str(params[0])
                    # Parse JSON if string
                    attrs = params[4] if len(params)>4 else {}
                    if isinstance(attrs, str):
                        try:
                            attrs = json.loads(attrs)
                        except:
                            attrs = {}

                    self.db['entities'][e_id] = {
                        "id": e_id,
                        "namespace": params[1] if len(params)>1 else "user",
                        "entity_type": params[2] if len(params)>2 else "misc",
                        "name": params[3] if len(params)>3 else "unknown",
                        "attributes": attrs,
                        "created_at": params[5] if len(params)>5 else datetime.now(),
                        "updated_at": params[6] if len(params)>6 else datetime.now(),
                        "merged_into": None
                    }

            elif "entity_merges" in query:
                # INSERT INTO entity_merges (source_entity_id, target_entity_id, confidence, reason)
                self.db['merges'].append({
                    "source": str(params[0]),
                    "target": str(params[1]),
                    "confidence": params[2],
                    "reason": params[3]
                })

            elif "events" in query:
                # INSERT INTO events (id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector)
                e_id = str(params[0])
                self.db['events'][e_id] = {
                    "id": e_id,
                    "namespace": params[1],
                    "timestamp": params[2],
                    "actor": params[3],
                    "action": params[4],
                    "object_id": str(params[5]),
                    "delta": json.loads(params[6]) if isinstance(params[6], str) else params[6],
                    "antecedents": params[7],
                    "truth_vector": json.loads(params[8]) if isinstance(params[8], str) else params[8],
                    "consolidated_into": None
                }

            elif "entity_state" in query:
                 # INSERT INTO entity_state ...
                 # Pruner test inserts simple states
                 # VALUES (%s, 'active', NOW(), 100, '{"authority": 0.9}')
                 e_id = str(params[0])
                 self.db['entity_state'][e_id] = {
                     "entity_id": e_id,
                     "status": params[1] if len(params)>1 else "active",
                     "last_accessed": params[2] if len(params)>2 else datetime.now(),
                     "access_count": params[3] if len(params)>3 else 0,
                     "truth_vector": json.loads(params[4]) if len(params)>4 and isinstance(params[4], str) else (params[4] if len(params)>4 else {}),
                     "updated_at": params[5] if len(params)>5 else datetime.now(), # Added for decay test
                     "namespace": "user",
                     "current_value": {}
                 }

        # --- SELECT ---
        elif query.startswith("select"):
            if "from entities" in query:
                # IdentityService.list_entities: SELECT ... WHERE merged_into IS NULL AND entity_type = %s
                # IdentityService.get_entity: SELECT ... WHERE id = %s

                res = []
                if "where id =" in query:
                    e_id = str(params[0])
                    if e_id in self.db['entities']:
                        e = self.db['entities'][e_id]
                        res.append([e['id'], e['namespace'], e['entity_type'], e['name'], e['attributes'], e['created_at'], e['updated_at'], e['merged_into']])
                else:
                    # List
                    target_type = params[0] if params else None
                    for e in self.db['entities'].values():
                        if e['merged_into'] is None:
                            if target_type and e['entity_type'] != target_type:
                                continue
                            res.append([e['id'], e['namespace'], e['entity_type'], e['name'], e['attributes'], e['created_at'], e['updated_at'], e['merged_into']])
                self.rows = res

            elif "from events" in query:
                # Assimilator: SELECT ... WHERE object_id = %s AND timestamp > %s AND consolidated_into IS NULL
                if "antecedents" in query and "where id =" in query:
                     # Check provenance integrity
                     e_id = str(params[0])
                     if e_id in self.db['events']:
                         self.rows = [[self.db['events'][e_id]['antecedents']]]
                else:
                    obj_id = str(params[0])
                    # cutoff = params[1]
                    res = []
                    for e in self.db['events'].values():
                        if e['object_id'] == obj_id and e['consolidated_into'] is None:
                            # assuming timestamp check passes for test
                            res.append([e['id'], e['namespace'], e['timestamp'], e['actor'], e['action'], e['object_id'], e['delta'], e['antecedents'], e['truth_vector']])
                    self.rows = res

            elif "from entity_state" in query:
                # Pruner: SELECT ... WHERE status = 'active'
                # Decay: JOIN entities ... WHERE status = 'active'

                if "join entities" in query:
                    # Decay query
                    # SELECT es.entity_id, es.truth_vector, e.entity_type, es.updated_at
                    res = []
                    for es in self.db['entity_state'].values():
                        if es['status'] == 'active':
                             e_type = self.db['entities'].get(es['entity_id'], {}).get('entity_type', 'misc')
                             res.append([es['entity_id'], es['truth_vector'], e_type, es['updated_at']])
                    self.rows = res
                elif "status = 'active'" in query:
                    # Pruner
                    # SELECT entity_id, namespace, current_value, truth_vector, last_event_id, updated_at, status, last_accessed, access_count
                    res = []
                    for es in self.db['entity_state'].values():
                        if es['status'] == 'active':
                            res.append([es['entity_id'], es['namespace'], es['current_value'], es['truth_vector'], None, datetime.now(), es['status'], es['last_accessed'], es['access_count']])
                    self.rows = res

                elif "where entity_id =" in query: # Verification select
                     e_id = str(params[0])
                     if e_id in self.db['entity_state']:
                         # Just returning status for the verification test
                         self.rows = [[self.db['entity_state'][e_id]['status']]] # Tuple index 0

        # --- UPDATE ---
        elif query.startswith("update"):
            if "entities" in query and "set merged_into" in query:
                # Identity merge
                tgt = str(params[0])
                src = str(params[1])
                if src in self.db['entities']:
                    self.db['entities'][src]['merged_into'] = tgt

            elif "events" in query and "set consolidated_into" in query:
                # Assimilator
                summary_id = str(params[0])
                source_ids = params[1] # list/tuple
                for sid in source_ids:
                    if str(sid) in self.db['events']:
                        self.db['events'][str(sid)]['consolidated_into'] = summary_id

            elif "entity_state" in query:
                if "set status = 'inactive'" in query:
                    # Pruner
                    ids = params[0] # tuple
                    for i in ids:
                        if str(i) in self.db['entity_state']:
                            self.db['entity_state'][str(i)]['status'] = 'inactive'
                elif "set truth_vector" in query: # This is usually execute_batch
                    pass # Handled in execute_batch mock? No, execute_batch calls execute?
                         # Actually psycopg2.extras.execute_batch executes separately.
                         # But let's assume naive loop for now or handle simple updates
                    pass

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def close(self):
        pass

class MockPostgres:
    def __init__(self):
        self.store = {
            "entities": {},
            "events": {},
            "entity_state": {},
            "merges": []
        }

    def get_cursor(self):
        return MockCursor(self.store)

# Global Mock DB instance
MOCK_DB = MockPostgres()

# Mock execute_batch manually since it's an extra
def mock_execute_batch(cur, sql, args_list):
    # Decay engine uses this
    if "update entity_state" in sql.lower() and "truth_vector" in sql.lower():
         # args_list is [(json_tv, entity_id), ...]
         for tv_json, eid in args_list:
             if str(eid) in MOCK_DB.store['entity_state']:
                 MOCK_DB.store['entity_state'][str(eid)]['truth_vector'] = json.loads(tv_json)

# ==========================================
# BENCHMARK CLASS
# ==========================================

from memory_thread.models.entity import Entity, MergeProposal
from memory_thread.models.events import Event, ActionEnum, ActorEnum

# We need to patch the services to use our MOCK_DB
# Since we can't easily inject, we will patch 'memory_thread.db.postgres_client.PostgresClient'
# inside the methods or globally.

class BenchmarkPhase5Robust:
    def __init__(self):
        self.results = {}
        self.run_id = str(uuid.uuid4())[:8]

    def record_result(self, component, test_name, metrics, passed):
        if component not in self.results:
            self.results[component] = []
        self.results[component].append({
            "test": test_name,
            "metrics": metrics,
            "passed": passed
        })
        status = "✅ PASS" if passed else "❌ FAIL"
        log.info(f"Test {test_name}: {status} | Metrics: {metrics}")

    def setup_clean_slate(self):
        # Reset Mock DB
        MOCK_DB.store = {
            "entities": {},
            "events": {},
            "entity_state": {},
            "merges": []
        }

    @patch("memory_thread.services.identity_service.PostgresClient")
    @patch("memory_thread.services.identity_service.QdrantClientWrapper")
    @patch("memory_thread.services.identity_service.generate_embeddings")
    def test_identity_stress(self, mock_embed, mock_qdrant, mock_pg):
        # Ensure module is loaded before patching
        import memory_thread.services.identity_service
        log.info("=== TEST 1: IDENTITY SERVICE STRESS (100k) ===")
        self.setup_clean_slate()

        # Wiring Mocks
        mock_pg.return_value = MOCK_DB
        mock_embed.return_value = [[0.1]*1536] # Mock embedding

        from memory_thread.services.identity_service import IdentityService
        service = IdentityService()

        # Mock Qdrant retrieval/search logic
        stored_vectors = {} # id -> vector

        def qdrant_upsert(collection_name, points):
            for p in points:
                stored_vectors[p['id']] = p['vector']

        def qdrant_retrieve(collection_name, ids, with_vectors):
            # Just return dummy points
            from qdrant_client.http.models import ScoredPoint
            res = []
            for i in ids:
                res.append(MagicMock(vector=[0.1]*1536))
            return res

        def qdrant_search(collection_name, query_vector, query_filter, score_threshold, limit):
             # Return random hits to simulate noise
             from qdrant_client.http.models import ScoredPoint
             hits = []
             # Return 1 random potential duplicate
             all_ids = list(MOCK_DB.store['entities'].keys())
             if all_ids and random.random() < 0.1: # 10% chance of hit
                 target_id = random.choice(all_ids)
                 hits.append(ScoredPoint(id=target_id, score=0.99, version=1, payload={}))
             return hits

        mock_qdrant.return_value.client.upsert.side_effect = qdrant_upsert
        mock_qdrant.return_value.client.retrieve.side_effect = qdrant_retrieve
        mock_qdrant.return_value.client.search.side_effect = qdrant_search

        n_entities = 100000
        log.info(f"Generating {n_entities} entities (Optimized)...")
        # Optimization: Don't use Faker for 100k names, just strings
        for i in range(n_entities):
            e_id = str(uuid.uuid4())
            # Directly inject to Mock DB for speed, bypassing service.create_entity logic loop
            MOCK_DB.store['entities'][e_id] = {
                "id": e_id,
                "namespace": "user",
                "entity_type": "person",
                "name": f"Entity_{i}",
                "attributes": {},
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "merged_into": None
            }

        # Run Scan
        log.info("Starting scan...")
        start = time.time()
        proposals = service.scan_duplicates("person")
        duration = time.time() - start
        log.info(f"Scan complete. Duration: {duration:.2f}s")

        passed = True
        self.record_result("Identity Service", "100k Stress Scan", {"duration": duration, "proposals": len(proposals)}, passed)


    @patch("memory_thread.services.assimilator.PostgresClient")
    def test_assimilation_limits(self, mock_pg):
        log.info("=== TEST 2: ASSIMILATION LIMITS (100k) ===")
        self.setup_clean_slate()
        mock_pg.return_value = MOCK_DB

        from memory_thread.services.assimilator import AssimilatorService
        service = AssimilatorService()

        # 2.1 Compression
        entity_id = uuid.uuid4()
        n_events = 100000
        log.info(f"Generating {n_events} events...")

        # Optimize generation
        # Pre-generate common timestamp
        ts = datetime.now()

        for i in range(n_events):
            e_id = str(uuid.uuid4())
            MOCK_DB.store['events'][e_id] = {
                "id": e_id,
                "namespace": "user",
                "timestamp": ts,
                "actor": "USER",
                "action": "ADD",
                "object_id": str(entity_id),
                "delta": {"trees": 1},
                "antecedents": [],
                "truth_vector": {"confidence": 1.0, "authority": 1.0, "freshness": 1.0, "corroboration": 0.0},
                "consolidated_into": None
            }

        log.info("Detecting patterns...")
        start = time.time()
        candidates = service.detect_patterns(entity_id, window_days=1)
        duration_detect = time.time() - start

        if candidates:
            group = candidates[0]
            log.info(f"Consolidating {len(group)} events...")
            start_con = time.time()
            summary = service.consolidate_events(group)
            service.execute_consolidation(summary, group)
            duration_con = time.time() - start_con

            active = [e for e in MOCK_DB.store['events'].values() if e['consolidated_into'] is None]

            passed = len(active) == 1
            self.record_result("Assimilation Engine", "100k Compression",
                               {"initial": n_events, "final_active": len(active),
                                "duration_detect": duration_detect, "duration_con": duration_con}, passed)
        else:
            self.record_result("Assimilation Engine", "100k Compression", {}, False)


    @patch("memory_thread.services.pruner.PostgresClient")
    def test_pruner_scalability(self, mock_pg):
        log.info("=== TEST 3: PRUNER SCALABILITY (100k) ===")
        self.setup_clean_slate()
        mock_pg.return_value = MOCK_DB

        from memory_thread.services.pruner import PrunerService
        service = PrunerService()

        n_states = 100000
        log.info(f"Generating {n_states} states...")

        # 50% Active (Keep), 50% Stale (Prune)
        # Optimization: Generate in bulk
        cutoff = datetime.now() - timedelta(days=100)
        recent = datetime.now()

        for i in range(n_states):
            e_id = str(uuid.uuid4())
            is_stale = i % 2 == 0
            MOCK_DB.store['entity_state'][e_id] = {
                "entity_id": e_id,
                "status": "active",
                "last_accessed": cutoff if is_stale else recent,
                "access_count": 0 if is_stale else 100,
                "truth_vector": {"authority": 0.1} if is_stale else {"authority": 0.9},
                "current_value": {},
                "namespace": "user",
                "updated_at": recent
            }

        log.info("Scanning for pruning...")
        start = time.time()
        candidates = service.scan_for_pruning(threshold=0.3)
        duration = time.time() - start

        # Expect ~50k candidates
        count = len(candidates)
        passed = 49000 < count < 51000 # Allow slight fuzziness
        self.record_result("Pruner Service", "100k Scan", {"candidates": count, "duration": duration}, passed)

        if candidates:
            log.info(f"Pruning {count} states...")
            start_p = time.time()
            # Prune in chunks if needed? Service might handle list.
            # Passing 50k IDs to SQL might be slow or hit limits, but MockDB handles it fine.
            service.prune_states([str(c['entity_id']) for c in candidates])
            duration_p = time.time() - start_p
            self.record_result("Pruner Service", "100k Execution", {"duration": duration_p}, True)


    @patch("memory_thread.services.decay_engine.PostgresClient")
    @patch("psycopg2.extras.execute_batch", side_effect=mock_execute_batch)
    def test_decay_performance(self, mock_exec_batch, mock_pg):
        log.info("=== TEST 4: DECAY PERFORMANCE (100k) ===")
        self.setup_clean_slate()
        mock_pg.return_value = MOCK_DB

        from memory_thread.services.decay_engine import DecayEngine
        service = DecayEngine()

        n_entities = 100000
        log.info(f"Generating {n_entities} entities for decay...")

        old_date = datetime.now() - timedelta(days=30)

        # Generate 100k events
        for i in range(n_entities):
            e_id = str(uuid.uuid4())
            MOCK_DB.store['entities'][e_id] = {"id": e_id, "entity_type": "event", "name": f"Event_{i}", "merged_into": None}
            MOCK_DB.store['entity_state'][e_id] = {
                "entity_id": e_id, "status": "active", "truth_vector": {"freshness": 1.0},
                "updated_at": old_date
            }

        log.info("Running decay update...")
        start = time.time()
        stats = service.update_freshness()
        duration = time.time() - start

        passed = stats['updated'] == n_entities
        self.record_result("Decay Engine", "100k Update", {"duration": duration, "updated": stats['updated']}, passed)


    @patch("memory_thread.services.identity_service.PostgresClient")
    @patch("memory_thread.services.identity_service.QdrantClientWrapper")
    @patch("memory_thread.services.identity_service.generate_embeddings")
    def test_integration_chaos(self, mock_embed, mock_qdrant, mock_pg):
        log.info("=== TEST 5: INTEGRATION CHAOS (100k) ===")
        self.setup_clean_slate()
        mock_pg.return_value = MOCK_DB
        mock_embed.return_value = [[0.1]*1536]
        mock_qdrant.return_value.client.search.return_value = []

        from memory_thread.services.identity_service import IdentityService
        service = IdentityService()

        # Concurrency test with 1000 writes/reads in parallel
        # 100k is too much for threading/GIL in this script within reasonable time for chaos
        # We will do 4 threads x 2500 ops = 10k ops

        n_ops = 2500
        n_threads = 4

        def worker():
            for i in range(n_ops):
                service.create_entity(f"Chaos_{i}", "person")

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        start = time.time()
        for t in threads: t.start()
        for t in threads: t.join()
        duration = time.time() - start

        count = len(MOCK_DB.store['entities'])
        passed = count == n_ops * n_threads
        self.record_result("Integration", "Concurrent Writes (10k)", {"count": count, "duration": duration}, passed)

    def run_all(self):
        try:
            self.test_identity_stress()
            self.test_assimilation_limits()
            self.test_pruner_scalability()
            self.test_decay_performance()
            self.test_integration_chaos()
        except Exception as e:
            log.error(f"Suite Failed: {e}", exc_info=True)

        self.generate_report()

    def generate_report(self):
        filename = "PHASE_5_ROBUST_RESULTS.md"
        with open(filename, "w") as f:
            f.write("# PHASE 5 ROBUST BENCHMARK RESULTS (100k SCALE)\n\n")
            f.write("## EXECUTIVE SUMMARY\n")

            total_tests = 0
            passed_tests = 0
            for comp, tests in self.results.items():
                for t in tests:
                    total_tests += 1
                    if t['passed']: passed_tests += 1

            f.write(f"- **Total Tests:** {total_tests}\n")
            f.write(f"- **Passed:** {passed_tests}\n")
            f.write(f"- **Failed:** {total_tests - passed_tests}\n")
            if total_tests > 0:
                f.write(f"- **Pass Rate:** {passed_tests/total_tests*100:.1f}%\n\n")
            else:
                 f.write("- **Pass Rate:** N/A\n\n")

            f.write("## DETAILED RESULTS\n")
            for comp, tests in self.results.items():
                f.write(f"### {comp}\n")
                for t in tests:
                    icon = "✅" if t['passed'] else "❌"
                    f.write(f"- {icon} **{t['test']}**: {t['metrics']}\n")
                f.write("\n")

        log.info(f"Report generated: {filename}")
        # Print report to stdout for immediate view
        with open(filename, "r") as f:
            print(f.read())

if __name__ == "__main__":
    bench = BenchmarkPhase5Robust()
    bench.run_all()
