import logging
from memory_thread.services.identity_service import IdentityService
from memory_thread.services.assimilator import AssimilatorService
from memory_thread.services.pruner import PrunerService
from memory_thread.services.decay_engine import DecayEngine

log = logging.getLogger(__name__)

class MaintenanceOrchestrator:
    def __init__(self):
        self.identity = IdentityService()
        self.assimilator = AssimilatorService()
        self.pruner = PrunerService()
        self.decay = DecayEngine()

    def run_daily_jobs(self):
        """
        Runs decay updates.
        """
        log.info("Starting Daily Maintenance...")
        stats = self.decay.update_freshness()
        log.info(f"Daily Decay: {stats}")
        log.info("Daily Maintenance Complete.")

    def run_weekly_jobs(self):
        """
        Runs identity scan and assimilation.
        """
        log.info("Starting Weekly Maintenance...")

        # 1. Identity Scan
        # For now, just scan generic types or configurable
        for type in ["person", "organization", "place"]:
            proposals = self.identity.scan_duplicates(type, threshold=0.98) # Conservative auto-merge
            for p in proposals:
                if p.confidence > 0.98:
                    self.identity.execute_merge(p)
            log.info(f"Identity Scan ({type}): {len(proposals)} proposals found.")

        # 2. Assimilation
        # Needs list of active entities.
        # This is expensive to run on ALL. Usually based on queue or dirty flag.
        # For prototype, we skip or run on top 10 most active?
        pass # Placeholder for full implementation

    def run_monthly_jobs(self):
        """
        Runs pruner.
        """
        log.info("Starting Monthly Maintenance...")
        candidates = self.pruner.scan_for_pruning(threshold=0.3)
        ids = [str(c['entity_id']) for c in candidates]
        if ids:
            self.pruner.prune_states(ids)
        log.info(f"Pruner: {len(ids)} states pruned.")

    def run_all(self):
        self.run_daily_jobs()
        self.run_weekly_jobs()
        self.run_monthly_jobs()
