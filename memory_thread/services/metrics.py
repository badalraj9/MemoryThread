"""Lightweight in-process metrics for Memory Thread.

No external dependencies. Provides counters and histograms that are safe to
call from multiple threads. Surfaced via the API ``/metrics`` endpoint and
:func:`get_metrics` (useful for tests and health checks).

The goal is operational visibility into the two historical failure modes:
  * silent recall degradation (keyword fallback when the graph is empty/stale)
  * slow graph replay on startup/crash-recovery
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

_lock = threading.Lock()
_counters: Dict[str, float] = {}
_histograms: Dict[str, List[float]] = {}

# Cap retained observations per histogram to bound memory under load.
_HISTOGRAM_CAP = 2000


def _tag_suffix(tags: Optional[Dict[str, str]]) -> str:
    if not tags:
        return ""
    return "|" + ",".join(f"{k}={v}" for k, v in sorted(tags.items()))


def incr(name: str, amount: float = 1.0, tags: Optional[Dict[str, str]] = None) -> None:
    """Increment a counter by ``amount`` (default 1)."""
    key = name + _tag_suffix(tags)
    with _lock:
        _counters[key] = _counters.get(key, 0.0) + amount


def observe(name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
    """Record an observation for a histogram metric (latency, size, ...)."""
    key = name + _tag_suffix(tags)
    with _lock:
        bucket = _histograms.setdefault(key, [])
        bucket.append(value)
        if len(bucket) > _HISTOGRAM_CAP:
            del bucket[: len(bucket) - _HISTOGRAM_CAP]


def get_metrics() -> Dict[str, Dict[str, float]]:
    """Return a snapshot of all metrics as {name: {stat: value}}."""
    with _lock:
        out: Dict[str, Dict[str, float]] = {}
        for k, v in _counters.items():
            out[k] = {"count": v}
        for k, vals in _histograms.items():
            if vals:
                out[k] = {
                    "count": len(vals),
                    "sum": sum(vals),
                    "avg": sum(vals) / len(vals),
                    "max": max(vals),
                    "min": min(vals),
                }
        return out


def reset_metrics() -> None:
    """Clear all metrics. Intended for tests only."""
    with _lock:
        _counters.clear()
        _histograms.clear()
