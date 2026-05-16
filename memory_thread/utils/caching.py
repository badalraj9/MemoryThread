from cachetools import LRUCache, TTLCache

# In-process cache for memoizing expensive function calls.
# This is NOT for inter-process communication.

# Cache for final results, with a Time-To-Live of 30 minutes (1800 seconds)
result_cache = TTLCache(maxsize=1000, ttl=1800)

# Caches for NLP artifacts with a longer TTL, e.g., 1 day (86400 seconds)
ner_cache = TTLCache(maxsize=5000, ttl=86400)
