"""
Rich Logging for Memory Thread.

Provides clean, colored console logging using rich.

Usage:
    from memory_thread.utils.logger import get_logger

    log = get_logger(__name__)
    log.info("Processing memory")
    log.warning("Memory low")
    log.error("Connection failed")
"""

import logging
import sys
import os
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

# Custom theme for rich
custom_theme = Theme(
    {
        "info": "green",
        "warning": "yellow",
        "error": "bold red",
        "debug": "dim white",
    }
)

# Global console instance
_console = Console(theme=custom_theme)

# Rich handler with custom formatting
_rich_handler = RichHandler(
    console=_console,
    show_time=False,
    show_path=False,
    show_level=False,
    markup=True,
    rich_tracebacks=True,
    tracebacks_show_locals=False,
)

# Configure format: level  module  message
_rich_handler.setFormatter(logging.Formatter("%(levelname)s  %(name)s  %(message)s"))


def get_logger(name: str):
    """
    Get a configured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger with Rich formatting
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.addHandler(_rich_handler)

    # Set level from env var or default
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.propagate = False

    return logger


# Convenience function for operation logging
def log_operation(
    logger, operation: str, status: str, duration_ms: Optional[float] = None, **kwargs
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
    msg = f"{operation} {status}"
    if duration_ms is not None:
        msg += f" ({duration_ms:.1f}ms)"
    if kwargs:
        msg += f" {kwargs}"

    if status == "failed":
        logger.error(msg)
    else:
        logger.info(msg)
