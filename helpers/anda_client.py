import asyncio
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import quote

import httpx

from helpers import env_config
from helpers.cache import TtlCache
from helpers.geo_proxy import proxy_for
from helpers.logging import MAIN_LOGGER_NAME
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_TIMEOUT = 20.0

_CSRF_RE = re.compile(r'name="ncsrf"\s+value="([a-f0-9]+)"')
_DOWNLOAD_LINK_RE = re.compile(
    r'href="(https://anda\.inec\.gob\.ec/anda5/index\.php/catalog/\d+/download/\d+)"'
    r'[^>]*title="([^"]+)"'
)

# NADA marks surveys with no microdata attached (aggregate-only publications,
# e.g. price indices) as "data_na" — in the catalog list endpoint that's the
# form_model field, in the per-survey detail endpoint it's data_access_type.
# Anything else ("direct", "external", etc.) means the survey has actual
# microdata behind it. data_class_id looks like the obvious field to check
# but it comes back null on every survey regardless of access — don't use it.
NO_MICRODATA_VALUE = "data_na"


def _anda_url(path: str) -> str:
    return f"{env_config.get_base_url('anda')}{path}"


# The catalog endpoint accepts up to 100 rows per page; anything larger is
# silently clamped by the server.
MAX_PAGE_SIZE = 100


