"""
Async PostgreSQL Client with Connection Pooling.

This module provides an async-first PostgreSQL client with:
- asyncpg connection pool for high concurrency
- Automatic retry with exponential backoff
- Health check capabilities
- Graceful shutdown

Usage:
    client = AsyncPostgresClient()
    await client.connect()
    
    row = await client.fetch_one("SELECT * FROM table WHERE id = $1", id)
    rows = await client.fetch_all("SELECT * FROM table")
    await client.execute("UPDATE table SET value = $1 WHERE id = $2", value, id)
    
    await client.close()
"""
import asyncio
import asyncpg
from asyncpg import Pool
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
import functools
import time

from memory_thread.config.settings import settings
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# Module-level pool (singleton pattern)
_pool: Optional[Pool] = None
_pool_lock = asyncio.Lock()


def _get_dsn() -> str:
    """Returns the PostgreSQL connection string."""
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@"
        f"{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


async def get_pool() -> Pool:
    """
    Returns the global connection pool, initializing if needed.
    Thread-safe singleton pattern.
    """
    global _pool
    
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                try:
                    _pool = await asyncpg.create_pool(
                        dsn=_get_dsn(),
                        min_size=settings.DB_POOL_MIN_CONN,
                        max_size=settings.DB_POOL_MAX_CONN,
                        command_timeout=60
                    )
                    log.info(
                        f"Async PostgreSQL pool initialized "
                        f"(min={settings.DB_POOL_MIN_CONN}, max={settings.DB_POOL_MAX_CONN})"
                    )
                except Exception as e:
                    log.error(f"Failed to initialize async PostgreSQL pool: {e}")
                    raise
    return _pool


async def close_pool():
    """Closes the connection pool. Call during shutdown."""
    global _pool
    
    async with _pool_lock:
        if _pool is not None:
            try:
                await _pool.close()
                log.info("Async PostgreSQL pool closed")
            except Exception as e:
                log.warning(f"Error closing async pool: {e}")
            finally:
                _pool = None


def retry_on_connection_error(max_attempts: int = None, wait_seconds: float = None):
    """
    Decorator for retrying async database operations on transient failures.
    Uses exponential backoff with configurable parameters.
    """
    max_attempts = max_attempts or settings.RETRY_MAX_ATTEMPTS
    wait_seconds = wait_seconds or settings.RETRY_WAIT_SECONDS
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except (asyncpg.PostgresConnectionError, asyncpg.InterfaceError, OSError) as e:
                    last_exception = e
                    if attempt < max_attempts:
                        delay = min(
                            wait_seconds * (2 ** (attempt - 1)),
                            settings.RETRY_WAIT_MAX_SECONDS
                        )
                        log.warning(
                            f"Async DB operation failed (attempt {attempt}/{max_attempts}): {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        log.error(f"Async DB operation failed after {max_attempts} attempts: {e}")
                        raise
                except Exception:
                    # Non-retryable error
                    raise
                    
            raise last_exception
        return wrapper
    return decorator


class AsyncPostgresClient:
    """
    Async PostgreSQL client with connection pooling.
    
    Usage:
        client = AsyncPostgresClient()
        await client.connect()
        
        row = await client.fetch_one("SELECT * FROM table WHERE id = $1", id)
        rows = await client.fetch_all("SELECT * FROM table")
        
        await client.close()
    """
    
    def __init__(self):
        """Initialize client. Pool is created lazily on first use."""
        self._pool: Optional[Pool] = None
        self._connected = False
    
    async def connect(self):
        """Initialize the connection pool."""
        if not self._connected:
            self._pool = await get_pool()
            self._connected = True
    
    async def close(self):
        """Close the pool (only if we own it)."""
        # Don't close the global pool, just mark as disconnected
        self._connected = False
    
    @asynccontextmanager
    async def acquire(self):
        """
        Async context manager for acquiring a connection.
        
        Usage:
            async with client.acquire() as conn:
                await conn.execute(...)
        """
        if not self._connected:
            await self.connect()
        
        async with self._pool.acquire() as conn:
            yield conn
    
    @asynccontextmanager
    async def transaction(self):
        """
        Async context manager for a transaction.
        
        Usage:
            async with client.transaction() as conn:
                await conn.execute(...)
                await conn.execute(...)
        """
        async with self.acquire() as conn:
            async with conn.transaction():
                yield conn
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Performs a health check on the database connection.
        
        Returns:
            Dict with status, latency, and pool info
        """
        result = {
            "status": "unknown",
            "latency_ms": None,
            "pool_size": None,
            "error": None
        }
        
        try:
            start = time.perf_counter()
            async with self.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            latency_ms = (time.perf_counter() - start) * 1000
            
            result.update({
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "pool_size": {
                    "min": settings.DB_POOL_MIN_CONN,
                    "max": settings.DB_POOL_MAX_CONN,
                    "current": self._pool.get_size() if self._pool else 0,
                    "free": self._pool.get_idle_size() if self._pool else 0
                }
            })
            
        except Exception as e:
            result.update({
                "status": "unhealthy",
                "error": str(e)
            })
            
        return result
    
    @retry_on_connection_error()
    async def execute(self, query: str, *args) -> str:
        """
        Executes a query with automatic retry on transient failures.
        
        Args:
            query: SQL query string (use $1, $2 for params)
            *args: Query parameters
            
        Returns:
            Status string (e.g., 'INSERT 0 1')
        """
        async with self.acquire() as conn:
            return await conn.execute(query, *args)
    
    @retry_on_connection_error()
    async def fetch_one(self, query: str, *args) -> Optional[asyncpg.Record]:
        """
        Fetches a single row with automatic retry.
        
        Args:
            query: SQL query string
            *args: Query parameters
            
        Returns:
            Record or None if not found
        """
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    @retry_on_connection_error()
    async def fetch_all(self, query: str, *args) -> List[asyncpg.Record]:
        """
        Fetches all rows with automatic retry.
        
        Args:
            query: SQL query string
            *args: Query parameters
            
        Returns:
            List of Records
        """
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)
    
    @retry_on_connection_error()
    async def fetch_val(self, query: str, *args, column: int = 0):
        """
        Fetches a single value.
        
        Args:
            query: SQL query string
            *args: Query parameters
            column: Column index to return
            
        Returns:
            Single value or None
        """
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args, column=column)
    
    @retry_on_connection_error()
    async def execute_many(self, query: str, args_list: List[tuple]) -> None:
        """
        Execute a query with multiple parameter sets.
        
        Args:
            query: SQL query string
            args_list: List of parameter tuples
        """
        async with self.acquire() as conn:
            await conn.executemany(query, args_list)


# Convenience function for record to dict conversion
def record_to_dict(record: asyncpg.Record) -> Dict[str, Any]:
    """Convert asyncpg Record to dict."""
    if record is None:
        return None
    return dict(record)


def records_to_dicts(records: List[asyncpg.Record]) -> List[Dict[str, Any]]:
    """Convert list of asyncpg Records to list of dicts."""
    return [dict(r) for r in records]
