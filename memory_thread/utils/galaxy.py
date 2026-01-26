"""
Cognitive Galaxy Schema Engine.

This module implements the "OLAP for Cognition" logic, providing
Slice, Dice, and Drill-down capabilities over the Memory Thread.
"""
from typing import List, Dict, Any, Optional
import json
import uuid
from dataclasses import dataclass

from memory_thread.utils.secure_sdk import SecureMemoryClient
from memory_thread.sdk import Memory

@dataclass
class GalaxyRow:
    """Represents a joined row in the Cognitive Galaxy."""
    # Fact (Source)
    source_uri: str
    # Dimension (Agent)
    agent_role: str
    authority: float
    # Dimension (Belief)
    belief_id: uuid.UUID
    content: str
    confidence: float
    # Lineage
    provenance: Dict[str, Any]

class GalaxyQueryEngine:
    def __init__(self, client: SecureMemoryClient):
        self.client = client

    def slice_by_source(self, source_query: str, limit: int = 20) -> List[GalaxyRow]:
        """
        SLICE operation: Select all beliefs derived from a specific source/fact.

        Since we are on a frozen core without native metadata index,
        we perform a semantic search for the source URI and post-filter.
        """
        # 1. Broad Recall to find mentions of the source
        # We assume the source URI is mentioned in the content or provenance
        results = self.client.recall(f"source:{source_query} OR '{source_query}'", top_k=limit * 2)

        rows = []
        for mem in results.memories:
            # We need to access the raw payload to check provenance
            # But SecureMemoryClient.recall unpacks it.
            # We have to inspect the 'source' attribute or reconstruct from memory.
            #
            # In SecureMemoryClient.recall:
            # mem.source is set to "Role (Auth: X)" OR "Namespace (Legacy)"
            # It DOES NOT expose the original filename/URI easily if it was packed in _provenance.
            #
            # However, looking at SecureMemoryClient.remember:
            # secure_payload = {"text": content, "_provenance": ...}
            #
            # And recall:
            # unpacks "text" into mem.content
            # uses _provenance to set mem.source (Role)
            #
            # WE ARE LOSING DATA in SecureMemoryClient.recall for this specific query.
            # To fix this without touching SecureMemoryClient, we need to bypass
            # the unpack logic or re-fetch.
            #
            # Actually, `mem` is an object. `SecureMemoryClient` modifies it in place.
            # But `mem` might still have other attributes? No.
            #
            # Hack: The `SecureMemoryClient` doesn't scrub the *original* content from the DB,
            # it just modifies the `Memory` object attribute before returning.
            # BUT, we are calling `self.client.recall`, which is the `SecureMemoryClient` method.
            #
            # Wait, `SecureMemoryClient` wraps the *Core* client.
            # We can access `self.client._core_client` directly to get the RAW data!
            # Then we can parse it ourselves.
            pass

        # BYPASS STRATEGY: Use Core Client to get raw data for OLAP
        core_results = self.client._core_client.recall(source_query, top_k=limit * 2)

        for mem in core_results.memories:
            # 2. Parse Raw Payload
            try:
                payload = json.loads(mem.content)
                if not isinstance(payload, dict):
                    # Legacy memory (Fact)
                    raw_text = mem.content
                    prov = None
                else:
                    # Secure Memory (Dimension)
                    raw_text = payload.get("text", "")
                    prov = payload.get("_provenance", {})
            except:
                raw_text = mem.content
                prov = None

            # 3. Filter: Does this relate to the source?
            # Check 1: Provenance Origin (if it tracks file/uri)
            # Check 2: Explicit mention in text
            match = False

            # Check Provenance Scope/Origin
            uri = "unknown"
            if prov:
                # Origin might capture it?
                # Scope might capture it?
                # For now, we rely on text matching or if the user stored it.
                pass

            if source_query.lower() in raw_text.lower():
                match = True
                uri = source_query # Inferred

            # If provenance exists, we can extract Agent info
            if match:
                role = "unknown"
                if prov and 'actor' in prov:
                    role = prov['actor'].get('role', 'unknown')
                elif mem.source:
                    role = mem.source # Legacy source field

                rows.append(GalaxyRow(
                    source_uri=uri,
                    agent_role=role,
                    authority=mem.authority,
                    belief_id=mem.id,
                    content=raw_text,
                    confidence=mem.confidence,
                    provenance=prov or {}
                ))

        return rows[:limit]

    def dice_by_authority(self, rows: List[GalaxyRow], min_auth: float = 0.0, role: str = None) -> List[GalaxyRow]:
        """
        DICE operation: Filter the slice by Agent Authority or Role.
        """
        filtered = []
        for r in rows:
            if r.authority < min_auth: continue
            if role and r.agent_role.lower() != role.lower(): continue
            filtered.append(r)
        return filtered

    def drill_down(self, belief_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """
        DRILL DOWN: Retrieve the full raw Event Log for a specific belief.
        """
        # Try to find in Core Client's local cache
        if hasattr(self.client._core_client, '_memories'):
            mem_state = self.client._core_client._memories.get(belief_id)
            if mem_state:
                # This is a MemoryState object (usually)
                # It has .current_value (dict) and .history (list of events)
                return {
                    "current_state": mem_state.current_value,
                    "history_len": len(mem_state.history),
                    "events": [e.payload for e in mem_state.history]
                }

        return None
