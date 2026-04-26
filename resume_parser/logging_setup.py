"""Single source of truth for logging configuration.

Importing `setup_logging()` once at app start gives every module a
namespaced logger that writes timestamped, level-coloured lines to stderr.
"""
from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False


class _ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",    # cyan
        "INFO": "\033[32m",     # green
        "WARNING": "\033[33m",  # yellow
        "ERROR": "\033[31m",    # red
        "CRITICAL": "\033[1;31m",
    }
    RESET = "\033[0m"

    def __init__(self, use_color: bool):
        super().__init__(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if not self.use_color:
            return msg
        color = self.COLORS.get(record.levelname, "")
        return f"{color}{msg}{self.RESET}" if color else msg


def setup_logging(level: str | int | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    resolved_level = level or os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_ColorFormatter(use_color=sys.stderr.isatty()))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved_level)

    # Quiet down chatty libraries.
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "pdfminer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
