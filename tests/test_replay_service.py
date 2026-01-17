import unittest
from unittest.mock import MagicMock, patch
import uuid
import json
from datetime import datetime

from memory_thread.services.replay_service import ReplayService
from memory_thread.models.events import Event, ActorEnum, ActionEnum, TruthVector

class TestReplayService(unittest.TestCase):

    @patch("memory_thread.services.replay_service.PostgresClient")
    def test_capture_trace(self, mock_pg_cls):
        # Setup Mock DB
        mock_pg = MagicMock()
        mock_pg_cls.return_value = mock_pg
        mock_cur = MagicMock()
        mock_pg.get_cursor.return_value.__enter__.return_value = mock_cur

        # Mock Data
        e_id = uuid.uuid4()

        # Mock State
        mock_cur.fetchone.return_value = {
            "entity_id": e_id,
            "namespace": "user",
            "current_value": {"count": 10},
            "truth_vector": {"confidence": 1.0, "authority": 1.0, "freshness": 1.0, "corroboration": 0.0},
            "version": 1,
            "last_event_id": uuid.uuid4(),
            "updated_at": datetime.now()
        }

        # Mock Events
        mock_cur.fetchall.return_value = [
            {
                "id": uuid.uuid4(),
                "namespace": "user",
                "timestamp": datetime.now(),
                "actor": "USER",
                "action": "ADD",
                "object_id": e_id,
                "delta": {"count": 10},
                "antecedents": [],
                "truth_vector": {"confidence": 1.0, "authority": 1.0, "freshness": 1.0, "corroboration": 0.0}
            }
        ]

        service = ReplayService()
        trace = service.capture_trace(e_id)

        self.assertEqual(trace['entity_id'], str(e_id))
        self.assertEqual(len(trace['events']), 1)
        self.assertEqual(trace['final_state']['current_value']['count'], 10)

    def test_replay_trace_success(self):
        # Create synthetic trace
        e_id = uuid.uuid4()
        trace = {
            "entity_id": str(e_id),
            "final_state": {
                "entity_id": str(e_id),
                "namespace": "user",
                "current_value": {"count": 10},
                "truth_vector": {"confidence": 1.0, "authority": 1.0, "freshness": 1.0, "corroboration": 0.0},
                "version": 1,
                "last_event_id": str(uuid.uuid4()),
                "updated_at": datetime.now().isoformat()
            },
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "namespace": "user",
                    "timestamp": datetime.now().isoformat(),
                    "actor": "USER",
                    "action": "ADD",
                    "object_id": str(e_id),
                    "delta": {"count": 10},
                    "antecedents": [],
                    "truth_vector": {"confidence": 1.0, "authority": 1.0, "freshness": 1.0, "corroboration": 0.0}
                }
            ]
        }

        service = ReplayService()

        # We need to ensure StateDerivationService logic works for this test.
        # Assuming ADD action adds numbers.
        success, diffs, state = service.replay_trace(trace)

        self.assertTrue(success, f"Replay failed with diffs: {diffs}")
        self.assertEqual(state.current_value['count'], 10)

    def test_replay_trace_failure(self):
        # Trace expects 20, but events only produce 10
        e_id = uuid.uuid4()
        trace = {
            "entity_id": str(e_id),
            "final_state": {
                "entity_id": str(e_id),
                "namespace": "user",
                "current_value": {"count": 20}, # EXPECTED 20
                "truth_vector": {"confidence": 1.0, "authority": 1.0, "freshness": 1.0, "corroboration": 0.0},
                "version": 1,
                "last_event_id": str(uuid.uuid4()),
                "updated_at": datetime.now().isoformat()
            },
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "namespace": "user",
                    "timestamp": datetime.now().isoformat(),
                    "actor": "USER",
                    "action": "ADD",
                    "object_id": str(e_id),
                    "delta": {"count": 10}, # ACTUALLY ADDS 10
                    "antecedents": [],
                    "truth_vector": {"confidence": 1.0, "authority": 1.0, "freshness": 1.0, "corroboration": 0.0}
                }
            ]
        }

        service = ReplayService()
        success, diffs, state = service.replay_trace(trace)

        self.assertFalse(success)
        self.assertTrue(any("Value Mismatch" in d for d in diffs))

if __name__ == "__main__":
    unittest.main()
