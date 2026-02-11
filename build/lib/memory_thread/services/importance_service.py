import logging
log = logging.getLogger(__name__)
def calculate_importance(mem) -> float:
    log.info(f"Placeholder: Calculating importance for {mem.get('id')}.")
    return mem.get('importance', 0.5)
