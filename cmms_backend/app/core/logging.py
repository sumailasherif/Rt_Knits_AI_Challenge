"""
Structured JSON logging using structlog.
Call configure_logging() once from main.py at startup.

structlog 24.x API notes:
  - merge_contextvars  is structlog.contextvars.merge_contextvars
  - format_exc_info    was renamed / split — use ExceptionRenderer (structlog >= 21)
  - JSONRenderer       is the production renderer
  - ConsoleRenderer    is used in development for human-readable output
"""
from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Shared processor chain used in both dev and prod
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        # ExceptionRenderer replaces the deprecated format_exc_info
        structlog.processors.ExceptionRenderer(),
    ]

    if settings.app_env == "development":
        # Human-readable coloured output for local development
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # Machine-parseable JSON for production / Docker log aggregation
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # ── stdlib logging bridge (so uvicorn / SQLAlchemy logs flow through structlog) ──
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Silence noisy third-party loggers in production
    for noisy in ("httpx", "httpcore", "openai", "chromadb", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    """Convenience helper — returns a bound structlog logger."""
    return structlog.get_logger(name)
