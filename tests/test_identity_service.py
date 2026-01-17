import unittest
import uuid
import json
from unittest.mock import MagicMock, patch
from memory_thread.services.identity_service import IdentityService, MergeProposal
from memory_thread.models.entity import Entity

class TestIdentityService(unittest.TestCase):
    def setUp(self):
        self.mock_pg = MagicMock()
        self.mock_qdrant = MagicMock()

        with patch('memory_thread.services.identity_service.PostgresClient', return_value=self.mock_pg), \
             patch('memory_thread.services.identity_service.QdrantClientWrapper', return_value=self.mock_qdrant):
            self.service = IdentityService()

    def test_create_entity(self):
        # Mock cursor
        mock_cursor = MagicMock()
        self.mock_pg.get_cursor.return_value.__enter__.return_value = mock_cursor

        # Mock Qdrant upsert
        self.mock_qdrant.client.upsert = MagicMock()

        entity = self.service.create_entity("John Doe", "person", {"age": 30})

        self.assertIsNotNone(entity.id)
        self.assertEqual(entity.name, "John Doe")

        # Verify SQL insert
        mock_cursor.execute.assert_called_once()
        args = mock_cursor.execute.call_args[0]
        self.assertIn("INSERT INTO entities", args[0])

        # Verify Qdrant upsert
        self.mock_qdrant.client.upsert.assert_called_once()

    def test_scan_duplicates(self):
        # Setup mocks
        e1 = Entity(name="John Doe", entity_type="person", id=uuid.uuid4())
        e2 = Entity(name="Johnathan Doe", entity_type="person", id=uuid.uuid4())

        self.service.list_entities = MagicMock(return_value=[e1, e2])
        self.service.get_entity = MagicMock(side_effect=lambda id: e1 if id == e1.id else e2)

        # Mock Qdrant retrieve (return a dummy vector)
        mock_point = MagicMock()
        mock_point.vector = [0.1] * 1536
        self.mock_qdrant.client.retrieve.return_value = [mock_point]

        # Mock Qdrant search (return e2 as neighbor for e1)
        mock_hit = MagicMock()
        mock_hit.id = str(e2.id)
        mock_hit.score = 0.96
        self.mock_qdrant.client.search.return_value = [mock_hit]

        proposals = self.service.scan_duplicates("person")

        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].confidence, 0.96)

    def test_execute_merge(self):
        e1 = Entity(name="John Doe", entity_type="person", id=uuid.uuid4())
        e2 = Entity(name="Johnathan Doe", entity_type="person", id=uuid.uuid4())

        proposal = MergeProposal(
            source_entity=e1,
            target_entity=e2,
            confidence=0.96,
            reason="Sim"
        )

        mock_cursor = MagicMock()
        self.mock_pg.get_cursor.return_value.__enter__.return_value = mock_cursor

        self.service.execute_merge(proposal)

        # Verify SQL update
        self.assertEqual(mock_cursor.execute.call_count, 2) # UPDATE entity + INSERT log

if __name__ == '__main__':
    unittest.main()
