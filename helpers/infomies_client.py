"""Client for infoMIES (info.desarrollohumano.gob.ec) — the statistics
sub-portal of what used to be MIES (Ministerio de Inclusión Económica y
Social), now folded into "Ministerio de Trabajo y Desarrollo Humano". Found
in a prior research pass via the "Fuente original" field of a real CKAN
dataset (see RESEARCH.md's "MIES/Ministerio de Desarrollo Humano, portal
infoMIES" entry) after mies.gob.ec/inclusion.gob.ec/desarrollohumano.gob.ec
all proved dead. This is a Joomla site (Phoca Download component) that
requires `curl --ssl-no-revoke` / an httpx client (not schannel) to reach at
all from this environment — same local TLS-stack quirk already documented
for helpers/arcotel_client.py, not a portal-side block: no login, no
CAPTCHA, plain GET.

Re-verified live 2026-09-03 (today), not assumed from the prior pass — and
it turned up real, meaningful differences from that pass, not just
confirmation:

- **The site's nav was reorganized since 2026-08-30** (menu items renamed
  to `servicios-de-inclusion-economica-usrext`/`...-social-usrext`), but the
  underlying content pages the prior pass found kept their old URLs/slugs
  (`usuarios-de-inclusion-economica/usuarios-externos-ie/...`,
  `usuarios-y-unidades-de-inclusion-social/usuarios-externos-is/...`) —
  still reachable, just no longer directly linked from the top nav. Same
  "URL outlives the nav" pattern already seen elsewhere in this project.
- **The "monthly databases" claim only holds for the current, in-progress
  year.** Confirmed by fetching every year 2019-2026 for both series: 2026
  (today) lists one file per month so far published (Jan-Jul for both ANC
  and IS as of this check); every *closed* year (2019-2025) lists exactly
  **one** file, labeled "DICIEMBRE" — the year-end snapshot, not a monthly
  archive. The prior research pass's "años 2019-2026 confirmados" was
  correct about the *years existing*, but its "Bases de datos MENSUALES"
  framing over-generalized from the one live year it happened to check
  (2026, mid-year). Treat this client's output as ground truth over that
  framing: for a closed year, expect one file.
- **A real "Boletines Zonales" successor exists that the prior pass never
  found**: `/index.php/reportes-boletines-zonales/reportes-boletines-zonales-{año}`,
  one consolidated **XLSX** (not .rar) per year, **2021-2026 and still being
  updated** (the 2026 file is 9.5 MB, `Content-Disposition` filename
  `boletines_zonales_jul2026.xlsx` — current as of this check), confirmed
  via the site's own search (`?searchword=boletin+zonal`), not linked from
  any nav menu found in this pass either. This is a different, actively
  maintained series from the old per-zone/per-month `zona-N-bz` bulletins
  below — surfaced separately by search_reportes_boletines_zonales.
  Ministry data-quality note, confirmed live: the year-page and the
  file's own internal filename regularly disagree (the "2022" year-page's
  file is internally named `boletines_zonales_2023.xlsx`) — same
  "ministry file naming is internally inconsistent" pattern already
  documented for helpers/minedec_client.py; treat the *page's* year as
  authoritative for cataloging (it's what determines which URL serves
  which snapshot), not the filename.
- **The old per-zone "Boletín Zonal" bulletins are confirmed discontinued**
  after 2021, across all 9 zones sampled (zona-1, zona-9) — 2017-2021, no
  2022+ page exists (real HTTP 404, "Categoría no encontrada"). Unlike the
  prior pass (which only link-counted these, never downloaded one), this
  pass confirmed the real format via HEAD: `.rar`
  (`Content-Type: application/x-rar-compressed`, e.g. "Reporte Zonal
  Noviembre.rar", ~1 MB for a single zone-month) — same format decision as
  the monthly BDD files below.
- The prior pass's guessed URL shape for these
  (`usuarios-de-inclusion-economica/boletin-zonal/zona-1-bz/2021-bz1`) does
  **not** exist (404) — the real path has no `usuarios-de-inclusion-
  economica/boletin-zonal/` prefix, it's just `/index.php/zona-N-bz/{año}-bzN`,
  reachable from `/index.php/usuarios-de-inclusion-economica/category/79-
  boletines-zonales` (a page the prior pass never opened). Each zone's own
  index page (`/index.php/zona-N-bz`) lists that zone's real year
  sub-pages, so this client discovers years from there instead of
  hardcoding them.
- Label conventions are not stable across years within the same zone: 2017
  uses "BOLETÍN - <mes>" while 2021 uses "REPORTE ZONAL - <mes>" for the
  same zone/series — the parser below doesn't depend on either wording, it
  reads the Phoca item structure generically (see _parse_phoca_items).

The two monthly BDD download links (`?download=ID:slug`) were confirmed to
be plain, unauthenticated GETs — no session cookie, no Referer needed (a
bare `curl -I` with no prior request returns the real file headers
directly), same as SIPA/Superbancos/MINEDEC's large-file portals.

Because the BDD/Boletín Zonal files are `.rar` (explicitly out of scope for
this project — see CLAUDE.md/ROADMAP.md's "Formatos y tipos de recursos"
section: subprocess/CVE risk, never read, only cataloged) and even the XLSX
consolidated report is 9-15 MB (over this project's 5 MB download/preview
cap — see helpers/csv_reader.MAX_DOWNLOAD_BYTES), this client, like
helpers/sipa_client.py/helpers/minedec_client.py, never fetches file bytes
server-side for the catalogued files. It only scrapes each listing page for
metadata + the direct URL; point the model at the URL directly.

Two embedded Power BI dashboards (`/index.php/sinepidpam`,
"reportes-dinamicos" under `/index.php/informacion`) remain unautomated,
same rationale as SUT/Superbancos (no export API for these tenants).
`geoportal.desarrollohumano.gob.ec` was tried again this pass and still
doesn't resolve/connect cleanly (a different TLS failure than the
`--ssl-no-revoke` one worked around above) — left unexplored, out of scope
for this pass. `/index.php/biblioteca`, `/index.php/documentos-
metodologicos`, `/index.php/estudios` all load (HTTP 200) but weren't
inspected beyond that — still unexplored, as in the prior pass.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from typing import Any

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://info.desarrollohumano.gob.ec"

# --- Bases mensuales (ANC / IS) --------------------------------------------

_ANC_BASE = f"{_BASE}/index.php/usuarios-de-inclusion-economica/usuarios-externos-ie"
_IS_BASE = f"{_BASE}/index.php/usuarios-y-unidades-de-inclusion-social/usuarios-externos-is"

# Year ranges confirmed live 2026-09-03 (see module docstring). These are
# hardcoded (not discovered) because, unlike the Boletín Zonal pages below,
# no index page on the site lists them — the parent category pages for both
# series render with zero sub-links. Will go stale for 2027+ the same way
# every other hardcoded-year-range client in this project does; a request
# for a year outside the known range raises rather than silently 404ing.
_SERIES: dict[str, dict[str, Any]] = {
    "anc": {
        "nombre": "Aseguramiento No Contributivo (usuarios de inclusión económica)",
        "anios": {year: f"{_ANC_BASE}/{year}-bdd-anc" for year in range(2019, 2027)},
    },
    "is": {
        "nombre": "Usuarios de Unidad de Atención del SIIMIES (inclusión social)",
        "anios": {
            **{year: f"{_IS_BASE}/{year}-externos-is" for year in range(2020, 2027)},
            # Real slug quirk confirmed live: 2019 alone carries a "-2"
            # suffix ("2019-externos-is-2"); the unsuffixed
            # "2019-externos-is" page exists but is empty (a duplicate/
            # abandoned Joomla menu item, not this series' real page).
            2019: f"{_IS_BASE}/2019-externos-is-2",
        },
    },
}

# --- Boletín Zonal (per zone, discontinued 2021) ---------------------------

_ZONAS = [f"zona-{n}-bz" for n in range(1, 10)]
_YEAR_LINK_RE = re.compile(r'href="(/index\.php/zona-\d+-bz/\d{4}-bz\d+)"')

# --- Reporte Boletines Zonales (consolidated annual XLSX, still updated) ---

_RBZ_BASE = f"{_BASE}/index.php/reportes-boletines-zonales"
_RBZ_ANIOS = {
    year: f"{_RBZ_BASE}/reportes-boletines-zonales-{year}" for year in range(2021, 2027)
}

# Pages are Phoca Download listings refreshed monthly at most (new BDD file
# or zonal report a few times a year) -- a few hours balances staleness
# against re-fetching/re-parsing on every call, same rationale as every
# other TtlCache in this project. One shared cache keyed by page URL since
# all three series above share the exact same page shape.
_page_cache = TtlCache(ttl_seconds=21600.0, max_entries=256)
_zona_index_cache = TtlCache(ttl_seconds=21600.0, max_entries=len(_ZONAS))
_fetch_lock = asyncio.Lock()

# Phoca's file-type icon is the only type signal in the listing HTML itself
# (no Content-Type/size shown until you fetch the file) -- confirmed live,
# only "rar" (BDD + Boletín Zonal files) and "spreadsheet" (the consolidated
# Reporte Boletines Zonales) seen so far; anything else falls back to the
# icon name itself, uppercased.
_ICON_FORMATS = {"rar": "RAR", "spreadsheet": "XLSX", "pdf": "PDF", "zip": "ZIP", "word": "DOCX"}

_ITEM_SPLIT_RE = re.compile(r'<div class="pd-filebox">')
_ICON_RE = re.compile(r"icon-(?P<icon>[a-z0-9]+)\.png")
# Phoca renders two anchors per file: the informative one
# (`<a class="" href="...">LABEL</a>`, inside a `pd-float` div) and a
# "Descarga" button (`<a class="btn btn-success" href="...">Descarga</a>`)
# pointing at the same URL with no useful label. Matching on the exact
# empty `class=""` deliberately skips the second, so no separate dedup step
# is needed (unlike helpers/sipa_client.py's equivalent parser).
_LINK_RE = re.compile(r'<a class="" href="(?P<href>[^"]+)"[^>]*>(?P<label>[^<]*)</a>')
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", unescape(_TAG_RE.sub("", text))).strip()


def _format_from_icon(icon: str | None) -> str:
    if icon is None:
        return "DESCONOCIDO"
    return _ICON_FORMATS.get(icon, icon.upper())


def _parse_phoca_items(page_html: str) -> list[dict[str, Any]]:
    """Parse one Phoca Download category page's file listing.

    Layout confirmed live (2026-09-03) and shared across every infoMIES
    page this client touches -- see module docstring for the label-wording
    caveat (2017 vs 2021) this parser deliberately doesn't depend on.
    """
    items: list[dict[str, Any]] = []
    for chunk in _ITEM_SPLIT_RE.split(page_html)[1:]:
        link_m = _LINK_RE.search(chunk)
        if link_m is None:
            continue
        icon_m = _ICON_RE.search(chunk)
        href = link_m.group("href")
        url = href if href.startswith("http") else _BASE + href
        items.append(
            {
                "label": _clean(link_m.group("label")),
                "url": url,
                "format": _format_from_icon(icon_m.group("icon") if icon_m else None),
            }
        )
    return items


async def _fetch_page_items(url: str) -> list[dict[str, Any]]:
    cached = _page_cache.get(url)
    if cached is not None:
        return cached
    async with _fetch_lock:
        cached = _page_cache.get(url)
        if cached is not None:
            return cached
        logger.info("Descargando página de infoMIES: %s", url)
        content, truncated = await download_bytes(url)
        if truncated:
            raise ValueError(f"La página de {url} superó el límite de descarga.")
        html_text = content.decode("utf-8", errors="replace")
        items = _parse_phoca_items(html_text)
        # Unlike most scrapers in this project, an empty result IS cached
        # here: confirmed live that a genuinely out-of-range year (e.g.
        # ANC 2018/2027) and a valid-but-not-yet-published month both
        # render the exact same "0 files" page shape -- there's no
        # "looks broken, don't trust it" signal to withhold caching on,
        # and re-fetching an empty page every call would defeat the point
        # of the cache for exactly the years callers are likeliest to
        # probe speculatively.
        _page_cache.set(url, items)
        return items


async def _fetch_zona_anios(zona: str) -> list[str]:
    """Discover the year sub-pages actually linked from one zone's index
    page. Scraped rather than hardcoded (unlike _SERIES above) because,
    unlike the BDD category pages, each zone's index page DOES list its
    real years -- confirmed live: 2017-2021 for every sampled zone."""
    cached = _zona_index_cache.get(zona)
    if cached is not None:
        return cached
    async with _fetch_lock:
        cached = _zona_index_cache.get(zona)
        if cached is not None:
            return cached
        url = f"{_BASE}/index.php/{zona}"
        logger.info("Descargando índice de años de la zona infoMIES: %s", zona)
        content, truncated = await download_bytes(url)
        if truncated:
            raise ValueError(f"La página de {url} superó el límite de descarga.")
        html_text = content.decode("utf-8", errors="replace")
        urls = sorted({_BASE + m.group(1) for m in _YEAR_LINK_RE.finditer(html_text)})
        if urls:
            _zona_index_cache.set(zona, urls)
        return urls


def _matches(item: dict[str, Any], q: str) -> bool:
    if not q:
        return True
    anio_str = str(item.get("anio") or "")
    return q in _strip(item["label"]) or q in _strip(item["url"]) or q in _strip(anio_str)


def list_zonas() -> list[str]:
    """The 9 fixed infoMIES "Boletín Zonal" zone keys (zona-1-bz .. zona-9-bz)."""
    return list(_ZONAS)


async def search_bases_mensuales(
    serie: str, anio: int | None = None, query: str = ""
) -> dict[str, Any]:
    """
    List infoMIES's monthly BDD (base de datos) files for one program.

    Args:
        serie: "anc" (Aseguramiento No Contributivo / inclusión económica)
            or "is" (Usuarios de Unidad de Atención del SIIMIES / inclusión
            social).
        anio: Specific year to fetch (e.g. 2024). Omit to fetch every known
            year and aggregate -- note this means multiple HTTP requests on
            a cold cache. A closed year (anything before the current one)
            returns exactly one file (the December/year-end snapshot); only
            the current, in-progress year has one file per month so far
            published -- see module docstring.
        query: Free text matched (accent-insensitive) against the file's
            label, year, or URL. Empty returns all files for the selected
            year(s).
    """
    info = _SERIES.get(serie)
    if info is None:
        valid = ", ".join(sorted(_SERIES))
        raise ValueError(f"Serie '{serie}' no reconocida. Válidas: {valid}")

    anios_disponibles = sorted(info["anios"])
    if anio is not None:
        if anio not in info["anios"]:
            raise ValueError(
                f"Año {anio} no está en el rango conocido para '{serie}' "
                f"({anios_disponibles[0]}-{anios_disponibles[-1]})."
            )
        anios = [anio]
    else:
        anios = anios_disponibles

    archivos: list[dict[str, Any]] = []
    for a in anios:
        url = info["anios"][a]
        for item in await _fetch_page_items(url):
            archivos.append({**item, "anio": a, "url_pagina": url})

    q = _strip(query)
    matched = [f for f in archivos if _matches(f, q)]
    return {
        "total": len(matched),
        "total_en_pagina": len(archivos),
        "source": f"infoMIES — {info['nombre']}",
        "serie": serie,
        "archivos": matched,
    }


async def get_boletines_zonales(
    zona: str, anio: int | None = None, query: str = ""
) -> dict[str, Any]:
    """
    List infoMIES's (discontinued) "Boletín Zonal" monthly bulletin files
    for one zone.

    Confirmed live range 2017-2021 across all 9 zones -- no 2022+ bulletin
    exists on any sampled zone (a real HTTP 404, not an empty page). Files
    are .rar (confirmed via HEAD on a sample) -- cataloged, never read. For
    the actively-updated successor series, use
    search_reportes_boletines_zonales instead.

    Args:
        zona: One of list_zonas()'s keys, e.g. "zona-1-bz".
        anio: Specific year to fetch. Omit to fetch every year linked from
            that zone's index page (typically 2017-2021 -- multiple HTTP
            requests on a cold cache).
        query: Free text matched (accent-insensitive) against the file's
            label, year, or URL.
    """
    if zona not in _ZONAS:
        raise ValueError(f"Zona '{zona}' no reconocida. Válidas: {', '.join(_ZONAS)}")

    zona_num = zona.split("-")[1]
    anio_urls = await _fetch_zona_anios(zona)
    if anio is not None:
        suffix = f"/{anio}-bz{zona_num}"
        anio_urls = [u for u in anio_urls if u.endswith(suffix)]
        if not anio_urls:
            raise ValueError(f"No se encontró la página del año {anio} para '{zona}'.")

    archivos: list[dict[str, Any]] = []
    for url in anio_urls:
        anio_m = re.search(r"/(\d{4})-bz\d+$", url)
        a = int(anio_m.group(1)) if anio_m else None
        for item in await _fetch_page_items(url):
            archivos.append({**item, "anio": a, "url_pagina": url})

    q = _strip(query)
    matched = [f for f in archivos if _matches(f, q)]
    return {
        "total": len(matched),
        "total_en_pagina": len(archivos),
        "source": f"infoMIES — Boletín Zonal ({zona})",
        "zona": zona,
        "archivos": matched,
    }


async def search_reportes_boletines_zonales(
    anio: int | None = None, query: str = ""
) -> dict[str, Any]:
    """
    List infoMIES's "Reporte Boletines Zonales" consolidated annual XLSX --
    one workbook per year, confirmed live 2021-2026 and still being
    updated (the 2026 file is dated as recently as July 2026 in its own
    filename). This is a different, newer series from the discontinued
    per-zone-per-month .rar bulletins in get_boletines_zonales, and wasn't
    found by this project's prior infoMIES research pass -- surfaced this
    time via the site's own search, since no nav menu links it directly.
    Files are ~9-15 MB, past this project's download/preview cap --
    cataloged, not fetched server-side.

    Args:
        anio: Specific year (2021-2026). Omit to fetch every year.
        query: Free text matched (accent-insensitive) against the file's
            label, year, or URL.
    """
    anios_disponibles = sorted(_RBZ_ANIOS)
    if anio is not None:
        if anio not in _RBZ_ANIOS:
            raise ValueError(
                f"Año {anio} no está en el rango conocido "
                f"({anios_disponibles[0]}-{anios_disponibles[-1]})."
            )
        anios = [anio]
    else:
        anios = anios_disponibles

    archivos: list[dict[str, Any]] = []
    for a in anios:
        url = _RBZ_ANIOS[a]
        for item in await _fetch_page_items(url):
            archivos.append({**item, "anio": a, "url_pagina": url})

    q = _strip(query)
    matched = [f for f in archivos if _matches(f, q)]
    return {
        "total": len(matched),
        "total_en_pagina": len(archivos),
        "source": "infoMIES — Reporte Boletines Zonales (consolidado anual)",
        "archivos": matched,
    }
