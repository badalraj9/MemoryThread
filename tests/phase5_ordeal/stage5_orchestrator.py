from tests.phase5_ordeal.mocks import apply_patches
apply_patches("stage5")

import logging
import threading
import time
from memory_thread.services.maintenance_orchestrator import MaintenanceOrchestrator

log = logging.getLogger("ordeal_stage5")
logging.basicConfig(level=logging.INFO)

def run_stage5():
    log.info("🔥 STAGE 5: Orchestrator Chaos...")
    orch = MaintenanceOrchestrator()

    # Run multiple threads of orchestration to simulate race/overlap
    threads = []

    def job_runner():
        try:
            orch.run_all()
        except Exception as e:
            log.error(f"Orchestrator thread failed: {e}")

    for _ in range(5):
        t = threading.Thread(target=job_runner)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    log.info("Stage 5 Complete.")

if __name__ == "__main__":
    run_stage5()
