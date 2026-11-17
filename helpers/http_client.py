"""Shared HTTP layer: one client factory and one retry policy for every source.

Before this module each client built its own ``httpx.AsyncClient`` with its
own timeout (25, 30 or 120 s) and only SERCOP handled HTTP 429. This keeps
that SERCOP behaviour, now available to any client
(docs/MCP_ARCHITECTURE.md § Fase 7):

- ``new_client`` sets the User-Agent, the geo proxy for geo-blocked hosts,
  redirects and a timeout chosen by profile instead of a per-file literal.
- ``get_with_retry`` retries transport errors and 429/5xx with backoff,
  honours ``Retry-After`` (capped), and after repeated 429s puts the host in
  a cooldown so later calls fail fast instead of hammering a source that
  already asked us to slow down.

Clients move onto it one at a time; TLS fallbacks stay where they are
(helpers/tls.py), since they differ per host.
"""

from __future__ import annotations

import asyncio
import logging
import time
from email.utils import parsedate_to_datetime
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from helpers.geo_proxy import proxy_for
from helpers.user_agent import USER_AGENT

logger = logging.getLogger("ecuador_mcp")

Profile = Literal["rapido", "normal", "lento"]

# rapido: small JSON APIs. normal: HTML pages and catalogs. lento: large
# files and slow government portals (bulk downloads, report servers).
TIMEOUTS: dict[str, float] = {"rapido": 15.0, "normal": 30.0, "lento": 120.0}

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_WAIT = 20.0

# host -> monotonic time the cooldown ends
_cooldowns: dict[str, float] = {}


class RateLimitedError(RuntimeError):
    """A host kept answering 429, or is still in its cooldown."""

    def __init__(self, host: str, seconds_left: float) -> None:
        super().__init__(f"{host} limitó las consultas (HTTP 429); reintenta en ~{seconds_left:.0f} s")
        self.host = host
        self.seconds_left = seconds_left


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def cooldown_remaining(host: str) -> float:
    return max(0.0, _cooldowns.get(host, 0.0) - time.monotonic())


def trip_cooldown(host: str, seconds: float) -> None:
    _cooldowns[host] = max(_cooldowns.get(host, 0.0), time.monotonic() + seconds)
    logger.warning("Cooldown for %s: %.0f s after repeated HTTP 429", host, seconds)


def reset_cooldowns() -> None:
    _cooldowns.clear()


def retry_wait(response: httpx.Response, attempt: int) -> float:
    """Seconds to wait before the next attempt, from Retry-After when given.

    Retry-After can be seconds or an HTTP date. Without it the wait grows
    with the attempt. Always between 1 s and MAX_RETRY_WAIT, so a source
    asking for an hour does not hang a tool call.
    """
    default = 2.0 * (attempt + 1)
    raw = response.headers.get("Retry-After")
    wait = default
    if raw:
        try:
            wait = float(raw)
        except ValueError:
            try:
                wait = parsedate_to_datetime(raw).timestamp() - time.time()
            except (TypeError, ValueError):
                wait = default
    return min(max(wait, 1.0), MAX_RETRY_WAIT)


def new_client(
    url: str,
    *,
    profile: Profile = "normal",
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """An AsyncClient for ``url``'s host with the project defaults."""
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, **(headers or {})},
        timeout=TIMEOUTS[profile],
        follow_redirects=True,
        proxy=proxy_for(url),
        **kwargs,
    )


async def get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    attempts: int = 3,
    cooldown_seconds: float = 45.0,
    **kwargs: Any,
) -> httpx.Response:
    """GET with the shared retry policy; the caller checks the status.

    Transport errors are retried and re-raised after the last attempt. A
    retryable status on the last attempt is returned as is (5xx) or, for
    429, trips the host's cooldown and raises RateLimitedError.
    """
    host = _host(url)
    left = cooldown_remaining(host)
    if left:
        raise RateLimitedError(host, left)
    for attempt in range(attempts):
        last = attempt + 1 >= attempts
        try:
            response = await client.get(url, params=params, **kwargs)
        except httpx.TransportError:
            if last:
                raise
            await asyncio.sleep(1.0 * (attempt + 1))
            continue
        if response.status_code not in RETRY_STATUSES:
            return response
        if not last:
            wait = retry_wait(response, attempt)
            logger.warning("%s answered %s; retrying in %.1f s", host, response.status_code, wait)
            await asyncio.sleep(wait)
            continue
        if response.status_code == 429:
            trip_cooldown(host, cooldown_seconds)
            raise RateLimitedError(host, cooldown_seconds)
        return response
    raise AssertionError("unreachable: attempts must be >= 1")
