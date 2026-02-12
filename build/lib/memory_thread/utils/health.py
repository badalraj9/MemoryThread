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
        self._qdrant = None
    
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
    def qdrant_client(self):
        """Lazy-load Qdrant client."""
        if self._qdrant is None:
            try:
                from memory_thread.db.qdrant_client import QdrantClientWrapper
                self._qdrant = QdrantClientWrapper()
            except Exception as e:
                log.error(f"Failed to initialize QdrantClient: {e}")
        return self._qdrant
    
    def check_postgres(self) -> Dict[str, Any]:
        """
        Check PostgreSQL connectivity and response time.
        
        Returns:
            Dict with status, latency_ms, and optional error
        """
        if self.postgres_client is None:
            return {
                "status": "unhealthy",
                "error": "PostgresClient not initialized"
            }
        return self.postgres_client.health_check()
    
    def check_qdrant(self) -> Dict[str, Any]:
        """
        Check Qdrant connectivity.
        
        Returns:
            Dict with status, latency_ms, and optional error
        """
        result = {
            "status": "unknown",
            "latency_ms": None,
            "error": None
        }
        
        if self.qdrant_client is None:
            result.update({
                "status": "unhealthy",
                "error": "QdrantClient not initialized"
            })
            return result
        
        try:
            start = time.perf_counter()
            # Get collections as a health check
            self.qdrant_client.client.get_collections()
            latency_ms = (time.perf_counter() - start) * 1000
            
            result.update({
                "status": "healthy",
                "latency_ms": round(latency_ms, 2)
            })
        except Exception as e:
            result.update({
                "status": "unhealthy",
                "error": str(e)
            })
            
        return result
    
    def full_check(self) -> Dict[str, Any]:
        """
        Perform full health check across all services.
        
        Returns:
            Dict with overall status and individual service statuses
        """
        postgres_status = self.check_postgres()
        qdrant_status = self.check_qdrant()
        
        # Overall status is healthy only if all services are healthy
        all_healthy = (
            postgres_status.get("status") == "healthy" and
            qdrant_status.get("status") == "healthy"
        )
        
        # Degraded if some services are down but not all
        any_healthy = (
            postgres_status.get("status") == "healthy" or
            qdrant_status.get("status") == "healthy"
        )
        
        if all_healthy:
            overall_status = "healthy"
        elif any_healthy:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"
        
        return {
            "status": overall_status,
            "version": "0.4.0",
            "services": {
                "postgres": postgres_status,
                "qdrant": qdrant_status
            }
        }


# Singleton instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get or create the singleton HealthChecker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker
