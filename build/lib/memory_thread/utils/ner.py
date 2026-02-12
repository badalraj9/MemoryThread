import spacy
from functools import lru_cache
nlp = spacy.load("en_core_web_sm")
@lru_cache(maxsize=1024)
def extract_entities(text: str) -> dict:
    doc = nlp(text)
    return {"persons": [e.text for e in doc.ents if e.label_ == "PERSON"], "orgs": [e.text for e in doc.ents if e.label_ == "ORG"], "locations": [e.text for e in doc.ents if e.label_ == "GPE"]}
