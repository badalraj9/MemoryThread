import types
from dataclasses import dataclass

from memory_thread.sdk import MemoryClient


@dataclass
class _FakePoint:
    id: str
    score: float
    payload: dict


class _FakeQueryResult:
    def __init__(self, points):
        self.points = points


class _TruthVsVectorQdrant:
    """
    Returns all topic memories as semantically relevant, but deliberately boosts several
    low-truth items so naive cosine ranking differs from MT's truth-aware ranking.
    """

    def __init__(self, memory_client):
        self.memory_client = memory_client
        self.client = self

    def query_points(self, collection_name, query, limit, query_filter=None):
        points = []
        for index, (entity_id, state) in enumerate(self.memory_client._memories.items()):
            topic_index = state.current_value["topic_index"]
            is_high_truth = state.current_value["truth_bucket"] == "high"

            if is_high_truth:
                score = 0.88 - (topic_index * 0.01)
            else:
                score = 0.96 - (topic_index * 0.01) if topic_index < 5 else 0.40 - (topic_index * 0.01)

            points.append(
                _FakePoint(
                    id=str(entity_id),
                    score=score,
                    payload={
                        "content": state.current_value["content"],
                        "type": state.current_value["type"],
                        "namespace": self.memory_client.namespace,
                        "confidence": state.truth_vector.confidence,
                        "authority": state.truth_vector.authority,
                        "freshness": state.truth_vector.freshness,
                    },
                )
            )

        points.sort(key=lambda point: point.score, reverse=True)
        return _FakeQueryResult(points[:limit])


def _average_high_truth_rank(items):
    high_truth_ranks = [
        rank
        for rank, item in enumerate(items, start=1)
        if "high_truth" in (item.content if hasattr(item, "content") else item.payload["content"])
    ]
    return sum(high_truth_ranks) / max(len(high_truth_ranks), 1)


def _topic_client(monkeypatch, topic: str):
    monkeypatch.setattr(MemoryClient, "_get_global_namespace", lambda self: self.namespace)
    client = MemoryClient(namespace=f"truth_{topic}", use_db=False)

    for i in range(10):
        entity_id = client.remember(
            f"{topic} high_truth memory {i} semantic anchor",
            confidence=0.9,
            authority=0.9,
            source="agent",
            memory_type="fact",
        )
        state = client._memories[entity_id]
        state.truth_vector.confidence = 0.9
        state.truth_vector.authority = 0.9
        state.truth_vector.freshness = 1.0
        state.truth_vector.corroboration = 4
        state.current_value["truth_bucket"] = "high"
        state.current_value["topic_index"] = i

    for i in range(10):
        entity_id = client.remember(
            f"{topic} low_truth memory {i} semantic anchor",
            confidence=0.2,
            authority=0.1,
            source="agent",
            memory_type="fact",
        )
        state = client._memories[entity_id]
        state.truth_vector.confidence = 0.2
        state.truth_vector.authority = 0.1
        state.truth_vector.freshness = 0.1
        state.truth_vector.corroboration = 0
        state.current_value["truth_bucket"] = "low"
        state.current_value["topic_index"] = i

    client._qdrant = _TruthVsVectorQdrant(client)
    client._generate_embedding = types.MethodType(lambda self, _: [0.0] * 8, client)
    return client


def test_truth_weighted_retrieval_ranks_high_truth_memories_higher(monkeypatch):
    topics = [f"topic_{i}" for i in range(5)]
    naive_top5_high_truth_counts = []
    mt_top5_high_truth_counts = []
    naive_avg_ranks = []
    mt_avg_ranks = []

    for topic in topics:
        client = _topic_client(monkeypatch, topic)
        raw_points = client._qdrant.client.query_points("memories", [0.0] * 8, 20).points
        naive_top5 = raw_points[:5]
        mt_top5 = client.recall(f"{topic} semantic anchor", top_k=5, min_truth_score=0.0).memories

        naive_top5_high_truth = sum("high_truth" in point.payload["content"] for point in naive_top5)
        mt_top5_high_truth = sum("high_truth" in memory.content for memory in mt_top5)
        naive_top5_high_truth_counts.append(naive_top5_high_truth)
        mt_top5_high_truth_counts.append(mt_top5_high_truth)

        naive_avg_ranks.append(_average_high_truth_rank(raw_points))
        mt_avg_ranks.append(_average_high_truth_rank(client.recall(f"{topic} semantic anchor", top_k=20, min_truth_score=0.0).memories))

        assert mt_top5_high_truth >= 4
        assert mt_top5_high_truth > naive_top5_high_truth

    assert sum(mt_top5_high_truth_counts) / len(mt_top5_high_truth_counts) >= 4.0
    assert sum(naive_avg_ranks) / len(naive_avg_ranks) > sum(mt_avg_ranks) / len(mt_avg_ranks)
