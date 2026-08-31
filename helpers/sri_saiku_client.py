"""Read-only client for the public SRI Saiku OLAP service.

This client deliberately uses Saiku's normal session, discovery and query
routes.  It does not depend on the ``/admin`` namespace, saved repositories,
drill-through, exports, or any write operation.

The first query surface is intentionally narrow: one cube, one row level and
one measure.  That is enough for public aggregate statistics while keeping
the MCP tool from becoming an arbitrary MDX execution proxy.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

SRI_SAIKU_ROOT = "https://srienlinea.sri.gob.ec/saiku"
SRI_SAIKU_SESSION_URL = f"{SRI_SAIKU_ROOT}/rest/saiku/session"
SRI_SAIKU_DISCOVER_URL = f"{SRI_SAIKU_ROOT}/rest/saiku/proxy/discover"
SRI_SAIKU_EXECUTE_URL = f"{SRI_SAIKU_ROOT}/rest/saiku/api/query/execute"

_TIMEOUT = 35.0
_MAX_QUERY_LIMIT = 100
_CUBE_CACHE_TTL = 900.0
_NAME_KEYS = {
    "name",
    "caption",
    "cube",
    "cubename",
    "dimension",
    "hierarchy",
    "level",
    "measure",
    "uniquename",
    "unique_name",
}
_UNSAFE_IDENTIFIER_CHARS = re.compile(r"[\x00-\x1f\x7f;'\"(){}<>/]")

_cube_cache = TtlCache(ttl_seconds=_CUBE_CACHE_TTL, max_entries=1)
_cube_fetch_lock = asyncio.Lock()


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        follow_redirects=True,
        timeout=_TIMEOUT,
    )


async def _json_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> Any:
    logger.debug("Saiku %s %s", method, url)
    response = await client.request(method, url, **kwargs)
    if response.is_error:
        detail = re.sub(r"\s+", " ", response.text).strip()[:300]
        raise RuntimeError(
            f"Saiku respondió HTTP {response.status_code} en {url}"
            + (f": {detail}" if detail else "")
        )
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"Saiku devolvió una respuesta no JSON en {url}") from exc


async def _start_session(client: httpx.AsyncClient) -> str:
    payload = await _json_request(client, "GET", SRI_SAIKU_SESSION_URL)
    if not isinstance(payload, dict):
        raise TypeError("La sesión anónima de Saiku no devolvió un objeto JSON")
    username = payload.get("username") or "anonymousUser"
    return str(username)


def _as_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("cubes", "datasources", "data", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    # Some Saiku versions return a map keyed by datasource/cube name.
    mapped = [value for value in payload.values() if isinstance(value, dict)]
    if mapped:
        return mapped
    return [payload]


def _string_value(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _cube_name_from_unique_name(unique_name: str | None) -> str | None:
    if not unique_name:
        return None
    parts = re.findall(r"\[([^\]]+)\]", unique_name)
    return parts[-1] if parts else None


def _normalise_cube(item: dict[str, Any]) -> dict[str, Any] | None:
    unique_name = _string_value(item, "uniqueName", "unique_name", "cubeUniqueName")
    cube = _string_value(item, "cube", "cubeName", "cubename")
    if cube and cube.startswith("["):
        cube = _cube_name_from_unique_name(cube) or cube
    cube = cube or _cube_name_from_unique_name(unique_name)
    cube = cube or _string_value(item, "name")

    connection = _string_value(item, "connection", "connectionName", "connectionname")
    catalog = _string_value(item, "catalog", "catalogName", "catalogname")
    schema = _string_value(item, "schema", "schemaName", "schemaname")

    if not cube:
        return None

    result: dict[str, Any] = {
        "connection": connection,
        "catalog": catalog,
        "schema": schema,
        "cube": cube,
        "unique_name": unique_name,
    }
    if connection and catalog and schema:
        result["cube_id"] = f"{connection}/{catalog}/{schema}/{cube}"
    else:
        result["cube_id"] = None
    return result


def _normalise_cubes(payload: Any) -> list[dict[str, Any]]:
    cubes: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for item in _as_items(payload):
        cube = _normalise_cube(item)
        if cube is None:
            continue
        key = (cube.get("cube_id"), cube.get("cube"))
        if key in seen:
            continue
        seen.add(key)
        cubes.append(cube)
    return cubes


async def _fetch_cubes_for_session(
    client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    cached = _cube_cache.get("cubes")
    if cached is not None:
        return cached

    async with _cube_fetch_lock:
        cached = _cube_cache.get("cubes")
        if cached is not None:
            return cached
        payload = await _json_request(client, "GET", SRI_SAIKU_DISCOVER_URL)
        cubes = _normalise_cubes(payload)
        _cube_cache.set("cubes", cubes)
        return cubes


async def _fetch_cubes() -> list[dict[str, Any]]:
    async with _client() as client:
        await _start_session(client)
        return await _fetch_cubes_for_session(client)


async def list_cubes() -> dict[str, Any]:
    """List cube identifiers visible through Saiku's public discovery route."""
    cubes = await _fetch_cubes()
    return {
        "source": SRI_SAIKU_DISCOVER_URL,
        "access": "anonymous read-only session",
        "cubes": cubes,
        "total": len(cubes),
    }


