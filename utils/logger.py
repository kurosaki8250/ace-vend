"""
Logger module for Project Aether
Provides structured logging for debugging and monitoring
"""

import logging
import sys
from datetime import datetime
from typing import Optional


def get_logger(
    name: str = "aether",
    level: int = logging.DEBUG,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Create and configure a logger instance.
    
    Args:
        name: Logger name
        level: Logging level (default: DEBUG)
        log_file: Optional file path to write logs
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Console handler with rich formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Optional file handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def log_request(logger: logging.Logger, model: str, prompt: str):
    """Log an LLM request being sent."""
    logger.debug(f"📤 SENDING REQUEST to {model}")
    logger.debug(f"Prompt length: {len(prompt)} characters")
    logger.debug(f"Prompt preview: {prompt[:200]}...")


def log_response(logger: logging.Logger, response: str, latency_ms: float):
    """Log an LLM response being received."""
    logger.debug(f"📥 RESPONSE RECEIVED ({latency_ms:.2f}ms)")
    logger.debug(f"Response length: {len(response)} characters")
    logger.debug(f"Response preview: {response[:200]}...")


def log_error(logger: logging.Logger, error: Exception, context: str = ""):
    """Log an error with context."""
    logger.error(f"❌ ERROR: {context}")
    logger.error(f"Exception type: {type(error).__name__}")
    logger.error(f"Exception message: {str(error)}")


# Default logger instance
default_logger = get_logger()
