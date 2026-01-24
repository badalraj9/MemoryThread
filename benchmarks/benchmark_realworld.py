"""
REAL-WORLD PERFORMANCE BENCHMARK (Simplified)

Tests actual MT throughput on YOUR hardware.
Single-process, no external dependencies.

Run: python benchmarks/benchmark_realworld.py
"""
import time
import uuid
from dataclasses import dataclass

from memory_thread.models.events import Event, EntityState, TruthVector, ActorEnum, ActionEnum
from memory_thread.services.tms_service import TMSService, TruthVectorService, StateDerivationService


@dataclass
class BenchmarkResult:
    name: str
    total_ops: int
    duration_sec: float
    ops_per_sec: float
    latency_us: float


def benchmark_event_creation(num_events: int = 100000) -> BenchmarkResult:
    """Benchmark raw event creation speed."""
    tms = TMSService()
    entity_id = uuid.uuid4()
    
    start = time.perf_counter()
    
    for i in range(num_events):
        tms.create_event(
            actor=ActorEnum.USER,
            action=ActionEnum.UPDATE,
            object_id=entity_id,
            delta={"value": i}
        )
    
    duration = time.perf_counter() - start
    return BenchmarkResult(
        name="Event Creation",
        total_ops=num_events,
        duration_sec=duration,
        ops_per_sec=num_events / duration,
        latency_us=(duration / num_events) * 1_000_000
    )


def benchmark_state_derivation(num_events: int = 100000) -> BenchmarkResult:
    """Benchmark state derivation (applying events)."""
    tms = TMSService()
    entity_id = uuid.uuid4()
    
    # Pre-create events
    events = [
        tms.create_event(ActorEnum.USER, ActionEnum.ADD, entity_id, {"counter": 1})
        for _ in range(num_events)
    ]
    
    state = EntityState(
        entity_id=entity_id,
        namespace="benchmark",
        current_value={"counter": 0},
        truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0),
        last_event_id=uuid.uuid4()
    )
    
    start = time.perf_counter()
    
    for event in events:
        state = StateDerivationService.apply_event(state, event)
    
    duration = time.perf_counter() - start
    
    # Verify
    assert state.current_value["counter"] == num_events
    
    return BenchmarkResult(
        name="State Derivation",
        total_ops=num_events,
        duration_sec=duration,
        ops_per_sec=num_events / duration,
        latency_us=(duration / num_events) * 1_000_000
    )


def benchmark_truth_scoring(num_scores: int = 500000) -> BenchmarkResult:
    """Benchmark Truth Vector scoring."""
    vectors = [
        TruthVector(
            confidence=0.5 + (i % 50) / 100,
            authority=0.7 + (i % 30) / 100,
            freshness=0.8 + (i % 20) / 100,
            corroboration=float(i % 10)
        )
        for i in range(1000)
    ]
    
    start = time.perf_counter()
    
    for i in range(num_scores):
        TruthVectorService.calculate_score(vectors[i % 1000])
    
    duration = time.perf_counter() - start
    return BenchmarkResult(
        name="Truth Scoring",
        total_ops=num_scores,
        duration_sec=duration,
        ops_per_sec=num_scores / duration,
        latency_us=(duration / num_scores) * 1_000_000
    )


def benchmark_full_pipeline(num_events: int = 50000) -> BenchmarkResult:
    """Full pipeline: create → apply → score."""
    tms = TMSService()
    entity_id = uuid.uuid4()
    
    state = EntityState(
        entity_id=entity_id,
        namespace="benchmark",
        current_value={"counter": 0},
        truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0),
        last_event_id=uuid.uuid4()
    )
    
    start = time.perf_counter()
    
    for i in range(num_events):
        event = tms.create_event(ActorEnum.USER, ActionEnum.ADD, entity_id, {"counter": 1})
        state = StateDerivationService.apply_event(state, event)
        _ = TruthVectorService.calculate_score(state.truth_vector)
    
    duration = time.perf_counter() - start
    return BenchmarkResult(
        name="Full Pipeline",
        total_ops=num_events,
        duration_sec=duration,
        ops_per_sec=num_events / duration,
        latency_us=(duration / num_events) * 1_000_000
    )


