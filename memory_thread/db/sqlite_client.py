"""
SQLite Client for Memory Thread.

A lightweight alternative to PostgreSQL for:
- Local development
- Single-user deployments
- Testing without external dependencies

The database file is created automatically.
"""
import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# Default database path
DEFAULT_DB_PATH = os.path.join(os.path.expanduser("~"), ".memory_thread", "mt.db")


class SQLiteClient:
    """
    SQLite client for Memory Thread.
    
    Drop-in replacement for PostgresClient when you don't need full Postgres.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SQLite client.
        
        Args:
            db_path: Path to database file. Defaults to ~/.memory_thread/mt.db
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Initialize schema
        self._init_schema()
        log.info(f"SQLite initialized: {self.db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    @contextmanager
    def get_cursor(self):
        """Context manager for database cursor."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_schema(self):
        """Initialize database schema."""
        with self.get_cursor() as cur:
            # Events table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    object_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    delta TEXT,
                    timestamp TEXT NOT NULL,
                    truth_vector TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Entity state table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS entity_state (
                    entity_id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    current_value TEXT,
                    truth_vector TEXT,
                    last_event_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Indexes
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_object_id ON events(object_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_entity_state_namespace ON entity_state(namespace)
            """)
    
    def save_event(self, event_id: str, object_id: str, actor: str, 
                   action: str, delta: Dict, timestamp: datetime,
                   truth_vector: Dict) -> bool:
        """Save an event to the database."""
        try:
            with self.get_cursor() as cur:
                cur.execute("""
                    INSERT OR REPLACE INTO events 
                    (id, object_id, actor, action, delta, timestamp, truth_vector)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    event_id,
                    object_id,
                    actor,
                    action,
                    json.dumps(delta),
                    timestamp.isoformat(),
                    json.dumps(truth_vector)
                ))
            return True
        except Exception as e:
            log.error(f"Failed to save event: {e}")
            return False
    
    def save_state(self, entity_id: str, namespace: str, current_value: Dict,
                   truth_vector: Dict, last_event_id: str) -> bool:
        """Save entity state (upsert)."""
        try:
            with self.get_cursor() as cur:
                cur.execute("""
                    INSERT OR REPLACE INTO entity_state
                    (entity_id, namespace, current_value, truth_vector, last_event_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    entity_id,
                    namespace,
                    json.dumps(current_value),
                    json.dumps(truth_vector),
                    last_event_id,
                    datetime.utcnow().isoformat()
                ))
            return True
        except Exception as e:
            log.error(f"Failed to save state: {e}")
            return False
    
    def get_state(self, entity_id: str) -> Optional[Dict]:
        """Get entity state by ID."""
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT entity_id, namespace, current_value, truth_vector, last_event_id
                FROM entity_state WHERE entity_id = ?
            """, (entity_id,))
            row = cur.fetchone()
            
            if row:
                return {
                    "entity_id": row["entity_id"],
                    "namespace": row["namespace"],
                    "current_value": json.loads(row["current_value"]) if row["current_value"] else {},
                    "truth_vector": json.loads(row["truth_vector"]) if row["truth_vector"] else {},
                    "last_event_id": row["last_event_id"]
                }
            return None
    
    def get_states_by_namespace(self, namespace: str) -> List[Dict]:
        """Get all states in a namespace."""
        states = []
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT entity_id, namespace, current_value, truth_vector, last_event_id
                FROM entity_state WHERE namespace = ?
            """, (namespace,))
            
            for row in cur.fetchall():
                states.append({
                    "entity_id": row["entity_id"],
                    "namespace": row["namespace"],
                    "current_value": json.loads(row["current_value"]) if row["current_value"] else {},
                    "truth_vector": json.loads(row["truth_vector"]) if row["truth_vector"] else {},
                    "last_event_id": row["last_event_id"]
                })
        
        return states
    
    def get_events_for_entity(self, object_id: str) -> List[Dict]:
        """Get all events for an entity."""
        events = []
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT id, object_id, actor, action, delta, timestamp, truth_vector
                FROM events WHERE object_id = ? ORDER BY timestamp
            """, (object_id,))
            
            for row in cur.fetchall():
                events.append({
                    "id": row["id"],
                    "object_id": row["object_id"],
                    "actor": row["actor"],
                    "action": row["action"],
                    "delta": json.loads(row["delta"]) if row["delta"] else {},
                    "timestamp": row["timestamp"],
                    "truth_vector": json.loads(row["truth_vector"]) if row["truth_vector"] else {}
                })
        
        return events
    
    def delete_state(self, entity_id: str) -> bool:
        """Delete an entity state."""
        try:
            with self.get_cursor() as cur:
                cur.execute("DELETE FROM entity_state WHERE entity_id = ?", (entity_id,))
            return True
        except Exception:
            return False
    
    def count_states(self, namespace: Optional[str] = None) -> int:
        """Count states, optionally by namespace."""
        with self.get_cursor() as cur:
            if namespace:
                cur.execute("SELECT COUNT(*) FROM entity_state WHERE namespace = ?", (namespace,))
            else:
                cur.execute("SELECT COUNT(*) FROM entity_state")
            return cur.fetchone()[0]
    
    def health_check(self) -> Dict[str, Any]:
        """Check database health."""
        try:
            with self.get_cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM entity_state")
                count = cur.fetchone()[0]
            
            return {
                "status": "healthy",
                "type": "sqlite",
                "path": self.db_path,
                "state_count": count
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Singleton instance
_client: Optional[SQLiteClient] = None


def get_sqlite_client(db_path: Optional[str] = None) -> SQLiteClient:
    """Get or create SQLite client singleton."""
    global _client
    if _client is None:
        _client = SQLiteClient(db_path)
    return _client
