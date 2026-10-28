"""Client for ARCONEL's published files on arconel.gob.ec, documented in
docs/RESEARCH.md § ARCONEL — archivos estáticos, tarifas, regulaciones,
Power BI (Trigésimo quinta pasada, re-checked 2026-10-26).

WordPress's media API does not list these (Download Monitor keeps them
outside the media library), so each section scrapes its pages:

- estadistica, mapas: Download Monitor libraries (the same `ul.ul-downloads`
  markup as the SGR/SENESCYT/CENACE libraries) with one category per year:
  the annual and multi-year statistics 1990-2025 and the Atlas (49 PDFs),
  and the electricity-sector maps (38 PDFs).
- balances: one current workbook per page, formatted for presentation: the
  Balance Nacional de Energía Eléctrica (rolling 12 months, newer than the
  CKAN copy), the 2015-2024 multi-year balance, coverage by province and
  per-capita consumption.
- tarifas: the four tariff pages (SPEE, alumbrado público, carga de
  vehículos eléctricos, proyección de subsidios), ~40 PDFs of resolutions,
  tariff schedules and cost reports under year headers, 2023-2026 only.
- regulaciones: the regulations in force, read from the `TEMAS` array in
  post 3765 ("Regulaciones vigentes del sector eléctrico ecuatoriano"), 51
  items in 10 topics with code, title and PDF. search_regulaciones (gob.ec)
  only carries 6 of them.

The live host is `arconel.gob.ec` without `www`.
"""

from __future__ import annotations

import asyncio
import json
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.text_utils import strip_accents as _strip

_BASE = "https://arconel.gob.ec"

_SECCIONES: list[dict[str, Any]] = [
    {
        "seccion": "estadistica",
        "nombre": "Estadística anual y multianual del sector eléctrico y Atlas (PDF, 1990-2025)",
        "paginas": [f"{_BASE}/publicaciones-estadistica-del-sector-electrico-2/"],
        "tipo": "biblioteca",
    },
    {
        "seccion": "mapas",
        "nombre": "Mapas del sector eléctrico (PDF)",
        "paginas": [f"{_BASE}/mapas-del-sector-electrico/"],
        "tipo": "biblioteca",
    },
    {
        "seccion": "balances",
        "nombre": "Balance nacional de energía eléctrica vigente, balance multianual, "
        "cobertura y consumo per cápita (XLS/XLSX)",
        "paginas": [
            f"{_BASE}/balance-nacional-de-energia-electrica/",
            f"{_BASE}/balance-multianual-de-energia/",
            f"{_BASE}/cobertura-anual-del-servicio/",
            f"{_BASE}/consumo-anual-per-capita/",
        ],
        "tipo": "enlaces",
    },
    {
        "seccion": "tarifas",
        "nombre": "Tarifas: pliegos tarifarios, costos y subsidios (PDF, 2023-2026)",
        "paginas": [
            f"{_BASE}/servicio-publico-de-energia-electrica-spee/",
            f"{_BASE}/servicio-de-alumbrado-publico-general-sapg/",
            f"{_BASE}/servicio-de-carga-de-vehiculos-electricos/",
            f"{_BASE}/proyeccion-de-subsidios-del-sector-electrico-ecuatoriano/",
        ],
        "tipo": "enlaces",
    },
    {
        "seccion": "regulaciones",
        "nombre": "Regulaciones y resoluciones vigentes del sector eléctrico (PDF)",
        "paginas": [f"{_BASE}/wp-json/wp/v2/posts/3765"],
        "url": f"{_BASE}/regulaciones-vigentes-del-sector-electrico-ecuatoriano/",
        "tipo": "temas",
    },
]
_PAGE_NAMES = {
    "balance-nacional-de-energia-electrica": "Balance nacional de energía eléctrica",
    "balance-multianual-de-energia": "Balance multianual de energía",
    "cobertura-anual-del-servicio": "Cobertura anual del servicio",
    "consumo-anual-per-capita": "Consumo anual per cápita",
    "servicio-publico-de-energia-electrica-spee": "Servicio público de energía eléctrica (SPEE)",
    "servicio-de-alumbrado-publico-general-sapg": "Alumbrado público general (SAPG)",
    "servicio-de-carga-de-vehiculos-electricos": "Carga de vehículos eléctricos",
    "proyeccion-de-subsidios-del-sector-electrico-ecuatoriano": "Proyección de subsidios",
}

# ARCONEL republishes a page when a new balance, tariff or yearbook comes
# out, a few times a year: the same 6 h TTL as the other libraries.
_cache = TtlCache(ttl_seconds=21600.0, max_entries=16)
_locks: dict[str, asyncio.Lock] = {}

