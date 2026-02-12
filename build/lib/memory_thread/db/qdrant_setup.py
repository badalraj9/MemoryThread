import qdrant_client
from qdrant_client.http import models
COLLECTION_NAME = "memory_vectors"
def setup_qdrant_collection(client: qdrant_client.QdrantClient):
    if COLLECTION_NAME not in [c.name for c in client.get_collections().collections]:
        client.create_collection(collection_name=COLLECTION_NAME, vectors_config=models.VectorParams(size=1536, distance=models.Distance.COSINE), hnsw_config=models.HnswConfigDiff(m=64, ef_construct=200))
    client.create_payload_index(collection_name=COLLECTION_NAME, field_name="memory_type", field_schema=models.PayloadSchemaType.KEYWORD)
    client.create_payload_index(collection_name=COLLECTION_NAME, field_name="metadata.negation", field_schema=models.PayloadSchemaType.BOOL)
