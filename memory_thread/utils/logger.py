"""
Structured Logging for Memory Thread.

Provides JSON-formatted logs with context binding for observability.
Supports both structlog and stdlib logging for compatibility.

By default, logs to 'memory_thread.log' to keep the terminal clean.
Console output is restricted to warnings/errors unless MT_DEBUG is set.
"""
import logging
import sys
import os
from typing import Any, Dict, Optional
from contextvars import ContextVar
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Try to use structlog if available, fallback to json logger
try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False

try:
    from pythonjsonlogger import jsonlogger
except ImportError:
    jsonlogger = None

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


class ContextAwareFormatter(jsonlogger.JsonFormatter if jsonlogger else logging.Formatter):
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


def get_logger(name: str):
    """
    Get a configured logger instance.
    
    Logs to 'memory_thread.log' (JSON) and Console (Human-readable WARNING+).
    """
    logger = logging.getLogger(name)
    
    # If already configured, return it
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # 1. File Handler (JSON, Debug info) - Always active
    file_handler = RotatingFileHandler("memory_thread.log", maxBytes=5*1024*1024, backupCount=3)
    file_handler.setLevel(logging.INFO)
    
    if jsonlogger:
        formatter = ContextAwareFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s"
        )
        file_handler.setFormatter(formatter)
    else:
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
    
    logger.addHandler(file_handler)

    # 2. Console Handler (Human-readable, Warnings only) - For user visibility
    # If MT_DEBUG is set, show INFO logs to console too
    console_level = logging.INFO if os.environ.get("MT_DEBUG") else logging.WARNING

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(
        "[%(levelname)s] %(message)s"  # Simple format for terminal
    ))

    logger.addHandler(console_handler)
    
    # Silence noisy libraries unless debugging
    if not os.environ.get("MT_DEBUG"):
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    return logger


def log_operation(
    logger,
    operation: str,
    status: str,
    duration_ms: Optional[float] = None,
    **kwargs
):
    """
    Log an operation with standardized fields.
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