_TAG_RE = re.compile(r"<[^>]+>")
_CAT_RE = re.compile(
    r'<li class="li-gray1" id="cat-\d+"[^>]*>\s*<a[^>]*><span class="ico">\+</span>([^<]+)</a>'
)
_DM_ENTRY_RE = re.compile(
    r'href="(https://arconel\.gob\.ec/wp-content/plugins/download-monitor/download\.php'
    r'\?id=\d+&(?:amp;)?force=1)"\s+title="Descargar ([^"]+)"'
)
_LINK_RE = re.compile(
    r'<a[^>]+href="(https://arconel\.gob\.ec/wp-content/uploads/[^"]+\.(pdf|xlsx?))"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_ANIO_RE = re.compile(r"\bA[ÑN]O\s+(\d{4})\b", re.IGNORECASE)
_TEMA_RE = re.compile(r'title:\s*"([^"]+)",\s*items:\s*\[')
_ITEM_RE = re.compile(
    r'\{\s*type:\s*"([^"]*)",\s*code:\s*"([^"]*)",\s*title:\s*"([^"]*)",\s*href:\s*"([^"]*)"\s*\}'
)


def _clean(text: str) -> str:
    return " ".join(unescape(_TAG_RE.sub(" ", text)).split())


def _biblioteca(html: str) -> list[dict[str, Any]]:
    """Download Monitor entries, each under its nearest category: the year
    for estadistica, the theme (generación, transmisión...) for mapas."""
    events = [(m.start(), "cat", _clean(m.group(1))) for m in _CAT_RE.finditer(html)]
    events += [(m.start(), "entry", m) for m in _DM_ENTRY_RE.finditer(html)]
    archivos, seen, grupo = [], set(), None
    for _, kind, data in sorted(events, key=lambda e: e[0]):
        if kind == "cat":
            grupo = data
            continue
        url = unescape(data.group(1))
        if url in seen:
            continue
        seen.add(url)

        # download.php hides the extension; every file in both libraries
        # checked on 2026-09-29 was a PDF.
        archivos.append(
            {"titulo": _clean(data.group(2)), "url": url, "formato": "PDF", "grupo": grupo}
        )
    return archivos


def _enlaces(html: str, pagina: str) -> list[dict[str, Any]]:
    """Direct file links in a page's body, with the nearest "AÑO YYYY"
    header before each one as `periodo`."""
    slug = urlparse(pagina).path.strip("/")
    archivos, seen = [], set()
    for match in _LINK_RE.finditer(html):
        url, extension, texto = match.groups()
        if url in seen:
            continue
        seen.add(url)
        anios = _ANIO_RE.findall(_clean(html[: match.start()])[-3000:])
        titulo = _clean(texto) or url.rsplit("/", 1)[-1]
        archivos.append(
            {
                "titulo": titulo,
                "url": url,
                "formato": extension.upper(),
                "grupo": _PAGE_NAMES.get(slug, slug),
                "periodo": anios[-1] if anios else None,
            }
        )
    return archivos


def _temas(payload: str) -> list[dict[str, Any]]:
    content = json.loads(payload)["content"]["rendered"]
    start = content.find("TEMAS")
    if start < 0:
        raise ValueError("La página de regulaciones de ARCONEL ya no trae el arreglo TEMAS.")
    content = unescape(content[start:])
    temas = [(m.start(), m.group(1)) for m in _TEMA_RE.finditer(content)]
    archivos = []
    for item in _ITEM_RE.finditer(content):
        tipo, codigo, titulo, url = item.groups()
        tema = next((t for pos, t in reversed(temas) if pos < item.start()), None)
        archivos.append(
            {
                "titulo": f"{codigo} — {titulo}",
                "url": url,
                "formato": "PDF" if url.lower().endswith(".pdf") else "DESCONOCIDO",
                "grupo": tema,
                "tipo": "Regulación" if tipo == "reg" else "Resolución",
            }
        )
    return archivos


async def _fetch(url: str) -> str:
    cached = _cache.get(url)
    if cached is not None:
        return cached
    lock = _locks.setdefault(url, asyncio.Lock())
    async with lock:
        cached = _cache.get(url)
        if cached is not None:
            return cached
        content, truncated = await download_bytes(url)
        if truncated:
            raise ValueError(f"La página {url} superó el límite de descarga.")
        text = content.decode("utf-8", errors="replace")
        _cache.set(url, text)
        return text


def list_secciones() -> list[dict[str, str]]:
    """The five fixed sections, each with its public page as `url`."""
    return [
        {"seccion": s["seccion"], "nombre": s["nombre"], "url": s.get("url") or s["paginas"][0]}
        for s in _SECCIONES
    ]


async def get_seccion_archivos(seccion: str) -> dict[str, Any]:
    """List one section's files (title, URL, format, group, period)."""
    entry = next((s for s in _SECCIONES if s["seccion"] == _strip(seccion)), None)
    if entry is None:
        raise ValueError(
            f"Sección '{seccion}' no reconocida. Válidas: {', '.join(s['seccion'] for s in _SECCIONES)}"
        )

    paginas = await asyncio.gather(*(_fetch(url) for url in entry["paginas"]))
    archivos: list[dict[str, Any]] = []
    for url, text in zip(entry["paginas"], paginas, strict=True):
        if entry["tipo"] == "biblioteca":
            archivos += _biblioteca(text)
        elif entry["tipo"] == "temas":
            archivos += _temas(text)
        else:
            archivos += _enlaces(text, url)
    return {
        "seccion": entry["seccion"],
        "nombre": entry["nombre"],
        "url": entry.get("url") or entry["paginas"][0],
        "archivos": archivos,
    }
