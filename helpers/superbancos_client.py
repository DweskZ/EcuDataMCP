"""Client for the Superintendencia de Bancos' statistics portal
(superbancos.gob.ec/estadisticas/portalestudios/), a WordPress site distinct
from the institutional site (/bancos/). No CKAN organization exists for this
source and there is no "datos abiertos" section anywhere on the domain.

Four sections are scraped here, all sharing the same TablePress-based table
markup (Elementor + the "TablePress" plugin), except the calendar which uses
a small "feature list" widget instead:

- boletines_financieros: monthly financial bulletins (/bancos/).
- servicios_financieros: cards, ATMs, non-bank correspondents, offices
  (/servicios-financieros/).
- informacion_historica: comparative annual behavior of public banks/CFN/
  BanEcuador/Banco de Desarrollo, plus Reporte de Estabilidad Financiera
  (/informacion-historica/).
- calendario_estadistico: 1-2 current-year publication calendars, linked
  from the portal home page footer.

boletines_financieros also merges in the years the static table misses,
via the site's "WP Cloud Plugin — Share-one-Drive" widget
(wp-content/plugins/onedrive) that lazy-loads recent years from a OneDrive
folder client-side. That widget's AJAX protocol WAS reverse-engineered
2026-08-30 by driving it in a real browser and capturing the request it
fires: POST wp-admin/admin-ajax.php, action=shareonedrive-get-filelist,
with listtoken/account_id/drive_id (from the widget's data-* attributes)
and _ajax_nonce (from the page's inline `ShareoneDrive_vars.refresh_nonce`)
-- all four values are embedded in the page's own static HTML, so no
browser or session/cookie is needed to replicate it (verified with a bare
httpx.post, no cookies). The download URLs it returns are themselves a
same-site admin-ajax.php proxy (action=shareonedrive-download), not
short-lived Microsoft Graph signed URLs -- they are stable, confirmed by
requesting the same URL twice. See _wpcp_list_year_folders/_wpcp_get_filelist
below.

servicios_financieros has NOT been extended the same way: unlike bancos/
(one widget), that page embeds *three* separate OneDrive widgets (distinct
listtoken per widget -- confirmed live) sitting under different headings
("Solicitudes de Servicios Financieros, Canales y Medios de Pago",
"Resoluciones de Servicios Financieros, Tarjetas y Canales", and a third
with no heading found in the 3000 chars before it, likely the "Estadísticas
Puntos de Atención" consolidation the page's own text mentions) -- the
protocol is the same, but mapping widget -> section label needs a closer
look at that page specifically before wiring it up. So for
servicios_financieros this client still only returns the static
TablePress archive tables (through ~abril 2021); informacion_historica has
no such widget at all. Do not describe boletines_financieros' coverage as
complete/unbounded either -- it now spans the static "OTROS AÑOS" table
(1997-2008) plus every OneDrive year folder found live (2009 through the
current year), which is still whatever the portal has actually uploaded,
not a guarantee of month-by-month completeness within a year.

Files are never downloaded here — only metadata and the direct URL, same
pattern as helpers/sipa_client.py (some boletines are 5+ MB ZIPs, well over
this project's 5 MB cap). The OneDrive download-proxy URLs are the one
exception to "URL carries the file extension" -- format is derived from
the file name instead for those entries.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.tls import os_trust_context, should_retry_with_os_trust
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://www.superbancos.gob.ec/estadisticas/portalestudios"

_SECCIONES: list[dict[str, str]] = [
    {
        "seccion": "boletines_financieros",
        "nombre": "Boletines Financieros Mensuales (1997-2008 estático + años recientes vía OneDrive)",
        "url": f"{_BASE}/bancos/",
    },
    {
        "seccion": "servicios_financieros",
        "nombre": (
            "Servicios Financieros — tarjetas, oficinas, cajeros y corresponsales "
            "(hasta ~abril 2021; ver docstring)"
        ),
        "url": f"{_BASE}/servicios-financieros/",
    },
    {
        "seccion": "informacion_historica",
        "nombre": (
            "Información Histórica — comportamiento financiero anual "
            "(banca pública/CFN/BanEcuador/Banco de Desarrollo) y "
            "Reporte de Estabilidad Financiera"
        ),
        "url": f"{_BASE}/informacion-historica/",
    },
    {
        "seccion": "calendario_estadistico",
        "nombre": "Calendario Estadístico (año vigente y anterior)",
        "url": f"{_BASE}/",
    },
]
_SECCIONES_BY_KEY = {s["seccion"]: s for s in _SECCIONES}

# Section pages change a few times a year at most (a new archived year, a
# new calendar). max_entries matches the fixed key space.
_files_cache = TtlCache(ttl_seconds=21600.0, max_entries=len(_SECCIONES))
_fetch_lock = asyncio.Lock()

_TAG_RE = re.compile(r"<[^>]+>")
_KNOWN_FORMATS = {"XLSX", "XLS", "CSV", "PDF", "ZIP", "DOCX", "DOC"}

_TABLE_RE = re.compile(r'<table id="tablepress-\d+"[^>]*>(?P<body>.*?)</table>', re.DOTALL)
_ROW_RE = re.compile(r"<tr[^>]*>(?P<row>.*?)</tr>", re.DOTALL)
_CELL_RE = re.compile(r"<(?:td|th)(?P<attrs>[^>]*)>(?P<cell>.*?)</(?:td|th)>", re.DOTALL)
_LINK_RE = re.compile(r'<a\s+href="(?P<url>[^"]+)"[^>]*>(?P<label>.*?)</a>', re.DOTALL)
_COLSPAN_RE = re.compile(r'colspan="\d+"')
_PERIODO_RE = re.compile(r"^año\b", re.IGNORECASE)

# Matched directly on the anchor text rather than a specific containing
# widget: the two calendar links observed live sit in two different
# Elementor widgets (an "icon-box" for the current year, a "feature-list"
# for the previous one) with no shared wrapper markup.
_CALENDARIO_RE = re.compile(
    r'<a\s+href="(?P<url>[^"]+)"[^>]*>\s*(?P<label>Calendario\s+Estad[ií]stico[^<]*?)\s*</a>',
    re.IGNORECASE,
)

# --- OneDrive widget ("WP Cloud Plugin — Share-one-Drive") ---
# The widget's own container div carries these as single-quoted HTML
# attributes (double quotes everywhere else on the site); the nonce lives
# in a separate inline <script> as a JSON-ish var, double-quoted as usual.
_WPCP_TOKEN_RE = re.compile(r"data-token='([0-9a-f]{32})'")
_WPCP_ACCOUNT_RE = re.compile(r"data-account-id='([0-9a-f-]{36})'")
_WPCP_DRIVE_RE = re.compile(r"data-drive-id='([^']+)'")
_WPCP_NONCE_RE = re.compile(r'"refresh_nonce":"(\d+)"')
_WPCP_YEAR_FOLDER_RE = re.compile(r"^Año \d{4}$")

_WPCP_AJAX_URL = f"{_BASE}/wp-admin/admin-ajax.php"

# The filelist response's "html" field uses the same single-quoted-attribute
# style as the widget container. Split-then-search-per-chunk, same pattern
# as helpers/sipa_client.py's accordion-item parsing, rather than one
# monolithic regex across an <a> tag that itself contains other quoted
# attributes in an unpredictable order.
#
# The name comes from this <a> tag's OWN data-name (e.g. "BOLETIN....zip"),
# not the outer <div class='entry file' data-name='...'> a few chars
# earlier -- that outer one is missing the extension (confirmed live), so
# pulling from there silently broke format detection for every OneDrive
# entry until caught by inspecting real output, not just by the regex
# matching successfully.
_WPCP_FILE_ENTRY_SPLIT_RE = re.compile(r"<div class='entry file '")
_WPCP_FILE_LINK_RE = re.compile(
    r"<a href='(?P<url>[^']+)'\s+class='entry_link entry_action_download'"
    r"[^>]*?data-name='(?P<name>[^']*)'"
)
_WPCP_FILE_MODIFIED_RE = re.compile(
    r"<div class='entry-info-modified-date entry-info-metadata'>(?P<modified>[^<]*)</div>"
)
_WPCP_FILE_SIZE_RE = re.compile(
    r"<div class='entry-info-size entry-info-metadata'>(?P<size>[^<]*)</div>"
)


def _clean(text: str) -> str:
    return unescape(_TAG_RE.sub("", text)).strip()


def _clean_formato(url: str) -> str:
    ext = url.rsplit(".", 1)[-1].upper() if "." in url.rsplit("/", 1)[-1] else ""
    return ext if ext in _KNOWN_FORMATS else "DESCONOCIDO"


def _is_superbancos_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "superbancos.gob.ec" or host.endswith(".superbancos.gob.ec")


def _formato_from_name(name: str) -> str:
    """Same as _clean_formato but keyed off a file name, not a URL -- the
    OneDrive download-proxy URL never carries the file's real extension."""
    ext = name.rsplit(".", 1)[-1].upper() if "." in name else ""
    return ext if ext in _KNOWN_FORMATS else "DESCONOCIDO"


