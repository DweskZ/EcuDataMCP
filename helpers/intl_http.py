"""Small JSON GET with retry for the international APIs (Comtrade, IMF, WHO,
ILO, UNHCR). Retries 429 and 5xx with backoff; a 429 body that says "try
again in N seconds" (Comtrade) is honoured. Errors are raised as
`SourceHTTPError` (a ValueError) with a Spanish message that names the
source and quotes the start of the body, so the tool reports something
actionable instead of a bare status code."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from helpers.logging import MAIN_LOGGER_NAME
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_TIMEOUT = httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=15.0)
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_MAX_WAIT_SECONDS = 15.0
_RETRY_IN = re.compile(r"in (\d+(?:\.\d+)?) second", re.IGNORECASE)


class SourceHTTPError(ValueError):
    def __init__(self, status: int, message: str, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _wait_seconds(resp: httpx.Response, attempt: int) -> float:
    # Only a 429 body is a rate-limit message; a 5xx page that happens to
    # contain "in N seconds" must not set the wait.
    match = _RETRY_IN.search(resp.text[:500]) if resp.status_code == 429 else None
    if match:
        return min(float(match.group(1)) + 1.0, _MAX_WAIT_SECONDS)
    header = resp.headers.get("Retry-After", "")
    if header.isdigit():
        return min(float(header), _MAX_WAIT_SECONDS)
    return min(2.0 * attempt, _MAX_WAIT_SECONDS)


async def get_json(
    url: str,
    *,
    fuente: str,
    params: dict[str, Any] | None = None,
    accept: str = "application/json",
    empty_statuses: frozenset[int] = frozenset({204}),
) -> Any | None:
    """GET `url` and parse JSON. Returns None for a status in
    `empty_statuses` (no data); raises SourceHTTPError otherwise."""
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    async with httpx.AsyncClient(
        headers=headers, timeout=_TIMEOUT, follow_redirects=True
    ) as session:
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            logger.info("%s GET %s params=%s", fuente, url, params)
            try:
                resp = await session.get(url, params=params)
            except httpx.TransportError as e:
                # Timeouts plus connect/DNS/read failures: retry, then report
                # them with the source's name instead of a raw httpx error.
                if attempt == _MAX_ATTEMPTS:
                    reason = (
                        "no respondió a tiempo"
                        if isinstance(e, httpx.TimeoutException)
                        else f"no se pudo conectar ({type(e).__name__})"
                    )
                    raise SourceHTTPError(0, f"{fuente} {reason}.") from e
                await _sleep(2.0 * attempt)
                continue
            if resp.status_code in empty_statuses:
                return None
            if resp.status_code in _RETRY_STATUSES and attempt < _MAX_ATTEMPTS:
                wait = _wait_seconds(resp, attempt)
                logger.warning("%s HTTP %s; reintento en %.1f s", fuente, resp.status_code, wait)
                await _sleep(wait)
                continue
            if resp.status_code >= 400:
                snippet = " ".join(resp.text[:300].split())
                hint = (
                    " (límite de tasa de la fuente; espera unos segundos y reintenta)"
                    if resp.status_code == 429
                    else ""
                )
                raise SourceHTTPError(
                    resp.status_code,
                    f"{fuente} respondió HTTP {resp.status_code}{hint}: {snippet}",
                    resp.text,
                )
            try:
                return resp.json()
            except ValueError as e:
                raise SourceHTTPError(
                    resp.status_code, f"{fuente} devolvió una respuesta que no es JSON."
                ) from e
    raise AssertionError("unreachable")
