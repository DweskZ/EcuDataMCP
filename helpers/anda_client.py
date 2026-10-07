import logging
import re
from typing import Any
from urllib.parse import quote

import httpx

from helpers import env_config
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
    """Every catalog row matching `query`, paging through the whole result set."""
    rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        result = await search_catalog(
            query=query, limit=MAX_PAGE_SIZE, page=page, session=session
        )
        batch = result.get("rows", [])
        rows.extend(batch)
        if not batch or len(rows) >= int(result.get("found") or 0):
            break
    return rows


async def list_microdata_files(
    survey_id: str,
    session: httpx.AsyncClient | None = None,
) -> list[dict[str, str]]:
    """Discover direct download links for a survey's microdata files.

    ANDA gates the file list behind a one-click usage-terms form (research/
    statistical use only, no re-identifying respondents, cite the source) on
    the "get-microdata" page before showing download links. This walks that
    flow — GET the page for its CSRF token, POST acceptance — to reveal them.

    The download URLs themselves turned out to require no session or cookie
    at all once known: a plain GET from a fresh client with no prior request
    returns the file directly. So nothing from this session needs to carry
    over to actually fetch a file — these links work on their own.

    Takes the survey's numeric id (not its idno) since that's what the
    get-microdata URL is keyed on; get it from get_survey()'s "id" field.
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
            return []
        resp = await session.post(
            url,
            data={"ncsrf": token_match.group(1), "accept": "Aceptar"},
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
        files: dict[str, str] = {}
        for link, filename in _DOWNLOAD_LINK_RE.findall(resp.text):
            files[link] = filename
        return [{"filename": name, "url": link} for link, name in files.items()]
    except httpx.HTTPError as exc:
        logger.error("ANDA microdata file listing failed for id=%s: %s", survey_id, exc)
        raise
    finally:
        if own:
            await session.aclose()


def has_microdata(row: dict[str, Any]) -> bool:
    """True if a catalog entry has downloadable microdata, not just aggregates.

    Catalog-list rows use `form_model`; per-survey detail records use
    `data_access_type` instead. Check whichever is present.
    """
    value = row.get("form_model", row.get("data_access_type"))
    # Absent on both fields is "unknown", not "yes" -- default to False so a
    # caller isn't pointed at a survey that turns out to have no microdata.
    return value is not None and value != NO_MICRODATA_VALUE
