"""Client for BCE's Cuentas Nacionales page family (contenido.bce.fin.ec) --
the "Cuentas Nacionales completas" gap flagged in ROADMAP.md ("Paquetes
anual/trimestral/regional, retropolación, Tabla Oferta-Utilización, Cuadro
Económico Integrado, Matriz de Empleo e Ingresos").

Confirmed live 2026-09-09: unlike helpers/bce_indices_client.py's ~35
"-indice(s)" pages (one shared `.bce-gi` widget, discoverable from the
site's own sitemap by slug), the Cuentas Nacionales pages carry no common
slug pattern and each renders its own bespoke, page-specific widget (class
prefixes `cna-`/`cnr-`/`cnt-` for tabbed vintages, or plain `<a>` links
inside a `.card-body` for single-series pages) -- confirmed by diffing the
raw HTML of a dozen of these pages. A sitemap-slug or shared-CSS-class
discovery approach (as used for the índice system) does not generalize
here; the ~18 pages below were hand-verified one by one and are hardcoded,
same rationale as `_EXTRA_TOPICS` in helpers/inec_client.py and `_PAGINAS`
in helpers/bce_precios_comex_client.py.

What DOES generalize across every page, regardless of its specific widget:
every real download is a plain `<a href="...">` pointing at
`/documentos/.../archivo.{xlsx,xls,pdf,csv,zip,docx}` -- confirmed against
all 18 pages live, from the simplest (3 links, no tabs) to the largest (80
links, `boletin-de-cuentas-nacionales-trimestrales`). `_extract_archivos`
parses on that structural fact alone (any `<a>` tag whose href contains
"/documentos/" and ends in a known data extension), rather than the
page's own CSS classes -- this is what lets one parser cover pages that
otherwise share no markup convention.

Content confirmed real and current as of this pass: annual national
accounts back to 1965 (`retropolacion_1965_2024p.xlsx`), quarterly national
accounts through Q1 2026, regional/provincial accounts 2007-2024,
input-output and social-accounting matrices (fixed-base 2007 and moving
base), the bioeconomy satellite account, and monthly IMAEC results.
IMAEC's own results page (`imaec-cuadros-de-resultados`) only exposes the
single latest month -- same rolling-window limitation already documented
for helpers/bce_publicaciones_client.py, not a parsing bug here.

Two pages deliberately excluded after live inspection: "cuentas-nacionales-
anuales" and "cuentas-nacionales-trimestrales" (and their sibling
"-definicion" pages) are pure navigation shells with no `/documentos/`
links of their own -- the same "loads the plugin but has no real content"
case bce_indices_client.py already excludes from its catalog.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import logging
import re
from typing import Any
from urllib.parse import urljoin

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://contenido.bce.fin.ec"
_SOURCE_NAME = "Banco Central del Ecuador — Cuentas Nacionales"

# Hand-verified 2026-09-09 (see module docstring for why this can't be
# discovered generically the way bce_indices_client's sitemap sweep works).
_PAGINAS = (
    {
        "pagina_id": "cuadros-de-resultados-cuentas-nacionales-anuales",
        "titulo": "Cuentas Nacionales Anuales — Cuadros de Resultados",
        "categoria": "anual",
    },
    {
        "pagina_id": "cuadros-de-resultados-cuentas-nacionales-anuales-regionales",
        "titulo": "Cuentas Nacionales Anuales Regionales — Cuadros de Resultados",
        "categoria": "regional",
    },
    {
        "pagina_id": "matriz-de-empleo-e-ingresos-mei",
        "titulo": "Matriz de Empleo e Ingresos (MEI)",
        "categoria": "anual",
    },
    {
        "pagina_id": "boletin-de-cuentas-nacionales-trimestrales",
        "titulo": "Boletín de Cuentas Nacionales Trimestrales",
        "categoria": "trimestral",
    },
    {
        "pagina_id": "cuentas-nacionales-regionales",
        "titulo": "Cuentas Nacionales Regionales — serie histórica provincial y cantonal",
        "categoria": "regional",
    },
    {
        "pagina_id": "matrices-especiales-de-cuentas-nacionales-base-fija",
        "titulo": "Matrices especiales de Cuentas Nacionales (base fija 2007)",
        "categoria": "base_fija",
    },
    {
        "pagina_id": "cuentas-nacionales-anuales-base-fija-2007-100",
        "titulo": "Cuentas Nacionales Anuales — base fija 2007=100",
        "categoria": "base_fija",
    },
    {
        "pagina_id": "cambio-de-ano-base-de-las-cuentas-nacionales-cab-2007",
        "titulo": "Cambio de Año Base de las Cuentas Nacionales (CAB 2007)",
        "categoria": "base_fija",
    },
    {
        "pagina_id": "tabla-de-oferta-y-utilizacion-tou",
        "titulo": "Tabla de Oferta y Utilización (TOU) — serie anual",
        "categoria": "anual",
    },
    {
        "pagina_id": "cuadro-economico-integrado-cei",
        "titulo": "Cuadro Económico Integrado (CEI) — serie anual",
        "categoria": "anual",
    },
    {
        "pagina_id": "formacion-bruta-de-capital-fijo",
        "titulo": "Formación Bruta de Capital Fijo (FBKF) — serie 1965-hoy",
        "categoria": "anual",
    },
    {
        "pagina_id": "matriz-insumo-producto",
        "titulo": "Matriz Insumo-Producto (MIP)",
        "categoria": "anual",
    },
    {
        "pagina_id": "matriz-de-contabilidad-social",
        "titulo": "Matriz de Contabilidad Social (MCS)",
        "categoria": "anual",
    },
    {
        "pagina_id": "resultados-cuentas-tematicas",
        "titulo": "Cuentas Temáticas — Bioeconomía",
        "categoria": "tematica",
    },
    {
        "pagina_id": "documentos-metodologicos-cuentas-nacionales-anuales",
        "titulo": "Documentos metodológicos — Cuentas Nacionales Anuales",
        "categoria": "metodologia",
    },
    {
        "pagina_id": "documentos-metodologicos-cuentas-nacionales-trimestrales",
        "titulo": "Documentos metodológicos — Cuentas Nacionales Trimestrales",
        "categoria": "metodologia",
    },
    {
        "pagina_id": "documentos-metodologicos-cuentas-tematicas",
        "titulo": "Documentos metodológicos — Cuentas Temáticas",
        "categoria": "metodologia",
    },
    {
        "pagina_id": "imaec-cuadros-de-resultados",
        "titulo": "IMAEC — Cuadros de Resultados (mensual, solo el mes más reciente)",
        "categoria": "imaec",
    },
)
_PAGINAS_BY_ID = {p["pagina_id"]: p for p in _PAGINAS}

# The page set changes rarely; each page's own file list changes at most
# quarterly (annual/regional packages) or monthly (IMAEC) -- same 6h TTL as
# every other BCE publication-list client in this project.
_catalog_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

_A_TAG_RE = re.compile(
    r"<a\b(?P<attrs>[^>]*)>(?P<inner>.*?)</a>", re.DOTALL | re.IGNORECASE
)
_HREF_RE = re.compile(r'href="(?P<href>[^"]+)"', re.IGNORECASE)
_FILE_HREF_RE = re.compile(
    r"/documentos/.+\.(?:xlsx|xls|pdf|csv|zip|docx?)(?:\?.*)?$", re.IGNORECASE
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_FORMATOS_POR_EXTENSION = {
    "pdf": "PDF",
    "xlsx": "XLSX",
    "xls": "XLS",
    "csv": "CSV",
    "zip": "ZIP",
    "doc": "DOC",
    "docx": "DOCX",
}


def _clean_text(fragment: str) -> str:
    without_tags = _TAG_RE.sub(" ", fragment)
    return html_lib.unescape(_WS_RE.sub(" ", without_tags).strip())


def _absolute(href: str) -> str:
    return href if href.startswith("http") else urljoin(_BASE, href)


def _formato_from_url(url: str) -> str:
    name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if "." not in name:
        return "DESCONOCIDO"
    ext = name.rsplit(".", 1)[-1].lower()
    return _FORMATOS_POR_EXTENSION.get(ext, ext.upper())


def _extract_archivos(html_text: str) -> list[dict[str, str]]:
    """Every `<a>` tag whose href is a `/documentos/...` file link,
    regardless of the page's own (bespoke, non-shared) widget markup --
    see module docstring."""
    archivos: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for m in _A_TAG_RE.finditer(html_text):
        href_m = _HREF_RE.search(m.group("attrs"))
        if not href_m or not _FILE_HREF_RE.search(href_m.group("href")):
            continue
        url = _absolute(href_m.group("href"))
        if url in seen_urls:
            continue
        seen_urls.add(url)
        archivos.append(
            {
                "label": _clean_text(m.group("inner")),
                "url": url,
                "format": _formato_from_url(url),
            }
        )
    return archivos


async def _fetch_pagina(pagina: dict[str, str]) -> dict[str, Any] | None:
    url = f"{_BASE}/{pagina['pagina_id']}/"
    try:
        content, truncated = await download_bytes(url)
        if truncated:
            logger.warning(
                "La página de Cuentas Nacionales %s superó el límite de descarga", url
            )
            return None
        html_text = content.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning(
            "No se pudo leer la página de Cuentas Nacionales %s: %s", url, exc
        )
        return None

    archivos = _extract_archivos(html_text)
    return {
        "pagina_id": pagina["pagina_id"],
        "titulo": pagina["titulo"],
        "categoria": pagina["categoria"],
        "url": url,
        "total_archivos": len(archivos),
        "archivos": archivos,
    }


async def _fetch_catalog() -> list[dict[str, Any]]:
    cached = _catalog_cache.get("catalog")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _catalog_cache.get("catalog")
        if cached is not None:
            return cached

        logger.info("Descargando páginas de Cuentas Nacionales del BCE")
        results = await asyncio.gather(*(_fetch_pagina(p) for p in _PAGINAS))
        catalog = [entry for entry in results if entry is not None]
        # A page that fetched fine but matched zero /documentos/ file links
        # is a real, valid state for one page (e.g. a stale monthly page
        # between updates) -- but every page in the whole catalog coming
        # back empty at once means the extractor itself broke against a
        # site-wide markup change, not that BCE removed every file. Same
        # "don't cache an apparent break" rationale as
        # helpers/bce_indices_client.py and helpers/bce_precios_comex_client.py.
        if catalog and any(entry["total_archivos"] > 0 for entry in catalog):
            _catalog_cache.set("catalog", catalog)
        return catalog


def clear_cache() -> None:
    """Clear the Cuentas Nacionales catalog cache; useful for refresh jobs and tests."""
    _catalog_cache.clear()


def _resumen(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if k != "archivos"}


async def search_cuentas_nacionales(query: str = "") -> dict[str, Any]:
    """
    List BCE Cuentas Nacionales page families -- annual/quarterly/regional
    national accounts packages, the historical retropolation series,
    input-output and social-accounting matrices, fixed-base (2007=100)
    series, the bioeconomy thematic account, and IMAEC monthly results.

    Returns summaries only (title, category, page URL, file count) -- call
    get_bce_cuentas_nacionales_archivo with the returned pagina_id to read
    one page's actual file list.

    Args:
        query: Free text matched (accent-insensitive) against the page's
            title, category, or id. Empty returns all pages.
    """
    catalog = await _fetch_catalog()
    q = _strip(query)
    matched = [
        entry
        for entry in catalog
        if not q
        or q in _strip(entry["titulo"])
        or q in _strip(entry["categoria"])
        or q in _strip(entry["pagina_id"])
    ]
    return {
        "total": len(matched),
        "total_paginas": len(catalog),
        "source": _SOURCE_NAME,
        "paginas": [_resumen(entry) for entry in matched],
    }


_MAX_ARCHIVOS = 200
_DEFAULT_MAX_ARCHIVOS = 50


async def get_archivo(
    pagina_id: str, max_archivos: int = _DEFAULT_MAX_ARCHIVOS
) -> dict[str, Any]:
    """
    Read the file list for one BCE Cuentas Nacionales page (from
    search_bce_cuentas_nacionales).

    Args:
        pagina_id: The page's id, from search_bce_cuentas_nacionales'
            `pagina_id` field (e.g. "boletin-de-cuentas-nacionales-trimestrales").
        max_archivos: Cap on returned files, 1-200.
    """
    catalog = await _fetch_catalog()
    entry = next((e for e in catalog if e["pagina_id"] == pagina_id.strip()), None)
    if entry is None:
        raise ValueError(
            f"Página de Cuentas Nacionales '{pagina_id}' no encontrada. "
            "Usa search_bce_cuentas_nacionales para ver los pagina_id válidos."
        )

    archivos = entry["archivos"]
    cap = min(max(max_archivos, 1), _MAX_ARCHIVOS)
    limitado = archivos[:cap]
    return {
        "source": _SOURCE_NAME,
        "pagina": _resumen(entry),
        "total_archivos": len(archivos),
        "archivos_mostrados": len(limitado),
        "truncado": len(archivos) > len(limitado),
        "archivos": limitado,
    }
