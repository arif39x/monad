from __future__ import annotations

import logging
from typing import Any
from pathlib import Path

try:
    import structlog
except ModuleNotFoundError:
    structlog = None

from orchestration.config import TelemetrySettings


def configure_logging(settings: TelemetrySettings) -> None:
    # Always log to a file to prevent polluting the TUI (stdout)
    log_file = Path("elyon.log")
    
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        filename=log_file,
        filemode="a",
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    if structlog is None:
        return

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    if settings.json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        # Use a wrapper that writes to a file instead of stdout
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    if structlog is None:
        return logging.getLogger(name)
    return structlog.get_logger(name)
