"""
Comprehensive tests for TMS (Truth Management System) services.

Tests cover:
- Truth Vector scoring with configurable weights
- Freshness decay calculations
- State derivation pipeline
- Database integration for state persistence
"""
import uuid
import datetime
import unittest
from unittest.mock import Mock, patch, MagicMock

from memory_thread.models.events import (
    Event, EntityState, TruthVector, ActorEnum, ActionEnum
)
from memory_thread.services.tms_service import (
    TruthVectorService, StateDerivationService, TMSService
)


class TestTruthVectorService(unittest.TestCase):
    """Tests for TruthVectorService."""
    
    def test_calculate_score_default_weights(self):
        """Test score calculation with default configuration."""
        vector = TruthVector(
            confidence=1.0,
            authority=1.0,
            freshness=1.0,
            corroboration=0.0
        )
        
        score = TruthVectorService.calculate_score(vector)
        
        # With default weights: 1*1.0 + 1.2*1.0 + 0.8*1.0 + 0.6*log(1) = 3.0
        # log(1+0) = 0, so corroboration contributes 0
        self.assertGreater(score, 0)
        self.assertAlmostEqual(score, 3.0, places=1)
    
    def test_calculate_score_with_corroboration(self):
        """Test that corroboration increases score logarithmically."""
        v1 = TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0)
        v2 = TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=10.0)
        
        score1 = TruthVectorService.calculate_score(v1)
        score2 = TruthVectorService.calculate_score(v2)
        
        # More corroboration = higher score
        self.assertGreater(score2, score1)
    
    def test_calculate_score_low_confidence(self):
        """Test that low confidence reduces score."""
        high_conf = TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0)
        low_conf = TruthVector(confidence=0.2, authority=1.0, freshness=1.0, corroboration=0.0)
        
        score_high = TruthVectorService.calculate_score(high_conf)
        score_low = TruthVectorService.calculate_score(low_conf)
        
        self.assertGreater(score_high, score_low)
    
    def test_decay_freshness_event_type(self):
        """Test freshness decay for event type (fast decay)."""
        vector = TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0)
        
        # Event from 10 days ago
        event_time = datetime.datetime.utcnow() - datetime.timedelta(days=10)
        
        decayed = TruthVectorService.decay_freshness(vector, event_time, "event")
        
        # Events decay fast (lambda=0.1), after 10 days: e^(-0.1*10) ≈ 0.367
        self.assertLess(decayed, 0.5)
        self.assertGreater(decayed, 0.3)
    
    def test_decay_freshness_fact_type(self):
        """Test freshness decay for fact type (slow decay)."""
        vector = TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0)
        
        # Fact from 100 days ago
        event_time = datetime.datetime.utcnow() - datetime.timedelta(days=100)
        
        decayed = TruthVectorService.decay_freshness(vector, event_time, "fact")
        
        # Facts decay slowly (lambda=0.001), after 100 days: e^(-0.1) ≈ 0.90
        self.assertGreater(decayed, 0.85)
    
    def test_decay_freshness_identity_never_decays(self):
        """Test that identity type never decays."""
        vector = TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0)
        
        # Identity from 1000 days ago
        event_time = datetime.datetime.utcnow() - datetime.timedelta(days=1000)
        
        decayed = TruthVectorService.decay_freshness(vector, event_time, "identity")
        
        # Identity has rate=0, should return 1.0
        self.assertEqual(decayed, 1.0)
    
    def test_decay_freshness_floor(self):
        """Test that freshness never goes below 0.01."""
        vector = TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0)
        
        # Very old prediction (fast decay)
        event_time = datetime.datetime.utcnow() - datetime.timedelta(days=365)
        
        decayed = TruthVectorService.decay_freshness(vector, event_time, "prediction")
        
        # Should hit floor
        self.assertGreaterEqual(decayed, 0.01)
    
    def test_merge_vectors(self):
        """Test vector merging."""
        v1 = TruthVector(confidence=0.8, authority=0.7, freshness=0.9, corroboration=2.0)
        v2 = TruthVector(confidence=0.6, authority=0.9, freshness=0.5, corroboration=1.0)
        
        merged = TruthVectorService.merge_vectors(v1, v2)
        
        # Authority takes max
        self.assertEqual(merged.authority, 0.9)
        # Freshness takes max
        self.assertEqual(merged.freshness, 0.9)
        # Corroboration increases
        self.assertGreater(merged.corroboration, v1.corroboration)


