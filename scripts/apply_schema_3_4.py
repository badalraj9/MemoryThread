import os
from psycopg2 import sql, connect as _connect
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

DB_HOST = os.environ.get("POSTGRES_SERVER", "localhost")
DB_NAME = os.environ.get("POSTGRES_DB", "memory_thread")
DB_USER = os.environ.get("POSTGRES_USER", "")
DB_PASS = os.environ.get("POSTGRES_PASSWORD", "")
SUPER_USER = os.environ.get("PG_SUPERUSER", "postgres")
SUPER_PASS = os.environ.get("PG_SUPERUSER_PASSWORD", "")


def apply_schema():
    try:
        conn = _connect(
            host=DB_HOST,
            dbname="postgres",
            user=SUPER_USER,
            password=SUPER_PASS,
        )
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute(
            sql.SQL("SELECT 1 FROM pg_catalog.pg_database WHERE datname = {}"),
            [sql.Literal(DB_NAME)],
        )
        exists = cur.fetchone()
        if not exists:
            log.info(f"Creating database {DB_NAME}...")
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))

        cur.close()
        conn.close()

        conn = _connect(
            host=DB_HOST,
            dbname=DB_NAME,
            user=SUPER_USER,
            password=SUPER_PASS,
        )
        conn.autocommit = True
        cur = conn.cursor()

        with open("memory_thread/db/schema_phase_3_4.sql", "r") as f:
            schema_sql = f.read()

        log.info("Applying Phase 3.4 Schema...")
        cur.execute(schema_sql)
        log.info("Schema applied successfully.")

        cur.close()
        conn.close()

    except Exception as e:
        log.error(f"Database setup failed: {e}")
        raise


if __name__ == "__main__":
    apply_schema()
