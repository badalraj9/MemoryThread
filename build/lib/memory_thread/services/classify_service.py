import re
from typing import Tuple

IDENTITY_TRIGGERS = r"\b(i am|i'm|i live in|my name is)\b"
PREFERENCE_TRIGGERS = r"\b(i prefer|my favorite|i like|i always|i usually)\b"
TEMPORAL_TRIGGERS = r"\b(today|yesterday|tonight|this morning|right now|i'm feeling)\b"
NEGATION_TRIGGERS = r"\b(not|don't|no longer|stopped|quit|isn't|aren't)\b"

def classify_memory(text: str) -> Tuple[str, bool]:
    text_lower = text.lower()
    has_identity = re.search(IDENTITY_TRIGGERS, text_lower) is not None
    has_preference = re.search(PREFERENCE_TRIGGERS, text_lower) is not None
    has_temporal = re.search(TEMPORAL_TRIGGERS, text_lower) is not None
    has_negation = re.search(NEGATION_TRIGGERS, text_lower) is not None

    if has_identity: return "identity", has_negation
    if has_preference: return "preference", has_negation
    if has_temporal: return "event", has_negation
    if has_negation: return "event", has_negation
    return "event", has_negation
