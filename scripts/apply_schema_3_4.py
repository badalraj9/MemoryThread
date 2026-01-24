import psycopg2
import os
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# Hardcoded for now based on environment, usually passed via env vars in prod
# Assuming standard Postgres setup in sandbox
DB_HOST = "localhost"
DB_NAME = "memory_thread"
DB_USER = "user"
DB_PASS = "password"

def apply_schema():
    try:
        # Connect to DB (using standard sandbox creds or defaults)
        # In this sandbox, we usually need to check what credentials work.
        # I will try standard local connection.
        conn = psycopg2.connect(
            host=DB_HOST,
            dbname="postgres", # Connect to default first
            user="postgres",
            password="password"
        )
        conn.autocommit = True
        cur = conn.cursor()

        # Create DB if not exists
        cur.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{DB_NAME}'")
        exists = cur.fetchone()
        if not exists:
            log.info(f"Creating database {DB_NAME}...")
            cur.execute(f"CREATE DATABASE {DB_NAME}")

        cur.close()
        conn.close()

        # Connect to actual DB
        conn = psycopg2.connect(
            host=DB_HOST,
            dbname=DB_NAME,
            user="postgres",
            password="password"
        )
        conn.autocommit = True
        cur = conn.cursor()

        # Read Schema File
        with open("memory_thread/db/schema_phase_3_4.sql", "r") as f:
            schema_sql = f.read()

        log.info("Applying Phase 3.4 Schema...")
        cur.execute(schema_sql)
        log.info("Schema applied successfully.")

        cur.close()
        conn.close()

    except Exception as e:
        log.error(f"Database setup failed: {e}")
        # If connection failed, likely env specific.
        # But for this task I assume standard setup.
        raise e

if __name__ == "__main__":
    apply_schema()
