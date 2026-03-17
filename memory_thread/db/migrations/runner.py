"""
Database migration runner.
Consolidates schema_phase_3_4.sql through schema_phase_7.sql into numbered migrations.
Tracks applied migrations in schema_version table.
"""

from typing import List, Optional
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


MIGRATIONS = [
    {
        "id": 1,
        "name": "core_tables",
        "description": "Events, entity_state, tms_health tables",
        "sql": """
            CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
            
            CREATE TABLE IF NOT EXISTS events (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                namespace TEXT NOT NULL DEFAULT 'user',
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                actor TEXT NOT NULL CHECK (actor IN ('USER', 'AGENT', 'SYSTEM')),
                action TEXT NOT NULL CHECK (action IN ('PLANT', 'ADD', 'REMOVE', 'UPDATE', 'OBSERVE', 'INFER')),
                object_id UUID NOT NULL,
                delta JSONB NOT NULL DEFAULT '{}',
                antecedents UUID[] DEFAULT '{}',
                truth_vector JSONB NOT NULL DEFAULT '{}',
                consolidated_into UUID REFERENCES events(id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_events_object_id ON events(object_id);
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_namespace ON events(namespace);
            CREATE INDEX IF NOT EXISTS idx_events_consolidated_into ON events(consolidated_into);
            
            CREATE TABLE IF NOT EXISTS entity_state (
                entity_id UUID PRIMARY KEY,
                namespace TEXT NOT NULL,
                current_value JSONB NOT NULL,
                truth_vector JSONB NOT NULL,
                version INTEGER NOT NULL DEFAULT 0,
                last_event_id UUID NOT NULL REFERENCES events(id),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
                last_accessed TIMESTAMPTZ DEFAULT NOW(),
                access_count INTEGER DEFAULT 0
            );
            
            CREATE INDEX IF NOT EXISTS idx_entity_state_namespace ON entity_state(namespace);
            CREATE INDEX IF NOT EXISTS idx_entity_state_status ON entity_state(status);
            CREATE INDEX IF NOT EXISTS idx_entity_state_last_accessed ON entity_state(last_accessed);
            
            CREATE TABLE IF NOT EXISTS tms_health (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                drift_count INTEGER DEFAULT 0,
                contradiction_count INTEGER DEFAULT 0,
                last_updated TIMESTAMPTZ DEFAULT NOW()
            );
            
            INSERT INTO tms_health (id, drift_count, contradiction_count)
            VALUES (1, 0, 0)
            ON CONFLICT (id) DO NOTHING;
        """,
    },
    {
        "id": 2,
        "name": "snapshots_and_transactions",
        "description": "Snapshots and transactions tables",
        "sql": """
            CREATE TABLE IF NOT EXISTS snapshots (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                entity_id UUID NOT NULL REFERENCES entity_state(entity_id),
                last_event_id UUID NOT NULL REFERENCES events(id),
                state_data JSONB NOT NULL,
                truth_vector JSONB NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                state_hash TEXT NOT NULL
            );
            
            CREATE INDEX IF NOT EXISTS idx_snapshots_entity_event ON snapshots(entity_id, last_event_id);
            
            CREATE TABLE IF NOT EXISTS transactions (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                root_event_id UUID NOT NULL REFERENCES events(id),
                status TEXT NOT NULL CHECK (status IN ('PENDING', 'COMMITTED', 'FAILED')),
                involved_entities UUID[] NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """,
    },
    {
        "id": 3,
        "name": "entities_and_merges",
        "description": "Entities and entity merges tables",
        "sql": """
            CREATE TABLE IF NOT EXISTS entities (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                namespace TEXT NOT NULL DEFAULT 'user',
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                attributes JSONB DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                merged_into UUID REFERENCES entities(id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
            CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
            CREATE INDEX IF NOT EXISTS idx_entities_merged_into ON entities(merged_into);
            
            CREATE TABLE IF NOT EXISTS entity_merges (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                source_entity_id UUID NOT NULL REFERENCES entities(id),
                target_entity_id UUID NOT NULL REFERENCES entities(id),
                confidence FLOAT NOT NULL,
                reason TEXT,
                timestamp TIMESTAMPTZ DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_entity_merges_source ON entity_merges(source_entity_id);
            CREATE INDEX IF NOT EXISTS idx_entity_merges_target ON entity_merges(target_entity_id);
        """,
    },
    {
        "id": 4,
        "name": "relations",
        "description": "Knowledge graph relations table",
        "sql": """
            CREATE TABLE IF NOT EXISTS relations (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                source_entity_id UUID NOT NULL REFERENCES entities(id),
                target_entity_id UUID NOT NULL REFERENCES entities(id),
                relation_type TEXT NOT NULL,
                confidence FLOAT NOT NULL DEFAULT 1.0,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                last_confirmed TIMESTAMPTZ DEFAULT NOW(),
                metadata JSONB DEFAULT '{}',
                is_inferred BOOLEAN DEFAULT FALSE,
                UNIQUE(source_entity_id, target_entity_id, relation_type)
            );
            
            CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_entity_id);
            CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_entity_id);
            CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
        """,
    },
    {
        "id": 5,
        "name": "insights_log",
        "description": "Insights log for contemplator",
        "sql": """
            CREATE TABLE IF NOT EXISTS insights_log (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                reflection_json JSONB NOT NULL
            );
            
            CREATE INDEX IF NOT EXISTS idx_insights_log_timestamp ON insights_log(timestamp);
        """,
    },
    {
        "id": 6,
        "name": "projects",
        "description": "Project registry table",
        "sql": """
            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                namespace TEXT UNIQUE NOT NULL,
                initialized_at TIMESTAMP NOT NULL DEFAULT NOW(),
                last_accessed TIMESTAMP NOT NULL DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_projects_namespace ON projects(namespace);
        """,
    },
    {
        "id": 7,
        "name": "schema_version",
        "description": "Schema version tracking table",
        "sql": """
            CREATE TABLE IF NOT EXISTS schema_version (
                version_id INTEGER PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            );
        """,
    },
]


