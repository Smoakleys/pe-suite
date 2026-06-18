"""Logging configuration: rotating file handler at .logs/gantt_builder.log + stderr.

Always on. The .logs/ directory is created automatically on first call. Log file
rotates at 10 MB, last 5 files retained.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_configured = False


def configure_logging(level: int = logging.INFO, log_dir: Path | None = None) -> None:
    """Set up the root logger with a rotating file handler and a stderr stream handler.

    Idempotent — calling more than once is a no-op.
    """
    global _configured
    if _configured:
        return

    log_dir = log_dir or Path(".logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "gantt_builder.log"

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    root.addHandler(stream_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger, ensuring logging is configured first."""
    if not _configured:
        configure_logging()
    return logging.getLogger(name)
