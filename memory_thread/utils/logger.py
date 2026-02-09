"""
Structured Logging for Memory Thread.

Provides JSON-formatted logs with context binding for observability.
Supports both structlog and stdlib logging for compatibility.

Usage:
    from memory_thread.utils.logger import get_logger
    
    log = get_logger(__name__)
    log.info("Processing memory", memory_id=uuid, namespace="default")
"""
import logging
import sys
import os
from typing import Any, Dict, Optional
from contextvars import ContextVar
from datetime import datetime

# Try to use structlog if available, fallback to json logger
try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False

from pythonjsonlogger import jsonlogger

# Context variables for request-scoped data
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_namespace: ContextVar[Optional[str]] = ContextVar("namespace", default=None)
_user_id: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


def set_context(
    request_id: Optional[str] = None,
    namespace: Optional[str] = None,
    user_id: Optional[str] = None
):
    """Set context variables for current request/operation."""
    if request_id:
        _request_id.set(request_id)
    if namespace:
        _namespace.set(namespace)
    if user_id:
        _user_id.set(user_id)


def clear_context():
    """Clear all context variables."""
    _request_id.set(None)
    _namespace.set(None)
    _user_id.set(None)


class ContextAwareFormatter(jsonlogger.JsonFormatter):
    """JSON formatter that includes context variables."""
    
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]):
        super().add_fields(log_record, record, message_dict)
        
        # Add context vars if present
        if _request_id.get():
            log_record["request_id"] = _request_id.get()
        if _namespace.get():
            log_record["namespace"] = _namespace.get()
        if _user_id.get():
            log_record["user_id"] = _user_id.get()
        
        # Add service metadata
        log_record["service"] = "memory-thread"
        log_record["timestamp"] = datetime.utcnow().isoformat() + "Z"


def _configure_structlog():
    """Configure structlog with appropriate processors."""
    if not STRUCTLOG_AVAILABLE:
        return
    
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True
    )


# Configure on module load
_configured = False


def get_logger(name: str, use_structlog: bool = False):
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        use_structlog: If True and available, return structlog logger
        
    Returns:
        Configured logger with JSON formatting and context awareness
    """
    global _configured
    
    if use_structlog and STRUCTLOG_AVAILABLE:
        if not _configured:
            _configure_structlog()
            _configured = True
        return structlog.get_logger(name)
    
    # Standard library logger with JSON formatting
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = ContextAwareFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    # Set level from env var or default
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.propagate = False
    
    return logger


# Convenience function for operation logging
def log_operation(
    logger,
    operation: str,
    status: str,
    duration_ms: Optional[float] = None,
    **kwargs
):
    """
    Log an operation with standardized fields.
    
    Args:
        logger: Logger instance
        operation: Operation name (e.g., "remember", "recall")
        status: Status (e.g., "started", "completed", "failed")
        duration_ms: Optional duration in milliseconds
        **kwargs: Additional context
    """
    extra = {
        "operation": operation,
        "status": status,
    }
    if duration_ms is not None:
        extra["duration_ms"] = round(duration_ms, 2)
    extra.update(kwargs)
    
    if status == "failed":
        logger.error(f"{operation} {status}", extra=extra)
    else:
        logger.info(f"{operation} {status}", extra=extra)

