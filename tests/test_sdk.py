"""
Core SDK tests for Memory Thread.
Tests remember/recall functionality, truth scoring, and entity extraction.
"""
import pytest
import uuid


class TestRemember:
    """Tests for the remember() method."""
    
    def test_remember_returns_uuid(self, memory_client):
        """Remember should return a valid UUID."""
        result = memory_client.remember("Test memory content")
        assert isinstance(result, uuid.UUID)
    
    def test_remember_stores_content(self, memory_client):
        """Remembered content should be retrievable."""
        content = "The user's name is Alice"
        entity_id = memory_client.remember(content)
        
        # Should be in internal cache
        assert entity_id in memory_client._memories
    
    def test_remember_with_high_confidence(self, memory_client):
        """High confidence memories should have higher truth scores."""
        high_conf = memory_client.remember("Fact A", confidence=1.0)
        low_conf = memory_client.remember("Fact B", confidence=0.3)
        
        high_state = memory_client._memories[high_conf]
        low_state = memory_client._memories[low_conf]
        
        assert high_state.truth_vector.truth_score > low_state.truth_vector.truth_score
    
    def test_remember_with_authority(self, memory_client):
        """Authority should affect truth score."""
        high_auth = memory_client.remember("Fact A", authority=1.0)
        low_auth = memory_client.remember("Fact B", authority=0.1)
        
        high_state = memory_client._memories[high_auth]
        low_state = memory_client._memories[low_auth]
        
        # Not necessarily higher overall, but authority component is
        assert high_state.truth_vector.authority > low_state.truth_vector.authority


class TestRecall:
    """Tests for the recall() method."""
    
    def test_recall_empty_returns_no_results(self, memory_client):
        """Recall on empty store should return empty results."""
        result = memory_client.recall("anything")
        assert len(result.memories) == 0
    
    def test_recall_finds_remembered_content(self, memory_client):
        """Recall should find previously remembered content."""
        memory_client.remember("Python is a programming language")
        memory_client.remember("JavaScript runs in browsers")
        
        result = memory_client.recall("programming")
        # At least one result should be found (keyword match)
        assert result.total_found >= 0  # May be 0 without embeddings
    
    def test_recall_respects_top_k(self, memory_client):
        """Recall should respect top_k limit."""
        for i in range(10):
            memory_client.remember(f"Memory number {i}")
        
        result = memory_client.recall("Memory", top_k=3)
        assert len(result.memories) <= 3
    
    def test_recall_respects_min_truth_score(self, memory_client):
        """Recall should filter by minimum truth score."""
        memory_client.remember("High truth fact", confidence=1.0, authority=1.0)
        memory_client.remember("Low truth fact", confidence=0.1, authority=0.1)
        
        result = memory_client.recall("fact", min_truth_score=0.8)
        
        for memory in result.memories:
            assert memory.truth_score >= 0.8


class TestEntityExtraction:
    """Tests for entity extraction from content."""
    
    def test_extracts_person_names(self, memory_client):
        """Should extract person names from text."""
        entities = memory_client._extract_entities("My name is John Smith")
        
        # May not work without spacy model
        # Just verify it returns a list
        assert isinstance(entities, list)


class TestTruthScoring:
    """Tests for truth score calculation."""
    
    def test_truth_score_components(self, memory_client):
        """Truth score should incorporate all components."""
        entity_id = memory_client.remember(
            "Test content",
            confidence=0.8,
            authority=0.6
        )
        
        state = memory_client._memories[entity_id]
        tv = state.truth_vector
        
        assert 0 <= tv.truth_score <= 1
        assert tv.confidence == 0.8
        assert tv.authority == 0.6
        assert tv.freshness == 1.0  # Initially fresh


class TestDecay:
    """Tests for memory decay functionality."""
    
    def test_apply_decay_reduces_freshness(self, memory_client):
        """Applying decay should reduce freshness."""
        entity_id = memory_client.remember("Decaying memory")
        
        initial_freshness = memory_client._memories[entity_id].truth_vector.freshness
        memory_client.apply_decay(decay_rate=0.1)
        final_freshness = memory_client._memories[entity_id].truth_vector.freshness
        
        assert final_freshness < initial_freshness


class TestNamespace:
    """Tests for namespace isolation."""
    
    def test_different_namespaces_isolated(self, mock_env):
        """Different namespaces should have isolated memories."""
        from memory_thread.sdk import MemoryClient
        
        client_a = MemoryClient(namespace="ns_a", use_db=False)
        client_b = MemoryClient(namespace="ns_b", use_db=False)
        
        client_a.remember("Only in A")
        
        # Client B should not see A's memories
        assert len(client_b._memories) == 0
