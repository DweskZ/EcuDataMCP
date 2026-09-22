"""Client recovering, via the Wayback Machine, the national outage-schedule
aggregator the Ministry of Energy and Mines briefly ran during the 2024
blackout crisis at `energia-ecuador.com` ("Portal para actualización de
racionamiento energético") — announced in a since-deleted ministry post
("Nuevo sitio web para revisar los horarios de cortes de energía") found
while re-investigating the historical blackout archive (see
docs/RESEARCH.md § Vigésimo séptima/octava pasada). The domain itself is
confirmed dead (DNS no longer resolves; a later Wayback capture from
2025-04-30 shows it repurposed as a parked-domain landing page).

**What this recovers, and why only one distributor:** the site was
WordPress + Elementor + TablePress, with one page per distributor —
confirmed live via the archived `wp-sitemap-posts-page-1.xml` (all nine
pages' `lastmod` cluster around 2024-04-23, the site's apparent launch
day): EEQ, Centrosur, CNEL, Emelnorte, EEASA (Ambato), Empresa Eléctrica
Azogues, Empresa Eléctrica Provincial Cotopaxi, Empresa Eléctrica Riobamba,
Empresa Eléctrica Regional del Sur (EERSSA). The Wayback Machine's crawler
only fully rendered **one** of those nine pages (Empresa Eléctrica Quito,
timestamp 2024-04-24 15:35:36) before the site went behind a Cloudflare
bot-challenge (`cdn-cgi/challenge-platform`) two to three days after
launch — every capture from 2024-04-26 onward, for the homepage and every
distributor subpage checked, is a `403`. No later capture exists (checked
through 2025-06); the ministry evidently took the whole aggregator down
after the crisis rather than just re-enabling Cloudflare's crawler
exception.

**The recovered table (EEQ, Pichincha, 40 rows)** covers one day's
province/canton/sector-level outage rotation (`PROVINCIA`, `CANTON`,
`SECTORES`, `PROGRAMACIÓN INICIO/FIN`, `REPROGRAMACIÓN INICIO/FIN`) —
the same granularity as EEQ's own PDF archive
(`helpers/centrosur_cortes_client.py`'s sibling for EEQ was never built;
see RESEARCH.md), but from an independent source with its own schema,
useful as a cross-check. It is a frozen historical snapshot of one
specific day (2024-04-24), not an ongoing series — there is no "next
page" to discover, unlike every other client in this project.

**A note on the accented characters:** the raw archived HTML looked
mangled in one earlier terminal inspection ("RUMI�AHUI"), which raised a
real concern about encoding corruption in the original scrape. Verified
against the raw bytes: the file is correctly `UTF-8` throughout (`RUMI`
+ `\xc3\x91` + `AHUI` decodes cleanly to "RUMIÑAHUI") — that garbling was
a terminal display artifact of the investigation session, not a defect in
the source or in this client's parsing.

The fetch goes through `archive.org/wayback/available` (not a hardcoded
`web.archive.org/web/<timestamp>/...` URL) so a future Wayback
re-consolidation of nearby captures under a different exact timestamp
doesn't silently break this client — the target date (2024-04-24) is what
matters, not the exact second IA happened to crawl it.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_ORIGINAL_URL = "https://energia-ecuador.com/empresa-electrica-quito/"
_TARGET_TIMESTAMP = "20240424"  # site's launch day; see module docstring
_AVAILABLE_API = "http://archive.org/wayback/available"
_WAYBACK_TIMEOUT = 30.0

# The source is a single frozen historical page (archive.org never changes
# a capture's bytes) -- a long TTL avoids re-fetching something that
# cannot change, while still surviving a server restart with a cold cache.
_snapshot_cache = TtlCache(ttl_seconds=2_592_000.0, max_entries=1)
_fetch_lock = asyncio.Lock()

_TABLE_RE = re.compile(r'<table[^>]*tablepress[^>]*>.*?</table>', re.IGNORECASE | re.DOTALL)
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_HEADER_CELL_RE = re.compile(r"<th[^>]*>(.*?)</th>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")

_COLUMNS = (
    "provincia",
    "canton",
    "sectores",
    "programacion_inicio",
    "programacion_fin",
    "reprogramacion_inicio",
    "reprogramacion_fin",
)


def _clean_cell(raw: str) -> str:
    return _TAG_RE.sub("", raw).replace("\xa0", " ").strip()


def _parse_rows(html: str) -> list[dict[str, Any]]:
    table_m = _TABLE_RE.search(html)
    if not table_m:
        return []

    all_rows = _ROW_RE.findall(table_m.group(0))
    data_rows: list[dict[str, Any]] = []
    for row_html in all_rows:
        if _HEADER_CELL_RE.search(row_html):
            continue  # the header <tr> uses <th>, not <td> -- skip it
        cells = [_clean_cell(c) for c in _CELL_RE.findall(row_html)]
        if not cells:
            continue
        entry = dict(zip(_COLUMNS, cells, strict=False))
        data_rows.append(entry)
    return data_rows


async def _resolve_snapshot_url(session: httpx.AsyncClient) -> str:
    resp = await session.get(
        _AVAILABLE_API,
        params={"url": _ORIGINAL_URL, "timestamp": _TARGET_TIMESTAMP},
        timeout=_WAYBACK_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    closest = (payload.get("archived_snapshots") or {}).get("closest") or {}
    snapshot_url = closest.get("url")
    if not snapshot_url:
        raise ValueError("La Wayback Machine no devolvió un snapshot para energia-ecuador.com")
    # "id_" makes archive.org return the raw captured bytes, without the
    # Wayback toolbar/link-rewriting it injects into a normal replay.
    return snapshot_url.replace(f"/{closest['timestamp']}/", f"/{closest['timestamp']}id_/", 1)


async def _fetch_snapshot() -> dict[str, Any]:
    cached = _snapshot_cache.get("snapshot")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _snapshot_cache.get("snapshot")
        if cached is not None:
            return cached

        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as session:
            logger.info("Resolviendo el snapshot de energia-ecuador.com en la Wayback Machine")
            snapshot_url = await _resolve_snapshot_url(session)
            logger.info("Descargando snapshot recuperado: %s", snapshot_url)
            resp = await session.get(snapshot_url, timeout=_WAYBACK_TIMEOUT)
            resp.raise_for_status()
            html = resp.text

        filas = _parse_rows(html)
        result = {"snapshot_url": snapshot_url, "filas": filas}
        if filas:
            _snapshot_cache.set("snapshot", result)
        return result


async def get_energia_ecuador_snapshot(query: str = "") -> dict[str, Any]:
    """
    Recover the national blackout-schedule aggregator
    (energia-ecuador.com, Ministerio de Energía y Minas, 2024 crisis) via
    the Wayback Machine — a single frozen snapshot (2024-04-24) of the
    Empresa Eléctrica Quito page, the only one of the site's nine
    distributor pages the Wayback Machine fully captured before the site
    went behind a Cloudflare block. See module docstring for the other
    eight distributors' confirmed-but-unrecoverable page URLs.

    Args:
        query: Free text matched (accent-insensitive) against canton or
            sectores. Empty returns all rows.
    """
    snapshot = await _fetch_snapshot()
    filas = snapshot["filas"]
    q = _strip(query)
    matched = [
        f
        for f in filas
        if not q or q in _strip(f.get("canton")) or q in _strip(f.get("sectores"))
    ]
    return {
        "total": len(matched),
        "total_en_snapshot": len(filas),
        "source": (
            "Ministerio de Energía y Minas — energia-ecuador.com (portal agregador nacional "
            "de racionamiento durante la crisis 2024), recuperado vía Wayback Machine — "
            "snapshot único del 2024-04-24, solo Empresa Eléctrica Quito"
        ),
        "url_original": _ORIGINAL_URL,
        "url_snapshot": snapshot["snapshot_url"],
        "fecha_snapshot": "2024-04-24",
        "filas": matched,
    }
