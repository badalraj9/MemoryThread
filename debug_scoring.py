#!/usr/bin/env python3
"""Debug: trace exact Truth Vector scoring computation"""

from memory_thread.sdk import MemoryClient
from memory_thread.services.tms_service import TruthVectorService

# Create client and store facts
client = MemoryClient(namespace="debug_scoring", use_db=False, durability_mode="sync")

guido_id = client.remember(
    "Python was created by Guido van Rossum", source="expert", confidence=0.95, authority=0.9
)

elon_id = client.remember(
    "Python was created by Elon Musk", source="rumor", confidence=0.1, authority=0.2
)

client.flush()

# Get internal state for both entities
print("=== INTERNAL STATE (from _memories) ===\n")
for entity_id, state in client._memories.items():
    content = state.current_value.get("content", "")
    tv = state.truth_vector

    # Manual calculation
    W1, W2, W3, W4 = 1.0, 1.2, 0.8, 0.6
    corr_score = __import__("math").log(1 + tv.corroboration)
    raw_score = W1 * tv.confidence + W2 * tv.authority + W3 * tv.freshness + W4 * corr_score
    capped_score = min(raw_score, 1.0)

    print(f"Content: {content}")
    print(f"  confidence:    {tv.confidence}")
    print(f"  authority:     {tv.authority}")
    print(f"  freshness:     {tv.freshness}")
    print(f"  corroboration: {tv.corroboration}")
    print(f"  corr_score (log): {corr_score:.4f}")
    print(f"  raw_score:       {raw_score:.4f}")
    print(f"  final (capped):  {capped_score:.4f}")
    print()

# Now check what recall returns
print("=== RECALL RESULTS ===\n")
results = client.recall("who created Python", min_truth_score=0.0, top_k=2)
for i, mem in enumerate(results.memories, 1):
    print(f"{i}. {mem.content}")
    print(f"   truth_score: {mem.truth_score:.4f}")
    print(f"   confidence:  {mem.confidence:.4f}")
    print(f"   authority:   {mem.authority:.4f}")
    print()

client.close()
