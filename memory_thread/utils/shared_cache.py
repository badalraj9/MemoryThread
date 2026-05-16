import multiprocessing as mp

class SharedCache:
    def __init__(self, manager):
        self._cache = manager.dict()

    def get(self, key):
        return self._cache.get(key)

    def set(self, key, value):
        self._cache[key] = value

    def __contains__(self, key):
        return key in self._cache

manager = mp.Manager()
result_cache = SharedCache(manager)
ner_cache = SharedCache(manager)
