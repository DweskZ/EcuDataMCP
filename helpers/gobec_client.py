import asyncio
import json
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import quote

import httpx

from helpers import env_config
from helpers.geo_proxy import proxy_for
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_TIMEOUT = 25.0
# gob.ec dropped the connection partway through a ~1.8 MB /tramites page
# from Render (httpx.ReadError, 2026-10-07) seconds after serving the same
# URL fine. The transport's own retries only cover failed connects, so
# these read-only GETs are retried here on any transport error (HTTP error
# statuses, including 5xx, are not retried).
_ATTEMPTS = 3
# Cap per attempt: _TIMEOUT is per read/connect, so a body trickling in just
# under it (or transport-level connect retries) could otherwise hold one call
# for minutes.
_ATTEMPT_DEADLINE = 60.0

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
        transport = httpx.AsyncHTTPTransport(
            retries=2, proxy=proxy_for(env_config.get_base_url("gobec_site"))
        )
        session = httpx.AsyncClient(
            headers=_HEADERS, transport=transport, follow_redirects=True
        )
    assert session is not None
    try:
        logger.debug("GobEC GET %s params=%s", url, params)
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                async with asyncio.timeout(_ATTEMPT_DEADLINE):
                    resp = await session.get(url, params=params, timeout=_TIMEOUT)
                break
            except (httpx.TransportError, TimeoutError) as exc:
                if attempt == _ATTEMPTS:
                    logger.error(
                        "GobEC gave up on %s after %d attempts: %r",
                        url, _ATTEMPTS, exc,
                    )
                    # ReadError and the timeouts stringify to "", which
                    # reached the user as "Error al buscar trámites: ".
                    raise RuntimeError(
                        f"gob.ec cortó o no respondió la consulta "
                        f"({type(exc).__name__}, {_ATTEMPTS} intentos); "
                        "reintenta en unos minutos."
                    ) from exc
                logger.warning(
                    "GobEC %s en %s (intento %d de %d); reintentando",
                    type(exc).__name__, url, attempt, _ATTEMPTS,
                )
                await asyncio.sleep(attempt)
        resp.raise_for_status()
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            # Confirmed live 2026-09-19: gob.ec's API sometimes answers a
            # blocked/bot-suspected request with HTTP 200 and an empty or
            # non-JSON body instead of a 4xx (unlike datosabiertos.gob.ec's
            # CKAN endpoint, which rejects the same kind of request with a
            # plain 403 -- see ckan_client._fetch_json). Give callers a
            # message that names the likely cause instead of the bare
            # json.JSONDecodeError text.
            logger.warning("GobEC response for %s was not valid JSON", url)
            raise RuntimeError(
                "El portal gob.ec devolvió una respuesta vacía o no válida. "
                "Esto suele pasar cuando el servidor se conecta desde fuera "
                "de Latinoamérica. Si el problema persiste, prueba "
                "conectando desde una VPN con salida en algún país de la "
                "región."
            ) from exc
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


_MAX_PAGINAS_INSTITUCIONES = 3  # ~1500 institutions