def _resolve_cube(cubes: list[dict[str, Any]], identifier: str) -> dict[str, Any]:
    value = str(identifier).strip()
    if not value:
        raise ValueError("Debes indicar un cube_id o nombre de cubo.")

    folded = strip_accents(value).casefold()
    matches = [
        cube
        for cube in cubes
        if folded
        in {
            strip_accents(str(cube.get("cube_id") or "")).casefold(),
            strip_accents(str(cube.get("cube") or "")).casefold(),
        }
    ]
    if not matches:
        available = ", ".join(
            str(cube.get("cube_id") or cube.get("cube")) for cube in cubes
        )
        raise ValueError(f"Cubo no encontrado: {value}. Disponibles: {available}")
    if len(matches) > 1:
        raise ValueError(f"El nombre de cubo es ambiguo: {value}; usa cube_id.")
    cube = matches[0]
    if not cube.get("cube_id"):
        raise ValueError(f"El cubo no tiene un identificador completo: {value}")
    return cube


def _discover_path(username: str, cube: dict[str, Any], suffix: str) -> str:
    parts = [
        str(username),
        "discover",
        str(cube["connection"]),
        str(cube["catalog"]),
        str(cube["schema"]),
        str(cube["cube"]),
    ]
    encoded = "/".join(quote(part, safe="") for part in parts)
    return f"{SRI_SAIKU_ROOT}/rest/saiku/{encoded}/{suffix}"


async def _fetch_cube_metadata(
    client: httpx.AsyncClient,
    username: str,
    cube: dict[str, Any],
) -> dict[str, Any]:
    suffixes = {
        "dimensions": "dimensions",
        "hierarchies": "hierarchies",
        "measures": "measures",
        "metadata": "metadata",
    }
    responses = await asyncio.gather(
        *(
            _json_request(
                client,
                "GET",
                _discover_path(username, cube, suffix),
            )
            for suffix in suffixes.values()
        )
    )
    return dict(zip(suffixes, responses, strict=True))


def _normalise_name(value: str) -> str:
    value = strip_accents(str(value)).strip().casefold()
    value = re.sub(r"\s+", " ", value)
    value = value.replace("[", "").replace("]", "")
    return value


