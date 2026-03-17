import re
from typing import Tuple

IDENTITY_TRIGGERS = r"\b(i am|i'm|i live in|my name is|i work at|i'm a)\b"
PREFERENCE_TRIGGERS = (
    r"\b(i prefer|my favorite|i like|i always|i usually|i hate|i dislike|i love)\b"
)
DECISION_TRIGGERS = r"\b(we decided|decided to use|going with|switched to|chose|we will use|going to use|decided on|selected)\b"
FAILURE_TRIGGERS = r"\b(failed|didn't work|broke|abandoned|gave up on|issue with|problem with|tried but|couldn't|doesn't work|no longer)\b"
FACT_TRIGGERS = r"\b(is defined as|means|refers to|always|never|the definition of|is a |is an |converts to|parses as)\b"
TEMPORAL_TRIGGERS = (
    r"\b(today|yesterday|tonight|this morning|right now|i'm feeling|last week|next week)\b"
)
NEGATION_TRIGGERS = (
    r"\b(not|don't|no longer|stopped|quit|isn't|aren't|won't|cannot|couldn't|never)\b"
)

TYPE_DECAY_RATES = {
    "identity": 0.0,
    "fact": 0.001,
    "preference": 0.01,
    "decision": 0.01,
    "failure": 0.01,
    "event": 0.1,
}


def classify_memory(text: str) -> Tuple[str, float, bool]:
    """
    Classify memory type and return type, confidence, and negation flag.

    Returns:
        Tuple[type, confidence, has_negation]
    """
    text_lower = text.lower()

    has_identity = re.search(IDENTITY_TRIGGERS, text_lower) is not None
    has_preference = re.search(PREFERENCE_TRIGGERS, text_lower) is not None
    has_decision = re.search(DECISION_TRIGGERS, text_lower) is not None
    has_failure = re.search(FAILURE_TRIGGERS, text_lower) is not None
    has_fact = re.search(FACT_TRIGGERS, text_lower) is not None
    has_temporal = re.search(TEMPORAL_TRIGGERS, text_lower) is not None
    has_negation = re.search(NEGATION_TRIGGERS, text_lower) is not None

    trigger_count = sum(
        [has_identity, has_preference, has_decision, has_failure, has_fact, has_temporal]
    )

    if has_negation:
        if has_preference:
            has_failure = True
            has_preference = False
        if has_decision:
            trigger_count -= 1

    if has_identity:
        confidence = 0.9 if trigger_count > 1 else 0.7
        if has_negation:
            confidence -= 0.2
        return "identity", confidence, has_negation

    if has_failure:
        confidence = 0.9 if trigger_count > 1 else 0.7
        return "failure", confidence, has_negation

    if has_decision:
        confidence = 0.9 if trigger_count > 1 else 0.7
        if has_negation:
            confidence -= 0.2
        return "decision", confidence, has_negation

    if has_fact:
        confidence = 0.9 if trigger_count > 1 else 0.7
        return "fact", confidence, has_negation

    if has_preference:
        confidence = 0.9 if trigger_count > 1 else 0.7
        if has_negation:
            confidence -= 0.1
        return "preference", confidence, has_negation

    if has_temporal:
        return "event", 0.7, has_negation

    if has_negation:
        return "event", 0.5, has_negation

    return "event", 0.5, has_negation


def get_decay_rate(memory_type: str) -> float:
    """Get decay rate for a given memory type."""
    return TYPE_DECAY_RATES.get(memory_type, 0.01)
