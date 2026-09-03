import json

import pytest

from helpers import inamhi_client

# Trimmed down from the real GetCapabilities responses observed live against
# geoservicios.inamhi.gob.ec (2026-09-02): same root/namespace structure,
# same element shapes, a representative subset of the 222 real layer names
# (mixing a WFS-enabled vector layer with title+abstract populated, two
# WFS-enabled vector layers with no title/abstract, and a WMS-only raster
# layer confirmed live to 404 on WFS GetFeature).
_WMS_CAPABILITIES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms"
    xmlns:xlink="http://www.w3.org/1999/xlink">
  <Service>
    <Name>WMS</Name>
    <Title>GeoNode Local GeoServer</Title>
  </Service>
  <Capability>
    <Layer>
      <Title>GeoServer Web Map Service</Title>
      <Layer queryable="1">
        <Name>geonode:regiones_precip</Name>
        <Title>regiones_precip</Title>
        <CRS>EPSG:4326</CRS>
        <CRS>CRS:84</CRS>
        <EX_GeographicBoundingBox>
          <westBoundLongitude>-81.08143968703934</westBoundLongitude>
          <eastBoundLongitude>-75.18816646892044</eastBoundLongitude>
          <southBoundLatitude>-5.016905981265428</southBoundLatitude>
          <northBoundLatitude>1.455707943869098</northBoundLatitude>
        </EX_GeographicBoundingBox>
      </Layer>
      <Layer queryable="1">
        <Name>geonode:cuencas_inamhi</Name>
        <Title>cuencas_inamhi</Title>
        <CRS>EPSG:4326</CRS>
        <CRS>CRS:84</CRS>
        <EX_GeographicBoundingBox>
          <westBoundLongitude>-91.66181641799994</westBoundLongitude>
          <eastBoundLongitude>-75.18714656799995</eastBoundLongitude>
          <southBoundLatitude>-5.016157323999948</southBoundLatitude>
          <northBoundLatitude>1.469580600000029</northBoundLatitude>
        </EX_GeographicBoundingBox>
      </Layer>
      <Layer queryable="1">
        <Name>geonode:ecuador_cantones</Name>
        <Title>Ecuador Cantones</Title>
        <Abstract>Cantons del Ecuador</Abstract>
        <CRS>EPSG:32717</CRS>
        <CRS>CRS:84</CRS>
        <EX_GeographicBoundingBox>
          <westBoundLongitude>-92.04546119218115</westBoundLongitude>
          <eastBoundLongitude>-75.16591671077339</eastBoundLongitude>
          <southBoundLatitude>-5.018619839783096</southBoundLatitude>
          <northBoundLatitude>1.7133188268370183</northBoundLatitude>
        </EX_GeographicBoundingBox>
      </Layer>
      <Layer queryable="1">
        <Name>geonode:wrf_tiempo_precipitacion</Name>
        <Title>wrf_tiempo_precipitacion</Title>
        <CRS>EPSG:4326</CRS>
        <CRS>CRS:84</CRS>
        <EX_GeographicBoundingBox>
          <westBoundLongitude>-81.1259</westBoundLongitude>
          <eastBoundLongitude>-74.9699</eastBoundLongitude>
          <southBoundLatitude>-5.1403</southBoundLatitude>
          <northBoundLatitude>1.5286999999999997</northBoundLatitude>
        </EX_GeographicBoundingBox>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>
"""

# wrf_tiempo_precipitacion deliberately absent -- confirmed live as WMS-only
# (WFS GetFeature on it returns an ows:ExceptionReport, "Feature type unknown").
_WFS_CAPABILITIES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:WFS_Capabilities version="2.0.0" xmlns:wfs="http://www.opengis.net/wfs/2.0"
    xmlns="http://www.opengis.net/wfs/2.0" xmlns:geonode="http://www.geonode.org/">
  <FeatureTypeList>
    <FeatureType>
      <Name>geonode:regiones_precip</Name>
      <Title>regiones_precip</Title>
    </FeatureType>
    <FeatureType>
      <Name>geonode:cuencas_inamhi</Name>
      <Title>cuencas_inamhi</Title>
    </FeatureType>
    <FeatureType>
      <Name>geonode:ecuador_cantones</Name>
      <Title>Ecuador Cantones</Title>
    </FeatureType>
  </FeatureTypeList>
</wfs:WFS_Capabilities>
"""

