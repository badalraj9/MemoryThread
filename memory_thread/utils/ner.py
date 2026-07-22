from typing import List
import spacy
from functools import lru_cache

nlp = spacy.load("en_core_web_sm")


@lru_cache(maxsize=1024)
def extract_entities(text: str) -> dict:
    doc = nlp(text)
    return {
        "persons": [e.text for e in doc.ents if e.label_ == "PERSON"],
        "orgs": [e.text for e in doc.ents if e.label_ == "ORG"],
        "locations": [e.text for e in doc.ents if e.label_ == "GPE"],
    }


def embed_text(text: str) -> List[float]:
    """Generate a text embedding vector using spaCy word vectors."""
    doc = nlp(text)
    if doc.vector_norm == 0:
        return [0.0] * 96
    return doc.vector.tolist()
