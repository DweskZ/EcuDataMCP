"""Client for SERCOP Open Contracting (OCDS) public API."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from helpers import env_config
from helpers.logging import MAIN_LOGGER_NAME
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_TIMEOUT = 30.0
_MAX_RETRIES = 3


def _sercop_url(path: str) -> str:
    return f"{env_config.get_base_url('sercop')}{path.lstrip('/')}"


async def _get_json(
    url: str,
    params: dict[str, Any] | None = None,
    session: httpx.AsyncClient | None = None,
) -> Any:
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
                    wait = 1.5 * (attempt + 1)
                    logger.warning(
                        "SERCOP rate limited (429); retrying in %.1fs", wait
                    )
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt + 1 < _MAX_RETRIES:
                    await asyncio.sleep(0.8 * (attempt + 1))
                    continue
                logger.error("SERCOP request failed for %s: %s", url, exc)
                raise
        if last_exc:
            raise last_exc
        raise httpx.HTTPStatusError(
            "SERCOP rate limited",
            request=httpx.Request("GET", url),
            response=httpx.Response(429),
        )
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

    last: dict[str, Any] = {"total": 0, "page": page, "pages": 0, "data": []}
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
            return last
    return last


async def get_contract_record(
    ocid: str, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Fetch full OCDS record package for a procedure OCID."""
    ocid = (ocid or "").strip()
    if not ocid:
        raise ValueError("ocid es obligatorio")
    result = await _get_json(
        _sercop_url("record"), params={"ocid": ocid}, session=session
    )
    if isinstance(result, dict):
        return result
    return {}
