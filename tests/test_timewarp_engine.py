"""
Tests for TimewarpEngine.

Tests cover:
- Late event insertion
- Timeline repair
- State recomputation
"""
import uuid
import datetime
import json
import unittest
from unittest.mock import Mock, patch, MagicMock

from memory_thread.models.events import (
    Event, EntityState, TruthVector, ActorEnum, ActionEnum
)
from memory_thread.services.timewarp_engine import TimewarpEngine


class TestTimewarpEngine(unittest.TestCase):
    """Tests for TimewarpEngine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.entity_id = uuid.uuid4()
        self.base_time = datetime.datetime.utcnow()
    
    def _create_event(self, action: ActionEnum, delta: dict, days_ago: int = 0) -> Event:
        """Helper to create test events."""
        return Event(
            actor=ActorEnum.USER,
            action=action,
            object_id=self.entity_id,
            delta=delta,
            timestamp=self.base_time - datetime.timedelta(days=days_ago),
            truth_vector=TruthVector(
                confidence=1.0,
                authority=1.0,
                freshness=1.0,
                corroboration=0.0
            )
        )
    
    @patch('memory_thread.services.timewarp_engine.PostgresClient')
    @patch('memory_thread.services.timewarp_engine.SnapshotService')
    @patch('memory_thread.services.timewarp_engine.ReplayService')
    def test_recompute_state_single_event(self, mock_replay, mock_snapshot, mock_pg):
        """Test state recomputation with a single event."""
        engine = TimewarpEngine()
        
        # Mock DB to return one event
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{
            'id': str(uuid.uuid4()),
            'namespace': 'user',
            'timestamp': self.base_time,
            'actor': 'USER',
            'action': 'PLANT',
            'object_id': str(self.entity_id),
            'delta': {'tree_count': 100},
            'antecedents': [],
            'truth_vector': json.dumps({
                'confidence': 1.0,
                'authority': 1.0,
                'freshness': 1.0,
                'corroboration': 0.0
            })
        }]
        
        mock_pg_instance = mock_pg.return_value
        mock_pg_instance.get_cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_pg_instance.get_cursor.return_value.__exit__ = Mock(return_value=False)
        engine.pg = mock_pg_instance
        
        state = engine._recompute_state(self.entity_id)
        
        self.assertIsNotNone(state)
        self.assertEqual(state.entity_id, self.entity_id)
        self.assertEqual(state.current_value.get('tree_count'), 100)
    
    @patch('memory_thread.services.timewarp_engine.PostgresClient')
    @patch('memory_thread.services.timewarp_engine.SnapshotService')
    @patch('memory_thread.services.timewarp_engine.ReplayService')
    def test_recompute_state_multiple_events(self, mock_replay, mock_snapshot, mock_pg):
        """Test state recomputation with multiple events in order."""
        engine = TimewarpEngine()
        
        event_id_1 = uuid.uuid4()
        event_id_2 = uuid.uuid4()
        event_id_3 = uuid.uuid4()
        
        # Mock DB to return events in chronological order
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                'id': str(event_id_1),
                'namespace': 'user',
                'timestamp': self.base_time - datetime.timedelta(days=2),
                'actor': 'USER',
                'action': 'PLANT',
                'object_id': str(self.entity_id),
                'delta': {'count': 100},
                'antecedents': [],
                'truth_vector': json.dumps({
                    'confidence': 1.0, 'authority': 1.0,
                    'freshness': 1.0, 'corroboration': 0.0
                })
            },
            {
                'id': str(event_id_2),
                'namespace': 'user',
                'timestamp': self.base_time - datetime.timedelta(days=1),
                'actor': 'USER',
                'action': 'ADD',
                'object_id': str(self.entity_id),
                'delta': {'count': 50},
                'antecedents': [],
                'truth_vector': json.dumps({
                    'confidence': 1.0, 'authority': 1.0,
                    'freshness': 1.0, 'corroboration': 0.0
                })
            },
            {
                'id': str(event_id_3),
                'namespace': 'user',
                'timestamp': self.base_time,
                'actor': 'SYSTEM',
                'action': 'REMOVE',
                'object_id': str(self.entity_id),
                'delta': {'count': 25},
                'antecedents': [],
                'truth_vector': json.dumps({
                    'confidence': 1.0, 'authority': 1.0,
                    'freshness': 1.0, 'corroboration': 0.0
                })
            }
        ]
        
        mock_pg_instance = mock_pg.return_value
        mock_pg_instance.get_cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_pg_instance.get_cursor.return_value.__exit__ = Mock(return_value=False)
        engine.pg = mock_pg_instance
        
        state = engine._recompute_state(self.entity_id)
        
        # 100 + 50 - 25 = 125
        self.assertEqual(state.current_value.get('count'), 125)
        self.assertEqual(state.version, 3)  # 3 events applied
    
    @patch('memory_thread.services.timewarp_engine.PostgresClient')
    @patch('memory_thread.services.timewarp_engine.SnapshotService')
    @patch('memory_thread.services.timewarp_engine.ReplayService')
    def test_recompute_state_no_events(self, mock_replay, mock_snapshot, mock_pg):
        """Test state recomputation with no events returns None."""
        engine = TimewarpEngine()
        
        # Mock empty result
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        
        mock_pg_instance = mock_pg.return_value
        mock_pg_instance.get_cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_pg_instance.get_cursor.return_value.__exit__ = Mock(return_value=False)
        engine.pg = mock_pg_instance
        
        state = engine._recompute_state(self.entity_id)
        
        self.assertIsNone(state)


class TestLateEventInsertion(unittest.TestCase):
    """Tests for late event insertion and timeline repair."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.entity_id = uuid.uuid4()
        self.base_time = datetime.datetime.utcnow()
    
    @patch('memory_thread.services.timewarp_engine.PostgresClient')
    @patch('memory_thread.services.timewarp_engine.SnapshotService')
    @patch('memory_thread.services.timewarp_engine.ReplayService')
    def test_insert_late_event_structure(self, mock_replay, mock_snapshot, mock_pg):
        """Test that insert_late_event has correct structure."""
        engine = TimewarpEngine()
        
        # Mock the cursor for both insert and recompute
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{
            'id': str(uuid.uuid4()),
            'namespace': 'user',
            'timestamp': self.base_time,
            'actor': 'USER',
            'action': 'ADD',
            'object_id': str(self.entity_id),
            'delta': {'value': 10},
            'antecedents': [],
            'truth_vector': json.dumps({
                'confidence': 1.0, 'authority': 1.0,
                'freshness': 1.0, 'corroboration': 0.0
            })
        }]
        
        mock_pg_instance = mock_pg.return_value
        mock_pg_instance.get_cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_pg_instance.get_cursor.return_value.__exit__ = Mock(return_value=False)
        engine.pg = mock_pg_instance
        
        # Create a "late" event (timestamp in the past)
        late_event = Event(
            actor=ActorEnum.USER,
            action=ActionEnum.ADD,
            object_id=self.entity_id,
            delta={"value": 5},
            timestamp=self.base_time - datetime.timedelta(days=5),
            truth_vector=TruthVector(
                confidence=1.0,
                authority=1.0,
                freshness=1.0,
                corroboration=0.0
            )
        )
        
        result = engine.insert_late_event(late_event)
        
        # Verify the result structure
        self.assertIn('status', result)
        self.assertEqual(result['status'], 'repaired')
        self.assertIn('new_state', result)


if __name__ == '__main__':
    unittest.main()
