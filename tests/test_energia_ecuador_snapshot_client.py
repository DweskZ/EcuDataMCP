import httpx
import pytest

from helpers import energia_ecuador_snapshot_client as client

# Real response shape from archive.org/wayback/available, confirmed live
# 2026-09-21 (see docs/RESEARCH.md § Vigésimo séptima pasada for the full
# recovery investigation).
_AVAILABLE_JSON = {
    "url": "energia-ecuador.com/empresa-electrica-quito/",
    "archived_snapshots": {
        "closest": {
            "status": "200",
            "available": True,
            "url": "http://web.archive.org/web/20240424233845/https://energia-ecuador.com/empresa-electrica-quito/",
            "timestamp": "20240424233845",
        }
    },
    "timestamp": "20240424",
}

_SNAPSHOT_URL = "http://web.archive.org/web/20240424233845id_/https://energia-ecuador.com/empresa-electrica-quito/"

# Trimmed but structurally faithful excerpt of the real archived TablePress
# table (headers use <th>, data rows use <td>; confirmed live the real
# table has 41 <tr> including the header, UTF-8 throughout).
_PAGE_HTML = """
<html><body>
<table class="tablepress tablepress-id-14 tablepress-responsive">
<thead><tr>
<th>PROVINCIA</th><th>CANTON</th><th>SECTORES</th>
<th>PROGRAMACIÓN INICIO</th><th>PROGRAMACIÓN FIN</th>
<th>REPROGRAMACIÓN INICIO</th><th>REPROGRAMACIÓN FIN</th>
</tr></thead>
<tbody>
<tr class="row-1">
<td>PICHINCHA</td><td>QUITO</td>
<td>CHIMBACALLE, RÍO CHAMBO</td>
<td>0:00</td><td>6:00</td><td></td><td></td>
</tr>
<tr class="row-2">
<td>PICHINCHA</td><td>RUMIÑAHUI</td>
<td>SANGOLQUÍ CENTRO</td>
<td>12:00</td><td>18:00</td><td></td><td></td>
</tr>
</tbody>
</table>
</body></html>
"""


@pytest.fixture(autouse=True)
def clear_cache():
    client._snapshot_cache.clear()
    yield
    client._snapshot_cache.clear()


async def test_resolve_snapshot_url_uses_available_api_and_adds_id_flag(httpx_mock):
    httpx_mock.add_response(
        url=httpx.URL(
            client._AVAILABLE_API,
            params={"url": client._ORIGINAL_URL, "timestamp": client._TARGET_TIMESTAMP},
        ),
        json=_AVAILABLE_JSON,
    )

    async with httpx.AsyncClient() as session:
        url = await client._resolve_snapshot_url(session)

    assert url == _SNAPSHOT_URL


async def test_get_energia_ecuador_snapshot_parses_rows_correctly(httpx_mock):
    httpx_mock.add_response(
        url=httpx.URL(
            client._AVAILABLE_API,
            params={"url": client._ORIGINAL_URL, "timestamp": client._TARGET_TIMESTAMP},
        ),
        json=_AVAILABLE_JSON,
    )
    httpx_mock.add_response(url=_SNAPSHOT_URL, html=_PAGE_HTML)

    result = await client.get_energia_ecuador_snapshot()

    assert result["total_en_snapshot"] == 2
    assert result["total"] == 2
    assert result["fecha_snapshot"] == "2024-04-24"
    first = result["filas"][0]
    assert first["provincia"] == "PICHINCHA"
    assert first["canton"] == "QUITO"
    assert first["programacion_inicio"] == "0:00"
    assert first["programacion_fin"] == "6:00"
    # The header row (<th> cells) must not leak into the parsed data.
    assert not any(f["provincia"] == "PROVINCIA" for f in result["filas"])


async def test_get_energia_ecuador_snapshot_filters_by_query_accent_insensitive(httpx_mock):
    httpx_mock.add_response(
        url=httpx.URL(
            client._AVAILABLE_API,
            params={"url": client._ORIGINAL_URL, "timestamp": client._TARGET_TIMESTAMP},
        ),
        json=_AVAILABLE_JSON,
    )
    httpx_mock.add_response(url=_SNAPSHOT_URL, html=_PAGE_HTML)

    result = await client.get_energia_ecuador_snapshot(query="ruminahui")

    assert result["total"] == 1
    assert result["total_en_snapshot"] == 2
    assert result["filas"][0]["canton"] == "RUMIÑAHUI"


async def test_missing_snapshot_raises(httpx_mock):
    httpx_mock.add_response(
        url=httpx.URL(
            client._AVAILABLE_API,
            params={"url": client._ORIGINAL_URL, "timestamp": client._TARGET_TIMESTAMP},
        ),
        json={"url": client._ORIGINAL_URL, "archived_snapshots": {}, "timestamp": "20240424"},
    )

    with pytest.raises(ValueError, match="Wayback"):
        await client._fetch_snapshot()
