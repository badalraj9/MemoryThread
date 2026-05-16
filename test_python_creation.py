#!/usr/bin/env python3
"""
Test script to store and retrieve Python creation facts with different trust levels
"""

from memory_thread.sdk import MemoryClient
import uuid


def test_python_creation_facts():
    # Initialize client with in-memory storage for testing
    client = MemoryClient(namespace="test", use_db=False, durability_mode="sync")

    # Store fact 1: Python was created by Guido van Rossum (high confidence, authority)
    guiddo_id = client.remember(
        "Python was created by Guido van Rossum", source="expert", confidence=0.95, authority=0.9
    )
    print(f"Stored Guido van Rossum fact with ID: {guiddo_id}")

    # Store fact 2: Python was created by Elon Musk (low confidence, unknown source)
    elon_id = client.remember(
        "Python was created by Elon Musk", source="rumor", confidence=0.1, authority=0.2
    )
    print(f"Stored Elon Musk fact with ID: {elon_id}")

    # Flush to ensure persistence
    client.flush()

    # Recall for "who created Python"
    print("\n--- Recall Results for 'who created Python' ---")
    results = client.recall("who created Python", min_truth_score=0.0)

    print(f"Found {results.total_found} memories:")
    for i, memory in enumerate(results.memories, 1):
        print(f"{i}. Content: {memory.content}")
        print(f"   Truth Score: {memory.truth_score:.3f}")
        print(f"   Confidence: {memory.confidence:.3f}")
        print(f"   Authority: {memory.authority:.3f}")
        print(f"   Freshness: {memory.freshness:.3f}")
        print(f"   Corroboration: {memory.corroboration}")
        print(f"   Source: {memory.source}")
        print(f"   Entity ID: {memory.entity_id}")
        print()

    client.close()


if __name__ == "__main__":
    test_python_creation_facts()
