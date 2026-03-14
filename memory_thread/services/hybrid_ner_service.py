import re
import spacy
from transformers import pipeline
from memory_thread.utils.caching import ner_cache

# Stage 1: Regex NER
REGEX_PATTERNS = {
    "EMAIL": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    "URL": r"https?://\S+",
    "IP": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
}


def regex_ner(text):
    entities = []
    for label, pattern in REGEX_PATTERNS.items():
        for match in re.finditer(pattern, text):
            entities.append({"entity": label, "value": match.group(0), "confidence": 1.0})
    return entities


# Stage 2: SpaCy NER
nlp = spacy.load("en_core_web_sm")


def spacy_ner(text):
    doc = nlp(text)
    entities = [{"entity": ent.label_, "value": ent.text} for ent in doc.ents]

    # Heuristic confidence score from Phase 3.4 spec
    if any(e["entity"] in ["PERSON", "ORG", "GPE", "PRODUCT"] for e in entities):
        confidence = 1.0
    elif any(e["entity"] in ["CARDINAL", "DATE"] for e in entities):
        confidence = 0.5
    else:
        confidence = 0.0

    return entities, confidence


# Stage 3: Transformer NER (Fallback) - lazy loaded
_transformer_pipeline = None


def _get_transformer_pipeline():
    global _transformer_pipeline
    if _transformer_pipeline is None:
        try:
            _transformer_pipeline = pipeline("ner", model="dslim/bert-base-NER")
        except Exception:
            _transformer_pipeline = False  # Mark as unavailable
    return _transformer_pipeline


def transformer_ner(text):
    pipeline = _get_transformer_pipeline()
    if not pipeline:
        return []
    try:
        entities = pipeline(text)
        return [{"entity": ent["entity"], "value": ent["word"]} for ent in entities]
    except Exception:
        return []


def extract_entities(text: str):
    import hashlib

    text_hash = hashlib.sha256(text.encode()).hexdigest()
    if text_hash in ner_cache:
        return ner_cache.get(text_hash)

    # Run all stages
    regex_entities = regex_ner(text)
    spacy_entities, confidence = spacy_ner(text)

    final_entities = regex_entities + spacy_entities

    # Fallback logic - only try transformer if confidence is low and pipeline available
    if confidence < 0.6 and _get_transformer_pipeline():
        try:
            transformer_entities = transformer_ner(text)
            final_entities += transformer_entities
        except Exception:
            pass  # Silently skip if transformer fails

    # Deduplicate entities
    seen = set()
    unique_entities = []
    for entity in final_entities:
        # A simple way to deduplicate, can be improved
        if entity["value"] not in seen:
            unique_entities.append(entity)
            seen.add(entity["value"])

    ner_cache[text_hash] = unique_entities
    return unique_entities
