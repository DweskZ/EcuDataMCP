"""Client for Ecuador's sectoral minimum wage tables (salarios mínimos
sectoriales — wage floors set per branch of economic activity, distinct from
the single national Salario Básico Unificado), scraped from the Ministerio
del Trabajo y Desarrollo Humano's document library
(https://www.trabajo.gob.ec/biblioteca/).

Investigated 2026-09-03 as a dedicated follow-up to the "débil" verdict in
RESEARCH.md's Octava pasada (Consejo Nacional de Salarios has no resolvable
domain, `consejosalarios.gob.ec` is NXDOMAIN; `trabajo.gob.ec`'s dynamic
pages — home, /salario-basico/, /tablas-sectoriales/ — time out, confirmed
again here). That prior pass only tried guessing `/wp-content/uploads/...`
paths, which really are unpredictable. This pass found something better:
`/biblioteca/` itself (unlike the pages above) responds — it's a single,
large (~2.3 MB), fully server-rendered page listing the ministry's entire
legal/document library, and every real download on it goes through a stable
`wp-content/plugins/download-monitor/download.php?id=<N>` link with the
document's real title in the surrounding `title="Ver ..."` attribute. That
makes the specific "Salarios Mínimos Sectoriales" entries genuinely
enumerable by filtering on the title text, rather than needing to guess
filenames.

**Coverage confirmed live:** one entry per year for 2020, 2021, 2022, 2023,
2024, and 2025 (most years have two: a spreadsheet — XLS/XLSX — of the raw
table, and a PDF of the signed annex/acuerdo); every one of the
`download.php?id=...` links found for these years was verified with a live
GET returning HTTP 200 during this investigation (see
tests/test_salarios_sectoriales_client.py for the confirmed ids/targets).
Nothing for 2026, and nothing before 2020 exists in this library listing.

**No 2026 table published (confirmed as of 2026-09-03):** the SBU for 2026
was fixed at USD 482 by Acuerdo Ministerial MDT-2025-195 (2025-12-15,
effective 2026-01-01), but that agreement only sets the *unified* national
floor. Press coverage (El Universo, El Diario) and the ministry's own public
statements confirm no sectoral table update has been issued for 2026 — the
2025 sectoral table stays in force by inaction. This client surfaces that as
a static note rather than trying to detect it live, since "no new entry
appeared" is inherently indistinguishable from "the page failed to load"
without a human checking press coverage periodically.

**What this does NOT cover:** the underlying `Acuerdo Ministerial` legal
text that *sets* each year's table is a separate library entry from the
"Tabla ..." / "Salarios Mínimos Sectoriales <year>" entry itself, and titled
by the year the acuerdo was *signed* (often December of the prior year) —
e.g. Acuerdo MDT-2023-180 (signed 2023) sets the 2024 table, and shows up
here tagged as `anio: 2023` because that's the year printed in its title.
Search by both the target year and the year before it if a specific year's
table seems to be missing.

Downloads are not resolved/parsed by this client — `download.php?id=...`
redirects to the real file (a `.pdf`, `.xls`, or `.xlsx` under
`/wp-content/uploads/downloads/...`), and callers should follow it via
`download_resource`/`preview_resource_data` rather than have this client
guess the format ahead of time.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import Any

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_PAGE_URL = "https://www.trabajo.gob.ec/biblioteca/"

# The library page is large (~2.3 MB) but changes only around once a year
# (a new sectoral table, published — when it is — sometime in Q4/Q1); a full
# day balances staleness against re-fetching/re-parsing a multi-MB page.
_entries_cache = TtlCache(ttl_seconds=86400.0, max_entries=1)
_fetch_lock = asyncio.Lock()

# Every real document link on the page follows this exact shape: the "Ver"
# (view) variant of a download-monitor link, immediately followed by a
# title="Ver <real document title>" attribute -- confirmed live against the
# actual page rather than assumed from the plugin's typical markup.
_ENTRY_RE = re.compile(
    r'<a\s+href="([^"]*?download\.php\?id=(\d+)&amp;force=0)"\s+title="Ver\s+([^"]*?)"',
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"(20\d{2})")

_NOTA_2026 = (
    "No hay tabla 2026 publicada en esta biblioteca (verificado 2026-09-03). "
    "El Acuerdo Ministerial MDT-2025-195 (2025-12-15) fijó el Salario Básico "
    "Unificado 2026 en USD 482 pero no una tabla sectorial nueva; según "
    "cobertura de prensa y el propio ministerio, la tabla sectorial de 2025 "
    "sigue vigente por falta de actualización."
)


def _parse_entries(page_html: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for match in _ENTRY_RE.finditer(page_html):
        href, doc_id, raw_title = match.group(1), match.group(2), match.group(3)
        title = html.unescape(raw_title).strip()
        norm_title = _strip(title)
        # Require both tokens so we don't pick up unrelated entries that
        # share only one word, e.g. "Plan Sectorial del Trabajo 2025-2029"
        # (sectorial, no salari) or "...fijar el salario básico unificado..."
        # (salari, no sectorial) -- confirmed both appear on this page.
        if "salari" not in norm_title or "sectorial" not in norm_title:
            continue
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)

        year_match = _YEAR_RE.search(title)
        anio = int(year_match.group(1)) if year_match else None

        url_ver = html.unescape(href)
        url_descarga = url_ver.replace("force=0", "force=1")

        entries.append(
            {
                "id": doc_id,
                "anio": anio,
                "titulo": title,
                "url_ver": url_ver,
                "url_descarga": url_descarga,
            }
        )

    entries.sort(key=lambda e: (e["anio"] or 0, e["id"]), reverse=True)
    return entries


async def _fetch_entries() -> list[dict[str, Any]]:
    cached = _entries_cache.get("entries")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _entries_cache.get("entries")
        if cached is not None:
            return cached

        logger.info(
            "Descargando la Biblioteca del Ministerio del Trabajo para "
            "salarios sectoriales"
        )
        content, truncated = await download_bytes(_PAGE_URL)
        if truncated:
            raise ValueError(
                f"La página de {_PAGE_URL} superó el límite de descarga."
            )
        page_html = content.decode("utf-8", errors="replace")

        entries = _parse_entries(page_html)
        if entries:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/bce_remesas_client.py / helpers/contraloria_client.py.
            _entries_cache.set("entries", entries)
        return entries


async def search_tablas_sectoriales(anio: int | None = None) -> dict[str, Any]:
    """
    List sectoral minimum wage table documents (Salarios Mínimos Sectoriales)
    found in the Ministerio del Trabajo's document library.

    Args:
        anio: Filter to this year (as printed in the document's own title —
            note some entries are the signing acuerdo, titled by the prior
            year; see this module's docstring). None returns all years found
            (currently 2020-2025).
    """
    entries = await _fetch_entries()
    matched = [e for e in entries if anio is None or e["anio"] == anio]
    result: dict[str, Any] = {
        "total": len(matched),
        "total_en_biblioteca": len(entries),
        "source": "Ministerio del Trabajo y Desarrollo Humano — Biblioteca",
        "url_fuente": _PAGE_URL,
        "tablas": matched,
        "nota": _NOTA_2026,
    }
    return result
