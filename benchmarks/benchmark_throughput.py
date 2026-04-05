"""
Reproduces the paper's throughput comparison using a WAL-backed MT-style pipeline
versus a bounded queue baseline.
"""

from __future__ import annotations

import argparse
import json
import logging
import queue
import re
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from itertools import cycle

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import memory_thread.services.wal as wal_module
from memory_thread.services.wal import WriteAheadLog
from memory_thread.sdk import MemoryClient


ENTITY_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")
NUMBER_PATTERN = re.compile(r"\b\d+\b")

logging.getLogger("memory_thread").setLevel(logging.WARNING)
logging.getLogger("memory_thread.services.tms_service").setLevel(logging.WARNING)


@dataclass
class Scenario:
    name: str
    producers: int
    with_cognitive_work: bool


@dataclass
class Result:
    name: str
    producers: int
    with_cognitive_work: bool
    system: str
    accepted_events: int
    processed_events: int
    accepted_eps: float
    processed_eps: float
    duration_sec: float


def cognitive_work(payload: str) -> None:
    entities = ENTITY_PATTERN.findall(payload)
    numbers = [int(value) for value in NUMBER_PATTERN.findall(payload)]
    truth_score = 0.5 + min(len(entities), 3) * 0.1 + min(len(numbers), 2) * 0.05
    contradiction_penalty = 0.2 if "not" in payload.lower() else 0.0
    _ = max(0.0, truth_score - contradiction_penalty)
    for _ in range(75):
        hash(payload)


def _payload(index: int) -> str:
    return (
        f"User Alice Example {index} prefers dark mode and has score {index % 10}. "
        f"Project Phoenix batch {index}."
    )


def _pregenerate_event_ids(count: int) -> list[str]:
    return [str(uuid.uuid4()) for _ in range(count)]


def _estimate_id_count(duration_sec: float, producers: int) -> int:
    return max(20000, int(duration_sec * producers * 5000))


def run_baseline(duration_sec: float, producers: int, with_work: bool) -> Result:
    admitted = 0
    processed = 0
    stop_at = time.perf_counter() + duration_sec
    grace_deadline = stop_at + min(1.0, max(0.25, duration_sec * 0.1))
    work_queue: queue.Queue[str] = queue.Queue(maxsize=256)
    lock = threading.Lock()
    durable_lock = threading.Lock()
    durability_file = Path(".bench_wal") / f"baseline_{producers}_{int(with_work)}.log"
    durability_file.parent.mkdir(parents=True, exist_ok=True)
    baseline_handle = open(durability_file, "a", encoding="utf-8")
    pregenerated_ids = cycle(_pregenerate_event_ids(_estimate_id_count(duration_sec, producers)))

    def worker():
        nonlocal processed
        while time.perf_counter() < grace_deadline:
            try:
                _, item = work_queue.get(timeout=0.01)
            except queue.Empty:
                continue
            if with_work:
                cognitive_work(item)
            with lock:
                processed += 1
            work_queue.task_done()

    def producer(offset: int):
        nonlocal admitted
        index = offset
        while time.perf_counter() < stop_at:
            item = _payload(index)
            event_id = next(pregenerated_ids)
            with durable_lock:
                baseline_handle.write(json.dumps({"id": event_id, "content": item}) + "\n")
                baseline_handle.flush()
            work_queue.put((event_id, item))
            with lock:
                admitted += 1
            index += producers

    workers = [threading.Thread(target=worker, daemon=True) for _ in range(max(2, producers))]
    prod_threads = [threading.Thread(target=producer, args=(i,), daemon=True) for i in range(producers)]
    for thread in workers + prod_threads:
        thread.start()
    for thread in prod_threads:
        thread.join()
    cutoff = time.perf_counter() + min(1.0, max(0.25, duration_sec * 0.1))
    while time.perf_counter() < cutoff and not work_queue.empty():
        time.sleep(0.01)
    baseline_handle.close()

    return Result(
        name=f"baseline_{producers}_{with_work}",
        producers=producers,
        with_cognitive_work=with_work,
        system="baseline",
        accepted_events=admitted,
        processed_events=processed,
        accepted_eps=admitted / duration_sec,
        processed_eps=processed / duration_sec,
        duration_sec=duration_sec,
    )


