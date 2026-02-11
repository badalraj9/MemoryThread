import zlib
import re
from collections import Counter
import numpy as np
from scipy.spatial.distance import cosine

# --- Archetype Profiles ---
# Pre-computed N-gram profiles for different text types
ARCHETYPES = {
    "NATURAL_LANGUAGE": Counter("the and of to a in that is was he for it with as his on be at by i this had not are but from or have an they which one you were her all she there would their we him been has when who will no more if out so up said what its about than into them can only other time new some could these two may first then do any my now".split()),
    "STRUCTURED_LOG": Counter("info warn error exception status code request response GET POST PUT DELETE timestamp".split()),
}

def get_ngram_profile(text: str, n: int = 1) -> Counter:
    """Generates a frequency profile of N-grams for a given text."""
    # Simple whitespace tokenizer
    tokens = text.lower().split()
    ngrams = zip(*[tokens[i:] for i in range(n)])
    return Counter(ngrams)

def to_vector(profile: Counter, vocabulary: set) -> np.ndarray:
    """Converts a Counter profile to a numpy vector based on a vocabulary."""
    return np.array([profile.get(word, 0) for word in vocabulary])

def route_text(text: str):
    """Routes text based on N-gram profile similarity to archetypes."""
    # Feature extraction from spec
    text_len = len(text)
    digit_ratio = sum(c.isdigit() for c in text) / text_len if text_len > 0 else 0
    is_log_signature = any(keyword in text[:50] for keyword in ["INFO", "WARN", "ERROR", "Exception"])

    # Routing rules from spec
    if text_len < 40 or digit_ratio > 0.4 or is_log_signature:
        return "TRIVIAL"
    if text_len < 200 and (re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text) or re.search(r"https?://\S+", text)):
        return "STRUCTURED"

    # N-gram routing for NATURAL vs. COMPLEX
    profile = get_ngram_profile(text)

    # Create a combined vocabulary
    vocabulary = set(ARCHETYPES["NATURAL_LANGUAGE"].keys()) | set(profile.keys())

    # Convert profiles to vectors
    v_text = to_vector(profile, vocabulary)
    v_natural = to_vector(ARCHETYPES["NATURAL_LANGUAGE"], vocabulary)

    # Cosine similarity
    # distance = 1 - similarity, so a small distance means high similarity
    similarity = 1 - cosine(v_text, v_natural)

    if similarity > 0.1: # Threshold can be tuned
        return "NATURAL"
    else:
        return "COMPLEX"
