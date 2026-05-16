#!/usr/bin/env python3
"""
Verify that authority tiebreaker is now explicit
"""

from memory_thread.sdk import MemoryClient


def test_explicit_tiebreaker():
    client = MemoryClient(namespace="tiebreak_test", use_db=False, durability_mode="sync")

    # Store facts with SAME parameters that would result in equal truth_score
    id1 = client.remember("Python created by Guido", source="expert", confidence=0.9, authority=0.9)
    id2 = client.remember("Python created by Elon", source="rumor", confidence=0.9, authority=0.2)

    client.flush()

    results = client.recall("Python creator", min_truth_score=0.0, top_k=2)

    print("=== Two facts with SAME confidence but DIFFERENT authority ===\n")
    for i, mem in enumerate(results.memories, 1):
        print(f"{i}. {mem.content}")
        print(f"   Truth Score: {mem.truth_score:.4f}")
        print(f"   Authority:   {mem.authority:.4f}")
        print()

    # Now test with identical parameters to force a true tie
    client2 = MemoryClient(namespace="true_tie_test", use_db=False, durability_mode="sync")

    id3 = client2.remember(
        "Python was created by Guido van Rossum", source="expert", confidence=0.5, authority=0.5
    )
    id4 = client2.remember(
        "Python was created by Bjarne Stroustrup", source="expert", confidence=0.5, authority=0.5
    )

    client2.flush()

    results2 = client2.recall("who created Python", min_truth_score=0.0, top_k=2)

    print("=== Two facts with IDENTICAL truth vector (true tie) ===\n")
    for i, mem in enumerate(results2.memories, 1):
        print(f"{i}. {mem.content}")
        print(f"   Truth Score: {mem.truth_score:.4f}")
        print(f"   Authority:   {mem.authority:.4f}")
        print()

    client.close()
    client2.close()


if __name__ == "__main__":
    test_explicit_tiebreaker()
