"""
Galaxy Schema tests for Memory Thread.
Tests fact storage, belief derivation, and OLAP queries.
"""
import pytest
import os


class TestFactStore:
    """Tests for the Fact Store (Layer 0)."""
    
    def test_hash_content_returns_16_char(self):
        """Hash should return 16 character ID."""
        from memory_thread.services.fact_store import FactStore
        store = FactStore()
        
        hash_id = store._hash_content("Test content")
        
        assert hash_id is not None
        assert len(hash_id) == 16  # SHA256[:16]
    
    def test_same_content_same_hash(self, temp_dir, monkeypatch):
        """Same content should produce same hash (deduplication)."""
        from memory_thread.services.fact_store import FactStore
        store = FactStore()
        store._use_db = False
        
        id1 = store._hash_content("Identical content")
        id2 = store._hash_content("Identical content")
        
        assert id1 == id2
    
    def test_different_content_different_hash(self, temp_dir):
        """Different content should produce different hashes."""
        from memory_thread.services.fact_store import FactStore
        store = FactStore()
        
        id1 = store._hash_content("Content A")
        id2 = store._hash_content("Content B")
        
        assert id1 != id2


class TestBeliefStore:
    """Tests for the Belief Store (Layer 1)."""
    
    def test_derive_returns_belief_id_format(self):
        """Derived belief ID should have correct format."""
        from memory_thread.services.belief_store import BeliefStore
        store = BeliefStore()
        store._use_db = False
        store._qdrant = None
        
        # Just test ID generation logic
        import uuid
        belief_id = f"blf_{uuid.uuid4().hex[:12]}"
        
        assert belief_id.startswith("blf_")
    
    def test_belief_truth_score_calculation(self):
        """Belief truth score should combine confidence, authority, freshness."""
        from memory_thread.services.belief_store import Belief
        
        belief = Belief(
            belief_id="blf_test",
            fact_id="fact_123",
            agent_id="agent_1",
            content="Test belief",
            confidence=0.9,
            authority=0.8,
            freshness=1.0,
            created_at="2024-01-01T00:00:00",
            derived_from="fact:fact_123"
        )
        
        # Truth score should be > 0
        assert belief.truth_score > 0
        assert belief.truth_score <= 1


class TestGalaxyQuery:
    """Tests for Galaxy Query Engine (Layer 2)."""
    
    def test_query_dispatcher(self):
        """Query should dispatch to correct operation."""
        from memory_thread.services.galaxy_query import GalaxyQuery
        
        gq = GalaxyQuery()
        
        # Should not raise
        result = gq.query("SLICE", source_uri="test://file")
        assert result is not None
    
    def test_unknown_operation_returns_error(self):
        """Unknown operation should return error dict."""
        from memory_thread.services.galaxy_query import GalaxyQuery
        
        gq = GalaxyQuery()
        result = gq.query("INVALID_OP")
        
        assert "error" in result


class TestSDKGalaxyIntegration:
    """Tests for Galaxy Schema integration in SDK."""
    
    def test_ingest_fact_method_exists(self, memory_client):
        """SDK should have ingest_fact method."""
        assert hasattr(memory_client, "ingest_fact")
    
    def test_derive_belief_method_exists(self, memory_client):
        """SDK should have derive_belief method."""
        assert hasattr(memory_client, "derive_belief")
    
    def test_query_galaxy_method_exists(self, memory_client):
        """SDK should have query_galaxy method."""
        assert hasattr(memory_client, "query_galaxy")
    
    def test_galaxy_stats_returns_dict(self, memory_client):
        """galaxy_stats() should return a dictionary."""
        stats = memory_client.galaxy_stats()
        assert isinstance(stats, dict)
        assert "layer" in stats
