"""Client for SIPA (Sistema de Información Pública Agropecuaria), the
Ministry of Agriculture, Livestock and Fisheries' statistics portal
(sipa.agricultura.gob.ec) — distinct from MPCEIP (industry/trade).

The site is Joomla-based. Its four "estadisticas-descargas" pages
(económico, productivo, social, censos y registros administrativos) each
list a fixed set of statistical files as direct XLSX/XLS download links
inside a UIKit accordion — no JS rendering needed, no login, confirmed
live. This replaces the ad hoc cacao/MPCEIP coverage `detect_series_pattern`
relied on before with the real, much richer source: agropecuario price,
trade, credit, production, and census series back to the early 2000s.

Unlike helpers/inec_client.py, the module list itself isn't scraped from a
nav menu — there are only four modules and their URLs are stable, so
they're hardcoded below — but each module's file listing is scraped live
the same way INEC's topic pages are.

Files here are sometimes large (one confirmed at 41.4 MB, well over this
project's 5 MB download/preview cap), so this client never fetches file
bytes — only metadata and the direct URL. Point the model at the URL
directly rather than routing it through download_resource/preview_resource_data.
"""

from __future__ import annotations

import logging
import re
from html import unescape
from typing import Any

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://sipa.agricultura.gob.ec"

_MODULOS: list[dict[str, str]] = [
    {
        "modulo": "economico",
        "nombre": "Económico",
        "url": f"{_BASE}/index.php/sipa-estadisticas/estadisticas-descargas/estadisticas-economicas",
    },
    {
        "modulo": "productivo",
        "nombre": "Productivo",
        "url": f"{_BASE}/index.php/sipa-estadisticas/estadisticas-descargas/estadisticas-productivas",
    },
    {
        "modulo": "social",
        "nombre": "Social",
        "url": f"{_BASE}/index.php/sipa-estadisticas/estadisticas-descargas/estadisticas-social",
    },
    {
        "modulo": "censos",
        "nombre": "Censos y Registros Administrativos",
        "url": (
            f"{_BASE}/index.php/sipa-estadisticas/estadisticas-descargas/"
            "censos-y-registros-administrativos"
        ),
    },
]
_MODULOS_BY_KEY = {m["modulo"]: m for m in _MODULOS}

# Module pages are refreshed rarely (new series added a few times a year).
_files_cache = TtlCache(ttl_seconds=21600.0, max_entries=16)

_TAG_RE = re.compile(r"<[^>]+>")
# Each accordion item is a numbered title followed by the download link;
# the description paragraph in between is common but NOT guaranteed — the
# censos module's items skip it entirely (confirmed live), so title/link
# are matched independently per item chunk rather than as one strict
# sequence, and the description is optional.
_ITEM_SPLIT_RE = re.compile(r'<div class="el-item">')
_TITLE_RE = re.compile(
    r'<h3 class="el-title uk-accordion-title">\s*(?P<numero>\d+)\.\s*(?P<titulo>.*?)\s*</h3>',
    re.DOTALL,
)
_DESC_RE = re.compile(
    r'<div class="uk-margin el-content"><p[^>]*>(?P<descripcion>.*?)</p></div>',
    re.DOTALL,
)
_LINK_RE = re.compile(
    r'<a\s+href="(?P<url>https://sipa\.agricultura\.gob\.ec/descargas/[^"]+)"\s+class="el-link'
)


def _clean(text: str) -> str:
    return unescape(_TAG_RE.sub("", text)).strip()


def list_modulos() -> list[dict[str, str]]:
    """The four fixed SIPA statistics-download modules."""
    return [dict(m) for m in _MODULOS]


def _parse_archivos(html: str) -> list[dict[str, Any]]:
    archivos = []
    # First chunk (before any "el-item") is page chrome, not an item.
    for chunk in _ITEM_SPLIT_RE.split(html)[1:]:
        title_m = _TITLE_RE.search(chunk)
        link_m = _LINK_RE.search(chunk)
        if title_m is None or link_m is None:
            continue
        desc_m = _DESC_RE.search(chunk)
        url = link_m.group("url")
        formato = url.rsplit(".", 1)[-1].upper()
        archivos.append(
            {
                "numero": int(title_m.group("numero")),
                "titulo": _clean(title_m.group("titulo")),
                "descripcion": _clean(desc_m.group("descripcion")) if desc_m else "",
                "url": url,
                "formato": formato,
            }
        )
    return archivos


async def get_modulo_archivos(modulo: str) -> dict[str, Any]:
    """
    Fetch one SIPA module page and list its direct download links.

    Args:
        modulo: One of the keys from list_modulos() ("economico",
            "productivo", "social", "censos").
    """
    info = _MODULOS_BY_KEY.get(modulo)
    if info is None:
        valid = ", ".join(sorted(_MODULOS_BY_KEY))
        raise ValueError(f"Módulo '{modulo}' no reconocido. Válidos: {valid}")

    cached = _files_cache.get(modulo)
    if cached is not None:
        return cached

    logger.info("Descargando página del módulo SIPA: %s", modulo)
    content, truncated = await download_bytes(info["url"])
    if truncated:
        raise ValueError(f"La página de {info['url']} superó el límite de descarga.")
    html = content.decode("utf-8", errors="replace")

    archivos = _parse_archivos(html)
    result = {
        "modulo": modulo,
        "nombre": info["nombre"],
        "url": info["url"],
        "archivos": archivos,
    }
    _files_cache.set(modulo, result)
    return result
