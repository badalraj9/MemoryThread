import datetime as dt
import math

import pytest

from memory_thread.models.events import TruthVector
from memory_thread.services.tms_service import TruthVectorService


TIME_POINTS = {
    "1_hour": dt.timedelta(hours=1),
    "1_day": dt.timedelta(days=1),
    "1_week": dt.timedelta(days=7),
    "1_month": dt.timedelta(days=30),
    "6_months": dt.timedelta(days=180),
}


def _freshness_after(delta: dt.timedelta, memory_type: str) -> float:
    vector = TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0)
    event_time = dt.datetime.utcnow() - delta
    return TruthVectorService.decay_freshness(vector, event_time, memory_type)


def test_decay_curves_match_paper_lambda_values():
    for memory_type, rate in TruthVectorService.DECAY_RATES.items():
        for delta in TIME_POINTS.values():
            actual = _freshness_after(delta, memory_type)
            if rate == 0.0:
                expected = 1.0
            else:
                expected = max(0.01, math.exp(-rate * delta.total_seconds() / 86400.0))
            assert actual == pytest.approx(expected, rel=1e-3)


def test_decay_curves_preserve_paper_behavior_expectations():
    identity_values = [_freshness_after(delta, "identity") for delta in TIME_POINTS.values()]
    prediction_values = [_freshness_after(delta, "prediction") for delta in TIME_POINTS.values()]
    fact_values = [_freshness_after(delta, "fact") for delta in TIME_POINTS.values()]

    assert all(value == pytest.approx(1.0) for value in identity_values)
    assert prediction_values[2] <= 0.05
    assert prediction_values[-1] == pytest.approx(0.01, abs=1e-9)
    assert fact_values[-1] > 0.5
    assert fact_values == sorted(fact_values, reverse=True)
