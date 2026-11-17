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
import html
import logging
import re
from typing import Any
from urllib.parse import unquote, urljoin

import httpx

from helpers.cache import TtlCache
from helpers.csv_reader import _decode_text, download_bytes
from helpers.geo_proxy import unreachable_hint
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


async def _download(url: str) -> tuple[bytes, bool]:
    """download_bytes, naming the host when the connection never completes.

    educacion.gob.ec drops connections from outside Ecuador (checked
    2026-11-07 from Canada and from GitHub's runners; it is on the geo-proxy
    list), and a bare ConnectTimeout stringifies to "".
    """
    try:
        return await download_bytes(url)
    except httpx.HTTPStatusError:
        raise
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"No se pudo conectar a {httpx.URL(url).host} ({type(exc).__name__}). "
            + unreachable_hint(url)
        ) from exc


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
        content, truncated = await _download(_PAGE_URL)
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


# -- per-school-year registers and thematic files (base-de-datos/) ------------

# A sibling page, educacion.gob.ec/base-de-datos/, splits the same AMIE
# registry by school year: for every year from 2009-2010 to 2024-2025 an
# "Inicio" and a "Fin" cut, each as XLSX and as a CSV twin (2_...csv), with
# its own dictionary and metadata. It also links thematic files through the
# download-monitor plugin (school connectivity, intercultural bilingual
# schools, typology 2024-2025, early-childhood family service, the violence
# victims support plan) and the 1993-1994 to 2006-2007 statistics with their
# bulletins. Built from a 2026-01 archived copy: educacion.gob.ec drops
# connections from outside Ecuador, GitHub's runners included, so it goes
# through the geo proxy when one is configured.
_BASES_URL = "https://educacion.gob.ec/base-de-datos/"
_REG_HREF_RE = re.compile(
    r'href="((?:https?:)?//educacion\.gob\.ec/wp-content/uploads/downloads/[^"]*?'
    r'Registros?Administrativos?_(\d{4})-(\d{4})-?(Inicio|Fin)\.(xlsx|csv))"',
    re.IGNORECASE,
)
_DLM_RE = re.compile(
    r'<a[^>]+href="([^"]*download-monitor/download\.php\?id=(\d+)[^"]*)"[^>]*>(.*?)</a>', re.DOTALL
)
_bases_cache = TtlCache(ttl_seconds=43200.0, max_entries=1, persist="minedec_bases")


def _bases_tipo(name: str, ext: str) -> str:
    low = name.lower()
    if "diccionario" in low:
        return "diccionario"
    if "metadato" in low:
        return "metadato"
    return f"registro_{ext.lower()}"


def parse_bases(page: str) -> list[dict[str, Any]]:
    """Per-year registry files and thematic downloads from base-de-datos/."""
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for href, y1, y2, corte, ext in _REG_HREF_RE.findall(page):
        url = "https:" + href if href.startswith("//") else href
        if url in seen:
            continue
        seen.add(url)
        tipo = _bases_tipo(url.rsplit("/", 1)[-1], ext)
        files.append(
            {
                "titulo": f"Registro administrativo {y1}-{y2} {corte} ({tipo.replace('_', ' ')})",
                "url": url,
                "formato": ext.upper(),
                "tipo": tipo,
                "periodo": f"{y1}-{y2}",
                "corte": corte.capitalize(),
            }
        )
    for href, ident, inner in _DLM_RE.findall(page):
        url = html.unescape(href)
        if url in seen:
            continue
        seen.add(url)
        label = _WS_RE.sub(" ", re.sub(r"<[^>]+>", " ", html.unescape(inner))).strip()
        label = re.sub(r"\s*\(\d+\)$", "", label)  # trailing download counter
        historic = re.fullmatch(r"(?:Bolet[ií]n electr[oó]nico )?(19|20)\d\d-(19|20)\d\d", label)
        files.append(
            {
                "titulo": label or f"Archivo {ident}",
                "url": url,
                "formato": None,
                "tipo": "historico_1993_2007" if historic else "tematico",
                "periodo": re.search(r"\d{4}-\d{4}", label).group(0) if re.search(r"\d{4}-\d{4}", label) else None,
                "corte": None,
            }
        )
    return files


async def _fetch_bases_fresh() -> list[dict[str, Any]]:
    cached = _bases_cache.get("bases")
    if cached is not None:
        return cached
    raw, truncated = await _download(_BASES_URL)
    if truncated:
        raise ValueError(f"La página {_BASES_URL} superó el límite de descarga.")
    files = parse_bases(_decode_text(raw))
    if files:
        _bases_cache.set("bases", files)
    return files


async def _fetch_bases() -> list[dict[str, Any]]:
    """Fresh fetch, or the last good copy when the source fails (see TtlCache.serve_stale)."""
    try:
        return await _fetch_bases_fresh()
    except Exception as exc:
        stale = _bases_cache.serve_stale("bases", exc)
        if stale is None:
            raise
        return stale


async def search_bases(query: str = "") -> dict[str, Any]:
    """Per-year AMIE registers (XLSX and CSV) and MINEDEC thematic files."""
    files = await _fetch_bases()
    q = _strip(query)
    matched = [
        f for f in files
        if not q or q in _strip(f"{f['titulo']} {f['tipo']} {f['periodo'] or ''} {f['corte'] or ''}")
    ]
    return {
        "source": "MINEDEC — bases de datos por año lectivo (AMIE) y archivos temáticos",
        "url_fuente": _BASES_URL,
        "nota": (
            "Un registro por año lectivo 2009-2010 a 2024-2025, corte Inicio o Fin, en XLSX "
            "y en CSV (tipo registro_csv), con diccionario y metadato. Pide 'csv 2024-2025' "
            "para el más reciente. Los archivos temáticos (tipo tematico) no declaran formato."
        ),
        "archivos": matched,
    }
