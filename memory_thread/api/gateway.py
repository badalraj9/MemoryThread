"""Batch ingest gateway — stub.

The ZMQ-based high-throughput ingest path is not yet implemented.
When implemented, this will accept batch events from multiple producers
via ZMQ and apply back-pressure based on WAL queue depth.
"""

from fastapi import APIRouter

router = APIRouter()
# ZMQ-based batch ingest — not yet implemented