def _extract_wpcp_params(html: str) -> dict[str, str] | None:
    """Pull the OneDrive widget's identifying params out of a section
    page's static HTML. Returns None if the page has no such widget (or,
    on a page with more than one, of the wrong widget) -- both mean "no
    OneDrive data available here", not an error."""
    token_m = _WPCP_TOKEN_RE.search(html)
    account_m = _WPCP_ACCOUNT_RE.search(html)
    drive_m = _WPCP_DRIVE_RE.search(html)
    nonce_m = _WPCP_NONCE_RE.search(html)
    if not (token_m and account_m and drive_m and nonce_m):
        return None
    return {
        "listtoken": token_m.group(1),
        "account_id": account_m.group(1),
        "drive_id": drive_m.group(1),
        "nonce": nonce_m.group(1),
    }


async def _wpcp_get_filelist(params: dict[str, str], folder_id: str, page_url: str) -> dict[str, Any]:
    """POST the OneDrive widget's own AJAX action and return its parsed
    JSON ({"tree": [...], "html": "...", ...}). folder_id="" lists the
    widget's root (both its immediate subfolders, in "tree", and any files
    directly in the root, in "html")."""
    data = {
        "id": folder_id,
        "drive_id": params["drive_id"],
        "listtoken": params["listtoken"],
        "account_id": params["account_id"],
        "sort": "name:desc",
        "action": "shareonedrive-get-filelist",
        "_ajax_nonce": params["nonce"],
        "mobile": "false",
        "query": "",
        "page_url": page_url,
    }
    headers = {"User-Agent": USER_AGENT}
    try:
        async with httpx.AsyncClient(headers=headers) as session:
            resp = await session.post(_WPCP_AJAX_URL, data=data, timeout=30.0)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError as exc:
        if not should_retry_with_os_trust(exc, _WPCP_AJAX_URL):
            raise
        async with httpx.AsyncClient(headers=headers, verify=os_trust_context()) as session:
            resp = await session.post(_WPCP_AJAX_URL, data=data, timeout=30.0)
            resp.raise_for_status()
            return resp.json()