async def find_institucion(
    query: str, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """
    Find institutions matching a query by searching through the first
    pages of the listing. Searches in name, siglas (acronym), and
    description.

    Returns {"resultados": [...], "paginas_leidas": n, "hay_mas": bool};
    `hay_mas` is True when the page cap was reached with every page still
    full, i.e. unread pages may hold more matches.
    """
    own = session is None
    if own:
        transport = httpx.AsyncHTTPTransport(
            retries=2, proxy=proxy_for(env_config.get_base_url("gobec_site"))
        )
        session = httpx.AsyncClient(
            headers=_HEADERS, transport=transport, follow_redirects=True
        )
    assert session is not None
    try:
        query_lower = _strip(query).lower()
        matches: list[dict[str, Any]] = []
        paginas_leidas = 0
        for page in range(_MAX_PAGINAS_INSTITUCIONES):
            items = await list_instituciones(page=page, session=session)
            if not items:
                break
            paginas_leidas += 1
            for inst in items:
                name = _strip(inst.get("institucion", "")).lower()
                siglas = _strip(inst.get("siglas", "")).lower()
                desc = _strip(inst.get("descripcion", "")).lower()
                if query_lower in name or query_lower in siglas or query_lower in desc:
                    matches.append(inst)
        else:
            # Never saw an empty page: the listing may continue past the cap.
            hay_mas = True
            return {"resultados": matches, "paginas_leidas": paginas_leidas, "hay_mas": hay_mas}
        return {"resultados": matches, "paginas_leidas": paginas_leidas, "hay_mas": False}
    finally:
        if own:
            await session.aclose()


def _single_record(result: Any, id_key: str, wanted_id: str) -> dict[str, Any] | None:
    """One gob.ec record for `wanted_id`, or None.

    gob.ec answers /<coleccion>/{id} either with the record itself or with a
    one-element list holding it (confirmed live 2026-10-17 for
    /regulaciones/5051). A list whose records do not carry `wanted_id` is
    the collection endpoint answering an unknown id: not found, never
    result[0].
    """
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        matches = [
            item
            for item in result
            if isinstance(item, dict) and str(item.get(id_key, "")) == wanted_id
        ]
        if len(matches) == 1:
            return matches[0]
    return None


async def get_institucion(
    institucion_id: str, session: httpx.AsyncClient | None = None
) -> dict[str, Any] | None:
    """Get details of a specific public institution."""
    institucion_id = str(institucion_id).strip()
    if not institucion_id.isascii() or not institucion_id.isdigit():
        raise ValueError(
            f"El ID de institución debe ser numérico (ej. '8'); se recibió '{institucion_id}'."
        )
    result = await _fetch_json(
        _gobec_url(f"instituciones/{quote(institucion_id, safe='')}"), session=session
    )
    return _single_record(result, "institucion_id", institucion_id)


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
    regulacion_id = str(regulacion_id).strip()
    if not regulacion_id.isascii() or not regulacion_id.isdigit():
        raise ValueError(
            f"El ID de regulación debe ser numérico (ej. '8'); se recibió '{regulacion_id}'."
        )
    result = await _fetch_json(
        _gobec_url(f"regulaciones/{quote(regulacion_id, safe='')}"), session=session
    )
    # gob.ec answers /regulaciones/{id} with a one-element list (confirmed
    # live 2026-10-17 for id 5051), so a list is only "not found" when none
    # of its records carries the requested id (the collection endpoint).
    return _single_record(result, "regulacion_id", regulacion_id)


async def find_regulaciones(
    query: str,
    max_pages: int = 5,
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Client-side search across regulation pages (gob.ec has no search param).

    Returns {"resultados": [...], "paginas_leidas": n, "hay_mas": bool};
    `hay_mas` is True when `max_pages` was reached with every page still
    full, i.e. unread pages may hold more matches.
    """
    words = [_strip(w) for w in query.split() if len(w) >= 2]
    if not words:
        return {"resultados": [], "paginas_leidas": 0, "hay_mas": False}

    own = session is None
    if own:
        transport = httpx.AsyncHTTPTransport(
            retries=2, proxy=proxy_for(env_config.get_base_url("gobec_site"))
        )
        session = httpx.AsyncClient(
            headers=_HEADERS, transport=transport, follow_redirects=True
        )
    assert session is not None
    try:
        matches: list[dict[str, Any]] = []
        paginas_leidas = 0
        for page in range(max(max_pages, 1)):
            items = await list_regulaciones(page=page, session=session)
            if not items:
                break
            paginas_leidas += 1
            for reg in items:
                blob = _strip(
                    f"{reg.get('regulacion', '')} {reg.get('descripcion', '')} "
                    f"{reg.get('tipo', '')} {reg.get('institucion_emisora', '')} "
                    f"{reg.get('registro_oficial_numero', '')}"
                )
                if all(w in blob for w in words):
                    matches.append(reg)
        else:
            # Never saw an empty page: the listing may continue past the cap.
            return {"resultados": matches, "paginas_leidas": paginas_leidas, "hay_mas": True}
        return {"resultados": matches, "paginas_leidas": paginas_leidas, "hay_mas": False}
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


async def get_tramite_estadisticas(
    tramite_id: str, session: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Monthly atenciones/quejas transparency series for a given trámite.

    Returns every month reported since the endpoint's own history starts
    (2021), newest first, exactly as gob.ec exposes it -- this is a small
    per-trámite series (tens of rows), not something that needs pagination.
    """
    result = await _fetch_json(
        _gobec_url(f"tramites-transparencia/{tramite_id}"), session=session
    )
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return [result]
    return []
