"""MSP medicine ceiling prices (Consejo Nacional de Fijación y Revisión de
Precios de Medicamentos).

The council publishes, at each revision, two workbooks on salud.gob.ec:

- "Consolidado precios techo actualizado": every regulated medicine with
  its resolution, active ingredient, pharmaceutical form, concentration,
  presentation and USD ceiling price (~1,810 rows, ~270 KB; on the
  ESTRATÉGICOS sheet the header is on row 3).
- "Segmentos de mercado bajo el régimen liberado de precios".

The WordPress media API lists every release with its real URL (107 + 24
when checked 2026-11-07, December 2016 to October 2026). Each file carries
`fecha_corte` (the date in its name, the revision it reflects) and `tipo`.
Files open with preview_resource_data / download_resource (well under 5 MB).
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlencode

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.text_utils import strip_accents

_MEDIA_URL = "https://www.salud.gob.ec/wp-json/wp/v2/media"
_PAGE_URL = "https://www.salud.gob.ec/consejo-nacional-de-fijacion-y-revision-de-precios-de-medicamentos/"
_SEARCHES = {
    "precios_techo": "Consolidado-precios-techo",
    "segmentos_mercado": "Segmentos-de-mercado",
}
_MAX_PAGES = 5
_DATE_RE = re.compile(r"(20\d\d)-(\d\d)-(\d\d)")

_cache = TtlCache(ttl_seconds=21600.0, max_entries=1, persist="msp_precios")


def parse_media(items: list[dict[str, Any]], tipo: str) -> list[dict[str, Any]]:
    """Spreadsheet releases of one series, deduplicated by URL."""
    out = []
    seen: set[str] = set()
    for item in items:
        url = item.get("source_url") or ""
        name = url.rsplit("/", 1)[-1]
        if not name.lower().endswith((".xlsx", ".xls")) or url in seen:
            continue
        seen.add(url)
        match = _DATE_RE.search(name)
        out.append(
            {
                "titulo": name.rsplit(".", 1)[0].replace("-", " ").strip(" ."),
                "url": url,
                "formato": name.rsplit(".", 1)[-1].upper(),
                "tipo": tipo,
                "fecha_corte": "-".join(match.groups()) if match else None,
                "fecha": str(item.get("date") or "")[:10] or None,
            }
        )
    return out


async def _fetch_fresh() -> list[dict[str, Any]]:
    cached = _cache.get("archivos")
    if cached is not None:
        return cached
    archivos: list[dict[str, Any]] = []
    for tipo, search in _SEARCHES.items():
        items: list[dict[str, Any]] = []
        for page in range(1, _MAX_PAGES + 1):
            query = urlencode(
                {"search": search, "per_page": 100, "page": page, "_fields": "date,source_url"}
            )
            raw, truncated = await download_bytes(
                f"{_MEDIA_URL}?{query}", raise_for_status=frozenset({400})
            )
            if truncated:
                raise ValueError("La API de medios de salud.gob.ec superó el límite de descarga.")
            batch = json.loads(raw.decode("utf-8", errors="replace"))
            if not isinstance(batch, list):
                break  # 400 past the last page
            items.extend(batch)
            if len(batch) < 100:
                break
        archivos.extend(parse_media(items, tipo))
    archivos.sort(key=lambda a: (a["fecha_corte"] or a["fecha"] or ""), reverse=True)
    if archivos:
        _cache.set("archivos", archivos)
    return archivos


async def _fetch() -> list[dict[str, Any]]:
    """Fresh fetch, or the last good copy when the source fails (see TtlCache.serve_stale)."""
    try:
        return await _fetch_fresh()
    except Exception as exc:
        stale = _cache.serve_stale("archivos", exc)
        if stale is None:
            raise
        return stale


async def search_precios(query: str = "") -> dict[str, Any]:
    archivos = await _fetch()
    q = strip_accents(query)
    if q:
        archivos = [
            a for a in archivos
            if q in strip_accents(f"{a['titulo']} {a['tipo']} {a['fecha_corte'] or ''}")
        ]
    return {
        "source": "MSP — Consejo Nacional de Fijación y Revisión de Precios de Medicamentos",
        "url_fuente": _PAGE_URL,
        "nota": (
            "tipo precios_techo: precio techo en USD de cada medicamento regulado (hoja "
            "ESTRATÉGICOS, encabezado en la fila 3); tipo segmentos_mercado: segmentos en "
            "régimen liberado. El primero de la lista es la revisión vigente."
        ),
        "archivos": archivos,
    }
