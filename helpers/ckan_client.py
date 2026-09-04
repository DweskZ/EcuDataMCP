import json
import logging
from typing import Any

import httpx

from helpers import env_config
from helpers.acronyms import expand_acronyms
from helpers.cache import categories_cache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.tls import should_retry_insecure
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_TIMEOUT = 20.0


async def _fetch_json(
    url: str,
    params: dict[str, Any] | None = None,
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    own = session is None
    if own:
        session = httpx.AsyncClient(headers={"User-Agent": USER_AGENT})
    assert session is not None
    try:
        logger.debug("CKAN GET %s params=%s", url, params)
        try:
            resp = await session.get(url, params=params, timeout=_TIMEOUT)
        except httpx.ConnectError as exc:
            if not should_retry_insecure(exc, url):
                raise
            # www.datosabiertos.gob.ec's TLS certificate expired 2026-07-28.
            # Only allowlisted portal hosts retry once with verify=False.
            # Set CKAN_INSECURE_TLS=0 after the government renews the cert.
            logger.warning(
                "CKAN TLS verification failed for %s (portal cert expired); "
                "retrying without verification",
                url,
            )
            async with httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT}, verify=False
            ) as insecure_session:
                resp = await insecure_session.get(url, params=params, timeout=_TIMEOUT)
        if resp.status_code == 403:
            # The portal has been observed rejecting connections from outside
            # Latin America (403) while accepting them from the region. Give
            # callers a message that points at the likely cause instead of a
            # bare "403 Forbidden".
            logger.warning("CKAN request to %s got 403 Forbidden", url)
            raise RuntimeError(
                "El portal de Datos Abiertos (datosabiertos.gob.ec) rechazó la "
                "conexión (403). Esto suele pasar cuando el servidor se conecta "
                "desde fuera de Latinoamérica. Si el problema persiste, prueba "
                "conectando desde una VPN con salida en algún país de la región."
            )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            error = data.get("error", {})
            raise ValueError(f"CKAN API error: {error}")
        return data["result"]
    except httpx.HTTPStatusError as exc:
        # Already actionable: raise_for_status()'s own message includes the
        # URL and status code, and 403 is special-cased above.
        logger.error("CKAN request failed for %s: %s", url, exc)
        raise
    except httpx.RequestError as exc:
        # A bare ConnectTimeout/ConnectError often stringifies to "" or
        # "timed out" with no host in it, leaving the model unable to tell
        # the caller anything useful. Name the host and the failure kind.
        logger.error("CKAN request failed for %s: %s", url, exc)
        raise RuntimeError(
            f"No se pudo conectar a {exc.request.url} ({type(exc).__name__}). "
            "El portal de Datos Abiertos podría estar caído, lento, o "
            "bloqueando la conexión; reintenta en unos minutos."
        ) from exc
    finally:
        if own:
            await session.aclose()


# Other CKAN instances the tools can target via `source=` -- the same
# API shape (package_search/package_show/resource_show/...), just a
# different portal, so no separate client module is needed per source.
# "nacional" is the historical default (www.datosabiertos.gob.ec); "cuenca"
# is the municipal portal (cuencaendatos.cuenca.gob.ec, confirmed live: CKAN
# 2.9.6, 92 datasets); "latacunga" is another municipal portal, "Data
# Mashca" (datosabiertos.latacunga.gob.ec, confirmed live: 15 datasets).
_SOURCES = {
    "nacional": ("ckan", "ckan_site"),
    "cuenca": ("cuenca", "cuenca_site"),
    "latacunga": ("latacunga", "latacunga_site"),
}


def _resolve_source(source: str) -> tuple[str, str]:
    try:
        return _SOURCES[source]
    except KeyError:
        raise ValueError(
            f"source inválido: {source!r}. Usa 'nacional', 'cuenca' o "
            "'latacunga'."
        ) from None


def _ckan_url(action: str, source: str = "nacional") -> str:
    api_key, _ = _resolve_source(source)
    return f"{env_config.get_base_url(api_key)}{action}"


