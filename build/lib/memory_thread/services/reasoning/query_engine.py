import uuid
from typing import List, Dict, Optional, Set
from collections import deque

from memory_thread.services.graph_service import GraphService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class QueryEngine:
    """
    Multi-Hop Graph Query Engine.
    Implements BFS/DFS for pathfinding.
    """
    def __init__(self):
        self.graph = GraphService()

    def find_path(self, start_id: uuid.UUID, end_id: uuid.UUID, max_hops: int = 3) -> Optional[List[Dict]]:
        """
        Finds the shortest path between start and end entities using BFS.
        Returns a list of relation dicts representing the path, or None.
        """
        if start_id == end_id:
            return []

        # Queue: (current_id, path_list)
        queue = deque([(str(start_id), [])])
        visited = {str(start_id)}

        while queue:
            curr_id, path = queue.popleft()

            if len(path) >= max_hops:
                continue

            # Fetch neighbors (outgoing edges for now, could be undirected)
            relations = self.graph.get_relations(uuid.UUID(curr_id), direction="out")

            for rel in relations:
                target = str(rel['target_entity_id'])

                new_path = path + [rel]

                if target == str(end_id):
                    return new_path

                if target not in visited:
                    visited.add(target)
                    queue.append((target, new_path))

        return None

    def find_common_neighbors(self, entity_a: uuid.UUID, entity_b: uuid.UUID) -> List[Dict]:
        """
        Finds entities connected to both A and B.
        A -> X <- B  (Common downstream)
        A <- X -> B  (Common upstream/parent)
        """
        # Get neighbors of A
        rels_a_out = self.graph.get_relations(entity_a, direction="out")
        targets_a = {str(r['target_entity_id']) for r in rels_a_out}

        # Get neighbors of B
        rels_b_out = self.graph.get_relations(entity_b, direction="out")
        targets_b = {str(r['target_entity_id']) for r in rels_b_out}

        common = targets_a.intersection(targets_b)

        # We could also check 'in' direction for common parents

        return list(common)
