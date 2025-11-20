# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

import logging
import sys
from typing import Optional, Any


class StructuredLogger:
    """
    Wrapper around standard logger to support structured logging.
    
    Allows passing key-value pairs as kwargs for better observability.
    """
    
    def __init__(self, logger: logging.Logger):
        self._logger = logger
    
    def _format_message(self, msg: str, **kwargs) -> str:
        """Format message with structured data."""
        if kwargs:
            extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
            return f"{msg} [{extra}]"
        return msg
    
    def debug(self, msg: str, **kwargs):
        """Log debug message with structured data."""
        self._logger.debug(self._format_message(msg, **kwargs))
    
    def info(self, msg: str, **kwargs):
        """Log info message with structured data."""
        self._logger.info(self._format_message(msg, **kwargs))
    
    def warning(self, msg: str, **kwargs):
        """Log warning message with structured data."""
        self._logger.warning(self._format_message(msg, **kwargs))
    
    def error(self, msg: str, **kwargs):
        """Log error message with structured data."""
        self._logger.error(self._format_message(msg, **kwargs))
    
    def critical(self, msg: str, **kwargs):
        """Log critical message with structured data."""
        self._logger.critical(self._format_message(msg, **kwargs))


def get_logger(name: str, level: Optional[int] = None) -> StructuredLogger:
    """
    Get a configured structured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        level: Optional logging level override
        
    Returns:
        Configured structured logger instance
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    if level is not None:
        logger.setLevel(level)
    elif not logger.level:
        logger.setLevel(logging.WARNING)  # Reduce noise for tests
    
    return StructuredLogger(logger)
