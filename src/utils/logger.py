"""Standardized structured logging configuration for geospatial ETL."""

import logging
import sys
from typing import Optional
from src.utils.config import settings


def setup_logger(name: Optional[str] = None) -> logging.Logger:
    """Configures and returns a thread-safe structured logger with timestamp,

    level, module name, and message format.
    """
    logger = logging.getLogger(name or "geospatial_pipeline")
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(log_level)

    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | [%(name)s:%(filename)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    logger.propagate = False
    return logger


logger = setup_logger()
