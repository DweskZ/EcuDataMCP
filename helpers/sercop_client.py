"""Client for SERCOP Open Contracting (OCDS) public API."""

from __future__ import annotations

import asyncio
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


# -- per-buyer summary ----------------------------------------------------------

# search_ocds returns 10 rows a page. 30 pages (300 processes) keeps one
# summary to a few seconds and well under SERCOP's rate limit; past it the
# summary says it is partial.
SUMMARY_MAX_PAGES = 30
_SUMMARY_CONCURRENCY = 3
_SUMMARY_TOP_BUYERS = 10
_SUMMARY_TOP_SUPPLIERS = 10


def _money(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _month(row: dict[str, Any]) -> int | None:
    month = row.get("month")
    if isinstance(month, int) and 1 <= month <= 12:
        return month
    date = str(row.get("date") or "")
    if len(date) >= 7 and date[5:7].isdigit():
        value = int(date[5:7])
        return value if 1 <= value <= 12 else None
    return None


def _ranked(groups: dict[str, dict[str, Any]], top: int, label: str) -> list[dict[str, Any]]:
    rows = [
        {label: name, "procesos": g["procesos"], "monto": round(g["monto"], 2)}
        for name, g in groups.items()
    ]
    rows.sort(key=lambda r: (-r["monto"], -r["procesos"], r[label]))
    return rows[:top]


def summarize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group search_ocds rows by exact buyer name and total them.

    ``amount`` (awarded or estimated value) is summed into ``monto_total`` and
    ``budget`` into ``presupuesto_total``; a process without an amount is
    counted but adds nothing, and ``procesos_con_monto`` says how many did.
    Buyers come back sorted by ``monto_total``.
    """
    buyers: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row.get("buyer") or "").strip() or "(sin comprador)"
        b = buyers.setdefault(
            name,
            {
                "comprador": name,
                "procesos": 0,
                "procesos_con_monto": 0,
                "monto_total": 0.0,
                "presupuesto_total": 0.0,
                "_tipos": {},
                "_meses": {},
                "_proveedores": {},
                "_fechas": [],
            },
        )
        amount = _money(row.get("amount"))
        budget = _money(row.get("budget"))
        b["procesos"] += 1
        if amount is not None:
            b["procesos_con_monto"] += 1
            b["monto_total"] += amount
        if budget is not None:
            b["presupuesto_total"] += budget
        for key, value in (
            ("_tipos", row.get("internal_type") or row.get("method") or "(sin tipo)"),
            ("_meses", _month(row)),
            ("_proveedores", row.get("suppliers")),
        ):
            if value in (None, ""):
                continue
            group = b[key].setdefault(value, {"procesos": 0, "monto": 0.0})
            group["procesos"] += 1
            group["monto"] += amount or 0.0
        if row.get("date"):
            b["_fechas"].append(str(row["date"])[:10])

    result = []
    for b in buyers.values():
        fechas = sorted(b.pop("_fechas"))
        meses = b.pop("_meses")
        result.append(
            {
                **{k: v for k, v in b.items() if not k.startswith("_")},
                "monto_total": round(b["monto_total"], 2),
                "presupuesto_total": round(b["presupuesto_total"], 2),
                "por_tipo": _ranked(b.pop("_tipos"), 20, "tipo"),
                "por_mes": [
                    {"mes": m, "procesos": g["procesos"], "monto": round(g["monto"], 2)}
                    for m, g in sorted(meses.items())
                ],
                "proveedores": _ranked(b.pop("_proveedores"), _SUMMARY_TOP_SUPPLIERS, "proveedor"),
                "primera_fecha": fechas[0] if fechas else None,
                "ultima_fecha": fechas[-1] if fechas else None,
            }
        )
    result.sort(key=lambda r: (-r["monto_total"], -r["procesos"], r["comprador"]))
    return result


async def summarize_buyer(
    buyer: str,
    year: int,
    query: str = "",
    max_pages: int = SUMMARY_MAX_PAGES,
) -> dict[str, Any]:
    """Page through search_ocds for one buyer keyword and summarize it.

    The API needs a search keyword of at least 3 characters; the buyer
    keyword doubles as it unless ``query`` narrows the topic. ``buyer`` is a
    keyword, so several institutions can match: each is summarized on its own.
    """
    buyer = (buyer or "").strip()
    if len(buyer) < 3:
        raise ValueError("comprador debe tener al menos 3 caracteres")
    search = (query or "").strip() or buyer

    first = await search_contracts(search=search, year=year, page=1, buyer=buyer)
    total = int(first.get("total") or 0)
    pages = int(first.get("pages") or 0)
    rows: list[dict[str, Any]] = list(first.get("data") or [])
    to_read = min(pages, max_pages)

    failed: list[int] = []
    semaphore = asyncio.Semaphore(_SUMMARY_CONCURRENCY)

    async def fetch(page: int) -> list[dict[str, Any]]:
        async with semaphore:
            try:
                result = await search_contracts(search=search, year=year, page=page, buyer=buyer)
            except Exception as exc:  # one bad page must not sink the summary
                logger.warning("SERCOP resumen: página %d falló: %s", page, exc)
                failed.append(page)
                return []
            return list(result.get("data") or [])

    for chunk in await asyncio.gather(*(fetch(p) for p in range(2, to_read + 1))):
        rows.extend(chunk)

    compradores = summarize_rows(rows)
    return {
        "comprador": buyer,
        "query": search,
        "year": year,
        "total_en_fuente": total,
        "procesos_leidos": len(rows),
        "parcial": len(rows) < total,
        "paginas_fallidas": sorted(failed),
        "monto_total": round(sum(c["monto_total"] for c in compradores), 2),
        "procesos_con_monto": sum(c["procesos_con_monto"] for c in compradores),
        "compradores": compradores[:_SUMMARY_TOP_BUYERS],
        "otros_compradores": max(len(compradores) - _SUMMARY_TOP_BUYERS, 0),
    }
