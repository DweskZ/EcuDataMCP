"""Client for the Superintendencia de Economía Popular y Solidaria's
statistics subdomain (estadisticas.seps.gob.ec) -- a WordPress site distinct
from the institutional site (seps.gob.ec), which actively blocks automated
connections (confirmed live: a "Blocked" page / non-200 response). This
subdomain returns a normal 200 via plain httpx and has no such protection.

No CKAN organization exists for SEPS (confirmed live 2026-09-02: a direct
`organization_list` call against the project's CKAN base, datosabiertos.gob.ec,
returns no "seps"-named organization), so this is the only path to SEPS'
published statistics.

Two pages carry the real content, both plain WordPress/Visual Composer
pages (no JS-rendered/AJAX-only content, confirmed by comparing curl output
against the rendered page):

- estadisticas-sfps/ ("Estadísticas SFPS" -- Sector Financiero Popular y
  Solidario: cooperatives, mutualistas, cajas): 5 tabs (Situación
  Financiera, Depósitos, Cartera de crédito, Tasas de interés, Inclusión
  financiera), 22 report panels total.
- estadisticas-eps/ ("Estadísticas EPS" -- non-financial Economía Popular y
  Solidaria organizations): 1 tab (Información sectorial), 4 report panels.

Each page lays its panels out as Bootstrap accordions (`panel-title` /
`panel-body`, NOT the TablePress markup Superbancos uses) nested inside
Visual Composer tabs+toggles. Every panel body holds one or more `<ul><li>`
lists of `<a href>` links, one per published period (usually a year, e.g.
"2026", "Años anteriores", or -- for the current year -- a label like
"2026 con corte al 31 de marzo"). Two link shapes were confirmed live:
a direct static `wp-content/uploads/.../*.pdf` (or .zip) URL, and a
redirect through the "Simple Download Monitor" plugin
(`?sdm_process_download=1&download_id=N`, or an older/inconsistent
`?smd_process_download=1&download_id=N` -- both spellings seen live on the
same page, not a bug in this client) that 302s to the same kind of static
uploads URL. Neither shape is followed here -- the page's own link is
returned as-is (it works when fetched directly), same choice Superbancos
makes for its own download-monitor links; format detection is URL-extension
based and comes back DESCONOCIDO for the redirect shape, exactly like
Superbancos' calendario_estadistico links. (Spot-checked live with
`curl -I`: both a `sdm_process_download` and a `smd_process_download` link
under Calificación de Riesgos 302 to a real .pdf.)

The roadmap's specific target, "boletines de calificadoras de riesgo", is
the "Calificación de Riesgos" panel under SFPS > Situación Financiera >
Reportes (seccion key sfps_reportes_calificacion_de_riesgos): PDF bulletins
of risk ratings assigned to SFPS entities by authorized rating agencies,
one per year from 2020 through 2025 plus a 2026 Q1 cut ("2026 con corte al
31 de marzo") -- confirmed live 2026-09-02, page text states coverage of
112 entities as of the most recent bulletin. It is one panel among 26
total; this client exposes all of them via the same list_secciones/
get_seccion_archivos shape used for Superbancos, since the underlying
markup and parsing logic is identical across all of them (verified against
every panel on both pages, not just the named one).

A "grupo" is set on an archivo only where the panel's own markup nests
links under a plain-text sub-heading `<li>` before their own `<ul>` (e.g.
Estados Financieros Mensuales splits "segmentos 1, 2, 3" from "segmentos 4
y 5"); most panels have none and grupo is None throughout.

Files are never downloaded here -- only metadata and the direct URL, same
pattern as helpers/superbancos_client.py and helpers/sipa_client.py.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME

logger = logging.getLogger(MAIN_LOGGER_NAME)

_SFPS_URL = "https://estadisticas.seps.gob.ec/index.php/estadisticas-sfps/"
_EPS_URL = "https://estadisticas.seps.gob.ec/index.php/estadisticas-eps/"

_PAGE_URLS: dict[str, str] = {"SFPS": _SFPS_URL, "EPS": _EPS_URL}

# Every accordion panel found live on both pages (2026-09-02), keyed by a
# stable slug derived from "<página>_<reportes|datos>_<título del panel>".
# collapse_id is the panel's own DOM id on its page (e.g. "collapse_3"),
# used to pick it out of the page's parsed accordion once downloaded.
_SECCIONES: dict[str, dict[str, str]] = {
    "sfps_reportes_estados_financieros_mensuales": {
        "pagina": "SFPS",
        "collapse_id": "collapse_0",
        "nombre": "Situación Financiera — Reportes — Estados Financieros Mensuales",
    },
    "sfps_reportes_estados_financieros_trimestrales": {
        "pagina": "SFPS",
        "collapse_id": "collapse_1",
        "nombre": "Situación Financiera — Reportes — Estados Financieros Trimestrales",
    },
    "sfps_reportes_patrimonio_tecnico": {
        "pagina": "SFPS",
        "collapse_id": "collapse_2",
        "nombre": "Situación Financiera — Reportes — Patrimonio técnico",
    },
    "sfps_reportes_calificacion_de_riesgos": {
        "pagina": "SFPS",
        "collapse_id": "collapse_3",
        "nombre": "Situación Financiera — Reportes — Calificación de Riesgos",
    },
    "sfps_datos_estados_financieros_mensuales": {
        "pagina": "SFPS",
        "collapse_id": "collapse_4",
        "nombre": "Situación Financiera — Bases de Datos — Estados Financieros Mensuales",
    },
    "sfps_datos_estados_financieros_trimestrales": {
        "pagina": "SFPS",
        "collapse_id": "collapse_5",
        "nombre": "Situación Financiera — Bases de Datos — Estados Financieros Trimestrales",
    },
    "sfps_reportes_captaciones_mensuales": {
        "pagina": "SFPS",
        "collapse_id": "collapse_6",
        "nombre": "Depósitos — Reportes — Captaciones mensuales",
    },
    "sfps_datos_captaciones_mensuales": {
        "pagina": "SFPS",
        "collapse_id": "collapse_7",
        "nombre": "Depósitos — Bases de Datos — Captaciones mensuales",
    },
    "sfps_datos_captaciones_trimestrales": {
        "pagina": "SFPS",
        "collapse_id": "collapse_8",
        "nombre": "Depósitos — Bases de Datos — Captaciones trimestrales",
    },
    "sfps_reportes_volumen_de_credito_mensual": {
        "pagina": "SFPS",
        "collapse_id": "collapse_9",
        "nombre": "Cartera de crédito — Reportes — Volumen de crédito mensual",
    },
    "sfps_reportes_colocaciones_mensuales": {
        "pagina": "SFPS",
        "collapse_id": "collapse_10",
        "nombre": "Cartera de crédito — Reportes — Colocaciones mensuales",
    },
    "sfps_reportes_alivio_financiero_resolucion_jprfm_2025_004_f": {
        "pagina": "SFPS",
        "collapse_id": "collapse_11",
        "nombre": "Cartera de crédito — Reportes — Alivio Financiero - Resolución JPRFM-2025-004-F",
    },
    "sfps_datos_volumen_de_credito_mensual": {
        "pagina": "SFPS",
        "collapse_id": "collapse_12",
        "nombre": "Cartera de crédito — Bases de Datos — Volumen de crédito mensual",
    },
    "sfps_datos_volumen_de_credito_trimestral": {
        "pagina": "SFPS",
        "collapse_id": "collapse_13",
        "nombre": "Cartera de crédito — Bases de Datos — Volumen de crédito trimestral",
    },
    "sfps_datos_colocaciones_mensuales": {
        "pagina": "SFPS",
        "collapse_id": "collapse_14",
        "nombre": "Cartera de crédito — Bases de Datos — Colocaciones mensuales",
    },
    "sfps_datos_colocaciones_trimestrales": {
        "pagina": "SFPS",
        "collapse_id": "collapse_15",
        "nombre": "Cartera de crédito — Bases de Datos — Colocaciones trimestrales",
    },
    "sfps_datos_tarjetas_de_credito_mensual": {
        "pagina": "SFPS",
        "collapse_id": "collapse_16",
        "nombre": "Cartera de crédito — Bases de Datos — Tarjetas de crédito mensual",
    },
    "sfps_reportes_tasa_de_interes": {
        "pagina": "SFPS",
        "collapse_id": "collapse_17",
        "nombre": "Tasas de interés — Reportes — Tasa de interés",
    },
    "sfps_datos_puntos_de_atencion_trimestral": {
        "pagina": "SFPS",
        "collapse_id": "collapse_18",
        "nombre": "Inclusión financiera — Bases de Datos — Puntos de atención trimestral",
    },
    "sfps_datos_entidades_trimestral": {
        "pagina": "SFPS",
        "collapse_id": "collapse_19",
        "nombre": "Inclusión financiera — Bases de Datos — Entidades trimestral",
    },
    "sfps_datos_socios_trimestral": {
        "pagina": "SFPS",
        "collapse_id": "collapse_20",
        "nombre": "Inclusión financiera — Bases de Datos — Socios trimestral",
    },
    "sfps_datos_directivas_trimestral": {
        "pagina": "SFPS",
        "collapse_id": "collapse_21",
        "nombre": "Inclusión financiera — Bases de Datos — Directivas trimestral",
    },
    "eps_datos_organizaciones_eps_mensuales": {
        "pagina": "EPS",
        "collapse_id": "collapse_0",
        "nombre": "Información sectorial — Bases de Datos — Organizaciones EPS mensuales",
    },
    "eps_datos_socios_eps_mensuales": {
        "pagina": "EPS",
        "collapse_id": "collapse_1",
        "nombre": "Información sectorial — Bases de Datos — Socios EPS mensuales",
    },
    "eps_datos_informacion_financiera_eps_anual": {
        "pagina": "EPS",
        "collapse_id": "collapse_2",
        "nombre": "Información sectorial — Bases de Datos — Información financiera EPS anual",
    },
    "eps_datos_directivos_trimestral": {
        "pagina": "EPS",
        "collapse_id": "collapse_3",
        "nombre": "Información sectorial — Bases de Datos — Directivos trimestral",
    },
}

_KNOWN_FORMATS = {"XLSX", "XLS", "CSV", "PDF", "ZIP", "DOCX", "DOC"}

# One page fetch covers every seccion on it (both pages combined hold all
# 26 known sections); pages change a handful of times a year (a new
# archived period), so a multi-hour TTL is plenty.
_page_cache = TtlCache(ttl_seconds=21600.0, max_entries=2)
_fetch_locks: dict[str, asyncio.Lock] = {"SFPS": asyncio.Lock(), "EPS": asyncio.Lock()}

_TAG_RE = re.compile(r"<[^>]+>")

# Each panel's body sits between its own <div id="collapse_N" ...><div
# class="panel-body"> and the "</div></div>\n</div>" triple-close that ends
# both the panel-body and its enclosing collapse/panel divs -- confirmed
# live to match all 22 SFPS panels and all 4 EPS panels, none dropped.
_PANEL_BODY_RE = re.compile(
    r'<div id="(?P<cid>collapse_\d+)" class="panel-collapse collapse"[^>]*>\s*'
    r'<div class="panel-body">(?P<body>.*?)</div></div>\s*</div>',
    re.DOTALL,
)

# Walks a panel body in document order, alternating between two things:
#  - a bare category <li> (plain text, no link, no nested <a> before its
#    </li> or its own <ul>) -- becomes the running "grupo" for links found
#    afterward, e.g. Estados Financieros Mensuales' "segmentos 1, 2, 3" vs
#    "segmentos 4 y 5" split;
#  - an <a href> -- one archivo entry (its link text is the "periodo",
#    e.g. "2026", "Años anteriores", "2026 con corte al 31 de marzo").
# The "<a\b" exclusion inside the grupo branch matters: a handful of
# entries wrap their link in <strong> (e.g. Calificación de Riesgos' most
# recent year), and without it the category branch would swallow the link
# as empty grupo text instead of leaving it for the link branch on the next
# iteration -- confirmed live this drops the 2026 calificadoras entry
# without it.
_ITEM_RE = re.compile(
    r'<li(?:\s+[^>]*)?>(?!\s*(?:<a\b|</li>|\s*<ul))(?P<grupo>(?:(?!</li>|<ul\b|<a\b).)*)'
    r'|<a\s+href="(?P<url>[^"]+)"[^>]*>(?P<label>[^<]*)</a>',
    re.DOTALL,
)

# First non-empty <p> in a panel body -- the short Spanish description that
# precedes its file list (e.g. Calificación de Riesgos' "...se dispone de
# información de 112 entidades.").
_FIRST_P_RE = re.compile(r"<p[^>]*>(?P<text>.*?)</p>", re.DOTALL)


def _clean(text: str) -> str:
    return unescape(_TAG_RE.sub("", text)).strip()


def _clean_formato(url: str) -> str:
    last_segment = url.rsplit("/", 1)[-1]
    ext = url.rsplit(".", 1)[-1].upper() if "." in last_segment else ""
    return ext if ext in _KNOWN_FORMATS else "DESCONOCIDO"


def _is_seps_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "estadisticas.seps.gob.ec"


def list_secciones() -> list[dict[str, str]]:
    """The 26 known SEPS statistics-page sections (22 on estadisticas-sfps/,
    4 on estadisticas-eps/), one per accordion panel found live on those
    pages -- includes sfps_reportes_calificacion_de_riesgos, the roadmap's
    "boletines de calificadoras de riesgo" target."""
    return [
        {"seccion": key, "nombre": info["nombre"], "url": _PAGE_URLS[info["pagina"]]}
        for key, info in _SECCIONES.items()
    ]


def _parse_panel_body(body: str, seccion_hint: str) -> dict[str, Any]:
    archivos: list[dict[str, Any]] = []
    grupo: str | None = None
    for m in _ITEM_RE.finditer(body):
        if m.group("url") is not None:
            url = unescape(m.group("url"))
            if not _is_seps_url(url):
                logger.warning(
                    "SEPS sección %s: descartado link con dominio inesperado (%s).",
                    seccion_hint,
                    url,
                )
                continue
            archivos.append(
                {
                    "grupo": grupo,
                    "periodo": None,
                    "titulo": _clean(m.group("label")),
                    "descripcion": "",
                    "url": url,
                    "formato": _clean_formato(url),
                }
            )
        else:
            g = _clean(m.group("grupo"))
            if g:
                grupo = g

    first_p = _FIRST_P_RE.search(body)
    descripcion = _clean(first_p.group("text")) if first_p else ""
    return {"descripcion": descripcion, "archivos": archivos}


def _parse_page(html: str) -> dict[str, dict[str, Any]]:
    """Parse every accordion panel in one SFPS/EPS page's HTML into
    {collapse_id: {"descripcion": str, "archivos": [...]}}."""
    panels: dict[str, dict[str, Any]] = {}
    for m in _PANEL_BODY_RE.finditer(html):
        cid = m.group("cid")
        panels[cid] = _parse_panel_body(m.group("body"), cid)
    return panels


async def _get_page_secciones(pagina: str) -> dict[str, dict[str, Any]]:
    cached = _page_cache.get(pagina)
    if cached is not None:
        return cached

    async with _fetch_locks[pagina]:
        cached = _page_cache.get(pagina)
        if cached is not None:
            return cached

        url = _PAGE_URLS[pagina]
        logger.info("Descargando página de estadísticas SEPS: %s (%s)", pagina, url)
        content, truncated = await download_bytes(url)
        if truncated:
            raise ValueError(f"La página de {url} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")

        parsed = _parse_page(html)
        if parsed:
            _page_cache.set(pagina, parsed)
        return parsed


async def get_seccion_archivos(seccion: str) -> dict[str, Any]:
    """
    Fetch one SEPS statistics section's page and list its direct download
    links.

    Args:
        seccion: One of the keys from list_secciones(), e.g.
            "sfps_reportes_calificacion_de_riesgos".
    """
    info = _SECCIONES.get(seccion)
    if info is None:
        valid = ", ".join(sorted(_SECCIONES))
        raise ValueError(f"Sección '{seccion}' no reconocida. Válidas: {valid}")

    pagina_secciones = await _get_page_secciones(info["pagina"])
    panel = pagina_secciones.get(info["collapse_id"], {"descripcion": "", "archivos": []})

    return {
        "seccion": seccion,
        "nombre": info["nombre"],
        "url": _PAGE_URLS[info["pagina"]],
        "descripcion": panel.get("descripcion", ""),
        "archivos": panel.get("archivos", []),
    }
