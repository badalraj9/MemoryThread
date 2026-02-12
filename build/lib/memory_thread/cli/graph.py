import typer
import uuid
import json
from memory_thread.services.graph_service import GraphService
from memory_thread.services.reasoning.query_engine import QueryEngine
from memory_thread.services.reasoning.inference_engine import InferenceEngine
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

app = typer.Typer(help="Phase 7: Knowledge Graph Tools")

@app.command("add")
def add_relation(
    source: str, target: str, type: str, confidence: float = 1.0
):
    service = GraphService()
    try:
        rid = service.add_relation(uuid.UUID(source), uuid.UUID(target), type, confidence)
        log.info(f"Created relation {rid}")
    except Exception as e:
        log.error(f"Error: {e}")

@app.command("path")
def find_path(start: str, end: str, hops: int = 3):
    engine = QueryEngine()
    path = engine.find_path(uuid.UUID(start), uuid.UUID(end), hops)
    if path:
        log.info("Path found:")
        for r in path:
            log.info(f" -[{r['relation_type']}]-> {r['target_entity_id']}")
    else:
        log.info("No path found.")

@app.command("infer")
def infer(entity: str):
    engine = InferenceEngine()
    engine.infer_transitive_relations(uuid.UUID(entity))
    log.info("Inference complete.")

if __name__ == "__main__":
    app()
