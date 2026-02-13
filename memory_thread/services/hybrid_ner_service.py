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

# Stage 3: Transformer NER (Fallback)
transformer_ner_pipeline = pipeline("ner", model="dslim/bert-base-NER")

def transformer_ner(text):
    entities = transformer_ner_pipeline(text)
    return [{"entity": ent["entity"], "value": ent["word"]} for ent in entities]

def extract_entities(text: str):
    import hashlib
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    if text_hash in ner_cache:
        return ner_cache.get(text_hash)

    # Run all stages
    try:
        regex_entities = regex_ner(text)
    except Exception as e:
        print(f"Regex NER failed: {e}")
        regex_entities = []

    try:
        spacy_entities, confidence = spacy_ner(text)
    except Exception as e:
        print(f"Spacy NER failed: {e}")
        spacy_entities, confidence = [], 0.0

    final_entities = regex_entities + spacy_entities

    # Fallback logic
    if confidence < 0.6:
        transformer_entities = transformer_ner(text)
        final_entities += transformer_entities

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