def run_mt(duration_sec: float, producers: int, with_work: bool, wal_dir: Path) -> Result:
    admitted = 0
    processed = 0
    stop_at = time.perf_counter() + duration_sec
    grace_deadline = stop_at + min(1.0, max(0.25, duration_sec * 0.1))
    lock = threading.Lock()
    backlog = queue.Queue()
    pregenerated_ids = cycle(_pregenerate_event_ids(_estimate_id_count(duration_sec, producers)))

    wal_module.WAL_DIR = wal_dir
    namespace_suffix = time.time_ns()
    wal = WriteAheadLog(
        namespace=f"bench_{producers}_{int(with_work)}_{namespace_suffix}",
        flush_batch_size=100,
        flush_interval_ms=10,
        async_flush=True,
    )

    def worker():
        while time.perf_counter() < grace_deadline:
            try:
                sequence, item = backlog.get(timeout=0.01)
            except queue.Empty:
                continue
            if with_work:
                cognitive_work(item)
            wal.commit(sequence)
            backlog.task_done()

    def producer(offset: int):
        nonlocal admitted
        index = offset
        while time.perf_counter() < stop_at:
            item = _payload(index)
            event_id = next(pregenerated_ids)
            sequence = wal.append(
                "remember",
                {
                    "entity_id": event_id,
                    "content": item,
                    "memory_type": "fact",
                },
            )
            backlog.put((sequence, item))
            with lock:
                admitted += 1
            index += producers
    workers = [threading.Thread(target=worker, daemon=True) for _ in range(max(2, producers))]
    prod_threads = [threading.Thread(target=producer, args=(i,), daemon=True) for i in range(producers)]
    for thread in workers + prod_threads:
        thread.start()
    for thread in prod_threads:
        thread.join()

    while time.perf_counter() < grace_deadline:
        stats = wal.stats()
        processed = stats["durable_commit_count"]
        if backlog.empty() and stats["buffered_record_count"] == 0:
            break
        time.sleep(0.01)
    wal.flush()
    processed = wal.stats()["durable_commit_count"]
    wal.close()

    return Result(
        name=f"mt_{producers}_{with_work}",
        producers=producers,
        with_cognitive_work=with_work,
        system="memory_thread",
        accepted_events=admitted,
        processed_events=processed,
        accepted_eps=admitted / duration_sec,
        processed_eps=processed / duration_sec,
        duration_sec=duration_sec,
    )


def run_slab(duration_sec: float, producers: int, with_work: bool, wal_dir: Path) -> Result:
    admitted = 0
    processed = 0
    stop_at = time.perf_counter() + duration_sec
    grace_deadline = stop_at + min(2.0, max(0.5, duration_sec * 0.2))
    lock = threading.Lock()
    pregenerated_ids = cycle(_pregenerate_event_ids(_estimate_id_count(duration_sec, producers)))

    wal_module.close_all_wals()
    wal_module.WAL_DIR = wal_dir
    client = MemoryClient(
        namespace=f"bench_slab_{producers}_{int(with_work)}_{time.time_ns()}",
        use_db=False,
        use_slab_ingest=True,
        slab_num_slabs=2048,
        slab_size=65536,
        slab_drain_threads=4,
        slab_drain_batch_size=32,
    )
    if with_work:
        client._slab_process_hook = cognitive_work

    def producer(offset: int):
        nonlocal admitted
        index = offset
        while time.perf_counter() < stop_at:
            item = _payload(index)
            event_id = next(pregenerated_ids)
            client.remember(
                item,
                source="benchmark",
                confidence=0.8,
                authority=0.5,
                memory_type="fact",
                entity_id=uuid.UUID(event_id),
            )
            with lock:
                admitted += 1
            index += producers

    prod_threads = [threading.Thread(target=producer, args=(i,), daemon=True) for i in range(producers)]
    for thread in prod_threads:
        thread.start()
    for thread in prod_threads:
        thread.join()

    while time.perf_counter() < grace_deadline:
        stats = client._slab_ingest.stats() if client._slab_ingest is not None else {}
        processed = stats.get("processed_count", 0)
        if processed >= admitted:
            break
        time.sleep(0.01)

    close_stats = client.close() or {}
    processed = close_stats.get("processed_count", processed)
    wal_module.close_all_wals()

    return Result(
        name=f"slab_{producers}_{with_work}",
        producers=producers,
        with_cognitive_work=with_work,
        system="slab_ingest",
        accepted_events=admitted,
        processed_events=processed,
        accepted_eps=admitted / duration_sec,
        processed_eps=processed / duration_sec,
        duration_sec=duration_sec,
    )


def print_table(results: list[Result]) -> None:
    headers = (
        "Scenario",
        "System",
        "Producers",
        "Cognitive Work",
        "Accepted EPS",
        "Processed EPS",
        "Accepted",
        "Processed",
    )
    print(" | ".join(headers))
    print(" | ".join(["---"] * len(headers)))
    for result in results:
        print(
            " | ".join(
                [
                    result.name,
                    result.system,
                    str(result.producers),
                    "yes" if result.with_cognitive_work else "no",
                    f"{result.accepted_eps:,.2f}",
                    f"{result.processed_eps:,.2f}",
                    str(result.accepted_events),
                    str(result.processed_events),
                ]
            )
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=Path("reports/throughput_benchmark.json"))
    args = parser.parse_args()

    scenarios = [
        Scenario("light_single_producer", producers=1, with_cognitive_work=False),
        Scenario("light_four_producers", producers=4, with_cognitive_work=False),
        Scenario("realistic_four_producers", producers=4, with_cognitive_work=True),
    ]

    wal_dir = Path(".bench_wal")
    wal_dir.mkdir(parents=True, exist_ok=True)

    results: list[Result] = []
    for scenario in scenarios:
        results.append(run_mt(args.duration, scenario.producers, scenario.with_cognitive_work, wal_dir))
        results.append(run_slab(args.duration, scenario.producers, scenario.with_cognitive_work, wal_dir))
        results.append(run_baseline(args.duration, scenario.producers, scenario.with_cognitive_work))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps([asdict(result) for result in results], indent=2), encoding="utf-8")
    print_table(results)


if __name__ == "__main__":
    main()
