"""Client for Ecuador's civil aviation AIS (Aeronautical Information Service)
site, IFIS — Internet Flight Information System
(www.ais.aviacioncivil.gob.ec), run by the DGAC.

Confirmed live (2026-09-02): `/metar/{icao}`, `/notam?designador={icao}` and
`/sigmet` are genuinely public — no login, no session cookie required to
resubmit (each GET is independently servable), no JS rendering. The `Entrar`
link and a login form appear on every page, but only `/fpl/*` (flight plans)
actually enforces it; querying these three sections anonymously returns real
data (verified against SEQM/Mariscal Sucre Intl. — Quito — and SEFG, the FIR
covering all of continental Ecuador; a live SIGMET for MT REVENTADOR volcanic
ash was captured during investigation). An unknown designador (e.g. "ZZZZ")
does not error — METAR returns a `No existe registro de METAR...` message,
NOTAM returns an empty result table; both are handled as a normal empty
result rather than an exception.

Response format is old-school server-rendered HTML (YUI/jQuery UI chrome
from ~2014, per the page's own footer copyright), not JSON and not raw
fixed-width text as the ICAO standard would suggest for a bare AIS feed —
the raw METAR/NOTAM/SIGMET *codification* text is embedded verbatim inside
labeled `<div>`/`<td class="codificacion">` elements alongside a
Spanish-language decoded/tabular rendering. This client extracts the raw
codification (the standard aeronautical text an LLM caller can decode
itself) plus, for NOTAM/SIGMET, the site's own decoded field table (as a
label -> value dict, generic over field names so it survives the site
adding/removing a field) rather than guessing a fixed schema per field ID
(each field's DOM id carries an opaque numeric suffix that is not stable
across requests).

SIGMET is FIR-wide (Ecuador has a single FIR, SEFG) with no query
parameter — `/sigmet` lists all currently active advisories, full stop.
METAR and NOTAM take a `designador` (ICAO code, e.g. SEQM, SEGU, SECU).

Genuinely high-frequency data (METAR/SPECI arrive hourly-to-sub-hourly per
aerodrome, NOTAM/SIGMET can change at any time) -- TTLs here are short
(5-10 min) rather than the hours-long TTLs used for the mostly-static
catalog/publication-list clients in this project.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import quote

import httpx

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://www.ais.aviacioncivil.gob.ec"
_AIP_BASE = f"{_BASE}/ifis3"
_SOURCE_NAME = "DGAC Ecuador — IFIS (Internet Flight Information System)"

# METAR/NOTAM keyed per ICAO designator; SIGMET is a single FIR-wide page.
_metar_cache = TtlCache(ttl_seconds=300.0, max_entries=64)
_notam_cache = TtlCache(ttl_seconds=600.0, max_entries=64)
_sigmet_cache = TtlCache(ttl_seconds=300.0, max_entries=1)

# AIP content (AD 2.x aerodrome data sheets) changes on the ~28-day AIRAC
# cycle, not hourly like METAR/NOTAM/SIGMET, so it gets the hours-long TTL
# this module's docstring describes for mostly-static catalog content.
_aip_cache = TtlCache(ttl_seconds=86400.0, max_entries=32)
_aip_index_cache = TtlCache(ttl_seconds=86400.0, max_entries=1)

# Keyed per designator so concurrent lookups for different aerodromes don't
# serialize on one shared lock — same rationale as
# helpers/bce_iem_client.py's per-bulletin locks.
_metar_locks: dict[str, asyncio.Lock] = {}
_notam_locks: dict[str, asyncio.Lock] = {}
_sigmet_lock = asyncio.Lock()
_aip_locks: dict[str, asyncio.Lock] = {}
_aip_index_lock = asyncio.Lock()


def _lock_for(store: dict[str, asyncio.Lock], key: str) -> asyncio.Lock:
    lock = store.get(key)
    if lock is None:
        lock = asyncio.Lock()
        store[key] = lock
    return lock


def _clean_text(text: str | None) -> str:
    """Unescape entities, turn <br/> into newlines, strip remaining tags,
    collapse per-line whitespace. Same approach as helpers/gobec_client's
    _clean_html, reused here for METAR/NOTAM/SIGMET raw codification blocks.
    """
    if not text:
        return ""
    value = text
    for _ in range(3):
        unescaped = unescape(value)
        if unescaped == value:
            break
        value = unescaped
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    lines = [line.strip() for line in value.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def _clean_inline(text: str | None) -> str:
    """Same cleanup as _clean_text but collapsed to a single line — for
    field values/labels that should never contain a line break.
    """
    return " ".join(_clean_text(text).split("\n")).strip()


# ---------------------------------------------------------------------------
# METAR
# ---------------------------------------------------------------------------

_METAR_NOT_FOUND_RE = re.compile(r"No existe registro de METAR", re.IGNORECASE)
_METAR_ENTRY_RE = re.compile(
    r'<div class="taf_h1">\s*(?P<tipo>METAR|SPECI) del '
    r"(?P<dia>\d{2})-(?P<mes>\d{2})-(?P<anio>\d{4}) a las "
    r"(?P<hora>\d{2}):(?P<minuto>\d{2}) UTC\s*</div>\s*"
    r'<div class="taf_h3 codificacion">\s*(?P<raw>.*?)\s*</div>',
    re.DOTALL,
)


def _parse_metar(html: str, designador: str) -> list[dict[str, Any]]:
    html = unescape(html)
    if _METAR_NOT_FOUND_RE.search(html):
        return []
    reportes = []
    for m in _METAR_ENTRY_RE.finditer(html):
        fecha_utc = (
            f"{m.group('anio')}-{m.group('mes')}-{m.group('dia')} "
            f"{m.group('hora')}:{m.group('minuto')}:00"
        )
        reportes.append(
            {
                "tipo": m.group("tipo"),
                "fecha_utc": fecha_utc,
                "raw": _clean_inline(m.group("raw")),
            }
        )
    return reportes


async def _fetch_metar_html(designador: str) -> str:
    url = f"{_BASE}/metar/{quote(designador)}"
    logger.info("Consultando METAR/SPECI de %s en IFIS", designador)
    content, truncated = await download_bytes(url)
    if truncated:
        raise ValueError(f"La página de {url} superó el límite de descarga.")
    return content.decode("utf-8", errors="replace")


async def get_metar(designador: str) -> dict[str, Any]:
    """
    Fetch the most recent METAR/SPECI reports for an Ecuadorian aerodrome
    from IFIS.

    Args:
        designador: ICAO code of the aerodrome/helipad (e.g. SEQM for
            Quito, SEGU for Guayaquil).
    """
    icao = designador.strip().upper()
    if not icao:
        raise ValueError("Debe especificar un designador OACI (ej. SEQM).")

    cached = _metar_cache.get(icao)
    if cached is not None:
        return cached

    async with _lock_for(_metar_locks, icao):
        cached = _metar_cache.get(icao)
        if cached is not None:
            return cached

        html = await _fetch_metar_html(icao)
        reportes = _parse_metar(html, icao)
        result = {
            "designador": icao,
            "total": len(reportes),
            "reportes": reportes,
            "source": f"{_SOURCE_NAME} — METAR/SPECI",
            "url_fuente": f"{_BASE}/metar/{icao}",
        }
        # Only cache a result that actually found something to render, or a
        # confirmed "no records" response -- both are legitimate outcomes
        # of a working scrape, so always cache here (unlike the "empty
        # scrape looks broken" caution other clients apply to a whole
        # listing page).
        _metar_cache.set(icao, result)
        return result


# ---------------------------------------------------------------------------
# NOTAM
# ---------------------------------------------------------------------------

_NOTAM_COUNT_RE = re.compile(r"NOTAMs\s*\((?P<n>\d+)\)")
_NOTAM_CAPTION_RE = re.compile(
    r"<caption>Descripci.n de Informe NOTAM para\s*aer.dromo\s*"
    r"(?P<nombre>.*?)\((?P<icao>[A-Za-z0-9]+)\)</caption>",
    re.DOTALL,
)
_NOTAM_BLOCK_RE = re.compile(
    r'<tr class="notam_raw">(?P<block>.*?)(?=<tr class="notam_raw">|</tbody>)',
    re.DOTALL,
)
_RAW_CODE_RE = re.compile(
    r'<td[^>]*headers="notam"[^>]*class="codificacion">\s*(?P<raw>.*?)\s*</td>',
    re.DOTALL,
)
_FIELD_PAIR_RE = re.compile(
    r'<td scope="row" id="[^"]+" headers="indice">\s*(?P<campo>.*?)\s*</td>\s*'
    r'<td headers="[^"]+ valor">\s*(?P<valor>.*?)\s*</td>',
    re.DOTALL,
)
_NOTAM_SERIE_RE = re.compile(r"^(?P<serie>\S+)\s+NOTAM(?P<accion>[NRC])")


def _parse_field_pairs(block: str) -> dict[str, str]:
    campos: dict[str, str] = {}
    for m in _FIELD_PAIR_RE.finditer(block):
        campo = _clean_inline(m.group("campo"))
        valor = _clean_inline(m.group("valor"))
        if campo:
            campos[campo] = valor
    return campos


def _parse_notam(html: str) -> tuple[list[dict[str, Any]], str | None, str | None]:
    html = unescape(html)
    caption_m = _NOTAM_CAPTION_RE.search(html)
    aerodromo_nombre = _clean_inline(caption_m.group("nombre")) if caption_m else None
    aerodromo_icao = caption_m.group("icao") if caption_m else None

    notams: list[dict[str, Any]] = []
    for block_m in _NOTAM_BLOCK_RE.finditer(html):
        block = block_m.group("block")
        raw_m = _RAW_CODE_RE.search(block)
        if not raw_m:
            continue
        raw = _clean_text(raw_m.group("raw"))
        if not raw:
            continue
        serie_m = _NOTAM_SERIE_RE.match(raw)
        notams.append(
            {
                "serie": serie_m.group("serie") if serie_m else None,
                "raw": raw,
                "campos": _parse_field_pairs(block),
            }
        )
    return notams, aerodromo_nombre, aerodromo_icao


async def _fetch_notam_html(designador: str) -> str:
    url = f"{_BASE}/notam?designador={quote(designador)}"
    logger.info("Consultando NOTAM de %s en IFIS", designador)
    content, truncated = await download_bytes(url)
    if truncated:
        raise ValueError(f"La página de {url} superó el límite de descarga.")
    return content.decode("utf-8", errors="replace")


async def get_notam(designador: str) -> dict[str, Any]:
    """
    Fetch active NOTAMs (Notices to Airmen) for an Ecuadorian aerodrome
    from IFIS.

    Args:
        designador: ICAO code of the aerodrome/helipad (e.g. SEQM for
            Quito, SEGU for Guayaquil).
    """
    icao = designador.strip().upper()
    if not icao:
        raise ValueError("Debe especificar un designador OACI (ej. SEQM).")

    cached = _notam_cache.get(icao)
    if cached is not None:
        return cached

    async with _lock_for(_notam_locks, icao):
        cached = _notam_cache.get(icao)
        if cached is not None:
            return cached

        html = await _fetch_notam_html(icao)
        notams, aerodromo_nombre, aerodromo_icao = _parse_notam(html)
        count_m = _NOTAM_COUNT_RE.search(html)
        result = {
            "designador": icao,
            "aerodromo_nombre": aerodromo_nombre,
            "aerodromo_icao": aerodromo_icao or icao,
            "total": len(notams),
            "total_declarado": int(count_m.group("n")) if count_m else None,
            "notams": notams,
            "source": f"{_SOURCE_NAME} — NOTAM",
            "url_fuente": f"{_BASE}/notam?designador={icao}",
        }
        _notam_cache.set(icao, result)
        return result


# ---------------------------------------------------------------------------
# SIGMET
# ---------------------------------------------------------------------------

_SIGMET_BLOCK_RE = re.compile(
    r'<tr class="sigmet_raw">(?P<block>.*?)(?=<tr class="sigmet_raw">|</tbody>)',
    re.DOTALL,
)
_SIGMET_RAW_CODE_RE = re.compile(
    r'<td[^>]*headers="sigmet"[^>]*class="codificacion">\s*(?P<raw>.*?)\s*</td>',
    re.DOTALL,
)


def _parse_sigmet(html: str) -> list[dict[str, Any]]:
    sigmets: list[dict[str, Any]] = []
    for block_m in _SIGMET_BLOCK_RE.finditer(html):
        block = block_m.group("block")
        raw_m = _SIGMET_RAW_CODE_RE.search(block)
        if not raw_m:
            continue
        raw = _clean_text(raw_m.group("raw"))
        if not raw:
            continue
        sigmets.append({"raw": raw, "campos": _parse_field_pairs(block)})
    return sigmets


async def _fetch_sigmet_html() -> str:
    url = f"{_BASE}/sigmet"
    logger.info("Consultando SIGMET activos en IFIS")
    content, truncated = await download_bytes(url)
    if truncated:
        raise ValueError(f"La página de {url} superó el límite de descarga.")
    return content.decode("utf-8", errors="replace")


async def get_sigmet() -> dict[str, Any]:
    """
    Fetch currently active SIGMETs (significant meteorological information —
    volcanic ash, severe turbulence/icing, thunderstorms, etc.) for
    Ecuador's FIR (SEFG) from IFIS.

    Ecuador has a single FIR, so this covers the whole country with no
    per-aerodrome parameter.
    """
    cached = _sigmet_cache.get("sigmet")
    if cached is not None:
        return cached

    async with _sigmet_lock:
        cached = _sigmet_cache.get("sigmet")
        if cached is not None:
            return cached

        html = await _fetch_sigmet_html()
        sigmets = _parse_sigmet(html)
        result = {
            "total": len(sigmets),
            "sigmets": sigmets,
            "source": f"{_SOURCE_NAME} — SIGMET",
            "url_fuente": f"{_BASE}/sigmet",
        }
        _sigmet_cache.set("sigmet", result)
        return result


# ---------------------------------------------------------------------------
# AIP (Aeronautical Information Publication) — AD 2.x aerodrome data sheets
# ---------------------------------------------------------------------------
#
# Confirmed live (2026-09-06): /ifis3/aip/AD%202%20{ICAO} is a fully public,
# server-rendered eAIP page (no login, no JS) generated by a MediaWiki-style
# exporter — each ICAO Annex 15 subsection is an <h1><span class="mw-headline">
# heading followed by a numbered field table (<td><b><i>N</i></b></td>
# label/value rows). An unknown designador returns a genuine HTTP 404, unlike
# METAR/NOTAM's "empty result" pattern, so it is surfaced as a ValueError
# instead of an empty list.

_AIP_SECTION_RE = re.compile(
    r'<h1><span class="mw-headline"[^>]*>(?P<titulo>.*?)</span></h1>', re.DOTALL
)
_AIP_FIELD_ROW_RE = re.compile(
    r"<tr>\s*<td[^>]*><b><i>\d+</i></b></td>\s*"
    r"<td><b><i>(?P<etiqueta>.*?)</i></b></td>\s*"
    r"<td>(?P<valor>.*?)</td>\s*</tr>",
    re.DOTALL,
)
_AIP_NOMBRE_RE = re.compile(r'<div class="center">(?P<nombre>.*?)</div>', re.DOTALL)
_AIP_INDEX_RE = re.compile(
    r'<a href="/ifis3/aip/AD%202%20(?P<icao>[A-Z]{4})"[^>]*>(?P<texto>.*?)</a>',
    re.DOTALL,
)


def _parse_aip_secciones(html: str) -> list[dict[str, Any]]:
    headers = list(_AIP_SECTION_RE.finditer(html))
    secciones = []
    for i, header_m in enumerate(headers):
        start = header_m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(html)
        block = html[start:end]
        campos = [
            {
                "etiqueta": _clean_inline(field_m.group("etiqueta")),
                "valor": _clean_text(field_m.group("valor")),
            }
            for field_m in _AIP_FIELD_ROW_RE.finditer(block)
        ]
        secciones.append(
            {"titulo": _clean_inline(header_m.group("titulo")), "campos": campos}
        )
    return secciones


async def get_aip_aerodromo(designador: str) -> dict[str, Any]:
    """
    Fetch the published AIP AD 2.x data sheet for an Ecuadorian
    aerodrome/helipad from DGAC's public eAIP.

    Args:
        designador: ICAO code of the aerodrome/helipad (e.g. SEQM for
            Quito, SEGU for Guayaquil).
    """
    icao = designador.strip().upper()
    if not icao:
        raise ValueError("Debe especificar un designador OACI (ej. SEQM).")

    cached = _aip_cache.get(icao)
    if cached is not None:
        return cached

    async with _lock_for(_aip_locks, icao):
        cached = _aip_cache.get(icao)
        if cached is not None:
            return cached

        url = f"{_AIP_BASE}/aip/AD%202%20{icao}"
        logger.info("Consultando AIP AD 2 de %s en IFIS3", icao)
        try:
            content, truncated = await download_bytes(url)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ValueError(
                    f"No existe ficha AIP para el designador {icao}. Usa "
                    "list_aip_aerodromos para ver los designadores publicados."
                ) from exc
            raise
        if truncated:
            raise ValueError(f"La página de {url} superó el límite de descarga.")

        html = unescape(content.decode("utf-8", errors="replace"))
        secciones = _parse_aip_secciones(html)
        nombre_m = _AIP_NOMBRE_RE.search(html)
        result = {
            "designador": icao,
            "nombre": _clean_inline(nombre_m.group("nombre")) if nombre_m else None,
            "total_secciones": len(secciones),
            "secciones": secciones,
            "source": f"{_SOURCE_NAME} — AIP AD 2 (ficha de aeródromo)",
            "url_fuente": url,
        }
        _aip_cache.set(icao, result)
        return result


async def list_aip_aerodromos() -> dict[str, Any]:
    """
    List the ICAO designators and names of every aerodrome/helipad with a
    published AIP AD 2.x page in DGAC's eAIP.
    """
    cached = _aip_index_cache.get("index")
    if cached is not None:
        return cached

    async with _aip_index_lock:
        cached = _aip_index_cache.get("index")
        if cached is not None:
            return cached

        url = f"{_AIP_BASE}/aip/AD%202"
        logger.info("Listando aeródromos AIP en IFIS3")
        content, truncated = await download_bytes(url)
        if truncated:
            raise ValueError(f"La página de {url} superó el límite de descarga.")

        html = unescape(content.decode("utf-8", errors="replace"))
        aerodromos = []
        seen: set[str] = set()
        for m in _AIP_INDEX_RE.finditer(html):
            icao = m.group("icao")
            if icao in seen:
                continue
            texto = _clean_inline(m.group("texto"))
            nombre_m = re.match(rf"AD 2 {icao} - (?P<nombre>.+)$", texto)
            if not nombre_m:
                # Excludes sub-procedure pages that share the AD 2 {icao}
                # prefix but carry extra text (e.g. "AD 2 SEGU 28.4 RNAV
                # SID 4 - ...") — those aren't a distinct aerodrome.
                continue
            seen.add(icao)
            aerodromos.append(
                {"designador": icao, "nombre": nombre_m.group("nombre").strip()}
            )

        result = {
            "total": len(aerodromos),
            "aerodromos": aerodromos,
            "source": f"{_SOURCE_NAME} — AIP, índice de aeródromos",
            "url_fuente": url,
        }
        _aip_index_cache.set("index", result)
        return result


def clear_cache() -> None:
    """Clear all cached METAR/NOTAM/SIGMET/AIP results; useful for tests."""
    _metar_cache.clear()
    _notam_cache.clear()
    _sigmet_cache.clear()
    _aip_cache.clear()
    _aip_index_cache.clear()