def _payload_names(payload: Any) -> set[str]:
    names: set[str] = set()

    def visit(value: Any, parent_key: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_folded = str(key).casefold()
                if key_folded in _NAME_KEYS and isinstance(child, str):
                    names.add(_normalise_name(child))
                if parent_key in {"dimensions", "hierarchies", "levels", "measures"}:
                    names.add(_normalise_name(str(key)))
                visit(child, key_folded)
        elif isinstance(value, list):
            for child in value:
                visit(child, parent_key)

    visit(payload)
    return {name for name in names if name}


def _require_metadata_name(
    payload: Any,
    requested: str,
    kind: str,
) -> None:
    available = _payload_names(payload)
    if available and _normalise_name(requested) not in available:
        preview = ", ".join(sorted(available)[:40])
        raise ValueError(f"{kind} no encontrado: {requested}. Disponibles: {preview}")


def _safe_identifier(value: str, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} no puede estar vacío.")
    if len(text) > 200 or _UNSAFE_IDENTIFIER_CHARS.search(text):
        raise ValueError(f"{label} contiene caracteres no permitidos.")
    return text


def _bracket_identifier(value: str) -> str:
    if value.startswith("[") and value.endswith("]") and value.count("[") == 1:
        return value
    return f"[{value}]"


def _hierarchy_reference(dimension: str, hierarchy: str) -> str:
    if hierarchy.startswith("[") and "]" in hierarchy:
        return hierarchy
    return f"{_bracket_identifier(dimension)}.{_bracket_identifier(hierarchy)}"


def _axis(
    location: str,
    hierarchies: list[dict[str, Any]] | None = None,
    limit: int | None = None,
    limit_measure: str | None = None,
) -> dict[str, Any]:
    return {
        "mdx": None,
        "filters": [],
        "sortOrder": None,
        "sortEvaluationLiteral": None,
        "hierarchizeMode": None,
        "location": location,
        "hierarchies": hierarchies or [],
        "nonEmpty": location != "FILTER",
        "aggregators": [],
        "limitFunction": "TOPCOUNT" if limit is not None else None,
        "limitFunctionN": limit,
        "limitFunctionSortLiteral": (
            f"[Measures].[{limit_measure}]" if limit_measure is not None else None
        ),
    }


def _build_aggregate_payload(
    cube: dict[str, Any],
    row_dimension: str,
    row_hierarchy: str,
    row_level: str,
    measure: str,
    limit: int,
) -> dict[str, Any]:
    row_dimension = _safe_identifier(row_dimension, "row_dimension")
    row_hierarchy = _safe_identifier(row_hierarchy, "row_hierarchy")
    row_level = _safe_identifier(row_level, "row_level")
    measure = _safe_identifier(measure, "measure")
    query_name = str(uuid4()).upper()

    row_hierarchy_spec = {
        "name": _hierarchy_reference(row_dimension, row_hierarchy),
        "levels": {row_level: {"name": row_level}},
        "cmembers": {},
    }
    cube_unique_name = cube.get("unique_name")
    if not cube_unique_name:
        cube_unique_name = ".".join(
            _bracket_identifier(str(cube[key]))
            for key in ("connection", "catalog", "schema", "cube")
        )

    return {
        "name": query_name,
        "queryModel": {
            "axes": {
                "FILTER": _axis("FILTER"),
                "COLUMNS": _axis("COLUMNS"),
                "ROWS": _axis(
                    "ROWS",
                    [row_hierarchy_spec],
                    limit=limit,
                    limit_measure=measure,
                ),
            },
            "visualTotals": False,
            "visualTotalsPattern": None,
            "lowestLevelsOnly": False,
            "details": {
                "axis": "COLUMNS",
                "location": "BOTTOM",
                "measures": [{"name": measure, "type": "EXACT"}],
            },
            "calculatedMeasures": [],
            "calculatedMembers": [],
        },
        "queryType": "OLAP",
        "type": "QUERYMODEL",
        "cube": {
            "uniqueName": cube_unique_name,
            "name": cube["cube"],
            "connection": cube["connection"],
            "catalog": cube["catalog"],
            "schema": cube["schema"],
            "caption": None,
            "visible": False,
        },
        "mdx": None,
        "parameters": {},
        "plugins": {},
        "properties": {
            "saiku.olap.query.automatic_execution": True,
            "saiku.olap.query.nonempty": True,
            "saiku.olap.query.nonempty.rows": True,
            "saiku.olap.query.nonempty.columns": True,
            "saiku.ui.render.mode": "table",
            "saiku.olap.query.filter": True,
            "saiku.olap.result.formatter": "flattened",
            "org.saiku.query.explain": False,
            "org.saiku.connection.scenario": False,
            "saiku.olap.query.drillthrough": False,
        },
        "metadata": {},
    }


async def describe_cube(identifier: str) -> dict[str, Any]:
    """Return public dimensions, hierarchies, measures and metadata for a cube."""
    async with _client() as client:
        username = await _start_session(client)
        cubes = await _fetch_cubes_for_session(client)
        cube = _resolve_cube(cubes, identifier)
        metadata = await _fetch_cube_metadata(client, username, cube)
    return {
        "source": SRI_SAIKU_DISCOVER_URL,
        "access": "anonymous read-only session",
        "cube": cube,
        "metadata": metadata,
    }


async def query_aggregate(
    cube_identifier: str,
    row_dimension: str,
    row_hierarchy: str,
    row_level: str,
    measure: str,
    limit: int = 25,
) -> dict[str, Any]:
    """Run one bounded aggregate query through Saiku's normal query API."""
    limit = min(max(int(limit), 1), _MAX_QUERY_LIMIT)
    async with _client() as client:
        username = await _start_session(client)
        cubes = await _fetch_cubes_for_session(client)
        cube = _resolve_cube(cubes, cube_identifier)
        metadata = await _fetch_cube_metadata(client, username, cube)
        _require_metadata_name(metadata["dimensions"], row_dimension, "Dimensión")
        _require_metadata_name(metadata["hierarchies"], row_hierarchy, "Jerarquía")
        _require_metadata_name(metadata["metadata"], row_level, "Nivel")
        _require_metadata_name(metadata["measures"], measure, "Medida")

        payload = _build_aggregate_payload(
            cube,
            row_dimension=row_dimension,
            row_hierarchy=row_hierarchy,
            row_level=row_level,
            measure=measure,
            limit=limit,
        )
        result = await _json_request(
            client,
            "POST",
            SRI_SAIKU_EXECUTE_URL,
            json=payload,
        )

    return {
        "source": SRI_SAIKU_EXECUTE_URL,
        "access": "anonymous read-only session",
        "cube": cube,
        "request": {
            "row_dimension": row_dimension,
            "row_hierarchy": row_hierarchy,
            "row_level": row_level,
            "measure": measure,
            "limit": limit,
        },
        "result": result,
    }


def clear_caches() -> None:
    """Clear client caches; primarily useful for tests and manual refreshes."""
    _cube_cache.clear()
