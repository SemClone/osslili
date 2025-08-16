"""
Logging utilities for semantic-copycat-oslili.
"""

import logging
import sys
from typing import Optional


def setup_logging(level: int = logging.INFO, log_file: Optional[str] = None):
    """
    Configure logging for the application.
    
    Args:
        level: Logging level
        log_file: Optional log file path
    """
    # Create formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Setup console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    
    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)
    
    # Set levels for specific loggers to reduce noise
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    logging.getLogger('requests').setLevel(logging.ERROR)
    
    # Control our package's logging based on level
    if level > logging.INFO:
        # In normal mode (ERROR level), suppress all but errors
        logging.getLogger('semantic_copycat_oslili').setLevel(logging.ERROR)
    else:
        # In verbose/debug mode, use the specified level
        logging.getLogger('semantic_copycat_oslili').setLevel(level)