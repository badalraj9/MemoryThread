import unittest
from unittest.mock import MagicMock, patch
from memory_thread.services.maintenance_orchestrator import MaintenanceOrchestrator

class TestMaintenanceOrchestrator(unittest.TestCase):
    def setUp(self):
        with patch('memory_thread.services.maintenance_orchestrator.IdentityService'), \
             patch('memory_thread.services.maintenance_orchestrator.AssimilatorService'), \
             patch('memory_thread.services.maintenance_orchestrator.PrunerService'), \
             patch('memory_thread.services.maintenance_orchestrator.DecayEngine'):
            self.orch = MaintenanceOrchestrator()

    def test_run_all(self):
        self.orch.decay.update_freshness = MagicMock(return_value={})
        self.orch.identity.scan_duplicates = MagicMock(return_value=[])
        self.orch.pruner.scan_for_pruning = MagicMock(return_value=[])

        self.orch.run_all()

        self.orch.decay.update_freshness.assert_called_once()
        self.orch.identity.scan_duplicates.assert_called()
        self.orch.pruner.scan_for_pruning.assert_called()

if __name__ == '__main__':
    unittest.main()
