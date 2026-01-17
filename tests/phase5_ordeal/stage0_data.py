from tests.phase5_ordeal.mocks import apply_patches
apply_patches("stage0")

import uuid
import random
import json
import logging
from datetime import datetime, timedelta
from faker import Faker
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.models.events import Event, ActorEnum, ActionEnum, TruthVector
from memory_thread.services.identity_service import IdentityService
from memory_thread.utils.embeddings import generate_embeddings
from memory_thread.db.qdrant_client import QdrantClientWrapper

log = logging.getLogger("ordeal_stage0")
logging.basicConfig(level=logging.INFO)

fake = Faker()

# Configuration (Scaled down for Sandbox)
NUM_ENTITIES = 2000 # vs 250k
NUM_EVENTS = 20000  # vs 15M
CHAINS_COUNT = 50   # vs 10k

def generate_data():
    pg = PostgresClient()
    qdrant = QdrantClientWrapper()
    identity_service = IdentityService()

    log.info("🔥 STAGE 0: Generating Chaos Dataset...")

    # 1. Generate Entities
    entities = []

    # Clusters
    clusters = [
        ["Jon Smyth", "John Smith", "J. Smith", "Johnny Smythe"],
        ["Apple", "Apple Inc", "APPLE", "apple fruit"],
        ["AI", "A.I", "Artificial Intel", "artificial intelligence"]
    ]

    for cluster in clusters:
        for name in cluster:
            e = identity_service.create_entity(name, "concept" if "AI" in name or "Apple" in name else "person")
            entities.append(e)

    # Random Entities
    for _ in range(NUM_ENTITIES):
        name = fake.name()
        e_type = random.choice(["person", "place", "organization"])
        # Inject fuzzy duplicates randomly
        if random.random() < 0.1:
            name_var = name + " " + random.choice(["Inc", "Jr", "Sr", "II"])
            identity_service.create_entity(name_var, e_type)

        e = identity_service.create_entity(name, e_type)
        entities.append(e)

    log.info(f"Created {len(entities)} entities.")

    # 2. Generate Events
    events = []
    base_time = datetime.now() - timedelta(days=20)

    with pg.get_cursor() as cur:
        for i in range(NUM_EVENTS):
            entity = random.choice(entities)
            timestamp = base_time + timedelta(minutes=i)

            # Anomalies
            if random.random() < 0.02: # Time corruption
                if random.random() < 0.5:
                    timestamp = base_time - timedelta(days=365) # Past
                else:
                    timestamp = base_time + timedelta(days=365) # Future

            delta = {"value": random.randint(1, 100)}
            action = ActionEnum.UPDATE

            # Contradictions
            if random.random() < 0.05:
                # Contradict previous (simplistic)
                delta = {"value": -9999}

            event_id = uuid.uuid4()
            tv = {
                "confidence": random.uniform(0.5, 1.0),
                "authority": random.uniform(0.1, 0.9),
                "freshness": 1.0,
                "corroboration": 1.0
            }

            cur.execute("""
                INSERT INTO events (id, namespace, timestamp, actor, action, object_id, delta, truth_vector)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(event_id), "user", timestamp, "USER", action.value, str(entity.id),
                json.dumps(delta), json.dumps(tv)
            ))

            # Update entity state (Layer 2) simulation
            cur.execute("""
                INSERT INTO entity_state (entity_id, namespace, current_value, truth_vector, last_event_id, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (entity_id) DO UPDATE
                SET current_value = EXCLUDED.current_value,
                    updated_at = EXCLUDED.updated_at,
                    last_event_id = EXCLUDED.last_event_id
            """, (
                str(entity.id), "user", json.dumps(delta), json.dumps(tv), str(event_id), timestamp
            ))

    # 3. Massive Provenance Chains
    log.info(f"Generating {CHAINS_COUNT} massive chains...")
    chain_entity = identity_service.create_entity("Chain Master", "system")
    with pg.get_cursor() as cur:
        for c in range(CHAINS_COUNT):
            chain_len = random.randint(100, 500) # Scaed down from 10k
            for k in range(chain_len):
                cur.execute("""
                    INSERT INTO events (id, namespace, timestamp, actor, action, object_id, delta, truth_vector)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    str(uuid.uuid4()), "user", datetime.now(), "SYSTEM", "ADD", str(chain_entity.id),
                    json.dumps({"counter": 1}), json.dumps({"confidence": 1.0, "authority": 1.0, "freshness": 1.0, "corroboration": 1.0})
                ))

    log.info("Stage 0 Complete.")

if __name__ == "__main__":
    generate_data()
