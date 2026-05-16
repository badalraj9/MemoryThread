#!/usr/bin/env python3
"""
Run Guido vs Elon test 50+ times to collect ranking statistics
"""

from memory_thread.sdk import MemoryClient
import uuid


def run_single_test(run_num):
    """Run a single test and return ranking result."""
    # Fresh client each time to avoid state leakage
    client = MemoryClient(namespace=f"test_run_{run_num}", use_db=False, durability_mode="sync")

    # Store fact 1: Python was created by Guido van Rossum (high confidence, authority)
    guiddo_id = client.remember(
        "Python was created by Guido van Rossum", source="expert", confidence=0.95, authority=0.9
    )

    # Store fact 2: Python was created by Elon Musk (low confidence, unknown source)
    elon_id = client.remember(
        "Python was created by Elon Musk", source="rumor", confidence=0.1, authority=0.2
    )

    client.flush()

    # Recall and get top result
    results = client.recall("who created Python", min_truth_score=0.0, top_k=1)

    client.close()

    if results.memories:
        top_content = results.memories[0].content
        truth_score = results.memories[0].truth_score
        confidence = results.memories[0].confidence
        authority = results.memories[0].authority

        if "Guido" in top_content:
            winner = "Guido"
        elif "Elon" in top_content:
            winner = "Elon"
        else:
            winner = "Unknown"

        return {
            "run": run_num,
            "winner": winner,
            "truth_score": truth_score,
            "confidence": confidence,
            "authority": authority,
        }
    return {"run": run_num, "winner": "None", "truth_score": 0, "confidence": 0, "authority": 0}


def main():
    num_runs = 60
    results = []

    print(f"Running {num_runs} Guido vs Elon tests...")
    print("-" * 60)

    for i in range(1, num_runs + 1):
        result = run_single_test(i)
        results.append(result)

        if i <= 10 or i % 10 == 0:
            print(
                f"Run {i:2d}: Winner={result['winner']:5s} | Truth={result['truth_score']:.3f} | Conf={result['confidence']:.3f} | Auth={result['authority']:.3f}"
            )

    print("-" * 60)

    # Aggregate statistics
    guido_wins = sum(1 for r in results if r["winner"] == "Guido")
    elon_wins = sum(1 for r in results if r["winner"] == "Elon")
    none_count = sum(1 for r in results if r["winner"] == "None" or r["winner"] == "Unknown")

    guido_truth_scores = [r["truth_score"] for r in results if r["winner"] == "Guido"]
    elon_truth_scores = [r["truth_score"] for r in results if r["winner"] == "Elon"]

    guido_confidences = [r["confidence"] for r in results if r["winner"] == "Guido"]
    elon_confidences = [r["confidence"] for r in results if r["winner"] == "Elon"]

    guido_authorities = [r["authority"] for r in results if r["winner"] == "Guido"]
    elon_authorities = [r["authority"] for r in results if r["winner"] == "Elon"]

    print(f"\n=== EVALUATION RESULTS ({num_runs} runs) ===\n")
    print(f"Guido wins: {guido_wins} ({guido_wins / num_runs * 100:.1f}%)")
    print(f"Elon wins:  {elon_wins} ({elon_wins / num_runs * 100:.1f}%)")
    print(f"None/Unknown: {none_count}")

    if guido_wins > 0:
        print(f"\nGuido Stats (when winning):")
        print(f"  Truth Score:  avg={sum(guido_truth_scores) / len(guido_truth_scores):.3f}")
        print(f"  Confidence:   avg={sum(guido_confidences) / len(guido_confidences):.3f}")
        print(f"  Authority:   avg={sum(guido_authorities) / len(guido_authorities):.3f}")

    if elon_wins > 0:
        print(f"\nElon Stats (when winning):")
        print(f"  Truth Score:  avg={sum(elon_truth_scores) / len(elon_truth_scores):.3f}")
        print(f"  Confidence:   avg={sum(elon_confidences) / len(elon_confidences):.3f}")
        print(f"  Authority:   avg={sum(elon_authorities) / len(elon_authorities):.3f}")

    print("\n=== INPUT PARAMETERS ===")
    print("Guido fact: confidence=0.95, authority=0.9 (source='expert')")
    print("Elon fact:  confidence=0.1, authority=0.2 (source='rumor')")

    return results


if __name__ == "__main__":
    main()
