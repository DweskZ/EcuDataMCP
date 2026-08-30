"""Client for INEC's dedicated Census 2022 microsite (censoecuador.gob.ec).

Separate domain from ecuadorencifras.gob.ec (though the actual files are
hosted back on that main domain, under documentos/web-inec/bd-censo/... and
dicc-censo/...). Confirmed live: this microsite has the real bulk census
microdata -- sector/canton/city-block level, CSV/SPSS/REDATAM formats, plus
the 2010 and 2001 censuses recoded onto 2022 geography for comparability --
far more complete than the "Censo de Población y Vivienda" topic page
already indexed by helpers/inec_client.py's search_inec_estadisticas.

Two host quirks, both confirmed live and handled centrally in
helpers/csv_reader.download_bytes / helpers/tls.py, not duplicated here:

- TLS: www.censoecuador.gob.ec's cert chain verifies against the OS trust
  store but not httpx's bundled certifi CAs (a missing intermediate, not a
  broken cert) -- handled by helpers.tls's OS-trust-store retry tier.
- HTTP status: /data-y-resultados/ returns HTTP 404 (a WordPress/Elementor
  bug) while still serving its full, real page content -- this module
  calls download_bytes(..., raise_for_status=False) to tolerate that
  specifically, not to hide genuine errors elsewhere.
"""

from __future__ import annotations

import logging
import re
from html import unescape
from typing import Any

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip_accents

logger = logging.getLogger(MAIN_LOGGER_NAME)

RESULTADOS_URL = "https://www.censoecuador.gob.ec/data-y-resultados/"

_FILE_LINK_RE = re.compile(
    r'href="(https://[^"]+\.(pdf|xlsx|xls|csv|zip|docx?))"',
    re.IGNORECASE,
)

# The real microsite is refreshed rarely (the 2022 census dataset is
# essentially static); a day balances staleness against not re-fetching a
# 160+ KB page on every call.
_resources_cache = TtlCache(ttl_seconds=86400.0, max_entries=1)


def _label_from_url(url: str) -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    name = name.rsplit(".", 1)[0]
    return name.replace("_", " ").replace("-", " ").replace("%20", " ").strip()


async def _fetch_resources() -> list[dict[str, str]]:
    cached = _resources_cache.get("resources")
    if cached is not None:
        return cached

    content, truncated = await download_bytes(RESULTADOS_URL, raise_for_status=False)
    if truncated:
        raise ValueError("La página de resultados del censo superó el límite de descarga")
    html = content.decode("utf-8", errors="replace")

    seen: dict[str, str] = {}
    for url, ext in _FILE_LINK_RE.findall(html):
        seen.setdefault(unescape(url), ext.upper())

    resources = [
        {"label": _label_from_url(url), "url": url, "format": fmt}
        for url, fmt in seen.items()
    ]
    if not resources:
        raise ValueError(
            "No se encontraron archivos en la página de resultados del censo "
            "(puede haber cambiado de estructura)"
        )
    _resources_cache.set("resources", resources)
    return resources


async def search_censo_recursos(query: str = "", limit: int = 30, offset: int = 0) -> dict[str, Any]:
    """
    Search the direct file links published on INEC's Census 2022 microsite.

    Covers full microdata (sector/cantón/manzana, CSV/SPSS/REDATAM), variable
    dictionaries, methodology/quality documents, and the 2010/2001 censuses
    recoded onto 2022 geography.

    Args:
        query: Free text matched (accent-insensitive) against the file
            label, e.g. "manzana", "diccionario", "2010", "spss". Empty
            returns every resource found.
        limit: Max results returned.
        offset: Pagination offset over the matched set.
    """
    resources = await _fetch_resources()
    q = _strip_accents(query)

    matched = [r for r in resources if not q or q in _strip_accents(r["label"])]
    page = matched[offset : offset + limit]
    return {
        "source_url": RESULTADOS_URL,
        "total": len(matched),
        "total_recursos": len(resources),
        "offset": offset,
        "recursos": page,
    }
