"""Fast recall-latency benchmark (after A/B/D fixes).

Builds the in-memory igraph directly (no WAL/persistence) and measures the
recall hot path at scale. Mirrors critical.md's micro-bench A / _recall_bench.py
so we can compare against the documented 'before' numbers:

  micro A before: 215 -> 824 -> 2,361 -> 4,938 ms  (V = 1k,2k,5k,10k)

Expectation after fix: flat-ish (O(K), not O(V)), since per-node vs.find and
the per-iteration set-build are gone, and content resolve is O(1) cached.
"""

import time
from memory_thread.services.graph_engine import graph_engine
from memory_thread.services.retrieval_service import retrieve_by_activation


def build(N: int):
    ge = graph_engine
    ge.clear()
    g = ge.graph
    for i in range(N):
        g.add_vertex(
            f"e{i}",
            type="entity",
            namespace="bench",
            cached_content=f"signal relay protocol channel {i} alpha bravo",
        )
        g.add_vertex(
            f"ev{i}",
            type="event",
            content=f"signal relay protocol channel {i} alpha bravo",
            timestamp="2026-01-01T00:00:00",
        )
        g.add_edge(f"ev{i}", f"e{i}", type="modifies")
        if i > 0:
            g.add_edge(f"e{i - 1}", f"e{i}", type="related")
    ge._rebuild_vertex_index()


def bench(N: int, K: int = 50, runs: int = 20):
    build(N)
    seeds = [f"e{i}" for i in range(K)]
    # warmup
    for _ in range(3):
        retrieve_by_activation(
            seeds=seeds, top_k=K, max_depth=1, decay=0.5, truth_threshold=0.0, namespace="bench"
        )
    samples = []
    for _ in range(runs):
        t = time.perf_counter()
        out = retrieve_by_activation(
            seeds=seeds, top_k=K, max_depth=1, decay=0.5, truth_threshold=0.0, namespace="bench"
        )
        samples.append((time.perf_counter() - t) * 1000)
    samples.sort()
    p50 = samples[len(samples) // 2]
    p99 = samples[-1]
    return p50, p99, len(out)


if __name__ == "__main__":
    print(f"{'V':>8} {'K':>4} {'p50_ms':>10} {'p99_ms':>10} {'results':>8}")
    for N in (1000, 2000, 5000, 10000, 20000):
        p50, p99, n = bench(N)
        print(f"{N:>8} {50:>4} {p50:>10.2f} {p99:>10.2f} {n:>8}")
