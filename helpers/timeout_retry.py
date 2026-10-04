"""Retry helper for slow government hosts that intermittently stall."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

from helpers.logging import MAIN_LOGGER_NAME

logger = logging.getLogger(MAIN_LOGGER_NAME)

T = TypeVar("T")

# Connect and read are split so a slow body (the SRI pages answer 200 and then
# stall mid-transfer) gets a long read budget without a long connect wait.
SLOW_HOST_TIMEOUT = httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=15.0)
_ATTEMPTS = 3
_BACKOFF_SECONDS = 2.0


async def retry_on_timeout(call: Callable[[], Awaitable[T]], label: str) -> T:
    """Await `call()`, retrying up to 3 times when the host times out."""
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            return await call()
        except httpx.TimeoutException:
            if attempt == _ATTEMPTS:
                raise
            logger.warning(
                "Timeout en %s (intento %d/%d); reintentando", label, attempt, _ATTEMPTS
            )
            await asyncio.sleep(_BACKOFF_SECONDS * attempt)
    raise AssertionError("unreachable")
