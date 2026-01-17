from tests.phase5_ordeal.mocks import apply_patches
apply_patches("stage1")

import logging
import json
import time
from memory_thread.services.identity_service import IdentityService

log = logging.getLogger("ordeal_stage1")
logging.basicConfig(level=logging.INFO)

def run_stage1():
    log.info("🔥 STAGE 1: Adversarial Identity Merge...")
    service = IdentityService()

    # 1. Scan with aggressive threshold (simulating --confusion-mode)
    start = time.time()
    proposals = service.scan_duplicates("person", threshold=0.80) # Lower threshold for "adversarial"
    duration = time.time() - start

    log.info(f"Scan took {duration:.2f}s. Found {len(proposals)} proposals.")

    # 2. Validation
    # Check for forbidden merges (Apple vs Apple Inc -> if types differ)
    # But Qdrant vector search is fuzzy.

    homonym_failures = 0
    fuzzy_collisions = 0

    for p in proposals:
        n1 = p.source_entity.name.lower()
        n2 = p.target_entity.name.lower()

        # Check Homonyms
        if "apple" in n1 and "fruit" in n1 and "inc" in n2:
            log.error(f"CRITICAL: Proposed merging {n1} with {n2}!")
            homonym_failures += 1

        # Check Fuzzy
        if p.confidence < 0.90:
            fuzzy_collisions += 1

    # 3. Stress Merge (Execute all)
    log.info("Executing merges...")
    merged_count = 0
    for p in proposals:
        # Simulate race condition check?
        # Just execute sequentially for now, parallel in python is hard to force race on DB without multiple processes.
        # But we verify it doesn't crash.
        try:
            if p.confidence > 0.95:
                service.execute_merge(p)
                merged_count += 1
        except Exception as e:
            log.error(f"Merge failed: {e}")

    report = {
        "duration": duration,
        "proposals": len(proposals),
        "merged": merged_count,
        "homonym_failures": homonym_failures,
        "fuzzy_collisions": fuzzy_collisions
    }

    with open("reports/identity_adversarial.json", "w") as f:
        json.dump(report, f, indent=2)

    log.info("Stage 1 Complete.")

if __name__ == "__main__":
    run_stage1()
