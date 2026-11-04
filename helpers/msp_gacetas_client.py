"""Client for MSP's (Ministerio de Salud Pública) weekly epidemiological
gazettes ("Gacetas Epidemiológicas"), every series the Dirección Nacional de
Vigilancia Epidemiológica publishes on salud.gob.ec: vaccine-preventable
diseases, vector-borne diseases, skin/re-emerging diseases, ETAS, IRAG,
outbreaks, toxic effects, respiratory, zoonotic, maternal and neonatal
deaths, tuberculosis, malnutrition, HIV and the older general/SIVE-Alerta
bulletins. Mapped live 2026-11-04 (docs/RESEARCH.md § Trigésimo sexta
pasada); this replaces the inmunoprevenibles-only client of 2026-09-10.

**Page discovery.** Each series has one WordPress post per period (roughly a
year), each a plain Gutenberg table of PDF links. A single paged
`/wp-json/wp/v2/posts?search=gaceta` sweep returns every archive page of
every series (110 on 2026-11-04, two result pages); `/wp-json/wp/v2/pages`
returns nothing. Slugs are then classified with one regex per series,
because MSP used two or three slug families per series over the years
(`gacetas-epidemiologicas-etas-2024`, `gaceta-etas-se-2022`,
`gacetas-enfermedades-transmitidas-por-agua-o-alimentos-2019`). Slugs that
match no series (two empty landing pages) are ignored. The slug's year is
not trusted: `gaceta-indicadores-2024` holds files uploaded 2024-2026, so
`anio`/`mes` come from the upload path.

**Week numbers.** Filenames changed conventions many times per series
(`INMUNO_03_2020`, `Gaceta-EPV-SE-35`, `ETV_Gaceta_42`, `5.-Gaceta-brotes-41`,
`VECTORES-10_20`, `SEMANA-47`). `semana` comes from an `SE`/`SEM`/`SEMANA`
marker when there is one and otherwise from the first standalone one- or
two-digit number (after dropping the `5.-` list prefix the brotes files
carry). Cumulative files (`SE-01-53`, `SE-01-SE45`, `Lepra-SE-01-03`) report
the last week of the range, with `semana_desde` holding the first; a
trailing number that is smaller than the week (`Gaceta-EPV-SE-22-1`) is
WordPress's duplicate-upload suffix, not a range.

**Links.** A few links are protocol-relative (`//www.salud.gob.ec/...`); 126
point at the dead host `instituciones.msp.gob.ec` and are dropped, which
leaves the 2012 Indicadores page empty and halves SIVE-Alerta. Some upload
paths carry an extra `/downloads/` segment. Files are deduplicated by URL
within a series (the same PDF is listed several times on some pages, and a
few are cross-posted to another series' page).
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://www.salud.gob.ec"
_WP_API_URL = f"{_BASE}/wp-json/wp/v2/posts"
_WP_TIMEOUT = 30.0
_CONCURRENCY = 3

# key, display name, slug regex, extra words that select the series in a
# query, tipo keywords (filename regex -> tipo; "general" otherwise).
_SERIES: list[dict[str, Any]] = [
    {
        "serie": "inmunoprevenibles",
        "nombre": "Inmunoprevenibles (enfermedades prevenibles por vacunación)",
        "slug": r"^(gacetas-inmunoprevenibles|enfermedades-prevenibles-por-vacunacion)",
        "alias": "vacunacion sarampion tosferina",
        "tipos": {r"tosferina": "tosferina"},
    },
    {
        "serie": "vectoriales",
        "nombre": "Enfermedades vectoriales",
        "slug": r"^gacetas-vectoriales",
        "alias": "dengue malaria paludismo chikungunya zika leishmaniasis",
        "tipos": {r"eventos-fa-|fiebre-amarilla": "fiebre_amarilla", r"dengue": "dengue"},
    },
    {
        "serie": "piel_reemergentes",
        "nombre": "Enfermedades de la piel o reemergentes",
        "slug": r"enfermedades-de-la-piel",
        "alias": "piel reemergentes lepra hansen hepatitis",
        "tipos": {r"lepra|hansen": "lepra", r"hepatitis": "hepatitis_c"},
    },
    {
        "serie": "indicadores",
        "nombre": "Gaceta Indicadores",
        "slug": r"^gaceta-indicadores",
        "alias": "",
        "tipos": {},
    },
    {
        "serie": "general",
        "nombre": "Gaceta General (2019-2022, antecesora de Indicadores)",
        "slug": r"^gacetas-epidemiologicas-gaceta-general",
        "alias": "",
        "tipos": {},
    },
    {
        "serie": "etas",
        "nombre": "ETAS (enfermedades transmitidas por agua y alimentos)",
        "slug": (
            r"^(gacetas-epidemiologicas-etas|gaceta-etas"
            r"|gacetas-enfermedades-transmitidas-por-agua)"
        ),
        "alias": "agua alimentos colera hepatitis a",
        "tipos": {r"colera": "colera"},
    },
    {
        "serie": "irag",
        "nombre": "IRAG (infecciones respiratorias agudas graves)",
        "slug": r"^(gacetas-epidemiologicas-infecciones-respiratorias|gacetas-epidemiologicas-2023$)",
        "alias": "infecciones respiratorias agudas graves",
        "tipos": {r"pisaac": "pisaac"},
    },
    {
        "serie": "brotes",
        "nombre": "Brotes",
        "slug": r"^(gacetas?-epidemiologicas?-brotes|gacetas-brotes|brotes(-\d+)?$)",
        "alias": "brote",
        "tipos": {},
    },
    {
        "serie": "efectos_toxicos",
        "nombre": "Efectos tóxicos (intoxicaciones)",
        "slug": r"^gacetas?-efectos?-toxicos?",
        "alias": "toxico intoxicaciones plaguicidas metanol",
        "tipos": {},
    },
    {
        "serie": "respiratorias",
        "nombre": "Enfermedades respiratorias y síndrome respiratorio",
        "slug": r"^(gaceta-enfermedades-respiratorias|gacetas-sindrome-respiratorio)",
        "alias": "neumonia influenza covid sindrome",
        "tipos": {},
    },
    {
        "serie": "zoonoticas",
        "nombre": "Enfermedades zoonóticas",
        "slug": r"^gacetas-enfermedades-zoonoticas",
        "alias": "zoonosis rabia leptospirosis",
        "tipos": {},
    },
    {
        "serie": "muerte_materna",
        "nombre": "Muerte materna",
        "slug": r"^(gacetas-muerte-materna|gacetas-muerte-evitable|gacetas-de-muerte-materna)",
        "alias": "maternas evitable",
        "tipos": {},
    },
    {
        "serie": "muerte_neonatal",
        "nombre": "Muerte neonatal (trimestral)",
        "slug": r"^gacetas-muerte-neonatal",
        "alias": "neonatales",
        "tipos": {},
    },
    {
        "serie": "tuberculosis",
        "nombre": "Tuberculosis",
        "slug": r"^gacetas-tuberculosis",
        "alias": "tb",
        "tipos": {},
    },
    {
        "serie": "desnutricion",
        "nombre": "Desnutrición (2016-2019)",
        "slug": r"^gacetas-desnutricion",
        "alias": "nutricion",
        "tipos": {},
    },
    {
        "serie": "vih",
        "nombre": "VIH (anual)",
        "slug": r"^gacetas-vih",
        "alias": "sida its",
        "tipos": {},
    },
    {
        "serie": "fiebre_amarilla",
        "nombre": "Fiebre amarilla",
        "slug": r"^gacetas-fiebre-amarilla",
        "alias": "",
        "tipos": {},
    },
    {
        "serie": "sive_alerta",
        "nombre": "SIVE-Alerta (gaceta general histórica, 2013-2018)",
        "slug": r"^gaceta-epidemiologica-ecuador-sive-alerta",
        "alias": "sive",
        "tipos": {},
    },
]
_SERIES_BY_KEY = {s["serie"]: s for s in _SERIES}
_SLUG_RES = [(s["serie"], re.compile(s["slug"])) for s in _SERIES]
_TIPO_RES = {
    s["serie"]: [(re.compile(pat, re.IGNORECASE), tipo) for pat, tipo in s["tipos"].items()]
    for s in _SERIES
}
_SERIES_TEXT = {
    s["serie"]: _strip(f"{s['serie'].replace('_', ' ')} {s['nombre']} {s['alias']}")
    for s in _SERIES
}

# The page list changes a few times a year; a page's PDFs weekly while its
# period is current.
_paginas_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_pagina_cache = TtlCache(ttl_seconds=3600.0, max_entries=256)
_paginas_lock = asyncio.Lock()

_PDF_LINK_RE = re.compile(r'href="([^"]+\.pdf)"', re.IGNORECASE)
_UPLOAD_PATH_RE = re.compile(r"/wp-content/uploads/(?:downloads/)?(\d{4})/(\d{2})/")
_LIST_PREFIX_RE = re.compile(r"^\d+\.-?")
# "N" covers the 2019 vectoriales "Gaceta N35".
_SE_RE = re.compile(
    r"(?<![A-Za-z])(?:SEMANA|SEM|SE|S|N)[\s_.\-]*(\d{1,3})(?!\d)", re.IGNORECASE
)
# "gaceta_brotesSE31": an uppercase SE glued to a lowercase word.
_SE_GLUED_RE = re.compile(r"(?<=[a-z])SE(\d{1,3})(?!\d)")
_RANGE_TAIL_RE = re.compile(
    r"^((?:[\s_\-]*(?:Y|A|AL)?[\s_\-]*(?:SE)?[\s_\-]*\d{1,2}(?!\d))+)", re.IGNORECASE
)
_NUM_RE = re.compile(r"(?<![0-9A-Za-z])(\d{1,2})(?![0-9])")
_YEAR_SUFFIX_RE = re.compile(r"(?<=\d)[_-](1[5-9]|2\d)$")


def _is_salud_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "salud.gob.ec" or host.endswith(".salud.gob.ec")


def _serie_de_slug(slug: str) -> str | None:
    return next((key for key, rx in _SLUG_RES if rx.search(slug)), None)


def _semana(stem: str) -> tuple[int | None, int | None]:
    """(semana, semana_desde) from a filename stem; see module docstring."""
    stem = _LIST_PREFIX_RE.sub("", stem)
    m = _SE_RE.search(stem) or _SE_GLUED_RE.search(stem)
    if m is None:
        # Without an SE marker, a trailing two-digit year ("VECTORES-10_20"
        # is week 10 of 2020) is not the end of a week range.
        stem = _YEAR_SUFFIX_RE.sub("", stem)
        m = _NUM_RE.search(stem)
    if m is None:
        return None, None
    digits = m.group(1)
    # "SE-341", "SE-041", "SE-81": WordPress's duplicate suffix glued to the
    # week (34, 04, 8), never a week above 53.
    if len(digits) == 3:
        digits = digits[:2]
    if int(digits) > 53:
        digits = digits[:1]
    first = int(digits)
    last = first
    tail = _RANGE_TAIL_RE.match(stem[m.end() :])
    if tail:
        for n in (int(x) for x in re.findall(r"\d{1,2}", tail.group(1))):
            if n <= last:
                break
            last = n
    if not 1 <= last <= 53:
        return None, None
    return last, (first if last != first else None)


async def _fetch_paginas() -> list[dict[str, str]]:
    """Every gazette archive page with its series, via one paged search."""
    cached = _paginas_cache.get("paginas")
    if cached is not None:
        return cached

    async with _paginas_lock:
        cached = _paginas_cache.get("paginas")
        if cached is not None:
            return cached

        logger.info("Descargando el listado de páginas de gacetas del MSP")
        posts: list[dict[str, Any]] = []
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as session:
            page = 1
            while True:
                resp = await session.get(
                    _WP_API_URL,
                    params={"search": "gaceta", "per_page": 100, "page": page, "_fields": "slug,link"},
                    timeout=_WP_TIMEOUT,
                )
                resp.raise_for_status()
                posts.extend(resp.json())
                if page >= int(resp.headers.get("X-WP-TotalPages", "1")):
                    break
                page += 1

        paginas = []
        for p in posts:
            serie = _serie_de_slug(p.get("slug", ""))
            if serie and _is_salud_url(p.get("link", "")):
                paginas.append({"serie": serie, "slug": p["slug"], "url": p["link"]})
        if paginas:
            _paginas_cache.set("paginas", paginas)
        return paginas


def _parse_archivos(html: str, pagina_url: str, serie: str) -> list[dict[str, Any]]:
    archivos: list[dict[str, Any]] = []
    for m in _PDF_LINK_RE.finditer(html):
        url = m.group(1)
        if url.startswith("//"):
            url = f"https:{url}"
        elif url.startswith("/"):
            url = f"{_BASE}{url}"
        if not _is_salud_url(url):
            continue
        filename = unquote(url.rsplit("/", 1)[-1])
        stem = filename.rsplit(".", 1)[0]
        upload_m = _UPLOAD_PATH_RE.search(url)
        semana, desde = _semana(stem)
        tipo = next((t for rx, t in _TIPO_RES[serie] if rx.search(filename)), "general")
        archivo: dict[str, Any] = {
            "titulo": stem,
            "url": url,
            "formato": "PDF",
            "serie": serie,
            "anio": upload_m.group(1) if upload_m else None,
            "mes": upload_m.group(2) if upload_m else None,
            "semana": str(semana) if semana is not None else None,
            "tipo": tipo,
            "pagina_origen": pagina_url,
        }
        if desde is not None:
            archivo["semana_desde"] = str(desde)
        archivos.append(archivo)
    return archivos


async def _fetch_pagina(pagina: dict[str, str], sem: asyncio.Semaphore) -> list[dict[str, Any]]:
    cached = _pagina_cache.get(pagina["url"])
    if cached is not None:
        return cached
    async with sem:
        logger.info("Descargando página de gacetas del MSP: %s", pagina["url"])
        try:
            content, truncated = await download_bytes(pagina["url"])
        except httpx.HTTPError:
            # salud.gob.ec answers the odd 503 under a burst; one retry
            # after a pause, then the caller reports the page as failed.
            await asyncio.sleep(2.0)
            content, truncated = await download_bytes(pagina["url"])
    if truncated:
        raise ValueError(f"La página {pagina['url']} superó el límite de descarga.")
    archivos = _parse_archivos(content.decode("utf-8", errors="replace"), pagina["url"], pagina["serie"])
    _pagina_cache.set(pagina["url"], archivos)
    return archivos


def _series_candidatas(tokens: list[str]) -> set[str]:
    """Series a query can be about: a token that names some series (its
    key, name or alias words) must name this one; tokens that name no
    series (years, weeks, file words) don't restrict anything."""
    candidatas = set(_SERIES_BY_KEY)
    for token in tokens:
        nombran = {k for k, text in _SERIES_TEXT.items() if token in text}
        if nombran:
            candidatas &= nombran
    return candidatas or set(_SERIES_BY_KEY)