class TestStateDerivationService(unittest.TestCase):
    """Tests for StateDerivationService."""
    
    def test_apply_event_add_action(self):
        """Test applying ADD action to state."""
        entity_id = uuid.uuid4()
        state = EntityState(
            entity_id=entity_id,
            namespace="user",
            current_value={"count": 100},
            truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0),
            last_event_id=uuid.uuid4()
        )
        
        event = Event(
            actor=ActorEnum.USER,
            action=ActionEnum.ADD,
            object_id=entity_id,
            delta={"count": 50},
            truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0)
        )
        
        new_state = StateDerivationService.apply_event(state, event)
        
        self.assertEqual(new_state.current_value["count"], 150)
        self.assertEqual(new_state.version, 1)
    
    def test_apply_event_remove_action(self):
        """Test applying REMOVE action to state."""
        entity_id = uuid.uuid4()
        state = EntityState(
            entity_id=entity_id,
            namespace="user",
            current_value={"inventory": 500},
            truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0),
            last_event_id=uuid.uuid4()
        )
        
        event = Event(
            actor=ActorEnum.SYSTEM,
            action=ActionEnum.REMOVE,
            object_id=entity_id,
            delta={"inventory": 75},
            truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0)
        )
        
        new_state = StateDerivationService.apply_event(state, event)
        
        self.assertEqual(new_state.current_value["inventory"], 425)
    
    def test_apply_event_update_action(self):
        """Test applying UPDATE action to state."""
        entity_id = uuid.uuid4()
        state = EntityState(
            entity_id=entity_id,
            namespace="user",
            current_value={"status": "pending", "count": 10},
            truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0),
            last_event_id=uuid.uuid4()
        )
        
        event = Event(
            actor=ActorEnum.AGENT,
            action=ActionEnum.UPDATE,
            object_id=entity_id,
            delta={"status": "completed", "count": 99},
            truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0)
        )
        
        new_state = StateDerivationService.apply_event(state, event)
        
        self.assertEqual(new_state.current_value["status"], "completed")
        self.assertEqual(new_state.current_value["count"], 99)
    
    def test_apply_event_mismatch_raises(self):
        """Test that mismatched entity IDs raise ValueError."""
        state = EntityState(
            entity_id=uuid.uuid4(),
            namespace="user",
            current_value={},
            truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0),
            last_event_id=uuid.uuid4()
        )
        
        event = Event(
            actor=ActorEnum.USER,
            action=ActionEnum.UPDATE,
            object_id=uuid.uuid4(),  # Different ID
            delta={},
            truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0)
        )
        
        with self.assertRaises(ValueError):
            StateDerivationService.apply_event(state, event)


class TestTMSService(unittest.TestCase):
    """Tests for TMSService."""
    
    def test_create_event(self):
        """Test event creation."""
        tms = TMSService()
        object_id = uuid.uuid4()
        
        event = tms.create_event(
            actor=ActorEnum.USER,
            action=ActionEnum.ADD,
            object_id=object_id,
            delta={"value": 42}
        )
        
        self.assertIsInstance(event.id, uuid.UUID)
        self.assertEqual(event.actor, ActorEnum.USER)
        self.assertEqual(event.action, ActionEnum.ADD)
        self.assertEqual(event.object_id, object_id)
        self.assertEqual(event.delta, {"value": 42})
        self.assertEqual(event.truth_vector.freshness, 1.0)
    
    def test_create_event_with_custom_confidence(self):
        """Test event creation with custom confidence/authority."""
        tms = TMSService()
        
        event = tms.create_event(
            actor=ActorEnum.AGENT,
            action=ActionEnum.INFER,
            object_id=uuid.uuid4(),
            delta={"inference": "test"},
            confidence=0.7,
            authority=0.5
        )
        
        self.assertEqual(event.truth_vector.confidence, 0.7)
        self.assertEqual(event.truth_vector.authority, 0.5)
    
    @patch('memory_thread.services.tms_service.TMSService.pg')
    def test_get_current_state_found(self, mock_pg):
        """Test getting state when it exists."""
        tms = TMSService()
        entity_id = uuid.uuid4()
        
        # Mock cursor context manager
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'entity_id': str(entity_id),
            'namespace': 'user',
            'current_value': '{"count": 100}',
            'truth_vector': '{"confidence": 1.0, "authority": 1.0, "freshness": 0.9, "corroboration": 2.0}',
            'version': 5,
            'last_event_id': str(uuid.uuid4()),
            'updated_at': datetime.datetime.utcnow()
        }
        
        mock_pg.get_cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_pg.get_cursor.return_value.__exit__ = Mock(return_value=False)
        
        state = tms.get_current_state(entity_id)
        
        self.assertIsNotNone(state)
        self.assertEqual(state.entity_id, entity_id)
        self.assertEqual(state.version, 5)
    
    @patch('memory_thread.services.tms_service.TMSService.pg')
    def test_get_current_state_not_found(self, mock_pg):
        """Test getting state when it doesn't exist."""
        tms = TMSService()
        
        # Mock empty result
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        
        mock_pg.get_cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_pg.get_cursor.return_value.__exit__ = Mock(return_value=False)
        
        state = tms.get_current_state(uuid.uuid4())
        
        self.assertIsNone(state)


class TestFiveThousandTreesProblem(unittest.TestCase):
    """
    The famous "5000 Trees" verification test.
    
    Scenario:
    - T=0: Empty state (0 trees)
    - T=1: PLANT 5000 trees
    - T=2: ADD 10 trees
    - T=3: REMOVE 20 trees
    - Expected: 4990 trees
    """
    
    def test_5000_trees_problem(self):
        """Verify the 5000 trees problem is solved correctly."""
        tms = TMSService()
        entity_id = uuid.uuid4()
        
        # Initial State (Empty)
        state = EntityState(
            entity_id=entity_id,
            namespace="user",
            current_value={"tree_count": 0},
            truth_vector=TruthVector(
                confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0
            ),
            last_event_id=uuid.uuid4()
        )
        
        # Event 1: PLANT 5000
        e1 = tms.create_event(ActorEnum.USER, ActionEnum.PLANT, entity_id, {"tree_count": 5000})
        state = StateDerivationService.apply_event(state, e1)
        self.assertEqual(state.current_value["tree_count"], 5000)
        
        # Event 2: ADD 10
        e2 = tms.create_event(ActorEnum.USER, ActionEnum.ADD, entity_id, {"tree_count": 10})
        state = StateDerivationService.apply_event(state, e2)
        self.assertEqual(state.current_value["tree_count"], 5010)
        
        # Event 3: REMOVE 20
        e3 = tms.create_event(ActorEnum.USER, ActionEnum.REMOVE, entity_id, {"tree_count": 20})
        state = StateDerivationService.apply_event(state, e3)
        self.assertEqual(state.current_value["tree_count"], 4990)


if __name__ == '__main__':
    unittest.main()