def site_url(source: str = "nacional") -> str:
    """Public site base URL for `source`, for building dataset/resource links."""
    _, site_key = _resolve_source(source)
    return env_config.get_base_url(site_key)


async def search_datasets(
    query: str = "",
    rows: int = 20,
    start: int = 0,
    category: str = "",
    sort: str = "",
    source: str = "nacional",
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "q": expand_acronyms(query),
        "rows": min(rows, 100),
        "start": start,
    }
    if category:
        params["fq"] = f"groups:{category}"
    if sort:
        params["sort"] = sort
    return await _fetch_json(
        _ckan_url("package_search", source), params=params, session=session
    )


async def recent_datasets(
    rows: int = 20,
    start: int = 0,
    source: str = "nacional",
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Newest packages by metadata_modified."""
    return await search_datasets(
        query="*:*",
        rows=rows,
        start=start,
        sort="metadata_modified desc",
        source=source,
        session=session,
    )


async def get_dataset(
    dataset_id: str, source: str = "nacional", session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    return await _fetch_json(
        _ckan_url("package_show", source), params={"id": dataset_id}, session=session
    )


async def get_resource(
    resource_id: str, source: str = "nacional", session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    return await _fetch_json(
        _ckan_url("resource_show", source), params={"id": resource_id}, session=session
    )


async def list_organizations(
    query: str = "",
    limit: int = 20,
    offset: int = 0,
    source: str = "nacional",
    session: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "all_fields": "true",
        "limit": min(limit, 100),
        "offset": offset,
    }
    if query:
        params["q"] = query
    return await _fetch_json(
        _ckan_url("organization_list", source), params=params, session=session
    )


async def _list_organization_packages(
    org_id: str, source: str, session: httpx.AsyncClient | None
) -> list[dict[str, Any]]:
    """Full package list for one organization.

    organization_show's own `packages` field is capped by the portal's
    per-page default -- confirmed live against a real 94-dataset
    organization, it silently returned only 10. package_search with an
    organization filter and an explicit high `rows` returns the true set.
    """
    result = await _fetch_json(
        _ckan_url("package_search", source),
        params={
            "fq": f"organization:{org_id}",
            "rows": 1000,
            "sort": "metadata_modified desc",
        },
        session=session,
    )
    return result.get("results", [])


async def get_organization(
    org_id: str,
    include_datasets: bool = True,
    source: str = "nacional",
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    org = await _fetch_json(
        _ckan_url("organization_show", source), params={"id": org_id}, session=session
    )
    if include_datasets:
        org["packages"] = await _list_organization_packages(org_id, source, session)
    return org


async def list_groups(
    source: str = "nacional",
    session: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    cache_key = f"group_list:{source}"
    cached = categories_cache.get(cache_key)
    if cached is not None:
        return cached
    result = await _fetch_json(
        _ckan_url("group_list", source), params={"all_fields": "true"}, session=session
    )
    categories_cache.set(cache_key, result)
    return result


async def get_group(
    group_id: str,
    include_datasets: bool = True,
    source: str = "nacional",
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"id": group_id}
    if include_datasets:
        params["include_datasets"] = "true"
    return await _fetch_json(
        _ckan_url("group_show", source), params=params, session=session
    )


async def datastore_search(
    resource_id: str,
    filters: dict[str, Any] | None = None,
    q: str = "",
    limit: int = 20,
    offset: int = 0,
    fields: list[str] | None = None,
    sort: str = "",
    source: str = "nacional",
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Query a CKAN DataStore resource (tabular API, no full-file download)."""
    params: dict[str, Any] = {
        "resource_id": resource_id,
        "limit": min(max(limit, 1), 100),
        "offset": max(offset, 0),
    }
    if filters:
        params["filters"] = json.dumps(filters)
    if q:
        params["q"] = q
    if fields:
        params["fields"] = ",".join(fields)
    if sort:
        params["sort"] = sort
    return await _fetch_json(
        _ckan_url("datastore_search", source), params=params, session=session
    )
