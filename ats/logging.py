"""Structured logging setup. JSON in production, plain text by default."""

from __future__ import annotations

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

_CONFIGURED = False


def configure(level: str = "INFO", *, json_format: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stderr)
    if json_format:
        handler.setFormatter(
            JsonFormatter(
                "%(asctime)s %(name)s %(levelname)s %(message)s",
                rename_fields={"asctime": "ts", "levelname": "level"},
            )
        )
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        )
    root = logging.getLogger("ats")
    root.handlers = [handler]
    root.setLevel(level.upper())
    root.propagate = False
    _CONFIGURED = True
