import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from memory_thread.services.pruner import PrunerService

class TestPrunerService(unittest.TestCase):
    def setUp(self):
        self.mock_pg = MagicMock()
        with patch('memory_thread.services.pruner.PostgresClient', return_value=self.mock_pg):
            self.service = PrunerService()

    def test_calculate_pruning_score(self):
        # Case 1: Fresh, frequent, important -> High score
        state_high = {
            "last_accessed": datetime.now(),
            "access_count": 100,
            "truth_vector": {"authority": 1.0}
        }
        score = self.service.calculate_pruning_score(state_high)
        # Recency (1.0 * 0.5) + Importance (1.0 * 0.3) + Freq (1.0 * 0.2) = 1.0
        self.assertAlmostEqual(score, 1.0, places=1)

        # Case 2: Old, rare, unimportant -> Low score
        state_low = {
            "last_accessed": datetime.now() - timedelta(days=91), # >90 days
            "access_count": 0,
            "truth_vector": {"authority": 0.0}
        }
        score_low = self.service.calculate_pruning_score(state_low)
        # Recency (0.0) + Importance (0.0) + Freq (0.0) = 0.0
        self.assertAlmostEqual(score_low, 0.0, places=1)

    def test_scan_for_pruning(self):
        # Mock DB
        rows = [
            # High value
            (uuid.uuid4(), "ns", {}, {"authority": 1.0}, uuid.uuid4(), datetime.now(), "active", datetime.now(), 100),
            # Low value
            (uuid.uuid4(), "ns", {}, {"authority": 0.0}, uuid.uuid4(), datetime.now(), "active", datetime.now() - timedelta(days=100), 0)
        ]

        mock_cursor = MagicMock()
        self.mock_pg.get_cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = rows

        candidates = self.service.scan_for_pruning(threshold=0.3)

        self.assertEqual(len(candidates), 1) # Only the low value one

if __name__ == '__main__':
    unittest.main()
