import logging, math
log = logging.getLogger(__name__)
RATES = {'identity': 0.0005, 'preference': 0.005, 'event': 0.02}
def apply_decay(imp, type, days) -> float:
    return max(0.01, imp * math.exp(-RATES.get(type, 0.02) * days))