def benchmark_burst(burst_size: int = 10000, num_bursts: int = 10) -> BenchmarkResult:
    """Simulate burst memory operations (realistic AI usage pattern)."""
    tms = TMSService()
    total_events = burst_size * num_bursts
    
    start = time.perf_counter()
    
    for burst in range(num_bursts):
        entity_id = uuid.uuid4()
        state = EntityState(
            entity_id=entity_id,
            namespace="benchmark",
            current_value={"counter": 0},
            truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0),
            last_event_id=uuid.uuid4()
        )
        
        for i in range(burst_size):
            event = tms.create_event(ActorEnum.USER, ActionEnum.ADD, entity_id, {"counter": 1})
            state = StateDerivationService.apply_event(state, event)
    
    duration = time.perf_counter() - start
    return BenchmarkResult(
        name=f"Burst Mode ({num_bursts}x{burst_size})",
        total_ops=total_events,
        duration_sec=duration,
        ops_per_sec=total_events / duration,
        latency_us=(duration / total_events) * 1_000_000
    )


def run_benchmarks():
    """Run complete benchmark suite."""
    print("\n" + "="*70)
    print("  MEMORY THREAD - REAL WORLD PERFORMANCE BENCHMARK")
    print("="*70)
    print("  Hardware: i5-12450H / 8GB RAM / RTX 3050")
    print("  Note: This tests pure Python TMS throughput, no DB/ZMQ overhead")
    print("="*70 + "\n")
    
    # Warm up
    print("⏳ Warming up...")
    tms = TMSService()
    for _ in range(5000):
        tms.create_event(ActorEnum.USER, ActionEnum.UPDATE, uuid.uuid4(), {"x": 1})
    
    results = []
    
    print("\n📊 Running benchmarks...\n")
    
    print("  [1/5] Event Creation (100k events)...")
    results.append(benchmark_event_creation(100000))
    
    print("  [2/5] State Derivation (100k applies)...")
    results.append(benchmark_state_derivation(100000))
    
    print("  [3/5] Truth Scoring (500k scores)...")
    results.append(benchmark_truth_scoring(500000))
    
    print("  [4/5] Full Pipeline (50k operations)...")
    results.append(benchmark_full_pipeline(50000))
    
    print("  [5/5] Burst Mode (10 bursts × 10k)...")
    results.append(benchmark_burst(10000, 10))
    
    # Results table
    print("\n" + "="*70)
    print("  RESULTS")
    print("="*70)
    print(f"\n{'Benchmark':<30} {'EPS':>12} {'Latency':>12} {'Total':>10}")
    print("-"*70)
    
    for r in results:
        print(f"{r.name:<30} {r.ops_per_sec:>10,.0f} {r.latency_us:>10.2f}µs {r.total_ops:>10,}")
    
    print("-"*70)
    
    # Summary
    pipeline_eps = next(r.ops_per_sec for r in results if "Pipeline" in r.name)
    burst_eps = next(r.ops_per_sec for r in results if "Burst" in r.name)
    scoring_eps = next(r.ops_per_sec for r in results if "Scoring" in r.name)
    
    print(f"\n📈 KEY METRICS:")
    print(f"   Full Pipeline (realistic):  {pipeline_eps:>10,.0f} EPS")
    print(f"   Burst Mode (AI pattern):    {burst_eps:>10,.0f} EPS")
    print(f"   Truth Scoring (pure):       {scoring_eps:>10,.0f} EPS")
    
    # Verdict
    print("\n" + "="*70)
    if pipeline_eps >= 20000:
        print("  ✅ EXCELLENT: Production-grade throughput!")
    elif pipeline_eps >= 10000:
        print("  ✅ GOOD: Ready for production AI workloads")
    elif pipeline_eps >= 5000:
        print("  ⚠️ ACCEPTABLE: Fine for personal AI assistant")
    else:
        print("  ❌ NEEDS OPTIMIZATION: Below production target")
    
    print("\n  CONTEXT:")
    print("  • A typical AI interaction creates ~10-100 memory operations")
    print(f"  • At {pipeline_eps:,.0f} EPS, MT can handle {pipeline_eps/50:.0f} AI interactions/sec")
    print("  • The 47k EPS claim was for ZMQ transport layer, not full pipeline")
    print("="*70 + "\n")
    
    return results


if __name__ == "__main__":
    run_benchmarks()