def _parse_wpcp_files(html_fragment: str, seccion: str) -> list[dict[str, Any]]:
    archivos = []
    for chunk in _WPCP_FILE_ENTRY_SPLIT_RE.split(html_fragment)[1:]:
        link_m = _WPCP_FILE_LINK_RE.search(chunk)
        if link_m is None:
            logger.warning(
                "Superbancos sección %s (OneDrive): entrada de archivo no "
                "matcheó el patrón esperado de link/nombre.",
                seccion,
            )
            continue
        url = link_m.group("url")
        if not _is_superbancos_url(url):
            logger.warning(
                "Superbancos sección %s (OneDrive): descartado link con "
                "dominio inesperado (%s).",
                seccion,
                url,
            )
            continue
        name = _clean(link_m.group("name"))
        modified_m = _WPCP_FILE_MODIFIED_RE.search(chunk)
        size_m = _WPCP_FILE_SIZE_RE.search(chunk)
        archivos.append(
            {
                "grupo": None,
                "periodo": None,
                "titulo": name,
                "descripcion": "",
                "modificado": _clean(modified_m.group("modified")) if modified_m else "",
                "tamano": _clean(size_m.group("size")) if size_m else "",
                "url": url,
                "formato": _formato_from_name(name),
            }
        )
    return archivos


async def _wpcp_boletines_recientes(html: str, page_url: str, seccion: str) -> list[dict[str, Any]]:
    """Boletines Financieros' OneDrive widget: one "Año NNNN" subfolder per
    year under the root, each holding that year's files directly (no
    further nesting) -- confirmed by driving the real widget in a browser.
    Returns [] (never raises) if the page has no widget or the AJAX call
    fails, so a portal-side change here degrades to "static tables only"
    instead of breaking the whole section."""
    params = _extract_wpcp_params(html)
    if params is None:
        return []
    try:
        root = await _wpcp_get_filelist(params, "", page_url)
    except Exception:
        logger.warning(
            "Superbancos sección %s: no se pudo listar la raíz del widget OneDrive.",
            seccion,
            exc_info=True,
        )
        return []

    year_folders = [
        node for node in root.get("tree") or [] if _WPCP_YEAR_FOLDER_RE.match(node.get("text", ""))
    ]
    archivos = list(_parse_wpcp_files(root.get("html") or "", seccion))
    for folder in year_folders:
        try:
            year_result = await _wpcp_get_filelist(params, folder["id"], page_url)
        except Exception:
            logger.warning(
                "Superbancos sección %s: no se pudo listar la carpeta OneDrive '%s'.",
                seccion,
                folder.get("text"),
                exc_info=True,
            )
            continue
        for archivo in _parse_wpcp_files(year_result.get("html") or "", seccion):
            archivo["grupo"] = folder["text"]
            archivos.append(archivo)
    return archivos


