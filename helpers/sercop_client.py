"""Client for SERCOP Open Contracting (OCDS) public API."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from helpers import env_config
from helpers.cache import TtlCache, sercop_search_cache
from helpers.ecuador_time import ECUADOR_TZ
from helpers.http_client import RateLimitedError, get_with_retry, new_client
from helpers.logging import MAIN_LOGGER_NAME

# Ecuador mainland is UTC-5 year-round (no DST); UTC would flip the default
# year at 19:00 local time on 31 Dec.
_ECUADOR_TZ = ECUADOR_TZ

logger = logging.getLogger(MAIN_LOGGER_NAME)

_MAX_RETRIES = 4
_negative_cache = TtlCache(ttl_seconds=90.0, max_entries=64)


class SercopRateLimitError(RateLimitedError):
    """Raised when SERCOP keeps returning HTTP 429 after retries."""

    def __init__(self, message: str, seconds_left: float = 0.0) -> None:
        RuntimeError.__init__(self, message)
        self.host = "datosabiertos.compraspublicas.gob.ec"
        self.seconds_left = seconds_left


def _sercop_url(path: str) -> str:
    return f"{env_config.get_base_url('sercop')}{path.lstrip('/')}"


async def _get_json(
    url: str,
    params: dict[str, Any] | None = None,
    session: httpx.AsyncClient | None = None,
) -> Any:
    own = session is None
    if own:
        session = new_client(url, headers={"Accept": "application/json"})
    assert session is not None
    try:
        logger.debug("SERCOP GET %s params=%s", url, params)
        try:
            resp = await get_with_retry(session, url, params=params, attempts=_MAX_RETRIES)
        except RateLimitedError as exc:
            raise SercopRateLimitError(
                "SERCOP limitó las consultas (HTTP 429) tras varios reintentos. "
                f"Espera ~{exc.seconds_left:.0f} s o usa un year/query distinto.",
                exc.seconds_left,
            ) from exc
        except httpx.TransportError as exc:
            logger.error("SERCOP request failed for %s: %s", url, exc)
            # A bare ConnectError/ConnectTimeout stringifies to something
            # like "All connection attempts failed", naming no host.
            # compraspublicas.gob.ec has been observed dropping the TCP
            # handshake entirely for connections from outside Ecuador/Latin
            # America -- the same regional restriction datosabiertos.gob.ec
            # enforces with a 403 (see ckan_client._fetch_json).
            raise RuntimeError(
                "No se pudo conectar al portal de Datos Abiertos de "
                "Compras Públicas (compraspublicas.gob.ec). Esto suele "
                "pasar cuando el servidor se conecta desde fuera de "
                "Latinoamérica. Si el problema persiste, prueba "
                "conectando desde una VPN con salida en algún país de "
                "la región."
            ) from exc
        resp.raise_for_status()
        return resp.json()
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

    start_year = year or datetime.now(_ECUADOR_TZ).year
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
