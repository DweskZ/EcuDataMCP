"""Client for Ecuador's SPNF (Sector Público No Financiero) fiscal-operations
workbook archive, published by the Ministerio de Economía y Finanzas (MEF) —
now folded into the Ministerio de Desarrollo Económico y Productivo (MDEP),
per RESEARCH.md's "Ministerio de Finanzas se fusionó/renombró" finding —
plus, as a secondary/complementary source, SENAE's own customs-collection
breakdown. Both confirmed live 2026-09-02.

**MEF/MDEP "Estadística Nueva Metodología" page (primary, current source).**
`finanzas.gob.ec/estadistica-nueva-metodologia-2017-2022/` (old URL slug;
the page's own <h1> reads "Estadística Nueva Metodología 2013 – 2026") 301s
to `www.economicoproductivo.gob.ec/estadistica-nueva-metodologia-2017-2022/`
— this client fetches that destination URL directly rather than the old
`finanzas.gob.ec` host. Confirmed live: the bare `finanzas.gob.ec` host
presents a TLS certificate for `economicoproductivo.gob.ec` (a real
hostname mismatch, not an artifact of following the redirect) and isn't on
this project's `helpers.tls` insecure-retry allowlist, so hitting it
directly raises `SSLCertVerificationError`; `www.economicoproductivo.gob.ec`
has no such issue and is what `helpers.csv_reader.download_bytes` reaches
successfully.

This is IMF GFSM-methodology fiscal data (the same standard BCE uses for
its IEM), covering SPNF income/expense, financial assets/liabilities, and
above/below-the-line financing, broken out by government-level sheet (e.g.
"GC" = Gobierno Central) inside each workbook — never parsed here (this
project's XLSX files are exposed as metadata + URL only, same as
helpers/sipa_client.py and helpers/bce_remesas_client.py; download and read
them via download_resource / the xlsx skill instead of a custom parser).

**Not a single static workbook**, contrary to an earlier research pass that
only sampled one file: live reality is a running archive of **76 distinct
XLSX files** (confirmed 2026-09-02) — monthly snapshots of "Operaciones de
Ingresos y Gastos SPNF" and "Operaciones de Activos Financieros y Pasivos
SPNF" (both numbered/dated per publication), plus "BLL" (Bajo la Línea) and
"Financiamiento SPNF y subsectores" financing files, with publish folders
running from 2025-01 through 2026-09. For tariff income specifically, read
row `1214 Arancelarios` (within `121 Ingresos tributarios`, sheet "GC") of
the newest "Operaciones de Ingresos y Gastos SPNF" file — annual series
2013-2025 plus quarterly breakdown confirmed in a prior pass (2023 = USD
1,180.4M, 2024 = USD 1,117.3M, 2025 = USD 1,231.4M).

**SENAE "Tributos Recaudados" page (secondary, stale but real — kept for
its category breakdown).** The bare `aduana.gob.ec` domain has no A record
at all; only `www.aduana.gob.ec` resolves, carrying
`/de-interes/tributos-recaudados/`, a WordPress `download-monitor`
accordion (same id-based pattern as helpers/cnig_client.py). Confirmed
live: exactly **60 XLSX files**, unchanged from the prior research pass —
2012-2021 only, nothing published since — broken out by **ADVALOREM** (the
tariff/derecho aduanero itself), **FODINFA**, **IVA**, **ICE**, **OTROS
TRIBUTOS**, and **TOTALES**, ten years times six categories. Kept in this
client rather than dropped as pure dead weight: it's the only source in
this project with a same-institution breakdown of the *other* border levies
alongside the tariff, which is exactly the context needed to interpret the
MEF figure correctly (see below) — even though SENAE's own series is frozen
at 2021.

**Scope distinction that matters for any caller of either source:**
"tariff revenue" is ambiguous in Ecuadorian public discourse. MEF's
"Arancelarios" line and SENAE's "ADVALOREM" category are the *tariff
(derecho aduanero) alone* — smaller than the roughly USD 3,776M press
coverage cites for 2024 "recaudación aduanera", because that figure (and
SENAE's own TOTALES category) also adds IVA and ICE collected at the
border, not just the tariff. Use "Arancelarios" / "ADVALOREM" for tariff
revenue in the strict sense; use SENAE's TOTALES (2012-2021 only, since it
never got updated) or sum the individual MEF/SENAE border-tax lines for the
broader "everything Aduana collects" figure.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from html import unescape
from typing import Any

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

# Hit the post-merger domain directly -- see module docstring for why the
# old finanzas.gob.ec host is skipped.
_MEF_PAGE_URL = (
    "https://www.economicoproductivo.gob.ec/estadistica-nueva-metodologia-2017-2022/"
)
# Bare aduana.gob.ec has no A record live -- only the www host resolves.
_SENAE_PAGE_URL = "https://www.aduana.gob.ec/de-interes/tributos-recaudados/"

# MEF is updated monthly; SENAE has been abandoned since 2021. A few hours
# balances staleness against re-fetching either page on every call -- same
# TTL as helpers/bce_remesas_client.py and helpers/sipa_client.py for
# similarly-paced sources.
_mef_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_senae_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_mef_lock = asyncio.Lock()
_senae_lock = asyncio.Lock()

_WS_RE = re.compile(r"\s+")

# Every real workbook link lives under /wp-content/uploads/.../<year>/<month>/
# on either the old finanzas.gob.ec host or the current
# economicoproductivo.gob.ec one (older files never got moved when the
# ministry merged) -- some sit directly under uploads/<year>/<month>/, a
# minority sit under an extra uploads/downloads/<year>/<month>/ segment
# (confirmed live), hence the non-capturing optional path segment rather
# than a fixed prefix.
_MEF_LINK_RE = re.compile(
    r'href="(https://(?:www\.)?(?:finanzas|economicoproductivo)\.gob\.ec'
    r'/wp-content/uploads/(?:[^"]*?/)?(\d{4})/(\d{2})/[^"/]+\.xlsx)"',
    re.IGNORECASE,
)

# Same download-monitor id pattern as helpers/cnig_client.py: SENAE's
# "Descargar <label>" anchor (force=1) carries the real label, the paired
# "ver" one (force=0) doesn't.
_SENAE_ENTRY_RE = re.compile(
    r'href="(https://(?:www\.)?aduana\.gob\.ec/wp-content/plugins/'
    r'download-monitor/download\.php\?id=(\d+)&force=1)"\s+title="Descargar ([^"]+)"'
)

# Ordered so more specific prefixes aren't shadowed by a shorter one; "ADVA"
# (not "ADVALOREM") deliberately also catches the live "Advaalorem" typo
# (confirmed on the 2016 file) without hardcoding that one misspelling.
_SENAE_CATEGORIAS: tuple[tuple[str, str], ...] = (
    ("ADVA", "ADVALOREM"),
    ("FODINFA", "FODINFA"),
    ("IVA", "IVA"),
    ("ICE", "ICE"),
    ("OTROS", "OTROS TRIBUTOS"),
    ("TOTALES", "TOTALES"),
)
_YEAR_RE = re.compile(r"(20\d{2})")


def _mef_label(url: str) -> str:
    """Filenames mix underscores and hyphens as separators inconsistently
    (Operaciones-de-Ingresos-y-Gastos vs Operaciones_de_Activos...); both
    are normalized to spaces for a readable label rather than guessing
    which one a given file uses.
    """
    filename = url.rsplit("/", 1)[-1]
    stem = filename.rsplit(".", 1)[0]
    return _WS_RE.sub(" ", stem.replace("_", " ").replace("-", " ")).strip()


def _parse_mef(html: str) -> list[dict[str, Any]]:
    archivos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for url, year, month in _MEF_LINK_RE.findall(html):
        if url in seen:
            continue
        seen.add(url)
        archivos.append(
            {
                "label": _mef_label(url),
                "url": url,
                "format": "XLSX",
                # The upload folder's year/month -- when the file was
                # published, not necessarily the fiscal period it covers
                # (that's usually encoded in the filename itself, e.g. a
                # "202605" prefix means "period 2026-05").
                "carpeta_publicacion": f"{year}-{month}",
            }
        )
    # Newest publication folder first -- helps pick the current workbook
    # out of 70+ historical snapshots without downloading each one.
    archivos.sort(key=lambda a: a["carpeta_publicacion"], reverse=True)
    return archivos


def _senae_categoria(label: str) -> str:
    upper = label.upper()
    for prefix, canonical in _SENAE_CATEGORIAS:
        if upper.startswith(prefix):
            return canonical
    return "OTROS"  # pragma: no cover -- defensive; every sampled label matched live


def _clean_senae_label(raw: str) -> str:
    label = raw
    if label.lower().endswith(".xlsx"):
        label = label[: -len(".xlsx")]
    return _WS_RE.sub(" ", unescape(label).replace("-", " ")).strip()


def _parse_senae(html: str) -> list[dict[str, Any]]:
    archivos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for url, entry_id, raw_label in _SENAE_ENTRY_RE.findall(html):
        if entry_id in seen:
            continue
        seen.add(entry_id)
        label = _clean_senae_label(raw_label)
        year_m = _YEAR_RE.search(label)
        archivos.append(
            {
                "id": entry_id,
                "label": label,
                "url": url,
                "format": "XLSX",
                "categoria": _senae_categoria(label),
                "anio": int(year_m.group(1)) if year_m else None,
            }
        )
    return archivos


async def _fetch(
    url: str,
    cache: TtlCache,
    lock: asyncio.Lock,
    parse: Callable[[str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    cached = cache.get("archivos")
    if cached is not None:
        return cached

    async with lock:
        # Re-check: another caller may have populated the cache while we
        # were waiting for the lock.
        cached = cache.get("archivos")
        if cached is not None:
            return cached

        logger.info("Descargando %s", url)
        content, truncated = await download_bytes(url)
        if truncated:
            raise ValueError(f"La página de {url} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")

        archivos = parse(html)
        if archivos:
            # Same "don't cache an apparently-empty/broken scrape" rationale
            # as helpers/bce_remesas_client.py / helpers/contraloria_client.py.
            cache.set("archivos", archivos)
        return archivos


def _fetch_mef() -> Awaitable[list[dict[str, Any]]]:
    return _fetch(_MEF_PAGE_URL, _mef_cache, _mef_lock, _parse_mef)


def _fetch_senae() -> Awaitable[list[dict[str, Any]]]:
    return _fetch(_SENAE_PAGE_URL, _senae_cache, _senae_lock, _parse_senae)


async def search_operaciones_spnf(query: str = "") -> dict[str, Any]:
    """
    List MEF/MDEP's Operaciones SPNF workbook archive (GFSM-methodology
    fiscal accounts: income/expense, assets/liabilities, financing),
    optionally filtered.

    Args:
        query: Free text matched (accent-insensitive) against the file's
            label or publication folder, e.g. "ingresos", "2026-06",
            "financiamiento". Empty returns all 76 files, newest
            publication folder first.
    """
    archivos = await _fetch_mef()
    q = _strip(query)
    matched = [
        a
        for a in archivos
        if not q or q in _strip(a["label"]) or q in _strip(a["carpeta_publicacion"])
    ]
    return {
        "total": len(matched),
        "total_en_pagina": len(archivos),
        "source": "Ministerio de Economía y Finanzas / MDEP — Operaciones SPNF (GFSM)",
        "url_fuente": _MEF_PAGE_URL,
        "archivos": matched,
    }


async def search_senae_tributos(query: str = "") -> dict[str, Any]:
    """
    List SENAE's Tributos Recaudados workbook archive (customs collection
    broken out by ADVALOREM/FODINFA/IVA/ICE/OTROS TRIBUTOS/TOTALES),
    optionally filtered. Stale: covers 2012-2021 only, nothing published
    since.

    Args:
        query: Free text matched (accent-insensitive) against the file's
            label or category, e.g. "advalorem", "2019", "totales". Empty
            returns all 60 files.
    """
    archivos = await _fetch_senae()
    q = _strip(query)
    matched = [
        a
        for a in archivos
        if not q or q in _strip(a["label"]) or q in _strip(a["categoria"])
    ]
    return {
        "total": len(matched),
        "total_en_pagina": len(archivos),
        "source": "SENAE — Tributos Recaudados (Aduana), 2012-2021",
        "url_fuente": _SENAE_PAGE_URL,
        "archivos": matched,
    }
