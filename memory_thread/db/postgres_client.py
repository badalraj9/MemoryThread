"""
PostgreSQL Client with Connection Pooling and Retry Logic.

This module provides a production-ready PostgreSQL client with:
- ThreadedConnectionPool for concurrent access
- Automatic retry with exponential backoff for transient failures
- Health check capabilities for monitoring
- Graceful shutdown with pool cleanup
"""

import atexit
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Optional, Dict, Any
from threading import Lock

from memory_thread.config.settings import settings
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# Module-level pool (singleton pattern)
_pool: Optional[ThreadedConnectionPool] = None
_pool_lock = Lock()


def _get_dsn() -> str:
    """Returns the PostgreSQL connection string."""
    return (
        f"dbname={settings.POSTGRES_DB} "
        f"user={settings.POSTGRES_USER} "
        f"password={settings.POSTGRES_PASSWORD} "
        f"host={settings.POSTGRES_SERVER} "
        f"port={settings.POSTGRES_PORT}"
    )


def get_pool() -> ThreadedConnectionPool:
    """
    Returns the global connection pool, initializing if needed.
    Thread-safe singleton pattern.
    """
    global _pool

    if _pool is None:
        with _pool_lock:
            if _pool is None:
                try:
                    _pool = ThreadedConnectionPool(
                        minconn=settings.DB_POOL_MIN_CONN,
                        maxconn=settings.DB_POOL_MAX_CONN,
                        dsn=_get_dsn(),
                        cursor_factory=RealDictCursor,
                    )
                    log.info(
                        f"PostgreSQL pool initialized "
                        f"(min={settings.DB_POOL_MIN_CONN}, max={settings.DB_POOL_MAX_CONN})"
                    )
                except Exception as e:
                    log.error(f"Failed to initialize PostgreSQL pool: {e}")
                    raise
    return _pool


def close_pool():
    """Closes the connection pool. Call during shutdown."""
    global _pool

    with _pool_lock:
        if _pool is not None:
            try:
                _pool.closeall()
                log.info("PostgreSQL pool closed")
            except Exception as e:
                log.warning(f"Error closing pool: {e}")
            finally:
                _pool = None


# Register cleanup on interpreter exit
atexit.register(close_pool)


def retry_on_connection_error(max_attempts: int = None, wait_seconds: float = None):
    """
    Decorator for retrying database operations on transient failures.
    Uses exponential backoff with configurable parameters.
    """
    import functools
    import time

    max_attempts = max_attempts or settings.RETRY_MAX_ATTEMPTS
    wait_seconds = wait_seconds or settings.RETRY_WAIT_SECONDS

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                    last_exception = e
                    if attempt < max_attempts:
                        # Exponential backoff with cap
                        delay = min(
                            wait_seconds * (2 ** (attempt - 1)), settings.RETRY_WAIT_MAX_SECONDS
                        )
                        log.warning(
                            f"Database operation failed (attempt {attempt}/{max_attempts}): {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        log.error(f"Database operation failed after {max_attempts} attempts: {e}")
                        raise
                except Exception as e:
                    # Non-retryable error
                    raise

            raise last_exception

        return wrapper

    return decorator


class PostgresClient:
    """
    PostgreSQL client with connection pooling.

    Usage:
        client = PostgresClient()
        with client.get_cursor() as cur:
            cur.execute("SELECT * FROM table")
            rows = cur.fetchall()
    """

    def __init__(self):
        """Initialize client. Pool is created lazily on first use."""
        self._pool = None

    @property
    def pool(self) -> ThreadedConnectionPool:
        """Lazy pool access."""
        if self._pool is None:
            self._pool = get_pool()
        return self._pool

    @contextmanager
    def get_cursor(self):
        """
        Context manager for database cursor with automatic connection handling.

        - Gets connection from pool
        - Commits on success, rolls back on error
        - Always returns connection to pool

        Yields:
            RealDictCursor for database operations
        """
        conn = None
        try:
            conn = self.pool.getconn()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
            conn.commit()
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    @contextmanager
    def get_connection(self):
        """
        Context manager for raw connection access.
        Use when you need more control than get_cursor provides.

        Yields:
            psycopg2 connection object
        """
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
            conn.commit()
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    def health_check(self) -> Dict[str, Any]:
        """
        Performs a health check on the database connection.

        Returns:
            Dict with status, latency, and pool info
        """
        import time

        result = {"status": "unknown", "latency_ms": None, "pool_size": None, "error": None}

        try:
            start = time.perf_counter()
            with self.get_cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()

            latency_ms = (time.perf_counter() - start) * 1000

            result.update(
                {
                    "status": "healthy",
                    "latency_ms": round(latency_ms, 2),
                    "pool_size": {
                        "min": settings.DB_POOL_MIN_CONN,
                        "max": settings.DB_POOL_MAX_CONN,
                    },
                }
            )

        except Exception as e:
            result.update({"status": "unhealthy", "error": str(e)})

        return result

    @retry_on_connection_error()
    def execute(self, query: str, params: tuple = None) -> int:
        """
        Executes a query with automatic retry on transient failures.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Number of rows affected
        """
        with self.get_cursor() as cur:
            cur.execute(query, params)
            return cur.rowcount

    @retry_on_connection_error()
    def fetch_one(self, query: str, params: tuple = None) -> Optional[Dict]:
        """
        Fetches a single row with automatic retry.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Row as dict, or None if not found
        """
        with self.get_cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()

    @retry_on_connection_error()
    def fetch_all(self, query: str, params: tuple = None) -> list:
        """
        Fetches all rows with automatic retry.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            List of rows as dicts
        """
        with self.get_cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


# Legacy function for backward compatibility
def get_postgres_connection():
    """
    DEPRECATED: Use PostgresClient with get_cursor() instead.

    This function creates a new connection each time.
    For production code, use PostgresClient which uses connection pooling.
    """
    log.warning(
        "get_postgres_connection() is deprecated. "
        "Use PostgresClient with get_cursor() for connection pooling."
    )
    return psycopg2.connect(
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_SERVER,
        port=settings.POSTGRES_PORT,
        cursor_factory=RealDictCursor,
    )
