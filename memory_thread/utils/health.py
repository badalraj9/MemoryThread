"""
Health Check Utilities.

Centralized health checking for all MT services.
Provides status checks for Postgres, Qdrant, and other dependencies.
"""

from typing import Dict, Any, Optional
import time
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


class HealthChecker:
    """
    Centralized health checker for all MT services.

    Usage:
        checker = HealthChecker()
        status = checker.full_check()
    """

    def __init__(self):
        self._pg = None

    @property
    def postgres_client(self):
        """Lazy-load PostgresClient."""
        if self._pg is None:
            try:
                from memory_thread.db.postgres_client import PostgresClient

                self._pg = PostgresClient()
            except Exception as e:
                log.error(f"Failed to initialize PostgresClient: {e}")
        return self._pg

    @property
    def check_postgres(self) -> Dict[str, Any]:
        """
        Check PostgreSQL connectivity and response time.

        Returns:
            Dict with status, latency_ms, and optional error
        """
        if self.postgres_client is None:
            return {"status": "unhealthy", "error": "PostgresClient not initialized"}
        return self.postgres_client.health_check()

    def full_check(self) -> Dict[str, Any]:
        """
        Perform full health check across all services.

        Returns:
            Dict with overall status and individual service statuses
        """
        postgres_status = self.check_postgres

        if postgres_status.get("status") == "healthy":
            overall_status = "healthy"
        else:
            overall_status = "degraded"

        return {
            "status": overall_status,
            "version": "0.4.0",
            "services": {"postgres": postgres_status},
        }


# Singleton instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get or create the singleton HealthChecker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker
