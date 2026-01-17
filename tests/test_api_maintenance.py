import unittest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from memory_thread.api.main import app

class TestMaintenanceAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_health_stats(self):
        response = self.client.get("/maintenance/health/stats")
        self.assertEqual(response.status_code, 200)
        self.assertIn("entities_count", response.json())

    @patch('memory_thread.api.routers.maintenance.IdentityService')
    def test_get_proposals(self, MockIdentityService):
        mock_service = MockIdentityService.return_value
        mock_service.scan_duplicates.return_value = []

        response = self.client.get("/maintenance/proposals")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

if __name__ == '__main__':
    unittest.main()
