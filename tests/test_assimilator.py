import unittest
import uuid
import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from memory_thread.services.assimilator import AssimilatorService
from memory_thread.models.events import Event, ActionEnum, ActorEnum, TruthVector

class TestAssimilatorService(unittest.TestCase):
    def setUp(self):
        self.mock_pg = MagicMock()
        with patch('memory_thread.services.assimilator.PostgresClient', return_value=self.mock_pg):
            self.service = AssimilatorService()

    def test_consolidate_events_arithmetic(self):
        # Create 5 "ADD TREE" events
        events = []
        obj_id = uuid.uuid4()
        for i in range(5):
            e = Event(
                id=uuid.uuid4(),
                namespace="user",
                timestamp=datetime.now(),
                actor=ActorEnum.USER,
                action=ActionEnum.ADD,
                object_id=obj_id,
                delta={"trees": 10},
                truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=1.0)
            )
            events.append(e)

        summary = self.service.consolidate_events(events)

        self.assertIsNotNone(summary)
        self.assertEqual(summary.object_id, obj_id)
        self.assertEqual(summary.delta["trees"], 50) # 10 * 5
        self.assertEqual(len(summary.antecedents), 5)
        self.assertEqual(summary.actor, ActorEnum.SYSTEM)

    def test_consolidate_events_state_update(self):
        # Create 3 "UPDATE STATUS" events
        events = []
        obj_id = uuid.uuid4()
        statuses = ["started", "processing", "finished"]

        for s in statuses:
            e = Event(
                id=uuid.uuid4(),
                namespace="user",
                timestamp=datetime.now(),
                actor=ActorEnum.USER,
                action=ActionEnum.UPDATE,
                object_id=obj_id,
                delta={"status": s},
                truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=1.0)
            )
            events.append(e)

        summary = self.service.consolidate_events(events)

        self.assertEqual(summary.delta["status"], "finished")

    def test_detect_patterns(self):
        # Mock database return
        # Setup: 3 events same type, 1 different
        obj_id = uuid.uuid4()
        tv = {"confidence": 1.0, "authority": 1.0, "freshness": 1.0, "corroboration": 1.0}
        rows = [
            (uuid.uuid4(), "user", datetime.now(), "USER", "ADD", obj_id, {"x": 1}, [], tv),
            (uuid.uuid4(), "user", datetime.now(), "USER", "ADD", obj_id, {"x": 1}, [], tv),
            (uuid.uuid4(), "user", datetime.now(), "USER", "ADD", obj_id, {"x": 1}, [], tv),
            (uuid.uuid4(), "user", datetime.now(), "USER", "REMOVE", obj_id, {"x": 1}, [], tv),
        ]

        mock_cursor = MagicMock()
        self.mock_pg.get_cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = rows

        groups = self.service.detect_patterns(obj_id)

        # Should find 2 groups:
        # Group 1: 3 ADD events
        # Group 2: 1 REMOVE event (though strictly a group of 1 isn't a pattern usually,
        # but my logic returns it if it's the end of chain.
        # Actually my logic: "if len(current_group) > 1: groups.append".
        # So group 2 (len 1) should be dropped?
        # Let's check logic:
        # Loop i=1 (Event 2): Match Event 1 -> append. Group=[E1, E2]
        # Loop i=2 (Event 3): Match Event 2 -> append. Group=[E1, E2, E3]
        # Loop i=3 (Event 4): No match Event 3.
        #    -> groups.append([E1, E2, E3])
        #    -> current_group=[E4]
        # End Loop.
        # if len(current_group) > 1: append. [E4] has len 1, so ignored.

        # Expectation: 1 group of 3 events.

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 3)
        self.assertEqual(groups[0][0].action, ActionEnum.ADD)

if __name__ == '__main__':
    unittest.main()