class MigrationRunner:
    def __init__(self, project_path: Optional[str] = None):
        self.project_path = project_path
        try:
            self.pg = PostgresClient()
        except Exception as e:
            log.warning(f"PostgreSQL unavailable, migrations require DB: {e}")
            self.pg = None

    def get_current_version(self) -> int:
        """Get the current schema version."""
        if not self.pg:
            return 0
        try:
            with self.pg.get_cursor() as cur:
                cur.execute(
                    "SELECT version_id FROM schema_version ORDER BY version_id DESC LIMIT 1"
                )
                row = cur.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def get_pending(self) -> List[str]:
        """Get list of pending migration names."""
        current_version = self.get_current_version()
        pending = []
        for migration in MIGRATIONS:
            if migration["id"] > current_version:
                pending.append(f"{migration['id']:03d}_{migration['name']}")
        return pending

    def run_migrations(self, target_version: Optional[int] = None) -> List[int]:
        """
        Run all pending migrations.

        Args:
            target_version: Optional target version. If None, runs all pending.

        Returns:
            List of applied migration IDs
        """
        if not self.pg:
            log.warning("PostgreSQL not available, skipping migrations")
            return []

        current_version = self.get_current_version()
        applied = []

        for migration in MIGRATIONS:
            if migration["id"] <= current_version:
                continue

            if target_version and migration["id"] > target_version:
                break

            log.info(f"Running migration {migration['id']}: {migration['name']}")

            try:
                with self.pg.get_cursor() as cur:
                    cur.execute(migration["sql"])

                    cur.execute(
                        "INSERT INTO schema_version (version_id) VALUES (%s)", (migration["id"],)
                    )

                applied.append(migration["id"])
                log.info(f"Migration {migration['id']} applied successfully")

            except Exception as e:
                log.error(f"Migration {migration['id']} failed: {e}")
                raise

        return applied


def run_all_migrations():
    """Run all pending migrations."""
    runner = MigrationRunner()
    applied = runner.run_migrations()
    if applied:
        print(f"Applied migrations: {applied}")
    else:
        print("No migrations to apply")
    return applied


if __name__ == "__main__":
    run_all_migrations()
