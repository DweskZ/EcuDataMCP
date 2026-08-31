"""Client for two Contraloría General del Estado pages that share the same
`WFDescarga.aspx?id={id}&tipo={tipo}&op=d` download pattern:

- "Datos Abiertos" (contraloria.gob.ec/Portal/24287, `tipo=pesdoc`) —
  quarterly CSV exports of approved audit reports (informes de auditoría
  aprobados) for every public institution in the country, plus a glossary.
- "Plan Anual de Control" (contraloria.gob.ec/Portal/Sistema/PlanAnualControl,
  `tipo=doc`) — one PDF per year (the "Acuerdo de aprobación") setting out
  that year's planned control actions.

Both pages list each document as a row with a "Descargar" button whose
onclick builds the download URL. No JS execution is needed — the id/tipo
pair is present as plain text in the page's HTML (inside the button's
onclick attribute), so it's scraped the same way as
helpers/inec_client.py's file links. Confirmed live: each "Datos Abiertos"
CSV is real (~130-155 KB, well under the 5 MB cap), columns `N°; Unidad de
Control; Entidad; Diligencia; Periodo Desde; Periodo Hasta; Tipo de
informe; N° Informe; Fecha Aprobación` — one row per audit report approved
for any institution in that quarter. "Plan Anual de Control" documents are
PDFs, not CSVs — get_informe() returns metadata only for those and points
callers at read_pdf.

Both lists grow over time (a new quarter/year roughly every three
months/year), so — unlike helpers/sipa_client.py's four fixed modules —
both pages are scraped live rather than hardcoded.

Reuses helpers/csv_reader.preview_csv for the actual download+parse
(encoding fallback for the site's non-UTF-8 CSVs, delimiter sniffing)
instead of reimplementing CSV handling here.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from typing import Any

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes, preview_csv
from helpers.logging import MAIN_LOGGER_NAME

logger = logging.getLogger(MAIN_LOGGER_NAME)

_SEED_URL = "https://www.contraloria.gob.ec/Portal/24287"
_PLAN_ANUAL_SEED_URL = "https://www.contraloria.gob.ec/Portal/Sistema/PlanAnualControl"
_SEED_URLS = (_SEED_URL, _PLAN_ANUAL_SEED_URL)
_BASE = "https://www.contraloria.gob.ec"

# The one tipo that is a CSV export ("Datos Abiertos" quarterly reports).
# Every other tipo (currently only "doc", Plan Anual de Control) is a PDF —
# get_informe() returns metadata only for those instead of trying preview_csv.
_CSV_TIPO = "pesdoc"

# The page is only refreshed when a new quarter is published (roughly every
# 3 months), same rationale as helpers/inec_client.py's topic-menu cache.
_informes_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

_TAG_RE = re.compile(r"<[^>]+>")
_ROW_RE = re.compile(
    r'<div class="col-sm-11">(?P<label>[^<]*)</div>\s*'
    r'<div class="col-sm-1">\s*<input\s+[^>]*onclick="javascript:\s*down\('
    r"'(?P<tipo>[^']+)',\s*(?P<id>\d+)\);\""
)


def _clean(text: str) -> str:
    return unescape(_TAG_RE.sub("", text)).strip()


async def _fetch_informes() -> list[dict[str, str]]:
    cached = _informes_cache.get("informes")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _informes_cache.get("informes")
        if cached is not None:
            return cached

        informes = []
        for seed_url in _SEED_URLS:
            logger.info("Descargando página de la Contraloría: %s", seed_url)
            content, truncated = await download_bytes(seed_url)
            if truncated:
                raise ValueError(f"La página de {seed_url} superó el límite de descarga.")
            html = content.decode("utf-8", errors="replace")

            for m in _ROW_RE.finditer(html):
                id_, tipo = m.group("id"), m.group("tipo")
                informes.append(
                    {
                        "id": id_,
                        "tipo": tipo,
                        "label": _clean(m.group("label")),
                        "url": f"{_BASE}/WFDescarga.aspx?id={id_}&tipo={tipo}&op=d",
                    }
                )
        if informes:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/sipa_client.py — an empty result here likely means
            # the page structure changed, not that the list is genuinely
            # empty, and shouldn't be pinned for 6 hours.
            _informes_cache.set("informes", informes)
        return informes


async def list_informes() -> list[dict[str, str]]:
    """List available Contraloría "Datos Abiertos" documents (quarterly
    audit-report CSVs plus the glossary)."""
    return await _fetch_informes()


async def get_informe(informe_id: str, max_rows: int = 50) -> dict[str, Any]:
    """
    Download and parse one Contraloría document by id.

    Args:
        informe_id: An "id" from list_informes().
        max_rows: Max data rows to return.
    """
    informes = await _fetch_informes()
    match = next((i for i in informes if i["id"] == informe_id), None)
    if match is None:
        valid = ", ".join(i["id"] for i in informes) or "(ninguno disponible)"
        raise ValueError(f"informe_id '{informe_id}' no encontrado. Válidos: {valid}")

    if match["tipo"] != _CSV_TIPO:
        # Plan Anual de Control (and any other non-pesdoc tipo) is a PDF, not
        # a CSV export -- nothing here to parse as a table. Metadata + URL
        # only, same pattern as SIPA/Supercías financials; read_pdf handles
        # the actual content.
        return {
            "label": match["label"],
            "url": match["url"],
            "tipo": match["tipo"],
            "is_pdf": True,
        }

    result = await preview_csv(match["url"], max_rows=max_rows)
    result["label"] = match["label"]
    result["url"] = match["url"]
    return result
