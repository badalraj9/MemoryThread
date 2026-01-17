import psycopg2
from psycopg2.extras import RealDictCursor
from memory_thread.config.settings import settings
from contextlib import contextmanager

def get_postgres_connection():
    return psycopg2.connect(
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_SERVER,
        port=settings.POSTGRES_PORT,
        cursor_factory=RealDictCursor
    )

class PostgresClient:
    def __init__(self):
        pass

    @contextmanager
    def get_cursor(self):
        conn = get_postgres_connection()
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
