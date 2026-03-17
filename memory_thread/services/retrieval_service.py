import logging
from datetime import datetime
from uuid import UUID
from memory_thread.services.vector_service import search_vectors
from memory_thread.services.graph_service import (
    get_neighbors,
    get_memories_by_ids,
    keyword_search_memories,
)
from memory_thread.utils.embeddings import generate_embeddings_async
from memory_thread.config.settings import settings
from memory_thread.services.tms_service import TruthVectorService
from memory_thread.models.events import TruthVector

log = logging.getLogger(__name__)


def retrieve_memories(query: str, top_k: int = 10) -> list:
    query_embedding = generate_embeddings_async((query,))[0]
    vector_candidates = search_vectors(query_embedding, top_k=40)
    keyword_candidates = keyword_search_memories(q=query, k=20)

    candidate_ids = {UUID(c.id) for c in vector_candidates} | {
        res["id"] for res in keyword_candidates
    }
    if not candidate_ids:
        return []

    memories_data = get_memories_by_ids(list(candidate_ids))
    if not memories_data:
        return []

    scored_memories = []
    now = datetime.utcnow()
    vector_scores = {UUID(c.id): c.score for c in vector_candidates}
    keyword_scores = {res["id"]: res.get("keyword_score", 0.0) for res in keyword_candidates}

    for memory_data in memories_data:
        memory_id = memory_data["id"]
        neighbors = get_neighbors(memory_id)

        vector_similarity = vector_scores.get(memory_id, 0.0)
        keyword_score = keyword_scores.get(memory_id, 0.0)
        edge_weight_sum = sum(n.get("weight", 0.0) for n in neighbors)

        graph_score = 0.0
        if neighbors:
            graph_score = min(edge_weight_sum / settings.MAX_EDGES_PER_NODE, 1.0)

        importance = memory_data.get("importance", 0.5)

        created_at = memory_data.get("created_at")
        if created_at:
            tv = TruthVector(
                confidence=memory_data.get("confidence", 0.5),
                authority=memory_data.get("authority", 0.5),
                freshness=memory_data.get("freshness", 1.0),
                corroboration=0.0,
            )
            memory_type = memory_data.get("type", "fact")
            recency = TruthVectorService.decay_freshness(tv, created_at, memory_type)
        else:
            recency = 0.5

        final_score = (
            (settings.SCORE_WEIGHT_VECTOR * vector_similarity)
            + (settings.SCORE_WEIGHT_KEYWORD * keyword_score)
            + (settings.SCORE_WEIGHT_GRAPH * graph_score)
            + (settings.SCORE_WEIGHT_IMPORTANCE * importance)
            + (settings.SCORE_WEIGHT_RECENCY * recency)
        )

        memory_data["score"] = final_score
        scored_memories.append(memory_data)

    return sorted(scored_memories, key=lambda x: x["score"], reverse=True)[:top_k]
