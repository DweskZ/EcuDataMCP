"""Client for INEC's dedicated Census 2022 microsite (censoecuador.gob.ec).

Separate domain from ecuadorencifras.gob.ec (though the actual files are
hosted back on that main domain, under documentos/web-inec/bd-censo/... and
dicc-censo/...). Confirmed live: this microsite has the real bulk census
microdata -- sector/canton/city-block level, CSV/SPSS/REDATAM formats, plus
the 2010 and 2001 censuses recoded onto 2022 geography -- and the 2022
results tabulados (XLSX and CSV by theme: population, housing, household,
including the household ICT tables with internet, computer and mobile phone
by province and canton), far more complete than the "Censo de Población y
Vivienda" topic page indexed by helpers/inec_client.py.

Two pages carry the files, both plain server-rendered WordPress/Elementor
HTML, no JSON API behind them:

- /resultados-censo/: presentations, the "Tabulados" tabs (Población,
  Vivienda, Hogar; each entry reads "Name – [Excel] y [CSV]"), the census
  databases and their dictionaries.
- /data-censo-ecuador/: databases, dictionaries, methodology, questionnaire,
  user guide and manuals. The ANDA study for the 2022 census (catalog 1085)
  links here as its only "data file".

The old /data-y-resultados/ URL is now a real 404 ("Página no encontrada")
that only serves the site chrome; treating it as a page of results (as this
client once did) hid every tabulado.

TLS: www.censoecuador.gob.ec's cert chain verifies against the OS trust
store but not httpx's bundled certifi CAs (a missing intermediate, not a
broken cert) -- handled by helpers.tls's OS-trust-store retry tier. Some
networks (GitHub Actions' US-based runners among them) get a 403 from this
host, likely a geo/bot block; that is raised as a distinct error instead of
falling through to the generic "no files found" message.

robots.txt allows everything (`Disallow:` empty) and links a Yoast sitemap.
"""

from __future__ import annotations

import logging
import re
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote

import httpx

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip_accents

logger = logging.getLogger(MAIN_LOGGER_NAME)

RESULTADOS_URL = "https://www.censoecuador.gob.ec/resultados-censo/"
DATA_URL = "https://www.censoecuador.gob.ec/data-censo-ecuador/"
_PAGES = (RESULTADOS_URL, DATA_URL)

_FILE_EXT_RE = re.compile(r"\.(pdf|xlsx|xls|csv|zip|rar|docx?)$", re.IGNORECASE)
_TEMA_HEADINGS = {"población": "poblacion", "vivienda": "vivienda", "hogar": "hogar"}
_GENERIC_LINK_TEXT = re.compile(
    r"^(formato\s+)?(excel|csv|spss|redatam|descargar|acceder|ir a .*|\d{4}|"
    r"cant[oó]n|sector|manzana)?$",
    re.IGNORECASE,
)
_NIVELES = {
    "CANT": "Cantón",
    "CANTON": "Cantón",
    "SECT": "Sector",
    "SECTOR": "Sector",
    "MANLOC": "Manzana",
}

# Search aliases for tabulados whose title does not contain the words a
# researcher types. Checked against the workbook's own index (03_2022_CPV_TIC:
# 5+ population by use of mobile phone, internet, computer/laptop and tablet,
# and households by availability of ICT goods and services, down to cantón).
_ALIASES = {
    "tecnologias de la informacion": (
        "tic internet computadora laptop celular telefono tablet conectividad "
        "brecha digital acceso digital"
    ),
    "servicios basicos": "agua luz electricidad alcantarillado basura",
    "condiciones de vida": "hacinamiento tenencia",
}
_CONTENIDO = {
    "tecnologias de la informacion": (
        "Población de 5+ años por uso de celular, internet, computadora/laptop y "
        "tablet en los últimos 3 meses (provincia y cantón, área, sexo) y hogares "
        "por disponibilidad de bienes y servicios TIC."
    ),
}

# The census files are refreshed rarely; a day balances staleness against
# not re-fetching two 200+ KB pages on every call.
_resources_cache = TtlCache(ttl_seconds=86400.0, max_entries=1)