def list_series() -> list[dict[str, str]]:
    """The series this client knows, without fetching anything."""
    return [{"serie": s["serie"], "nombre": s["nombre"]} for s in _SERIES]


async def search_gacetas(query: str = "") -> dict[str, Any]:
    """
    List MSP's epidemiological gazette PDFs, every series, 2013-present.

    Args:
        query: Free-text words (accent-insensitive), all of which must match
            the file's serie, series name, titulo, anio, semana or tipo. A
            word naming a series ("vectoriales", "brotes", "tuberculosis",
            "dengue"...) also limits which series' pages are fetched. Empty
            returns every file of every series.
    """
    tokens = _strip(query).split()
    candidatas = _series_candidatas(tokens)
    try:
        todas = await _fetch_paginas()
    except httpx.HTTPError as e:
        # httpx's connect timeouts stringify to "", which left callers with
        # "Error al buscar archivos de msp: " and nothing else.
        raise ValueError(
            f"salud.gob.ec no respondió ({type(e).__name__}). Desde fuera de Ecuador "
            "el sitio suele descartar la conexión (p. ej. desde Azure Brazil South); "
            "configura ECUADOR_MCP_GEO_PROXY (docs/GEOBLOCK_PLAN.md) o reintenta luego."
        ) from e
    paginas = [p for p in todas if p["serie"] in candidatas]

    sem = asyncio.Semaphore(_CONCURRENCY)
    por_pagina = await asyncio.gather(
        *(_fetch_pagina(p, sem) for p in paginas), return_exceptions=True
    )

    archivos: list[dict[str, Any]] = []
    fallidas: list[str] = []
    seen: set[tuple[str, str]] = set()
    for pagina, lista in zip(paginas, por_pagina, strict=True):
        if isinstance(lista, BaseException):
            logger.warning("Página de gacetas del MSP no disponible: %s (%s)", pagina["url"], lista)
            fallidas.append(pagina["url"])
            continue
        for a in lista:
            key = (a["serie"], a["url"])
            if key in seen:
                continue
            seen.add(key)
            archivos.append(a)

    def texto(a: dict[str, Any]) -> str:
        return _strip(
            f"{_SERIES_TEXT[a['serie']]} {a['titulo']} {a.get('anio') or ''} "
            f"{a.get('semana') or ''} {a['tipo']}"
        )

    matched = [a for a in archivos if all(t in texto(a) for t in tokens)]
    matched.sort(
        key=lambda a: (a["serie"], a.get("anio") or "", a.get("mes") or "", int(a.get("semana") or 0)),
    )
    if paginas and len(fallidas) == len(paginas):
        raise ValueError("salud.gob.ec no respondió para ninguna página de gacetas; reintenta luego.")
    por_serie: dict[str, int] = {}
    for a in matched:
        por_serie[a["serie"]] = por_serie.get(a["serie"], 0) + 1
    nota = (
        "Series: "
        + ", ".join(s["serie"] for s in _SERIES)
        + ". Nombra una en query para limitarla (p. ej. 'vectoriales 2026')."
    )
    if fallidas:
        nota += f" Sin respuesta de {len(fallidas)} página(s); la lista puede estar incompleta."
    return {
        "total": len(matched),
        "total_en_archivo": len(archivos),
        "por_serie": por_serie,
        "source": "MSP — Gacetas epidemiológicas (vigilancia epidemiológica semanal)",
        "url_fuente": f"{_BASE}/gacetas-epidemiologicas/",
        "nota": nota,
        "paginas_con_error": fallidas,
        "archivos": matched,
    }
