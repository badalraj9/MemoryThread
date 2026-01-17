from qdrant_client import QdrantClient
from memory_thread.config.settings import settings

def get_qdrant_client():
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

class QdrantClientWrapper:
    def __init__(self):
        self.client = get_qdrant_client()
