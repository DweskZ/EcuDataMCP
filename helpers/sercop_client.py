"""Client for SERCOP Open Contracting (OCDS) public API."""

from __future__ import annotations

import asyncio
import logging
import time
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
_SUMMARY_CONCURRENCY = 2
# Request budget as a multiple of the page count: the source samples rows at
# random per request, so completing needs several passes.
_SUMMARY_SWEEPS = 6
# Wall-clock cap so a rate-limited source cannot hold a tool call for minutes.
_SUMMARY_DEADLINE_SECONDS = 150.0
# Distinct rows already collected for a (buyer, search, year, total): a repeat
# call resumes from them, so successive runs converge on the same full set.
_summary_rows_cache = TtlCache(ttl_seconds=900.0, max_entries=32)
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


def _row_key(row: dict[str, Any]) -> str:
    """Identity of a search row: the OCID, else the numeric process id."""
    return str(row.get("ocid") or row.get("id") or "")


def _stable_rows(by_key: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Unique rows in a fixed order, so the sums never depend on arrival order."""
    return [by_key[k] for k in sorted(by_key)]


async def summarize_buyer(
    buyer: str,
    year: int,
    query: str = "",
    max_pages: int = SUMMARY_MAX_PAGES,
    max_requests: int | None = None,
) -> dict[str, Any]:
    """Collect one buyer's search_ocds rows and summarize them.

    The API needs a search keyword of at least 3 characters; the buyer
    keyword doubles as it unless ``query`` narrows the topic. ``buyer`` is a
    keyword, so several institutions can match: each is summarized on its own.

    search_ocds has no stable ordering: the same ``page`` returns a different
    set of rows on each call (``sort``/``order`` are ignored), so one pass
    over pages 1..N repeats some processes and misses others while the row
    count still equals ``total``. The pages are therefore swept repeatedly
    (uncached) and the rows de-duplicated by OCID until every distinct
    process has been seen or the request budget runs out. Rows are summed in
    OCID order. The result is ``parcial`` unless as many distinct processes
    as the source reports were collected.
    """
    buyer = (buyer or "").strip()
    if len(buyer) < 3:
        raise ValueError("comprador debe tener al menos 3 caracteres")
    search = (query or "").strip() or buyer
    budget = max_requests if max_requests is not None else max_pages * _SUMMARY_SWEEPS

    by_key: dict[str, dict[str, Any]] = {}
    failed: set[int] = set()
    requests_made = 0
    stop_reason = ""
    deadline = time.monotonic() + _SUMMARY_DEADLINE_SECONDS
    semaphore = asyncio.Semaphore(_SUMMARY_CONCURRENCY)

    def absorb(result: dict[str, Any]) -> None:
        for row in result.get("data") or []:
            if isinstance(row, dict):
                key = _row_key(row)
                if key:
                    by_key.setdefault(key, row)

    session = new_client(_sercop_url("search_ocds"), headers={"Accept": "application/json"})
    try:

        async def fetch(page: int) -> dict[str, Any]:
            return await _get_json(
                _sercop_url("search_ocds"),
                params={"year": year, "search": search, "page": page, "buyer": buyer},
                session=session,
            )

        first = await fetch(1)
        requests_made = 1
        if not isinstance(first, dict):
            first = {}
        total = int(first.get("total") or 0)
        pages = int(first.get("pages") or 0)
        absorb(first)
        memo_key = (search.lower(), year, buyer.lower(), total)
        remembered = _summary_rows_cache.get(memo_key)
        if isinstance(remembered, dict):
            for key, row in remembered.items():
                by_key.setdefault(key, row)
        to_read = min(pages, max_pages)
        # Past the page cap the summary is partial by design; never collect
        # more than the cap so the output size stays bounded.
        goal = min(total, to_read * 10) if pages else 0

        async def fetch_guarded(page: int) -> None:
            nonlocal requests_made, stop_reason
            def exhausted() -> bool:
                return bool(stop_reason) or requests_made >= budget or time.monotonic() > deadline

            if exhausted():
                return
            async with semaphore:
                if exhausted():
                    return
                requests_made += 1
                try:
                    absorb(await fetch(page))
                except SercopRateLimitError as exc:
                    # The host is cooling down; hammering it only extends the block.
                    logger.warning("SERCOP resumen: página %d limitada: %s", page, exc)
                    failed.add(page)
                    stop_reason = "rate_limited"
                except Exception as exc:  # one bad page must not sink the summary
                    logger.warning("SERCOP resumen: página %d falló: %s", page, exc)
                    failed.add(page)

        sweep = 0
        while len(by_key) < goal and requests_made < budget and not stop_reason:
            if time.monotonic() > deadline:
                break
            # Sweep 0 reads pages 2..N once; later sweeps re-draw every page,
            # since a page is a random sample of the not-yet-seen rows too.
            first_page = 2 if sweep == 0 else 1
            before = len(by_key)
            await asyncio.gather(*(fetch_guarded(p) for p in range(first_page, to_read + 1)))
            sweep += 1
            if sweep > 1 and len(by_key) == before and failed:
                break
    finally:
        await session.aclose()

    if by_key:
        _summary_rows_cache.set(memo_key, dict(by_key))
    rows = _stable_rows(by_key)
    compradores = summarize_rows(rows)
    complete = len(rows) >= total and not (pages > max_pages)
    return {
        "comprador": buyer,
        "query": search,
        "year": year,
        "total_en_fuente": total,
        "procesos_leidos": len(rows),
        "parcial": not complete,
        "paginas_fallidas": sorted(failed),
        "solicitudes": requests_made,
        "monto_total": round(sum(c["monto_total"] for c in compradores), 2),
        "procesos_con_monto": sum(c["procesos_con_monto"] for c in compradores),
        "compradores": compradores[:_SUMMARY_TOP_BUYERS],
        "otros_compradores": max(len(compradores) - _SUMMARY_TOP_BUYERS, 0),
    }
