import json

import pytest

from helpers import sri_saiku_client

_DISCOVER = [
    {
        "name": "Contribuyentes",
        "connection": "contribuyentes",
        "catalog": "Declaracion",
        "schema": "Declaracion",
        "cube": "Contribuyentes",
        "uniqueName": "[contribuyentes].[Declaracion].[Declaracion].[Contribuyentes]",
    }
]

_DIMENSIONS = {
    "dimensions": [
        {"name": "[Geografia]", "caption": "Geografía"},
    ]
}
_HIERARCHIES = {
    "hierarchies": [
        {"name": "[Geografia].[Geografia]", "caption": "Geografía"},
    ]
}
_MEASURES = {"measures": [{"name": "TOTAL RUCS", "caption": "TOTAL RUCS"}]}
_METADATA = {
    "dimensions": [
        {
            "name": "[Geografia]",
            "hierarchies": [
                {
                    "name": "[Geografia].[Geografia]",
                    "levels": [{"name": "Provincia"}],
                }
            ],
        }
    ]
}


@pytest.fixture(autouse=True)
def clear_caches():
    sri_saiku_client.clear_caches()
    yield
    sri_saiku_client.clear_caches()


@pytest.mark.asyncio
async def test_list_cubes_uses_session_and_public_discovery(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url=sri_saiku_client.SRI_SAIKU_SESSION_URL,
        json={"username": "anonymousUser", "roles": ["ROLE_ANONYMOUS"]},
    )
    httpx_mock.add_response(
        method="GET",
        url=sri_saiku_client.SRI_SAIKU_DISCOVER_URL,
        json=_DISCOVER,
    )

    result = await sri_saiku_client.list_cubes()

    assert result["total"] == 1
    assert result["cubes"] == [
        {
            "connection": "contribuyentes",
            "catalog": "Declaracion",
            "schema": "Declaracion",
            "cube": "Contribuyentes",
            "unique_name": "[contribuyentes].[Declaracion].[Declaracion].[Contribuyentes]",
            "cube_id": "contribuyentes/Declaracion/Declaracion/Contribuyentes",
        }
    ]


@pytest.mark.asyncio
async def test_query_aggregate_builds_bounded_read_only_request(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url=sri_saiku_client.SRI_SAIKU_SESSION_URL,
        json={"username": "anonymousUser"},
    )
    httpx_mock.add_response(
        method="GET",
        url=sri_saiku_client.SRI_SAIKU_DISCOVER_URL,
        json=_DISCOVER,
    )
    for suffix, payload in (
        ("dimensions", _DIMENSIONS),
        ("hierarchies", _HIERARCHIES),
        ("measures", _MEASURES),
        ("metadata", _METADATA),
    ):
        httpx_mock.add_response(
            method="GET",
            url=(
                f"{sri_saiku_client.SRI_SAIKU_ROOT}/rest/saiku/anonymousUser/"
                f"discover/contribuyentes/Declaracion/Declaracion/Contribuyentes/{suffix}"
            ),
            json=payload,
        )
    httpx_mock.add_response(
        method="POST",
        url=sri_saiku_client.SRI_SAIKU_EXECUTE_URL,
        json={"cellset": {"axes": [], "cells": []}},
    )

    result = await sri_saiku_client.query_aggregate(
        "contribuyentes/Declaracion/Declaracion/Contribuyentes",
        row_dimension="Geografia",
        row_hierarchy="Geografia",
        row_level="Provincia",
        measure="TOTAL RUCS",
        limit=25,
    )

    request = next(r for r in httpx_mock.get_requests() if r.method == "POST")
    payload = json.loads(request.content)
    rows_axis = payload["queryModel"]["axes"]["ROWS"]
    assert rows_axis["limitFunction"] == "TOPCOUNT"
    assert rows_axis["limitFunctionN"] == 25
    assert rows_axis["limitFunctionSortLiteral"] == "[Measures].[TOTAL RUCS]"
    assert payload["cube"]["name"] == "Contribuyentes"
    assert payload["queryModel"]["details"]["measures"] == [
        {"name": "TOTAL RUCS", "type": "EXACT"}
    ]
    assert result["result"]["cellset"]["cells"] == []


@pytest.mark.asyncio
async def test_query_aggregate_rejects_unknown_measure_before_post(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url=sri_saiku_client.SRI_SAIKU_SESSION_URL,
        json={"username": "anonymousUser"},
    )
    httpx_mock.add_response(
        method="GET",
        url=sri_saiku_client.SRI_SAIKU_DISCOVER_URL,
        json=_DISCOVER,
    )
    for suffix, payload in (
        ("dimensions", _DIMENSIONS),
        ("hierarchies", _HIERARCHIES),
        ("measures", _MEASURES),
        ("metadata", _METADATA),
    ):
        httpx_mock.add_response(
            method="GET",
            url=(
                f"{sri_saiku_client.SRI_SAIKU_ROOT}/rest/saiku/anonymousUser/"
                f"discover/contribuyentes/Declaracion/Declaracion/Contribuyentes/{suffix}"
            ),
            json=payload,
        )

    with pytest.raises(ValueError, match="Medida no encontrado"):
        await sri_saiku_client.query_aggregate(
            "contribuyentes/Declaracion/Declaracion/Contribuyentes",
            row_dimension="Geografia",
            row_hierarchy="Geografia",
            row_level="Provincia",
            measure="NO EXISTE",
        )

    assert not [r for r in httpx_mock.get_requests() if r.method == "POST"]