def list_secciones() -> list[dict[str, str]]:
    """The four fixed Superbancos statistics sections."""
    return [dict(s) for s in _SECCIONES]


def _parse_tablepress_archivos(html: str, seccion: str) -> list[dict[str, Any]]:
    """Parse every TablePress table in html into a flat list of archivos.

    Handles two header styles observed live: a <thead><th colspan=...> row,
    and a plain <td colspan=...> row inside <tbody> with no <thead> at all
    -- both are treated as a "grupo" (section) label that carries forward
    until the next one. A cell with no link whose text starts with "Año" is
    treated as that row's "periodo" label instead of a data entry (the
    Información Histórica tables put the year in column 1 and months as
    links in the following columns; other tables put the year directly in
    the link text and never trigger this branch).
    """
    archivos = []
    current_grupo: str | None = None
    for table_m in _TABLE_RE.finditer(html):
        body = table_m.group("body")
        for row_m in _ROW_RE.finditer(body):
            row = row_m.group("row")
            current_periodo: str | None = None
            for cell_m in _CELL_RE.finditer(row):
                attrs = cell_m.group("attrs")
                cell = cell_m.group("cell")
                link_m = _LINK_RE.search(cell)

                if link_m is None:
                    text = _clean(cell)
                    if not text:
                        continue
                    if _COLSPAN_RE.search(attrs):
                        current_grupo = text
                    elif _PERIODO_RE.match(text):
                        current_periodo = text
                    continue

                url = link_m.group("url")
                if not _is_superbancos_url(url):
                    logger.warning(
                        "Superbancos sección %s: descartado link con dominio "
                        "inesperado (%s) — posible enlace roto en la página fuente.",
                        seccion,
                        url,
                    )
                    continue
                titulo = _clean(link_m.group("label")) or _clean(cell)
                descripcion = _clean(cell[link_m.end():])
                archivos.append(
                    {
                        "grupo": current_grupo,
                        "periodo": current_periodo,
                        "titulo": titulo,
                        "descripcion": descripcion,
                        "url": url,
                        "formato": _clean_formato(url),
                    }
                )
    return archivos


def _parse_calendario(html: str) -> list[dict[str, Any]]:
    archivos = []
    for m in _CALENDARIO_RE.finditer(html):
        label = _clean(m.group("label"))
        url = m.group("url")
        if not _is_superbancos_url(url):
            logger.warning(
                "Superbancos calendario_estadistico: descartado link con "
                "dominio inesperado (%s).",
                url,
            )
            continue
        archivos.append(
            {
                "grupo": None,
                "periodo": None,
                "titulo": label,
                "descripcion": "",
                "url": url,
                # No extension in the URL (a download-monitor redirect); the
                # real Content-Type is XLSX despite the page styling it as
                # a PDF download icon -- confirmed live, not assumed here.
                "formato": _clean_formato(url),
            }
        )
    return archivos


async def get_seccion_archivos(seccion: str) -> dict[str, Any]:
    """
    Fetch one Superbancos section page and list its direct download links.

    Args:
        seccion: One of the keys from list_secciones() ("boletines_financieros",
            "servicios_financieros", "informacion_historica",
            "calendario_estadistico").
    """
    info = _SECCIONES_BY_KEY.get(seccion)
    if info is None:
        valid = ", ".join(sorted(_SECCIONES_BY_KEY))
        raise ValueError(f"Sección '{seccion}' no reconocida. Válidas: {valid}")

    cached = _files_cache.get(seccion)
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _files_cache.get(seccion)
        if cached is not None:
            return cached

        logger.info("Descargando página de sección Superbancos: %s", seccion)
        content, truncated = await download_bytes(info["url"])
        if truncated:
            raise ValueError(f"La página de {info['url']} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")

        if seccion == "calendario_estadistico":
            archivos = _parse_calendario(html)
        else:
            archivos = _parse_tablepress_archivos(html, seccion)
            if seccion == "boletines_financieros":
                archivos = archivos + await _wpcp_boletines_recientes(html, info["url"], seccion)

        result = {
            "seccion": seccion,
            "nombre": info["nombre"],
            "url": info["url"],
            "archivos": archivos,
        }
        if archivos:
            _files_cache.set(seccion, result)
        return result
