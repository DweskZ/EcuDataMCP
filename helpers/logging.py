import logging
import os
from functools import wraps
from typing import Any, Callable

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


def log_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to log MCP tool invocations."""

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        tool_name = func.__name__
        logger.info("Tool called: %s | params: %s", tool_name, kwargs or args)
        try:
            result = await func(*args, **kwargs)
            logger.debug("Tool %s completed successfully", tool_name)
            return result
        except Exception:
            logger.exception("Tool %s failed", tool_name)
            raise

    return wrapper