async def search_catalog(
    query: str = "",
    limit: int = 10,
    page: int = 1,
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Search the ANDA (NADA) survey/census catalog.

    ANDA's full-text search (`sk`) is loose — multi-word queries are matched
    fairly broadly rather than as a strict AND, so short specific keywords
    work better than long phrases.
    """
    own = session is None
    if own:
        session = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            proxy=proxy_for(env_config.get_base_url("anda_site")),
        )
    assert session is not None
    try:
        params: dict[str, Any] = {"ps": min(limit, MAX_PAGE_SIZE)}
        if page > 1:
            params["page"] = page
        if query:
            params["sk"] = query
        logger.debug("ANDA GET catalog params=%s", params)
        resp = await session.get(
            _anda_url("catalog"), params=params, timeout=_TIMEOUT, follow_redirects=True
        )
        resp.raise_for_status()
        return resp.json().get("result", {})
    except httpx.HTTPError as exc:
        logger.error("ANDA request failed: %s", exc)
        raise
    finally:
        if own:
            await session.aclose()


async def get_survey(
    idno: str,
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Fetch full DDI-style metadata for one survey.

    Accepts the idno or the numeric catalog id. The idno is not a safe key on
    its own (some contain spaces, and several studies share a prefix), so an
    all-digit value is looked up as the numeric id (`id_format=id`) and any
    idno is URL-encoded.
    """
    own = session is None
    if own:
        session = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            proxy=proxy_for(env_config.get_base_url("anda_site")),
        )
    assert session is not None
    try:
        logger.debug("ANDA GET catalog detail idno=%s", idno)
        by_numeric_id = idno.strip().isdigit()
        resp = await session.get(
            _anda_url(f"catalog/{quote(idno.strip(), safe='')}"),
            params={"id_format": "id"} if by_numeric_id else None,
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        if resp.status_code == 400:
            try:
                message = resp.json().get("message", "")
            except ValueError:
                message = ""
            if message == "IDNO-NOT-FOUND":
                raise ValueError(f"No se encontró ninguna encuesta con idno '{idno}' en ANDA.")
        resp.raise_for_status()
        return resp.json().get("dataset", {})
    except httpx.HTTPError as exc:
        logger.error("ANDA survey detail request failed for %s: %s", idno, exc)
        raise
    finally:
        if own:
            await session.aclose()


async def search_catalog_all(
    query: str,
    max_pages: int = 5,
    session: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Every catalog row matching `query`, paging through the whole result set.

    The first page says how many rows exist (`found`), so the remaining pages
    are fetched concurrently instead of one after another.
    """
    first = await search_catalog(query=query, limit=MAX_PAGE_SIZE, page=1, session=session)
    rows: list[dict[str, Any]] = list(first.get("rows", []))
    found = int(first.get("found") or 0)
    if not rows or len(rows) >= found:
        return rows
    last_page = min(max_pages, -(-found // len(rows)))
    rest = await asyncio.gather(
        *(
            search_catalog(query=query, limit=MAX_PAGE_SIZE, page=p, session=session)
            for p in range(2, last_page + 1)
        )
    )
    for result in rest:
        rows.extend(result.get("rows", []))
    return rows


_RESOURCE_SPLIT_RE = re.compile(r'<div class="resource"')
_RESOURCE_NAME_RE = re.compile(r'<span class="resource-info"[^>]*>(.*?)</span>', re.DOTALL)
_ANCHOR_RE = re.compile(r"<a\s([^>]*)>(.*?)</a>", re.DOTALL)
_HREF_RE = re.compile(r'href="([^"]+)"')
_TITLE_RE = re.compile(r'title="([^"]*)"')
_CATALOG_DOWNLOAD_RE = re.compile(r"/catalog/\d+/download/\d+")
_TAG_RE = re.compile(r"<[^>]+>")

# How the microdata of one study can be obtained, as seen on its get-microdata
# page (not as flagged by the catalog, which is unreliable: CPV 2022 is
# "direct" in the catalog but has no attached file, only an external link).
ACCESS_DIRECT = "directo"
ACCESS_EXTERNAL = "enlace_externo"
ACCESS_REGISTRATION = "registro"
ACCESS_REQUEST = "solicitud"
ACCESS_NONE = "ninguno"
ACCESS_UNKNOWN = "desconocido"

# Obtainable at all (even if it takes an account or a request).
_OBTAINABLE = {ACCESS_DIRECT, ACCESS_EXTERNAL, ACCESS_REGISTRATION, ACCESS_REQUEST}

# Two layers: an in-memory 6 h cache (fast path, keyed by study id) and a
# persistent per-study store on disk, so a new session does not re-probe the
# same studies. The persistent key carries the catalog's `changed` timestamp,
# so an edited study is probed again; the TTL bounds how long an unchanged
# study is trusted (ANDA can switch a study to a login wall without touching
# `changed`).
_access_cache = TtlCache(ttl_seconds=6 * 3600.0, max_entries=1024)
_access_store = TtlCache(ttl_seconds=7 * 86400.0, max_entries=2048, persist="anda_access")

# Concurrent probes against anda.inec.gob.ec; it answered 8 at once without
# throttling in the live benchmark (RESEARCH, Cuadragésima segunda pasada).
VERIFY_CONCURRENCY = 8
# `verificar_acceso="auto"` probes only this many results (the top of the page).
AUTO_VERIFY_TOP = 10

# Catalog `form_model` values that fully decide the access type without a
# probe. "public" is ANDA's login wall (351, 365, 389 all read "Inicie sesión
# para acceder a los datos"). "direct" is NOT reliable (CPV 2022 is "direct"
# with only an external link) and "remote"/"licensed" were never seen live, so
# those still go through the real download page.
_FORM_MODEL_ACCESS = {
    "public": {
        "tipo_acceso": ACCESS_REGISTRATION,
        "archivos": [],
        "enlaces_externos": [],
        "nota": "ANDA exige iniciar sesión (cuenta gratuita); inferido del catálogo (form_model=public).",
    },
}


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG_RE.sub(" ", text))).strip()


def parse_microdata_page(html: str) -> dict[str, Any]:
    """Classify a get-microdata page (after the terms step) by how data is served.

    Returns `tipo_acceso`, `archivos` (files hosted by ANDA), `enlaces_externos`
    (files that ANDA only links to) and a `nota`. Direct files win over external
    links when a study has both; a page showing neither is "ninguno" when ANDA
    says so explicitly, and a ValueError otherwise (an unrecognised page is not
    evidence that there is nothing to download).
    """
    files: dict[str, str] = {}
    for link, filename in _DOWNLOAD_LINK_RE.findall(html):
        files[link] = filename

    external: dict[str, str] = {}
    for block in _RESOURCE_SPLIT_RE.split(html)[1:]:
        name_match = _RESOURCE_NAME_RE.search(block)
        name = _squash(name_match.group(1)) if name_match else ""
        for attrs, _inner in _ANCHOR_RE.findall(block):
            href_match = _HREF_RE.search(attrs)
            if not href_match or 'class="download' not in attrs:
                continue
            href = unescape(href_match.group(1))
            if _CATALOG_DOWNLOAD_RE.search(href):
                continue
            title_match = _TITLE_RE.search(attrs)
            external.setdefault(href, name or (title_match.group(1) if title_match else href))

    external_links = [{"nombre": n, "url": u} for u, n in external.items()]
    direct_files = [{"filename": n, "url": u} for u, n in files.items()]
    text = _squash(re.sub(r"<(script|style).*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)).lower()

    if direct_files:
        return {
            "tipo_acceso": ACCESS_DIRECT,
            "archivos": direct_files,
            "enlaces_externos": external_links,
            "nota": None,
        }
    if external_links:
        return {
            "tipo_acceso": ACCESS_EXTERNAL,
            "archivos": [],
            "enlaces_externos": external_links,
            "nota": (
                "ANDA no aloja los archivos: solo enlaza a otro sitio (el catálogo la "
                "marca como acceso 'direct' aunque no haya archivos adjuntos)."
            ),
        }
    if "inicie sesión" in text or "regístrese" in text or "log in to access" in text:
        return {
            "tipo_acceso": ACCESS_REGISTRATION,
            "archivos": [],
            "enlaces_externos": [],
            "nota": "ANDA exige iniciar sesión (cuenta gratuita) para ver los archivos.",
        }
    if "data access not available" in text:
        return {
            "tipo_acceso": ACCESS_NONE,
            "archivos": [],
            "enlaces_externos": [],
            "nota": "ANDA indica 'Data Access Not Available' para este estudio.",
        }
    if re.search(r"access-licensed|solicitar (el )?acceso|request access|/request", html, re.IGNORECASE):
        return {
            "tipo_acceso": ACCESS_REQUEST,
            "archivos": [],
            "enlaces_externos": [],
            "nota": "El acceso a los microdatos requiere enviar una solicitud al INEC.",
        }
    if "data-files" in html or 'class="resources' in html:
        return {
            "tipo_acceso": ACCESS_NONE,
            "archivos": [],
            "enlaces_externos": [],
            "nota": "La página de descarga no lista archivos ni enlaces.",
        }
    raise ValueError("No se reconoció la página get-microdata de ANDA; puede haber cambiado")


async def get_microdata_access(
    survey_id: str,
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """How a survey's microdata can really be obtained (see parse_microdata_page).

    ANDA gates the file list behind a one-click usage-terms form (research/
    statistical use only, no re-identifying respondents, cite the source) on
    the "get-microdata" page before showing download links. This walks that
    flow — GET the page for its CSRF token, POST acceptance — and classifies
    what it reveals. Pages without the form (login wall, "Data Access Not
    Available") are classified from the first response.

    Direct download URLs need no session or cookie once known: a plain GET from
    a fresh client returns the file. Takes the survey's numeric id (not its
    idno), since that is what the get-microdata URL is keyed on.
    """
    own = session is None
    if own:
        session = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            proxy=proxy_for(env_config.get_base_url("anda_site")),
        )
    assert session is not None
    try:
        url = f"{env_config.get_base_url('anda_site')}index.php/catalog/{survey_id}/get-microdata"
        page = await session.get(url, timeout=_TIMEOUT, follow_redirects=True)
        page.raise_for_status()
        token_match = _CSRF_RE.search(page.text)
        if not token_match:
            try:
                return parse_microdata_page(page.text)
            except ValueError:
                # An anti-bot or geoblock page has no form either; reading that
                # as "no files" would be a false negative.
                raise ValueError(
                    "No se encontró el token CSRF en la página get-microdata de ANDA; "
                    "la página puede estar bloqueada o haber cambiado"
                ) from None
        resp = await session.post(
            url,
            data={"ncsrf": token_match.group(1), "accept": "Aceptar"},
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return parse_microdata_page(resp.text)
    except httpx.HTTPError as exc:
        logger.error("ANDA microdata access lookup failed for id=%s: %s", survey_id, exc)
        raise
    finally:
        if own:
            await session.aclose()


async def list_microdata_files(
    survey_id: str,
    session: httpx.AsyncClient | None = None,
) -> list[dict[str, str]]:
    """Direct download links for a survey's microdata (empty if ANDA only links out)."""
    access = await get_microdata_access(survey_id, session=session)
    return access["archivos"]


def catalog_access(row: dict[str, Any]) -> dict[str, Any] | None:
    """Access decided by the catalog flag alone, when that is reliable (else None)."""
    if not has_microdata(row):
        return None
    return _FORM_MODEL_ACCESS.get(str(row.get("form_model")))


def _store_key(survey_id: str, row: dict[str, Any]) -> str:
    return f"{survey_id}|{row.get('changed') or ''}"


async def verify_access(
    rows: list[dict[str, Any]],
    concurrency: int = VERIFY_CONCURRENCY,
    top: int | None = None,
) -> dict[str, dict[str, Any] | None]:
    """Real access type for catalog rows flagged as having microdata.

    Keyed by the row's numeric id. Rows ANDA marks `data_na` are skipped (no
    microdata by definition); a lookup that fails maps to None so callers fall
    back to the catalog flag instead of failing the whole search. Per study the
    answer comes from, in order: the catalog flag when it is reliable
    (`form_model=public`), the 6 h memory cache, the persistent store (keyed by
    id + the catalog's `changed`), and finally the real download page, probed
    with up to `concurrency` requests at once. `top` limits the work to the
    first N rows; the rest are absent from the result.
    """
    candidates = [r for r in rows if r.get("id") and has_microdata(r)]
    if top is not None:
        candidates = candidates[:top]
    out: dict[str, dict[str, Any] | None] = {}
    pending: list[dict[str, Any]] = []
    for row in candidates:
        survey_id = str(row["id"])
        decided = catalog_access(row)
        if decided is not None:
            out[survey_id] = decided
            continue
        cached = _access_cache.get(survey_id)
        if cached is None:
            stored = _access_store.get(_store_key(survey_id, row))
            if stored is not None:
                cached = _access_cache_from_store(stored)
                _access_cache.set(survey_id, cached)
        if cached is not None:
            out[survey_id] = cached
        else:
            pending.append(row)
    if not pending:
        return out

    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        proxy=proxy_for(env_config.get_base_url("anda_site")),
    ) as session:

        async def one(row: dict[str, Any]) -> None:
            survey_id = str(row["id"])
            async with sem:
                try:
                    access = await get_microdata_access(survey_id, session=session)
                except Exception as exc:
                    logger.warning("ANDA access check skipped for %s: %s", survey_id, exc)
                    out[survey_id] = None
                    return
            _access_cache.set(survey_id, access)
            _access_store.set(
                _store_key(survey_id, row),
                {"tipo_acceso": access["tipo_acceso"], "nota": access.get("nota")},
            )
            out[survey_id] = access

        await asyncio.gather(*(one(r) for r in pending))
    return out


def _access_cache_from_store(stored: dict[str, Any]) -> dict[str, Any]:
    """The persistent store keeps only the classification, not the file lists."""
    return {"archivos": [], "enlaces_externos": [], **stored}


def access_summary(row: dict[str, Any], access: dict[str, Any] | None) -> dict[str, Any]:
    """`tipo_acceso` + `microdatos_disponibles` for a catalog row or survey record.

    `microdatos_disponibles` is true when there is a way to obtain the data
    (direct file, external link, login or request), false when ANDA offers
    none; without a verified lookup it falls back to the catalog flag, with
    `tipo_acceso` "desconocido".
    """
    if not has_microdata(row):
        return {"tipo_acceso": ACCESS_NONE, "microdatos_disponibles": False}
    if access is None:
        return {"tipo_acceso": ACCESS_UNKNOWN, "microdatos_disponibles": True}
    return {
        "tipo_acceso": access["tipo_acceso"],
        "microdatos_disponibles": access["tipo_acceso"] in _OBTAINABLE,
    }


def has_microdata(row: dict[str, Any]) -> bool:
    """True if a catalog entry has downloadable microdata, not just aggregates.

    Catalog-list rows use `form_model`; per-survey detail records use
    `data_access_type` instead. Check whichever is present.
    """
    value = row.get("form_model", row.get("data_access_type"))
    # Absent on both fields is "unknown", not "yes" -- default to False so a
    # caller isn't pointed at a survey that turns out to have no microdata.
    return value is not None and value != NO_MICRODATA_VALUE
