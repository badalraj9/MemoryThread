import uuid
from typing import List, Dict
from memory_thread.services.graph_service import GraphService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class InferenceEngine:
    """
    Rule-based inference engine.
    Applies logic patterns to deduce new relations.
    """
    def __init__(self):
        self.graph = GraphService()

    def infer_transitive_relations(self, entity_id: uuid.UUID):
        """
        Rule: If A works_at B and B located_in C -> A located_in C (contextual).
        Or simpler: A part_of B, B part_of C -> A part_of C.
        """
        # Fetch 1-hop
        rels = self.graph.get_relations(entity_id, direction="out")

        for r1 in rels:
            if r1['relation_type'] == 'part_of':
                mid_id = r1['target_entity_id']
                # Fetch 2-hop
                rels2 = self.graph.get_relations(uuid.UUID(mid_id), direction="out")
                for r2 in rels2:
                    if r2['relation_type'] == 'part_of':
                        target_id = r2['target_entity_id']
                        # Infer A -> C
                        log.info(f"Inferring TRANSITIVE: {entity_id} part_of {target_id}")
                        self.graph.add_relation(
                            entity_id, uuid.UUID(target_id),
                            "part_of",
                            confidence=r1['confidence'] * r2['confidence'] * 0.9, # Decay confidence
                            is_inferred=True,
                            metadata={"rule": "transitivity"}
                        )
