import logging
import re
from html import unescape
from typing import Any

import httpx

from helpers import env_config
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_TIMEOUT = 25.0

# Browser-like UA required — gob.ec rejects bot-style User-Agents
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def _clean_html(text: str) -> str:
    """Strip HTML tags, preserving line breaks for list items and paragraphs."""
    if not text:
        return ""
    # gob.ec often double-encodes entities (&amp;quot; → &quot; → ")
    for _ in range(3):
        unescaped = unescape(text)
        if unescaped == text:
            break
        text = unescaped
    # Insert line breaks before block/list elements
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</tr>", "\n", text, flags=re.IGNORECASE)
    # Add bullet for list items
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    # Strip all remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Clean up whitespace per line, remove blank lines
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


async def _fetch_json(
    url: str,
    params: dict[str, Any] | None = None,
    session: httpx.AsyncClient | None = None,
) -> Any:
    own = session is None
    if own:
        transport = httpx.AsyncHTTPTransport(retries=2)
        session = httpx.AsyncClient(
            headers=_HEADERS, transport=transport, follow_redirects=True
        )
    assert session is not None
    try:
        logger.debug("GobEC GET %s params=%s", url, params)
        resp = await session.get(url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        logger.error("GobEC request failed for %s: %s", url, exc)
        raise
    finally:
        if own:
            await session.aclose()


def _gobec_url(path: str) -> str:
    return f"{env_config.get_base_url('gobec')}{path}"


async def search_tramites(
    institution_id: str = "",
    page: int = 0,
    session: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """
    List trámites, optionally filtered by institution.
    The gob.ec search param is unreliable, so we only filter by institution
    and let the tool do client-side text filtering.
    """
    params: dict[str, Any] = {"page": page}
    if institution_id:
        params["institution"] = institution_id
    result = await _fetch_json(_gobec_url("tramites"), params=params, session=session)
    if isinstance(result, list):
        return result
    return []


async def get_tramite(
    tramite_id: str, session: httpx.AsyncClient | None = None
) -> dict[str, Any] | None:
    """Get detailed info about a specific government procedure."""
    result = await _fetch_json(_gobec_url(f"tramites/{tramite_id}"), session=session)
    if isinstance(result, list) and result:
        return result[0]
    if isinstance(result, dict):
        return result
    return None


async def list_instituciones(
    page: int = 0,
    session: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """List public institutions from gob.ec."""
    result = await _fetch_json(
        _gobec_url("instituciones"), params={"page": page}, session=session
    )
    if isinstance(result, list):
        return result
    return []


async def find_institucion(
    query: str, session: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """
    Find institutions matching a query by searching through all pages.
    Searches in name, siglas (acronym), and description.
    """
    own = session is None
    if own:
        transport = httpx.AsyncHTTPTransport(retries=2)
        session = httpx.AsyncClient(
            headers=_HEADERS, transport=transport, follow_redirects=True
        )
    assert session is not None
    try:
        query_lower = query.lower()
        matches: list[dict[str, Any]] = []
        for page in range(3):  # Max 3 pages (~1500 institutions)
            items = await list_instituciones(page=page, session=session)
            if not items:
                break
            for inst in items:
                name = inst.get("institucion", "").lower()
                siglas = inst.get("siglas", "").lower()
                desc = inst.get("descripcion", "").lower()
                if query_lower in name or query_lower in siglas or query_lower in desc:
                    matches.append(inst)
        return matches
    finally:
        if own:
            await session.aclose()


async def get_institucion(
    institucion_id: str, session: httpx.AsyncClient | None = None
) -> dict[str, Any] | None:
    """Get details of a specific public institution."""
    result = await _fetch_json(
        _gobec_url(f"instituciones/{institucion_id}"), session=session
    )
    if isinstance(result, list) and result:
        return result[0]
    if isinstance(result, dict):
        return result
    return None


async def list_regulaciones(
    page: int = 0,
    session: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """List regulations published on gob.ec."""
    result = await _fetch_json(
        _gobec_url("regulaciones"), params={"page": page}, session=session
    )
    if isinstance(result, list):
        return result
    return []


async def get_regulacion(
    regulacion_id: str, session: httpx.AsyncClient | None = None
) -> dict[str, Any] | None:
    """Get details of a specific regulation."""
    result = await _fetch_json(
        _gobec_url(f"regulaciones/{regulacion_id}"), session=session
    )
    if isinstance(result, list) and result:
        return result[0]
    if isinstance(result, dict):
        return result
    return None


async def find_regulaciones(
    query: str,
    max_pages: int = 5,
    session: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Client-side search across regulation pages (gob.ec has no search param)."""
    words = [_strip(w) for w in query.split() if len(w) >= 2]
    if not words:
        return []

    own = session is None
    if own:
        transport = httpx.AsyncHTTPTransport(retries=2)
        session = httpx.AsyncClient(
            headers=_HEADERS, transport=transport, follow_redirects=True
        )
    assert session is not None
    try:
        matches: list[dict[str, Any]] = []
        for page in range(max(max_pages, 1)):
            items = await list_regulaciones(page=page, session=session)
            if not items:
                break
            for reg in items:
                blob = _strip(
                    f"{reg.get('regulacion', '')} {reg.get('descripcion', '')} "
                    f"{reg.get('tipo', '')} {reg.get('institucion_emisora', '')} "
                    f"{reg.get('registro_oficial_numero', '')}"
                )
                if all(w in blob for w in words):
                    matches.append(reg)
        return matches
    finally:
        if own:
            await session.aclose()


async def get_tramite_regulaciones(
    tramite_id: str, session: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Regulations that underpin a given trámite."""
    result = await _fetch_json(
        _gobec_url(f"tramites-regulaciones/{tramite_id}"), session=session
    )
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return [result]
    return []
