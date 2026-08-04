import json
import logging
from typing import Any

import httpx

from helpers import env_config
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
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            error = data.get("error", {})
            raise ValueError(f"CKAN API error: {error}")
        return data["result"]
    except httpx.HTTPError as exc:
        logger.error("CKAN request failed for %s: %s", url, exc)
        raise
    finally:
        if own:
            await session.aclose()


def _ckan_url(action: str) -> str:
    return f"{env_config.get_base_url('ckan')}{action}"


async def search_datasets(
    query: str = "",
    rows: int = 20,
    start: int = 0,
    category: str = "",
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"q": query, "rows": min(rows, 100), "start": start}
    if category:
        params["fq"] = f"groups:{category}"
    return await _fetch_json(_ckan_url("package_search"), params=params, session=session)


async def get_dataset(
    dataset_id: str, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    return await _fetch_json(
        _ckan_url("package_show"), params={"id": dataset_id}, session=session
    )


async def get_resource(
    resource_id: str, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    return await _fetch_json(
        _ckan_url("resource_show"), params={"id": resource_id}, session=session
    )


async def list_organizations(
    query: str = "",
    limit: int = 20,
    offset: int = 0,
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
        _ckan_url("organization_list"), params=params, session=session
    )


async def get_organization(
    org_id: str,
    include_datasets: bool = True,
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"id": org_id}
    if include_datasets:
        params["include_datasets"] = "true"
    return await _fetch_json(
        _ckan_url("organization_show"), params=params, session=session
    )


async def list_groups(
    session: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    cached = categories_cache.get("group_list")
    if cached is not None:
        return cached
    result = await _fetch_json(
        _ckan_url("group_list"), params={"all_fields": "true"}, session=session
    )
    categories_cache.set("group_list", result)
    return result


async def get_group(
    group_id: str,
    include_datasets: bool = True,
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"id": group_id}
    if include_datasets:
        params["include_datasets"] = "true"
    return await _fetch_json(
        _ckan_url("group_show"), params=params, session=session
    )


async def datastore_search(
    resource_id: str,
    filters: dict[str, Any] | None = None,
    q: str = "",
    limit: int = 20,
    offset: int = 0,
    fields: list[str] | None = None,
    sort: str = "",
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
        _ckan_url("datastore_search"), params=params, session=session
    )
