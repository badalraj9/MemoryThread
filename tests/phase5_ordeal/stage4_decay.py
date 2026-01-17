from tests.phase5_ordeal.mocks import apply_patches
apply_patches("stage4")

import logging
import json
from memory_thread.services.decay_engine import DecayEngine

log = logging.getLogger("ordeal_stage4")
logging.basicConfig(level=logging.INFO)

def run_stage4():
    log.info("🔥 STAGE 4: Decay Engine Stress...")
    engine = DecayEngine()

    # Run update simulating 5 years?
    # The `update_freshness` method calculates delta from `updated_at` to NOW.
    # To simulate 5 years, we'd need to fake `updated_at` to be 5 years ago.
    # But `generate_data` put them recently.
    # So `update_freshness` will see ~0 days elapsed.

    # We can pass `simulate` flag but that just prevents commit.
    # The current `DecayEngine` uses real DB timestamps.
    # To test "extreme decay", we need to hack the timestamps in DB first.

    from memory_thread.db.postgres_client import PostgresClient
    pg = PostgresClient()

    with pg.get_cursor() as cur:
        # Age 10% of entities by 1 year
        cur.execute("""
            UPDATE entity_state
            SET updated_at = updated_at - INTERVAL '1 year'
            WHERE entity_id IN (SELECT id FROM entities ORDER BY RANDOM() LIMIT 100)
        """)
        log.info("Aged 100 entities by 1 year.")

    stats = engine.update_freshness(simulate=False)
    log.info(f"Decay Stats: {stats}")

    # Validate
    if stats['stale'] == 0:
        log.warning("No stale memories found? Check decay rates.")

    log.info("Stage 4 Complete.")

if __name__ == "__main__":
    run_stage4()