_WFS_EXCEPTION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/1.1" version="2.0.0">
<ows:Exception exceptionCode="InvalidParameterValue" locator="typeName">
<ows:ExceptionText>Feature type geonode:wrf_tiempo_precipitacion unknown</ows:ExceptionText>
</ows:Exception>
</ows:ExceptionReport>
"""

_WMS_CAPS_URL = (
    f"{inamhi_client._WMS_URL}?service=WMS&version=1.3.0&request=GetCapabilities"
)
_WFS_CAPS_URL = (
    f"{inamhi_client._WFS_URL}?service=WFS&version=2.0.0&request=GetCapabilities"
)


def _mock_capabilities(httpx_mock, wms_xml=_WMS_CAPABILITIES_XML, wfs_xml=_WFS_CAPABILITIES_XML):
    httpx_mock.add_response(url=_WMS_CAPS_URL, text=wms_xml)
    httpx_mock.add_response(url=_WFS_CAPS_URL, text=wfs_xml)


@pytest.fixture(autouse=True)
def clear_cache():
    inamhi_client._catalog_cache.clear()
    yield
    inamhi_client._catalog_cache.clear()


@pytest.mark.asyncio
async def test_search_capas_lists_all_layers_with_wfs_flags(httpx_mock):
    _mock_capabilities(httpx_mock)

    result = await inamhi_client.search_capas()

    assert result["total"] == 4
    assert result["total_en_catalogo"] == 4
    assert result["total_con_wfs"] == 3

    by_name = {c["name"]: c for c in result["capas"]}
    assert by_name["geonode:regiones_precip"]["wfs_disponible"] is True
    assert by_name["geonode:cuencas_inamhi"]["wfs_disponible"] is True
    assert by_name["geonode:wrf_tiempo_precipitacion"]["wfs_disponible"] is False

    cantones = by_name["geonode:ecuador_cantones"]
    assert cantones["title"] == "Ecuador Cantones"
    assert cantones["abstract"] == "Cantons del Ecuador"
    assert "EPSG:32717" in cantones["crs"]
    assert cantones["bbox_geografico"]["southBoundLatitude"] == pytest.approx(-5.018619839783096)

    # Layer with no <Title> falls back to its Name (none in this fixture set
    # actually lack a Title, so assert the common case: title == name when
    # GeoServer's title is just a copy of the layer name).
    assert by_name["geonode:regiones_precip"]["title"] == "regiones_precip"
    assert by_name["geonode:regiones_precip"]["abstract"] is None


@pytest.mark.asyncio
async def test_search_capas_filters_by_query_accent_insensitive(httpx_mock):
    _mock_capabilities(httpx_mock)

    result = await inamhi_client.search_capas(query="cantones")

    assert result["total"] == 1
    assert result["capas"][0]["name"] == "geonode:ecuador_cantones"


@pytest.mark.asyncio
async def test_search_capas_filters_by_abstract(httpx_mock):
    _mock_capabilities(httpx_mock)

    result = await inamhi_client.search_capas(query="canton")

    assert result["total"] == 1
    assert result["capas"][0]["name"] == "geonode:ecuador_cantones"


@pytest.mark.asyncio
async def test_search_capas_solo_wfs_excludes_raster_only_layers(httpx_mock):
    _mock_capabilities(httpx_mock)

    result = await inamhi_client.search_capas(solo_wfs=True)

    assert result["total"] == 3
    names = {c["name"] for c in result["capas"]}
    assert "geonode:wrf_tiempo_precipitacion" not in names


@pytest.mark.asyncio
async def test_get_layer_features_returns_attributes(httpx_mock):
    _mock_capabilities(httpx_mock)
    feature_json = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "regiones_precip.1",
                "geometry": {"type": "MultiPolygon", "coordinates": [[[[1, 2], [3, 4]]]]},
                "properties": {
                    "gridcode": 13,
                    "rango": "2800 - 3000",
                    "dhnom": "Demarcación hidrográfica Esmeraldas",
                    "area_km2": 50,
                },
            }
        ],
        "totalFeatures": 430,
        "numberMatched": 430,
        "numberReturned": 1,
    }
    httpx_mock.add_response(
        url=(
            f"{inamhi_client._WFS_URL}?service=WFS&version=2.0.0&request=GetFeature"
            "&typeNames=geonode%3Aregiones_precip&count=2&outputFormat=application%2Fjson"
        ),
        text=json.dumps(feature_json),
    )

    result = await inamhi_client.get_layer_features("geonode:regiones_precip", count=2)

    assert result["capa"] == "geonode:regiones_precip"
    assert result["total_features_en_capa"] == 430
    assert result["features_devueltas"] == 1
    feature = result["features"][0]
    assert feature["id"] == "regiones_precip.1"
    assert feature["tipo_geometria"] == "MultiPolygon"
    assert feature["propiedades"]["dhnom"] == "Demarcación hidrográfica Esmeraldas"
    # Coordinates are dropped, not the whole geometry block.
    assert "coordinates" not in feature


@pytest.mark.asyncio
async def test_get_layer_features_caps_count_at_max(httpx_mock):
    _mock_capabilities(httpx_mock)
    httpx_mock.add_response(
        url=(
            f"{inamhi_client._WFS_URL}?service=WFS&version=2.0.0&request=GetFeature"
            f"&typeNames=geonode%3Acuencas_inamhi&count={inamhi_client.MAX_FEATURE_COUNT}"
            "&outputFormat=application%2Fjson"
        ),
        text=json.dumps({"type": "FeatureCollection", "features": [], "totalFeatures": 34}),
    )

    result = await inamhi_client.get_layer_features("geonode:cuencas_inamhi", count=999)

    assert result["features_devueltas"] == 0
    assert f"count={inamhi_client.MAX_FEATURE_COUNT}" in result["url_consulta"]


@pytest.mark.asyncio
async def test_get_layer_features_raises_for_raster_only_layer(httpx_mock):
    _mock_capabilities(httpx_mock)

    with pytest.raises(ValueError, match="solo WMS"):
        await inamhi_client.get_layer_features("geonode:wrf_tiempo_precipitacion")


@pytest.mark.asyncio
async def test_get_layer_features_raises_for_unknown_layer(httpx_mock):
    _mock_capabilities(httpx_mock)

    with pytest.raises(ValueError, match="no encontrada"):
        await inamhi_client.get_layer_features("geonode:no_existe")


@pytest.mark.asyncio
async def test_get_layer_features_surfaces_wfs_exception_report(httpx_mock):
    # A layer that passes the catalog's wfs_disponible check but GeoServer
    # itself rejects at GetFeature time (e.g. removed between capabilities
    # fetch and query) -- confirms the XML ExceptionReport fallback parsing.
    _mock_capabilities(httpx_mock)
    httpx_mock.add_response(
        url=(
            f"{inamhi_client._WFS_URL}?service=WFS&version=2.0.0&request=GetFeature"
            "&typeNames=geonode%3Aregiones_precip&count=5&outputFormat=application%2Fjson"
        ),
        text=_WFS_EXCEPTION_XML,
    )

    with pytest.raises(ValueError, match="Feature type geonode:wrf_tiempo_precipitacion unknown"):
        await inamhi_client.get_layer_features("geonode:regiones_precip")


@pytest.mark.asyncio
async def test_empty_catalog_is_not_cached(httpx_mock):
    empty_wms = """<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Capability><Layer><Title>Empty</Title></Layer></Capability>
</WMS_Capabilities>
"""
    empty_wfs = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:WFS_Capabilities version="2.0.0" xmlns:wfs="http://www.opengis.net/wfs/2.0">
  <FeatureTypeList/>
</wfs:WFS_Capabilities>
"""
    _mock_capabilities(httpx_mock, wms_xml=empty_wms, wfs_xml=empty_wfs)
    _mock_capabilities(httpx_mock)

    first = await inamhi_client.search_capas()
    assert first["total_en_catalogo"] == 0

    second = await inamhi_client.search_capas()
    assert second["total_en_catalogo"] == 4
