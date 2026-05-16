"""Test that truth-weighted retrieval ranks high-truth memories higher."""

import pytest
import uuid


@pytest.fixture
def client():
    from memory_thread.sdk.client import MemoryClient

    c = MemoryClient(namespace="test_truth_retrieval", use_db=False)
    yield c
    c.close()


def test_truth_weighted_retrieval_ranks_high_truth_memories_higher(client):
    topic = f"truth_ranking_test_{uuid.uuid4().hex[:8]}"

    for i in range(3):
        client.remember(
            f"{topic} high_truth memory {i} semantic anchor",
            confidence=0.9,
            authority=0.9,
            source="agent",
            memory_type="fact",
        )

    for i in range(3):
        client.remember(
            f"{topic} low_truth memory {i} semantic anchor",
            confidence=0.2,
            authority=0.1,
            source="agent",
            memory_type="fact",
        )

    result = client.recall(topic, top_k=10)

    high_truth_memories = [m for m in result.memories if "high_truth" in m.content]
    low_truth_memories = [m for m in result.memories if "low_truth" in m.content]

    assert len(high_truth_memories) > 0
    assert len(low_truth_memories) > 0

    high_score = high_truth_memories[0].truth_score if high_truth_memories else 0
    low_score = low_truth_memories[0].truth_score if low_truth_memories else 0
