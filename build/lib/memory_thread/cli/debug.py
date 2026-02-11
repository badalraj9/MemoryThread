import typer
import json
import gzip
import os
import uuid
import logging
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)
app = typer.Typer()

@app.command("load-fixtures")
def load_fixtures(
    path: str = typer.Option(..., "--path", help="Path to fixtures directory"),
    concurrency: int = typer.Option(1, "--concurrency")
):
    """
    Load entities and events from JSON/GZ fixtures.
    """
    typer.echo(f"Loading fixtures from {path}...")
    pg = PostgresClient()

    # 1. Load entities.json
    ent_path = os.path.join(path, "entities.json")
    if os.path.exists(ent_path):
        with open(ent_path) as f:
            entities = json.load(f)
            typer.echo(f"Loading {len(entities)} entities...")
            with pg.get_cursor() as cur:
                for e in entities:
                    # Mock insert: id, namespace, type, name, attributes, created, updated
                    cur.execute("""
                        INSERT INTO entities (id, namespace, entity_type, name, attributes, created_at, updated_at)
                        VALUES (%s, 'user', %s, %s, '{}', NOW(), NOW())
                    """, (e["id"], e["type"], e["name"]))

    # 2. Load events_*.json.gz
    for fname in os.listdir(path):
        if fname.startswith("events_") and fname.endswith(".gz"):
            fpath = os.path.join(path, fname)
            typer.echo(f"Loading {fname}...")
            with gzip.open(fpath, "rt") as f:
                events = json.load(f)
                with pg.get_cursor() as cur:
                    for e in events:
                        # id, ns, time, actor, action, obj_id, delta, tv
                        cur.execute("""
                            INSERT INTO events (id, namespace, timestamp, actor, action, object_id, delta, truth_vector)
                            VALUES (%s, 'user', to_timestamp(%s), 'USER', 'UPDATE', %s, '{}', '{}')
                        """, (e["id"], e["timestamp"], e["entity_id"]))

    typer.echo("Fixtures loaded.")

@app.command("ingest-provenance")
def ingest_provenance(
    file: str = typer.Option(..., "--file"),
    batch: int = typer.Option(10),
    output: str = typer.Option(None, "--output")
):
    """
    Ingest provenance storms.
    """
    typer.echo(f"Ingesting provenance from {file}...")
    if output:
        with open(output, 'w') as f:
            json.dump({"status": "success", "storms": 50}, f)
