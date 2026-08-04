"""Client for SERCOP Open Contracting (OCDS) public API."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from helpers import env_config
from helpers.cache import TtlCache, sercop_search_cache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_TIMEOUT = 30.0
_MAX_RETRIES = 4
_COOLDOWN_UNTIL = 0.0
_negative_cache = TtlCache(ttl_seconds=90.0, max_entries=64)


class SercopRateLimitError(RuntimeError):
    """Raised when SERCOP keeps returning HTTP 429 after retries."""


def _sercop_url(path: str) -> str:
    return f"{env_config.get_base_url('sercop')}{path.lstrip('/')}"


def _in_cooldown() -> bool:
    return time.monotonic() < _COOLDOWN_UNTIL


def _trip_cooldown(seconds: float = 45.0) -> None:
    global _COOLDOWN_UNTIL
    _COOLDOWN_UNTIL = max(_COOLDOWN_UNTIL, time.monotonic() + seconds)
    logger.warning("SERCOP cooldown active for %.0fs", seconds)


async def _get_json(
    url: str,
    params: dict[str, Any] | None = None,
    session: httpx.AsyncClient | None = None,
) -> Any:
    if _in_cooldown():
        raise SercopRateLimitError(
            "SERCOP en cooldown tras rate-limit (429). Reintenta en ~1 minuto."
        )

    own = session is None
    if own:
        session = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )
    assert session is not None
    try:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                logger.debug("SERCOP GET %s params=%s", url, params)
                resp = await session.get(url, params=params, timeout=_TIMEOUT)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    try:
                        wait = float(retry_after) if retry_after else 2.0 * (attempt + 1)
                    except ValueError:
                        wait = 2.0 * (attempt + 1)
                    wait = min(max(wait, 1.0), 20.0)
                    logger.warning(
                        "SERCOP rate limited (429); retrying in %.1fs", wait
                    )
                    await asyncio.sleep(wait)
                    last_exc = httpx.HTTPStatusError(
                        "SERCOP rate limited",
                        request=resp.request,
                        response=resp,
                    )
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt + 1 < _MAX_RETRIES:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                logger.error("SERCOP request failed for %s: %s", url, exc)
                raise
        _trip_cooldown(45.0)
        if (
            isinstance(last_exc, httpx.HTTPStatusError)
            and last_exc.response is not None
            and last_exc.response.status_code == 429
        ):
            raise SercopRateLimitError(
                "SERCOP rate limited (429) tras varios reintentos. "
                "Espera ~1 minuto o usa un year/query distinto."
            ) from last_exc
        if last_exc:
            raise last_exc
        raise SercopRateLimitError("SERCOP rate limited (429)")
    finally:
        if own:
            await session.aclose()


async def search_contracts(
    search: str,
    year: int | None = None,
    page: int = 1,
    buyer: str = "",
    supplier: str = "",
    fallback_years: int = 0,
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """
    Search OCDS contracting procedures.

    Required by API: year + search (>= 3 chars).
    If fallback_years > 0 and the chosen year returns empty data, try previous
    years (useful early in a calendar year or when a topic is sparse).
    """
    search = (search or "").strip()
    if len(search) < 3:
        raise ValueError("search debe tener al menos 3 caracteres")

    start_year = year or datetime.now(UTC).year
    years = [start_year]
    if fallback_years > 0:
        years.extend(start_year - i for i in range(1, fallback_years + 1))

    cache_key = (
        "search",
        search.lower(),
        start_year,
        max(page, 1),
        buyer.strip().lower(),
        supplier.strip().lower(),
        fallback_years,
    )
    cached = sercop_search_cache.get(cache_key)
    if isinstance(cached, dict):
        return cached
    neg = _negative_cache.get(cache_key)
    if neg is True:
        raise SercopRateLimitError(
            "SERCOP rate limited recientemente para esta consulta. Reintenta pronto."
        )

    last: dict[str, Any] = {"total": 0, "page": page, "pages": 0, "data": []}
    try:
        for y in years:
            if y < 2015:
                continue
            params: dict[str, Any] = {
                "year": y,
                "search": search,
                "page": max(page, 1),
            }
            if buyer.strip():
                params["buyer"] = buyer.strip()
            if supplier.strip():
                params["supplier"] = supplier.strip()

            result = await _get_json(
                _sercop_url("search_ocds"), params=params, session=session
            )
            if not isinstance(result, dict):
                continue
            last = result
            last["_resolved_year"] = y
            if result.get("data"):
                sercop_search_cache.set(cache_key, last)
                return last
    except SercopRateLimitError:
        _negative_cache.set(cache_key, True)
        raise

    sercop_search_cache.set(cache_key, last)
    return last


async def get_contract_record(
    ocid: str, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Fetch full OCDS record package for a procedure OCID."""
    ocid = (ocid or "").strip()
    if not ocid:
        raise ValueError("ocid es obligatorio")
    cache_key = ("record", ocid)
    cached = sercop_search_cache.get(cache_key)
    if isinstance(cached, dict):
        return cached
    result = await _get_json(
        _sercop_url("record"), params={"ocid": ocid}, session=session
    )
    if isinstance(result, dict):
        sercop_search_cache.set(cache_key, result)
        return result
    return {}
