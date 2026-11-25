import re
import socket
import time

import httpx
import pytest

from helpers import maate_client


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_DISK_CACHE", "0")

    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    maate_client._catalog_cache.clear()
    yield
    maate_client._catalog_cache.clear()


_CAPS = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:WFS_Capabilities xmlns:wfs="http://www.opengis.net/wfs/2.0" xmlns="http://www.opengis.net/wfs/2.0"
  xmlns:ows="http://www.opengis.net/ows/1.1"><FeatureTypeList>
<FeatureType><Name>mae_ide:v_fa210_snap_a</Name><Title>Sistema Nacional de Área Protegida SNAP</Title>
  <ows:WGS84BoundingBox><ows:LowerCorner>-92.1 -5.0</ows:LowerCorner><ows:UpperCorner>-75.2 1.4</ows:UpperCorner></ows:WGS84BoundingBox>
</FeatureType>
<FeatureType><Name>mae_ide:v_fc010_deforestacion_22_24_a</Name><Title>v_fc010_deforestacion_22_24_a</Title></FeatureType>
<FeatureType><Name>mae_ide:v_ff010_cobertura_vegetal_2024_a</Name><Title>Cobertura de la tierra 2024</Title>
  <Abstract>Mapa de cobertura y uso de la tierra</Abstract></FeatureType>
<FeatureType><Name>tiger:giant_polygon</Name><Title>World rectangle</Title></FeatureType>
</FeatureTypeList></wfs:WFS_Capabilities>"""

_DESCRIBE = {
    "featureTypes": [
        {
            "typeName": "v_fa210_snap_a",
            "properties": [
                {"name": "csnap", "type": "xsd:string", "localType": "string"},
                {"name": "nam", "type": "xsd:string", "localType": "string"},
                {"name": "are", "type": "xsd:double", "localType": "number"},
                {"name": "geom", "type": "gml:MultiSurface", "localType": "MultiSurface"},
            ],
        }
    ]
}

_CAPS_URL = re.compile(r"http://ide\.ambiente\.gob\.ec:8080/geoserver/ows\?.*GetCapabilities")


def test_parse_feature_types_drops_the_geoserver_demo_workspace():
    entries = maate_client.parse_feature_types(_CAPS.encode())

    assert [e["name"] for e in entries] == [
        "mae_ide:v_fa210_snap_a",
        "mae_ide:v_fc010_deforestacion_22_24_a",
        "mae_ide:v_ff010_cobertura_vegetal_2024_a",
    ]
    assert entries[0]["bbox_geografico"] == {"minx": -92.1, "miny": -5.0, "maxx": -75.2, "maxy": 1.4}
    assert entries[1]["bbox_geografico"] is None
    assert entries[2]["abstract"] == "Mapa de cobertura y uso de la tierra"


async def test_search_ignores_accents_and_matches_the_layer_name(httpx_mock):
    httpx_mock.add_response(url=_CAPS_URL, content=_CAPS.encode(), is_reusable=True)

    by_title = await maate_client.search_capas("area protegida")
    by_name = await maate_client.search_capas("deforestacion")
    by_abstract = await maate_client.search_capas("uso de la tierra")
    everything = await maate_client.search_capas()

    assert [c["name"] for c in by_title["capas"]] == ["mae_ide:v_fa210_snap_a"]
    assert [c["name"] for c in by_name["capas"]] == ["mae_ide:v_fc010_deforestacion_22_24_a"]
    assert [c["name"] for c in by_abstract["capas"]] == ["mae_ide:v_ff010_cobertura_vegetal_2024_a"]
    assert everything["total"] == everything["total_en_catalogo"] == 3
    assert everything["total_con_wfs"] == 3


async def test_search_needs_every_word_but_not_next_to_each_other(httpx_mock):
    httpx_mock.add_response(url=_CAPS_URL, content=_CAPS.encode(), is_reusable=True)

    # Layer names use underscores, so "deforestacion 22" is never a substring.
    spread_over_the_name = await maate_client.search_capas("deforestacion 22")
    one_word_missing = await maate_client.search_capas("deforestacion 1990")

    assert [c["name"] for c in spread_over_the_name["capas"]] == [
        "mae_ide:v_fc010_deforestacion_22_24_a"
    ]
    assert one_word_missing["total"] == 0


async def test_sample_asks_for_attributes_only(httpx_mock):
    httpx_mock.add_response(url=_CAPS_URL, content=_CAPS.encode(), is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r".*/geoserver/ows\?.*DescribeFeatureType.*"), json=_DESCRIBE
    )
    httpx_mock.add_response(
        url=re.compile(r".*/geoserver/ows\?.*GetFeature.*"),
        json={
            "features": [
                {
                    "id": "v_fa210_snap_a.1",
                    "geometry": None,
                    "properties": {"csnap": "HB01003", "nam": "GALÁPAGOS", "are": 795339.8},
                }
            ],
            "numberMatched": 81,
        },
    )

    result = await maate_client.get_layer_features("mae_ide:v_fa210_snap_a", count=50)

    get_feature = next(r for r in httpx_mock.get_requests() if "GetFeature" in str(r.url))
    assert get_feature.url.params["propertyName"] == "csnap,nam,are"
    assert get_feature.url.params["count"] == "20"
    assert result["campos"] == ["csnap", "nam", "are"]
    assert result["tipo_geometria"] == "MultiSurface"
    assert result["features"][0]["propiedades"]["nam"] == "GALÁPAGOS"
    assert result["total_features_en_capa"] == 81
    assert result["titulo"] == "Sistema Nacional de Área Protegida SNAP"


async def test_unknown_layer_points_to_the_search(httpx_mock):
    httpx_mock.add_response(url=_CAPS_URL, content=_CAPS.encode(), is_reusable=True)

    # The demo workspace is not in the catalog, so it cannot be queried either.
    with pytest.raises(ValueError, match=r"search_capas_geo\(fuente='maate'\)"):
        await maate_client.get_layer_features("tiger:giant_polygon")


async def test_geoserver_exception_report_becomes_a_readable_error(httpx_mock):
    httpx_mock.add_response(url=_CAPS_URL, content=_CAPS.encode(), is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r".*/geoserver/ows\?.*DescribeFeatureType.*"), json=_DESCRIBE
    )
    httpx_mock.add_response(
        url=re.compile(r".*/geoserver/ows\?.*GetFeature.*"),
        content=(
            b'<?xml version="1.0"?><ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/1.1">'
            b"<ows:Exception><ows:ExceptionText>Layer not available</ows:ExceptionText>"
            b"</ows:Exception></ows:ExceptionReport>"
        ),
    )

    with pytest.raises(ValueError, match="GetFeature falló: Layer not available"):
        await maate_client.get_layer_features("mae_ide:v_fa210_snap_a")


async def test_catalog_is_served_stale_when_the_host_goes_down(httpx_mock):
    httpx_mock.add_response(url=_CAPS_URL, content=_CAPS.encode())
    await maate_client.search_capas()

    # Expire the cached copy (tests/test_cache.py sets entries the same way), then
    # make the host refuse the next fetch.
    _, catalog = maate_client._catalog_cache._store["catalog"]
    maate_client._catalog_cache._store["catalog"] = (time.time() - 1, catalog)
    httpx_mock.add_exception(httpx.ConnectError("down"), url=_CAPS_URL)

    result = await maate_client.search_capas("snap")

    assert [c["name"] for c in result["capas"]] == ["mae_ide:v_fa210_snap_a"]
