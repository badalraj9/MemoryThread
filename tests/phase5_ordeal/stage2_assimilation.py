from tests.phase5_ordeal.mocks import apply_patches
apply_patches("stage2")

import logging
import json
import uuid
from memory_thread.services.assimilator import AssimilatorService
from memory_thread.db.postgres_client import PostgresClient

log = logging.getLogger("ordeal_stage2")
logging.basicConfig(level=logging.INFO)

def run_stage2():
    log.info("🔥 STAGE 2: Extreme Assimilation...")
    service = AssimilatorService()
    pg = PostgresClient()

    # Identify "Chain Master" entity from Stage 0
    chain_master_id = None
    with pg.get_cursor() as cur:
        cur.execute("SELECT id FROM entities WHERE name = 'Chain Master'")
        row = cur.fetchone()
        if row:
            chain_master_id = row[0]

    if not chain_master_id:
        log.warning("Chain Master not found. Skipping massive chain test.")
    else:
        # Run assimilation on Chain Master
        log.info(f"Assimilating massive chains for {chain_master_id}...")
        try:
            groups = service.detect_patterns(uuid.UUID(str(chain_master_id)), window_days=30)
            log.info(f"Found {len(groups)} groups.")

            for group in groups:
                summary = service.consolidate_events(group)
                if summary:
                    service.execute_consolidation(summary, group)
            log.info("Chain Master assimilated.")
        except Exception as e:
            log.error(f"Assimilation crashed: {e}")

    # General Assimilation on random entities
    # Fetch 100 random entities
    with pg.get_cursor() as cur:
        cur.execute("SELECT id FROM entities ORDER BY RANDOM() LIMIT 100")
        rows = cur.fetchall()

    for row in rows:
        eid = row[0]
        try:
            groups = service.detect_patterns(uuid.UUID(str(eid)), window_days=30)
            for group in groups:
                summary = service.consolidate_events(group)
                if summary:
                    service.execute_consolidation(summary, group)
        except Exception as e:
            log.error(f"Random assimilation failed for {eid}: {e}")

    log.info("Stage 2 Complete.")

if __name__ == "__main__":
    run_stage2()
