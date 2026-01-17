import uuid
import json
import logging
import os
from unittest.mock import MagicMock

DB_FILE = "tests/phase5_ordeal/mock_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {
        "events": [],
        "entities": [],
        "entity_state": [],
        "entity_merges": []
    }

def save_db(db):
    # Serialize complex types (UUID, datetime) to string
    # But for a simple mock, we just use the data as is if it's serializable.
    # Our tests insert strings for UUIDs usually? No, mostly UUID objects.
    # We need a custom encoder.

    class CustomEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, uuid.UUID):
                return str(obj)
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            return super().default(obj)

    with open(DB_FILE, "w") as f:
        json.dump(db, f, cls=CustomEncoder)

class MockCursor:
    def __init__(self, client):
        self.client = client
        self.db = client.db
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute(self, query, params=None):
        query = query.strip().lower()

        # Helper to convert params to serializable form for storage
        def clean_params(p):
            if not p: return p
            return [str(x) if isinstance(x, uuid.UUID) or hasattr(x, 'isoformat') else x for x in p]

        c_params = clean_params(params)

        if query.startswith("insert into events"):
            self.db["events"].append(c_params)
            self.client._dirty = True
        elif query.startswith("insert into entities"):
            self.db["entities"].append(c_params)
            self.client._dirty = True
        elif query.startswith("insert into entity_state"):
            # Upsert logic
            eid = c_params[0]
            found = False
            for i, row in enumerate(self.db["entity_state"]):
                if row[0] == eid:
                    self.db["entity_state"][i] = c_params
                    found = True
                    break
            if not found:
                self.db["entity_state"].append(c_params)
            self.client._dirty = True
        elif query.startswith("select id from entities"):
            if "where name =" in query:
                name_to_find = params[0] if params else None
                # entities: id, ns, type, name, ...
                self.rows = [(e[0],) for e in self.db["entities"] if e[3] == name_to_find]
            elif "order by random()" in query:
                 limit = 100
                 self.rows = [(e[0],) for e in self.db["entities"][:limit]]
            else:
                self.rows = [(e[0],) for e in self.db["entities"]]

        elif query.startswith("select entity_id, current_value"):
            self.rows = [(e[0], e[2], e[3]) for e in self.db["entity_state"]]
        elif query.startswith("select id, namespace, timestamp"):
             # events: id, ns, time, actor, action, obj_id, ...
             oid = str(params[0]) if params else None
             self.rows = [e for e in self.db["events"] if str(e[5]) == oid]
        elif query.startswith("update entity_state"):
            # Update specific logic (e.g., pruning, decay)
            # If "set updated_at" (Stage 4)
            if "set updated_at = updated_at -" in query:
                 # Logic too complex to mock perfectly with text parsing
                 pass
            elif "set status = 'inactive'" in query:
                # Pruning
                ids = params[0]
                for i, row in enumerate(self.db["entity_state"]):
                    if row[0] in ids:
                        # row is list, need to update status column?
                        # entity_state mock schema: [eid, ns, val, tv, last_evt, updated]
                        # We don't have status in insert above?
                        # Stage 0 inserts 6 cols.
                        # We need to handle schema evolution in mock?
                        pass
            self.client._dirty = True
        elif query.startswith("select"):
             if "from entities where id =" in query:
                 eid = str(params[0])
                 for e in self.db["entities"]:
                     if str(e[0]) == eid:
                         row = list(e)
                         if len(row) < 8: row.append(None)
                         self.rows = [tuple(row)]
                         return
                 self.rows = []
             else:
                 self.rows = []
        else:
            self.rows = []

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

class MockPostgresClient:
    def __init__(self):
        self.db = load_db()
        self._dirty = False

    def get_cursor(self):
        # On exit of cursor context, we should probably save if dirty?
        # But cursor doesn't know when context ends easily unless we wrap it.
        # We'll save on commit or just destructively save in execute for safety in subprocesses.
        # Optimization: We can save in __del__ or rely on manual saves?
        # Better: Save in cursor.__exit__?
        # No, MockCursor.__exit__ is called.
        return MockCursorWrapper(self)

class MockCursorWrapper(MockCursor):
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.client._dirty:
            save_db(self.client.db)
            self.client._dirty = False

class MockQdrantClientWrapper:
    def __init__(self):
        self.client = MagicMock()
        self.client.retrieve.return_value = []
        self.client.search.return_value = []
        self.client.upsert = MagicMock()
        self.client.get_collection = MagicMock()
        self.client.create_collection = MagicMock()
        self.client.delete = MagicMock()

def apply_patches(stage_module_name):
    import sys
    from unittest.mock import patch

    targets = [
        'memory_thread.db.postgres_client.PostgresClient',
        'memory_thread.db.qdrant_client.QdrantClientWrapper',
        'memory_thread.services.identity_service.PostgresClient',
        'memory_thread.services.identity_service.QdrantClientWrapper',
        'memory_thread.services.assimilator.PostgresClient',
        'memory_thread.services.pruner.PostgresClient',
        'memory_thread.services.decay_engine.PostgresClient',
        'memory_thread.services.maintenance_orchestrator.IdentityService',
    ]

    p1 = patch('memory_thread.db.postgres_client.PostgresClient', MockPostgresClient)
    p2 = patch('memory_thread.db.qdrant_client.QdrantClientWrapper', MockQdrantClientWrapper)

    p1.start()
    p2.start()

    return p1, p2