class _PageParser(HTMLParser):
    """Flatten a page into ordered ("text", s) and ("link", href, text) events."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple[str, ...]] = []
        self._skip = 0
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "a":
            self._href = dict(attrs).get("href")
            self._link_text = []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(self._skip - 1, 0)
        elif tag == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", " ".join(self._link_text)).strip()
            self.events.append(("link", self._href, text))
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self._href is not None:
            self._link_text.append(text)
        else:
            self.events.append(("text", text))


def _label_from_url(url: str) -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    name = name.rsplit(".", 1)[0]
    return unquote(name).replace("_", " ").replace("-", " ").strip()


def _normalize_url(url: str) -> str:
    url = unescape(url).strip()
    if url.startswith("http://www.censoecuador.gob.ec"):
        url = "https://" + url[len("http://") :]
    return url


def _classify(url: str, link_text: str, context: str, tema: str | None) -> dict[str, Any]:
    name = _label_from_url(url)
    ext = _FILE_EXT_RE.search(url).group(1).upper()  # type: ignore[union-attr]
    up = url.upper()
    year_match = re.search(r"(?:^|[/_])(2001|2010|2022)(?:[/_.]|$)", url)
    anio = year_match.group(1) if year_match else None
    if "DICC-CENSO" in up or "DICCIONARIO" in up:
        nivel = next((v for k, v in _NIVELES.items() if re.search(rf"_{k}(?:_|\.)", up)), None)
        label = "Diccionario de variables" + (f" – {nivel}" if nivel else "")
        return {"label": label + (f" {anio}" if anio else ""), "format": ext, "tipo": "diccionario", "anio": anio}
    is_bulk = ext in ("ZIP", "RAR")
    if is_bulk and ("/BD-CENSO/" in up or "/PUBLIC/BBD_CPV" in up or "/PUBLIC/BDD_CPV" in up):
        nivel = next((v for k, v in _NIVELES.items() if re.search(rf"[_/]{k}[_/.]", up)), None)
        if nivel is None and "NACIONAL" in up:
            nivel = "Nacional"
        fmt = next((f for f in ("REDATAM", "SPSS", "SAV", "CSV") if f in up), ext)
        fmt = "SPSS" if fmt == "SAV" else fmt
        recod = " (recodificado a la geografía 2022)" if "CORRESP" in up else ""
        label = f"Base de datos CPV {anio or '2022'} – {nivel or name} – {fmt}{recod}"
        return {"label": label, "format": ext, "tipo": "microdatos", "anio": anio or "2022", "nivel": nivel}
    if "/WP-CONTENT/UPLOADS/" in up and link_text.lower().startswith("formato") and context:
        suffix = "Excel" if ext in ("XLSX", "XLS") else "CSV"
        label = f"{context} – {suffix}"
        entry: dict[str, Any] = {"label": label, "format": ext, "tipo": "tabulado", "anio": "2022"}
        if tema:
            entry["tema"] = tema
        return entry
    label = link_text if link_text and not _GENERIC_LINK_TEXT.match(link_text) else name
    label = re.sub(r"^Descargar\s+", "", label)
    return {"label": label, "format": ext, "tipo": "documento"}


def parse_page(html: str) -> list[dict[str, Any]]:
    """Every census file linked from one page, with a descriptive label and tipo."""
    parser = _PageParser()
    parser.feed(html)
    out: list[dict[str, Any]] = []
    tema: str | None = None
    context = ""
    for event in parser.events:
        if event[0] == "text":
            text = event[1]
            key = text.lower()
            if key in _TEMA_HEADINGS:
                tema = _TEMA_HEADINGS[key]
                continue
            if key.startswith("datos") and "histórico" in key:
                tema = None
            if len(text) > 3 and key != "formato excel":
                context = text.rstrip(" –-—:").strip()
            continue
        _, href, link_text = event
        url = _normalize_url(href)
        if not url.startswith("http") or not _FILE_EXT_RE.search(url):
            continue
        out.append({"url": url, **_classify(url, link_text, context, tema)})
    return out


def _enrich(entry: dict[str, Any]) -> dict[str, Any]:
    key = _strip_accents(entry["label"])
    for needle, aliases in _ALIASES.items():
        if needle in key:
            entry["palabras_clave"] = aliases
    for needle, contenido in _CONTENIDO.items():
        if needle in key:
            entry["contenido"] = contenido
    return entry


async def _fetch_page(url: str) -> str:
    try:
        content, truncated = await download_bytes(url)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise ValueError(
            f"censoecuador.gob.ec respondió HTTP {status} en {url} en lugar de la "
            "página de resultados -- si es 403 es probablemente un bloqueo "
            "geográfico/anti-bot del portal; si es 404, el sitio cambió de "
            "estructura. Prueba conectando desde una VPN con salida en algún país "
            "de la región si el problema persiste."
        ) from exc
    if truncated:
        raise ValueError(f"La página {url} del censo superó el límite de descarga")
    return content.decode("utf-8", errors="replace")


async def _fetch_resources() -> list[dict[str, Any]]:
    cached = _resources_cache.get("resources")
    if cached is not None:
        return cached

    seen: dict[str, dict[str, Any]] = {}
    for page_url in _PAGES:
        for entry in parse_page(await _fetch_page(page_url)):
            seen.setdefault(entry["url"], entry)

    resources = [_enrich(e) for e in seen.values()]
    if not resources:
        raise ValueError(
            "No se encontraron archivos en las páginas de resultados del censo "
            "(puede haber cambiado de estructura)"
        )
    _resources_cache.set("resources", resources)
    return resources


async def search_censo_recursos(query: str = "", limit: int = 30, offset: int = 0) -> dict[str, Any]:
    """
    Search the direct file links published on INEC's Census 2022 microsite.

    Covers the results tabulados (population, housing, household incl. ICT;
    XLSX and CSV-in-ZIP), full microdata (sector/cantón/manzana, CSV/SPSS/
    REDATAM), variable dictionaries, methodology/quality documents, and the
    2010/2001 censuses recoded onto 2022 geography.

    Args:
        query: Free text; every word must match (accent-insensitive) the
            file's label, tipo, tema or search aliases, e.g. "internet",
            "tabulado hogar", "manzana", "diccionario", "2010", "spss". Empty
            returns every resource found.
        limit: Max results returned.
        offset: Pagination offset over the matched set.
    """
    resources = await _fetch_resources()
    words = _strip_accents(query).split()

    def blob(r: dict[str, Any]) -> str:
        parts = (r["label"], r.get("tipo"), r.get("tema"), r.get("anio"), r.get("palabras_clave"))
        return _strip_accents(" ".join(str(p) for p in parts if p))

    matched = [r for r in resources if all(w in blob(r) for w in words)]
    page = matched[offset : offset + limit]
    return {
        "source_url": RESULTADOS_URL,
        "total": len(matched),
        "total_recursos": len(resources),
        "offset": offset,
        "recursos": page,
    }
