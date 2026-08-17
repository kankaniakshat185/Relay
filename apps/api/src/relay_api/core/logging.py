"""Structured (JSON) logging setup.

Plain `print`/bare `logging` calls are not used elsewhere in the app —
everything goes through a logger configured here, so log lines are
searchable/filterable in Render's log viewer and carry consistent fields.
"""

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from relay_api.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO if settings.is_production else logging.DEBUG)

    # Quiet down noisy third-party loggers unless something's actually wrong.
    for noisy in ("uvicorn.access", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
