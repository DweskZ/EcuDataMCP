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


def log_level() -> int:
    """The LOG_LEVEL env var as a stdlib level; INFO when unset or unknown."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    return logging.getLevelNamesMapping().get(level_name, logging.INFO)


def setup_logging() -> None:
    level = log_level()
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.setLevel(level)


# uvicorn validates its log_level against this set (no WARN/FATAL/NOTSET).
_UVICORN_LEVELS = frozenset({"critical", "error", "warning", "info", "debug"})


def uvicorn_log_level() -> str:
    """LOG_LEVEL in the lower-case spelling `uvicorn.run(log_level=)` accepts."""
    name = logging.getLevelName(log_level()).lower()
    return name if name in _UVICORN_LEVELS else "info"


def uvicorn_logging_config() -> dict[str, Any]:
    """dictConfig for uvicorn's loggers at the same level as LOG_LEVEL, so a
    quieter/louder setting also applies to the access log."""
    level = logging.getLevelName(log_level())
    return {
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
            "uvicorn": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.error": {"level": level},
            "uvicorn.access": {
                "handlers": ["default"],
                "level": level,
                "propagate": False,
            },
        },
    }


# Full docstring of every tool, by name. Tools advertise a short
# `description=` in tools/list (it's paid for in every conversation's
# context); the full reference is served on demand by the
# ecuador://herramientas/{nombre} resource from this registry.
TOOL_DOCS: dict[str, str] = {}


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


_SENSITIVE_KEYS = frozenset(
    {"identificacion", "ruc", "cedula", "query", "q", "token", "supplier", "buyer"}
)


def _redact(params: dict[str, Any]) -> dict[str, Any]:
    return {k: "***" if k.lower() in _SENSITIVE_KEYS else v for k, v in params.items()}


def log_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to log MCP tool invocations and record their usage."""
    TOOL_DOCS[func.__name__] = inspect.cleandoc(func.__doc__ or "")

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        tool_name = func.__name__
        # Argument values can be RUCs/cédulas (see helpers/usage.py): INFO
        # carries only the tool and argument names; values are DEBUG-only
        # and redacted for sensitive keys.
        logger.info("Tool called: %s | args: %s", tool_name, sorted(kwargs))
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Tool %s params: %s", tool_name, _redact(kwargs))
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
