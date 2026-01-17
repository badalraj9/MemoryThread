import re
from typing import Dict, List
REGEX_PATTERNS = {"email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), "date": re.compile(r'\b(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b')}
def extract_patterns(text: str) -> Dict[str, List[str]]:
    extractions = {}
    for entity_type, pattern in REGEX_PATTERNS.items():
        found = pattern.findall(text)
        if found: extractions[entity_type] = found
    return extractions
