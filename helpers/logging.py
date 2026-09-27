import inspect
import logging
import os
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from helpers import usage

MAIN_LOGGER_NAME = "ecuador_mcp"

logger = logging.getLogger(MAIN_LOGGER_NAME)


def setup_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.setLevel(level)


UVICORN_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s | uvicorn | %(levelname)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
    },
}


# Full docstring of every tool, by name. Tools advertise a short
# `description=` in tools/list (it's paid for in every conversation's
# context); the full reference is served on demand by the
# ecuador://herramientas/{nombre} resource from this registry.
TOOL_DOCS: dict[str, str] = {}


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def log_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to log MCP tool invocations and record their usage."""
    TOOL_DOCS[func.__name__] = inspect.cleandoc(func.__doc__ or "")

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        tool_name = func.__name__
        logger.info("Tool called: %s | params: %s", tool_name, kwargs or args)
        started = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
        except Exception:
            usage.record(tool_name, ok=False, duration_ms=_elapsed_ms(started))
            logger.exception("Tool %s failed", tool_name)
            raise
        usage.record(tool_name, ok=True, duration_ms=_elapsed_ms(started))
        logger.debug("Tool %s completed successfully", tool_name)
        return result

    return wrapper
