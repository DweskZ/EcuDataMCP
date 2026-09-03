"""Client for MINEDEC's (Ministerio de Educación, Deporte y Cultura) "Datos
Abiertos" page (educacion.gob.ec/datos-abiertos-minedec/) — the historical
K-12/basic-education enrollment registry. Distinct from this project's
existing SENESCYT/higher-education CKAN coverage (13 datasets under
`organization=ministerio-de-educacion`, itself the renamed SENESCYT — see
helpers/ckan_client.py callers): that coverage is higher education, this
page is basic education (matrícula escolar).

Confirmed live (2026-09-03, `curl`/HEAD against the real page and files,
not assumed from a filename pattern):

- The page is a WordPress/Elementor page, not an accordion list or a CKAN
  dataset — file links are `<a>` tags wrapping icon `<img>`s (icon PNGs
  carry the visible label — "Inicio", "Fin", "Metadato", "Diccionario" —
  there's no link text/alt text to scrape), all pointing at
  `/wp-content/uploads/downloads/2026/04/<N><filename>.xlsx` under the same
  origin.
- There are five real files today (all HTTP 200, non-empty
  Content-Length), not the two the prior filename-pattern guess
  (`...-{Inicio,Fin}.xlsx`) implied:
    1. `1Registro-Administrativo-Historico_2009-202X-Inicio.xlsx` — the
       main start-of-year registry. ~139 MB (Last-Modified 2026-05-04).
       Note "202X" is a **literal placeholder in the real filename**, not a
       redacted year — the ministry did not update it when re-exporting.
    2. `2Registro-Administrativo-Historico_2009-2024-Fin.xlsx` — the main
       end-of-year registry, through 2024. ~31 MB (Last-Modified
       2026-04-20). Its declared end year (2024) does not match the
       Inicio file's "202X" or the metadata files' declared 2025 — the
       three files disagree on the exact final year covered; treat the
       registry files themselves as authoritative and this client's
       `anio_hasta` as approximate, sourced from the filename only.
    3. `3MINEDEC_Metadato_RegistroAdministrativo_2009_2025_Inicio.xlsx` —
       metadata for the Inicio file, declares 2009-2025. ~17 KB.
    4. `4MINEDUC_metadato_RegistroAdministrativo_2021-202Fin.xlsx` —
       metadata for the Fin file. Two real inconsistencies in this one
       filename, confirmed live, not typos introduced here: it says
       "MINEDUC" (the ministry's old acronym, pre-rename to MINEDEC) where
       every other file says "MINEDEC", and its year range is truncated
       ("202Fin" — a digit is missing before "Fin"). ~17 KB.
    5. `5Diccionario_Registro-Administrativo-Historico.xlsx` — the shared
       data dictionary (column definitions), not split by Inicio/Fin.
       ~22 KB.
  (The page also links an unrelated `Manual-MAIS-CE.pdf` — a health-in-schools
  manual — from the same `/uploads/downloads/` path prefix but a different
  subfolder and naming scheme; the scrape below is anchored to the
  "Registro-Administrativo" / "RegistroAdministrativo" filename substring
  so that file is correctly excluded.)
- "Last updated April 2026" from the prior research pass is confirmed but
  refined: the upload folder is `2026/04`, but the two large registry
  files' actual `Last-Modified` headers are 2026-04-20 (Fin) and
  2026-05-04 (Inicio) — i.e. genuinely current, updated within the last
  several months of "today" (2026-09-02), not stale.

Because the two registry files are 31-139 MB — far past this project's
5 MB download cap (see helpers/csv_reader.MAX_DOWNLOAD_BYTES) — this
client, like helpers/sipa_client.py and helpers/bce_remesas_client.py,
never fetches file bytes server-side. It only scrapes the page for
metadata + the direct URL; point the model at the URL directly rather than
routing it through download_resource/preview_resource_data.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import unquote, urljoin

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_PAGE_URL = "https://educacion.gob.ec/datos-abiertos-minedec/"
_BASE = "https://educacion.gob.ec"

# The page is hand-maintained and refreshed a few times a year (new school
# year's registry file); a long TTL balances staleness against re-fetching
# and re-parsing a ~117 KB HTML page on every call.
_files_cache = TtlCache(ttl_seconds=43200.0, max_entries=1)
_fetch_lock = asyncio.Lock()

# Anchored to "Registro-Administrativo"/"RegistroAdministrativo" (present in
# all five known files, hyphenated or not, case-insensitive) rather than the
# broader "/uploads/downloads/" path segment, which the page also uses for
# an unrelated file (Manual-MAIS-CE.pdf, a health-in-schools manual).
_LINK_RE = re.compile(
    r'href="([^"]*[Rr]egistro-?[Aa]dministrativo[^"]*\.(?:xlsx|xls))"',
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")
_LEADING_DIGIT_RE = re.compile(r"^\d+")


def _label_from_url(url: str) -> str:
    """Derive a human label from the filename: the surrounding HTML carries
    no usable text (the visible labels are baked into icon PNGs — see the
    module docstring), but the filenames themselves
    (Registro-Administrativo-Historico_2009-202X-Inicio.xlsx,
    MINEDEC_Metadato_RegistroAdministrativo_2009_2025_Inicio.xlsx) are
    already descriptive, same rationale as helpers/bce_remesas_client.py.
    """
    filename = unquote(url.rsplit("/", 1)[-1])
    stem = filename.rsplit(".", 1)[0]
    stem = _LEADING_DIGIT_RE.sub("", stem)  # CMS ordering prefix: "1", "2", ...
    return _WS_RE.sub(" ", stem.replace("_", " ").replace("-", " ")).strip()

def _classify(filename: str) -> tuple[str, str | None]:
    """(tipo, periodo) from the filename: tipo is registro/metadato/
    diccionario; periodo is inicio/fin/None. Kept deliberately simple —
    see the module docstring for why parsing an exact year range out of
    these filenames is not reliable (they disagree with each other).
    """
    low = filename.lower()
    if "diccionario" in low:
        tipo = "diccionario"
    elif "metadato" in low:
        tipo = "metadato"
    else:
        tipo = "registro"
    if "inicio" in low:
        periodo = "inicio"
    elif "fin" in low:
        periodo = "fin"
    else:
        periodo = None
    return tipo, periodo


def _parse_files(html: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _LINK_RE.finditer(html):
        href = m.group(1)
        url = href if href.startswith("http") else urljoin(_BASE, href)
        if url in seen:
            continue
        seen.add(url)
        filename = unquote(url.rsplit("/", 1)[-1])
        tipo, periodo = _classify(filename)
        fmt = url.rsplit(".", 1)[-1].upper()
        files.append(
            {
                "label": _label_from_url(url),
                "url": url,
                "format": fmt,
                "tipo": tipo,
                "periodo": periodo,
            }
        )
    return files


async def _fetch_files() -> list[dict[str, Any]]:
    cached = _files_cache.get("files")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _files_cache.get("files")
        if cached is not None:
            return cached

        logger.info("Descargando la página de Datos Abiertos del MINEDEC")
        content, truncated = await download_bytes(_PAGE_URL)
        if truncated:
            raise ValueError(f"La página de {_PAGE_URL} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")

        files = _parse_files(html)
        if files:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/bce_remesas_client.py / helpers/contraloria_client.py.
            _files_cache.set("files", files)
        return files


async def search_matricula(query: str = "") -> dict[str, Any]:
    """
    List (optionally filtered) MINEDEC basic-education historical enrollment
    registry files: the Inicio/Fin registry XLSX, their metadata files, and
    the shared data dictionary.

    Args:
        query: Free text matched (accent-insensitive) against the file's
            label, tipo ("registro"/"metadato"/"diccionario"), periodo
            ("inicio"/"fin"), or URL. Empty returns all files.
    """
    files = await _fetch_files()
    q = _strip(query)
    matched = [
        f
        for f in files
        if not q
        or q in _strip(f["label"])
        or q in _strip(f.get("tipo"))
        or q in _strip(f.get("periodo"))
        or q in _strip(f["url"])
    ]
    return {
        "total": len(matched),
        "total_en_pagina": len(files),
        "source": "MINEDEC — Registro Administrativo Histórico (Educación Básica)",
        "url_fuente": _PAGE_URL,
        "archivos": matched,
    }
