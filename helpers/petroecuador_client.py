"""Client for EP Petroecuador's "Cifras Institucionales" page
(eppetroecuador.ec/?p=3721): annual and monthly statistical reports,
financial statements, daily field production, sales prices, dispatches and
risk reports.

Confirmed live 2026-10-10 with a browser-identifying User-Agent. The page
is plain WordPress markup, not a download-monitor library: eight
`div.Headerinfo` blocks (Estados Financieros, Informes Estadísticos
Mensuales, Informes Estadísticos Anuales, Exploración y Producción,
Comercialización, Refinación, Comercialización Internacional, Gestión de
Riesgos y Oportunidades), each followed by a `div.paleta` with a `<ul>` of
links. Links are a mix of direct `wp-content/uploads/...pdf` files and
`download-monitor/download.php?id=N` redirects (a 302 to the current PDF, so
the id is stable while the file behind it is replaced), some of them
relative (`wp-content/plugins/...`), plus one link to another WordPress page
(`?p=8062`, "Precios de Venta en Terminales") and one to the `eppintranet`
subdomain. Some `<li>` carry text only, with no link (production cost per
barrel); those are not files and are not listed.

The "Producción de Campo BPPD" link text embeds the day's figure and
effective date ("356,570 Bls (Fecha efectiva: ...)"); it is kept verbatim as
the title because the page itself publishes it that way, and it changes
daily.

Sections have no ids on the page (the `<a name>` anchors repeat), so each
section id is the accent-free snake_case of its heading. Format comes from
the URL extension; `download.php` links carry none and are reported as
DESCONOCIDO, like the other download-monitor sources.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://www.eppetroecuador.ec"
_CIFRAS_URL = f"{_BASE}/?p=3721"
_SOURCE = "EP Petroecuador — Cifras Institucionales, eppetroecuador.ec"

# The page changes when a report is published (monthly) or the daily
# production figure is refreshed; 6 h keeps that figure reasonably current.
_page_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_HEADER_RE = re.compile(r'<div class="Headerinfo">(?P<name>.*?)</div>', re.DOTALL)
_LINK_RE = re.compile(r'<a\s[^>]*?href="(?P<url>[^"]+)"[^>]*>(?P<label>.*?)</a>', re.DOTALL)
_EXT_RE = re.compile(r"\.(pdf|xlsx?|csv|zip|docx?)$", re.IGNORECASE)


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", unescape(_TAG_RE.sub("", text))).strip()


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _strip(name)).strip("_")


def _is_petroecuador_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "eppetroecuador.ec" or host.endswith(".eppetroecuador.ec")


def _formato(url: str) -> str:
    path = urlparse(url).path
    ext = _EXT_RE.search(path)
    if ext:
        return ext.group(1).upper()
    if "download.php" in path:
        return "DESCONOCIDO"
    return "HTML"


def _secciones(html: str) -> list[dict[str, Any]]:
    headers = list(_HEADER_RE.finditer(html))
    secciones: list[dict[str, Any]] = []
    for i, h in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(html)
        nombre = _clean(h.group("name"))
        archivos: list[dict[str, Any]] = []
        seen: set[str] = set()
        for lm in _LINK_RE.finditer(html, h.end(), end):
            url = urljoin(_CIFRAS_URL, unescape(lm.group("url")).strip())
            if url in seen:
                continue
            if not _is_petroecuador_url(url):
                logger.warning(
                    "Petroecuador cifras: descartado link con dominio inesperado (%s).",
                    url,
                )
                continue
            seen.add(url)
            archivos.append(
                {
                    "titulo": _clean(lm.group("label")),
                    "url": url,
                    "formato": _formato(url),
                }
            )
        secciones.append({"id": _slug(nombre), "nombre": nombre, "archivos": archivos})
    return secciones


async def _fetch_html() -> str:
    cached = _page_cache.get("html")
    if cached is not None:
        return cached
    async with _fetch_lock:
        cached = _page_cache.get("html")
        if cached is not None:
            return cached
        logger.info("Descargando Cifras Institucionales de Petroecuador (%s)", _CIFRAS_URL)
        content, truncated = await download_bytes(_CIFRAS_URL)
        if truncated:
            raise ValueError(f"La página {_CIFRAS_URL} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")
        if _HEADER_RE.search(html):
            # Don't cache an apparently broken/empty page.
            _page_cache.set("html", html)
        return html


async def list_categorias() -> dict[str, Any]:
    """List the sections of Petroecuador's Cifras Institucionales page."""
    secciones = _secciones(await _fetch_html())
    return {
        "total": len(secciones),
        "source": _SOURCE,
        "url_fuente": _CIFRAS_URL,
        "categorias": [
            {"id": s["id"], "nombre": s["nombre"], "total_archivos": len(s["archivos"])}
            for s in secciones
        ],
    }


async def get_categoria_archivos(categoria: str) -> dict[str, Any]:
    """Links of one section; `categoria` is its id or nombre (accent/case-insensitive)."""
    secciones = _secciones(await _fetch_html())
    q = _strip(categoria)
    match = next((s for s in secciones if s["id"] == q or _strip(s["nombre"]) == q), None)
    if match is None:
        valid = ", ".join(f"{s['id']}:{s['nombre']}" for s in secciones)
        raise ValueError(f"Sección '{categoria}' no reconocida. Válidas: {valid}")
    return {
        "id": match["id"],
        "nombre": match["nombre"],
        "total": len(match["archivos"]),
        "source": _SOURCE,
        "url_fuente": _CIFRAS_URL,
        "archivos": match["archivos"],
    }
