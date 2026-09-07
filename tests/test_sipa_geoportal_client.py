import json

import pytest

from helpers import sipa_geoportal_client

# Trimmed down from the real GetCapabilities responses observed live against
# geoportal.agricultura.gob.ec (2026-09-03): same root/namespace structure,
# same element shapes, real layer names/titles/abstracts for the
# registros/E50k store (3 layers, all WFS-enabled -- a normal case), the
# tematicas/Rraster store (2 pure-raster layers -- WFS service responds but
# the FeatureTypeList is empty, so no vector data), and the
# sigtierras/catastro_rural store (WFS explicitly disabled server-side,
# confirmed live via GeoServer's own ows:ExceptionReport -- this is the
# rural cadastre store flagged as most valuable by prior research, and it's
# WMS-only).

_WMS_E50K_XML = """<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms"
    xmlns:xlink="http://www.w3.org/1999/xlink">
  <Service>
    <Name>WMS</Name>
    <Title>WMS Registros administrativos 1:50.000 - MAG</Title>
  </Service>
  <Capability>
    <Layer>
      <Title>WMS Registros administrativos 1:50.000 - MAG</Title>
      <Layer queryable="1" opaque="0">
        <Name>vw_censo_palmicultor</Name>
        <Title>Censo palmicultor 1:50.000</Title>
        <Abstract>2005 (versión 2). Registro administrativo que se determina la ubicación geográfica de predios de palma africana a nivel nacional.</Abstract>
        <CRS>EPSG:32717</CRS>
        <CRS>CRS:84</CRS>
        <EX_GeographicBoundingBox>
          <westBoundLongitude>-80.51807245872769</westBoundLongitude>
          <eastBoundLongitude>-76.17455371906047</eastBoundLongitude>
          <southBoundLatitude>-2.8842089140410416</southBoundLatitude>
          <northBoundLatitude>1.4593098256261747</northBoundLatitude>
        </EX_GeographicBoundingBox>
      </Layer>
      <Layer queryable="1" opaque="0">
        <Name>vw_censo_porcicola</Name>
        <Title>Censo porcícola 1:50.000</Title>
        <Abstract>2010 (versión 2). Registro administrativo que determina la ubicación geográfica de las granjas porcinas a nivel nacional.</Abstract>
        <CRS>EPSG:32717</CRS>
        <CRS>CRS:84</CRS>
        <EX_GeographicBoundingBox>
          <westBoundLongitude>-81.84178046566707</westBoundLongitude>
          <eastBoundLongitude>-75.5531427069116</eastBoundLongitude>
          <southBoundLatitude>-4.948279754395087</southBoundLatitude>
          <northBoundLatitude>1.3403580043603835</northBoundLatitude>
        </EX_GeographicBoundingBox>
      </Layer>
      <Layer queryable="1" opaque="0">
        <Name>vw_registro_avicola</Name>
        <Title>Registro avícola 1:50.000</Title>
        <Abstract>2015. Registro administrativo que determina la ubicación geográfica de las granjas avícolas y sus productores a nivel nacional.</Abstract>
        <CRS>EPSG:32717</CRS>
        <CRS>CRS:84</CRS>
        <EX_GeographicBoundingBox>
          <westBoundLongitude>-81.67989096089853</westBoundLongitude>
          <eastBoundLongitude>-75.7774353664335</eastBoundLongitude>
          <southBoundLatitude>-4.9523717963594525</southBoundLatitude>
          <northBoundLatitude>0.9500837981055917</northBoundLatitude>
        </EX_GeographicBoundingBox>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>
"""

# GOTCHA (confirmed live): the WFS FeatureType <Name> is qualified with the
# *store* name ("E50k:"), while the WMS <Name> for the very same layer
# (above) is bare ("vw_censo_palmicultor") -- the client matches these by
# bare name.
_WFS_E50K_XML = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:WFS_Capabilities version="2.0.0" xmlns:wfs="http://www.opengis.net/wfs/2.0"
    xmlns="http://www.opengis.net/wfs/2.0" xmlns:E50k="http://geoportal.agricultura.gob.ec/registros/E50k">
  <FeatureTypeList>
    <FeatureType>
      <Name>E50k:vw_censo_palmicultor</Name>
      <Title>Censo palmicultor 1:50.000</Title>
    </FeatureType>
    <FeatureType>
      <Name>E50k:vw_censo_porcicola</Name>
      <Title>Censo porcícola 1:50.000</Title>
    </FeatureType>
    <FeatureType>
      <Name>E50k:vw_registro_avicola</Name>
      <Title>Registro avícola 1:50.000</Title>
    </FeatureType>
  </FeatureTypeList>
</wfs:WFS_Capabilities>
"""

_WMS_RRASTER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Service>
    <Name>WMS</Name>
    <Title>WMS Temáticas raster - MAG</Title>
  </Service>
  <Capability>
    <Layer>
      <Title>WMS Temáticas raster - MAG</Title>
      <Layer queryable="1" opaque="0">
        <Name>ma002_carbono_organico_suelos</Name>
        <Title>Carbono Orgánico en los Suelos 1 km - 1era versión</Title>
        <Abstract>2017 (versión 1). Carbono que se encuentra en forma de residuos orgánicos.</Abstract>
        <CRS>EPSG:4326</CRS>
        <EX_GeographicBoundingBox>
          <westBoundLongitude>-81.2</westBoundLongitude>
          <eastBoundLongitude>-75.1</eastBoundLongitude>
          <southBoundLatitude>-5.0</southBoundLatitude>
          <northBoundLatitude>1.5</northBoundLatitude>
        </EX_GeographicBoundingBox>
      </Layer>
      <Layer queryable="1" opaque="0">
        <Name>ma002_carbono_organico_suelos_v2</Name>
        <Title>Carbono Orgánico en los Suelos 1 km - 2da versión</Title>
        <CRS>EPSG:4326</CRS>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>
"""

# Confirmed live: WFS service itself responds normally for a raster store,
# but the FeatureTypeList is empty -- no vector feature types, same net
# effect (no attribute data) as a disabled service, but a different XML
# shape worth covering separately.
_WFS_RRASTER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:WFS_Capabilities version="2.0.0" xmlns:wfs="http://www.opengis.net/wfs/2.0"
    xmlns="http://www.opengis.net/wfs/2.0">
  <FeatureTypeList/>
</wfs:WFS_Capabilities>
"""

_WMS_CATASTRO_RURAL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Service>
    <Name>WMS</Name>
    <Title>WMS Catastro Rural - SIGTIERRAS</Title>
  </Service>
  <Capability>
    <Layer>
      <Title>WMS Catastro Rural - SIGTIERRAS</Title>
      <Layer queryable="1" opaque="0">
        <Name>vw_predios_jun2023</Name>
        <Title>Predios catastrados</Title>
        <CRS>EPSG:32717</CRS>
      </Layer>
      <Layer queryable="1" opaque="0">
        <Name>vw_construcciones_jun2023</Name>
        <Title>Construcciones</Title>
        <CRS>EPSG:32717</CRS>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>
"""

# Confirmed live: GeoServer replies to GetCapabilities itself (not just
# GetFeature) with a real ows:ExceptionReport for this store -- "Service
# WFS is disabled" -- rather than an empty FeatureTypeList.
_WFS_DISABLED_EXCEPTION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows" version="1.0.0">
<ows:Exception exceptionCode="NoApplicableCode">
<ows:ExceptionText>org.geoserver.platform.ServiceException: Service WFS is disabled
Service WFS is disabled</ows:ExceptionText>
</ows:Exception>
</ows:ExceptionReport>
"""

_WFS_GETFEATURE_EXCEPTION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/1.1" version="2.0.0">
<ows:Exception exceptionCode="InvalidParameterValue" locator="typeName">
<ows:ExceptionText>Feature type E50k:vw_registro_avicola unknown</ows:ExceptionText>
</ows:Exception>
</ows:ExceptionReport>
"""

_BASE = sipa_geoportal_client._BASE_URL

_URLS = {
    ("registros", "E50k", "wms"): f"{_BASE}/registros/E50k/wms?service=WMS&version=1.3.0&request=GetCapabilities",
    ("registros", "E50k", "wfs"): f"{_BASE}/registros/E50k/wfs?service=WFS&version=2.0.0&request=GetCapabilities",
    ("tematicas", "Rraster", "wms"): f"{_BASE}/tematicas/Rraster/wms?service=WMS&version=1.3.0&request=GetCapabilities",
    ("tematicas", "Rraster", "wfs"): f"{_BASE}/tematicas/Rraster/wfs?service=WFS&version=2.0.0&request=GetCapabilities",
    ("sigtierras", "catastro_rural", "wms"): f"{_BASE}/sigtierras/catastro_rural/wms?service=WMS&version=1.3.0&request=GetCapabilities",
    ("sigtierras", "catastro_rural", "wfs"): f"{_BASE}/sigtierras/catastro_rural/wfs?service=WFS&version=2.0.0&request=GetCapabilities",
}

_TEST_ENDPOINTS = [("registros", "E50k"), ("tematicas", "Rraster"), ("sigtierras", "catastro_rural")]


def _mock_all_endpoints(httpx_mock):
    httpx_mock.add_response(url=_URLS[("registros", "E50k", "wms")], text=_WMS_E50K_XML)
    httpx_mock.add_response(url=_URLS[("registros", "E50k", "wfs")], text=_WFS_E50K_XML)
    httpx_mock.add_response(url=_URLS[("tematicas", "Rraster", "wms")], text=_WMS_RRASTER_XML)
    httpx_mock.add_response(url=_URLS[("tematicas", "Rraster", "wfs")], text=_WFS_RRASTER_XML)
    httpx_mock.add_response(
        url=_URLS[("sigtierras", "catastro_rural", "wms")], text=_WMS_CATASTRO_RURAL_XML
    )
    httpx_mock.add_response(
        url=_URLS[("sigtierras", "catastro_rural", "wfs")], text=_WFS_DISABLED_EXCEPTION_XML
    )


@pytest.fixture(autouse=True)
def small_endpoint_list(monkeypatch):
    """Point the client at 3 endpoints instead of the real 24, so tests don't
    need to mock every store -- covers a normal WFS-enabled store, a
    raster-only store (empty FeatureTypeList), and a WFS-disabled store
    (ExceptionReport), which is the full set of shapes the real catalog has.
    """
    monkeypatch.setattr(sipa_geoportal_client, "_ENDPOINTS", _TEST_ENDPOINTS)
    sipa_geoportal_client._catalog_cache.clear()
    yield
    sipa_geoportal_client._catalog_cache.clear()


def test_parse_wms_layers_extracts_name_title_abstract_crs_bbox():
    layers = sipa_geoportal_client._parse_wms_layers(_WMS_E50K_XML.encode())

    assert len(layers) == 3
    by_name = {layer["name"]: layer for layer in layers}
    palmicultor = by_name["vw_censo_palmicultor"]
    assert palmicultor["title"] == "Censo palmicultor 1:50.000"
    assert "palma africana" in palmicultor["abstract"]
    assert "EPSG:32717" in palmicultor["crs"]
    assert palmicultor["bbox_geografico"]["southBoundLatitude"] == pytest.approx(-2.8842089140410416)


def test_parse_wfs_type_names_maps_bare_name_to_qualified_name():
    mapping = sipa_geoportal_client._parse_wfs_type_names(_WFS_E50K_XML.encode())

    # The WMS layer's bare name ("vw_censo_palmicultor") must map to the
    # WFS-qualified name ("E50k:vw_censo_palmicultor") -- this is the
    # store-prefix mismatch gotcha the client works around.
    assert mapping == {
        "vw_censo_palmicultor": "E50k:vw_censo_palmicultor",
        "vw_censo_porcicola": "E50k:vw_censo_porcicola",
        "vw_registro_avicola": "E50k:vw_registro_avicola",
    }


def test_parse_wfs_type_names_returns_empty_dict_for_empty_feature_type_list():
    mapping = sipa_geoportal_client._parse_wfs_type_names(_WFS_RRASTER_XML.encode())

    assert mapping == {}


def test_parse_wfs_type_names_returns_empty_dict_for_disabled_service_exception():
    mapping = sipa_geoportal_client._parse_wfs_type_names(_WFS_DISABLED_EXCEPTION_XML.encode())

    assert mapping == {}


@pytest.mark.asyncio
async def test_search_capas_merges_wms_and_wfs_across_endpoints(httpx_mock):
    _mock_all_endpoints(httpx_mock)

    result = await sipa_geoportal_client.search_capas()

    assert result["total_en_catalogo"] == 3 + 2 + 2  # E50k + Rraster + catastro_rural
    assert result["total"] == result["total_en_catalogo"]
    assert result["total_con_wfs"] == 3  # only the E50k layers have WFS
    assert set(result["categorias"]) == {"registros", "tematicas", "sigtierras"}

    by_id = {c["id"]: c for c in result["capas"]}
    palmicultor = by_id["registros/E50k/vw_censo_palmicultor"]
    assert palmicultor["wfs_disponible"] is True
    assert palmicultor["wfs_typename"] == "E50k:vw_censo_palmicultor"

    raster = by_id["tematicas/Rraster/ma002_carbono_organico_suelos"]
    assert raster["wfs_disponible"] is False
    assert raster["wfs_typename"] is None

    predios = by_id["sigtierras/catastro_rural/vw_predios_jun2023"]
    assert predios["wfs_disponible"] is False
    assert predios["wfs_typename"] is None


@pytest.mark.asyncio
async def test_search_capas_filters_by_query_accent_insensitive(httpx_mock):
    _mock_all_endpoints(httpx_mock)

    result = await sipa_geoportal_client.search_capas(query="porcicola")

    assert result["total"] == 1
    assert result["capas"][0]["id"] == "registros/E50k/vw_censo_porcicola"


@pytest.mark.asyncio
async def test_search_capas_filters_by_categoria(httpx_mock):
    _mock_all_endpoints(httpx_mock)

    result = await sipa_geoportal_client.search_capas(categoria="sigtierras")

    assert result["total"] == 2
    assert all(c["categoria"] == "sigtierras" for c in result["capas"])


@pytest.mark.asyncio
async def test_search_capas_solo_wfs_excludes_raster_and_disabled_stores(httpx_mock):
    _mock_all_endpoints(httpx_mock)

    result = await sipa_geoportal_client.search_capas(solo_wfs=True)

    assert result["total"] == 3
    assert all(c["categoria"] == "registros" for c in result["capas"])


@pytest.mark.asyncio
async def test_get_layer_features_returns_attributes(httpx_mock):
    _mock_all_endpoints(httpx_mock)
    feature_json = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "vw_censo_palmicultor.1",
                "geometry": {"type": "MultiPoint", "coordinates": [[1, 2]]},
                "properties": {
                    "provincia": "ESMERALDAS",
                    "canton": "QUININDE",
                    "superficie_ha": 12.5,
                },
            }
        ],
        "totalFeatures": 4381,
        "numberMatched": 4381,
        "numberReturned": 1,
    }
    httpx_mock.add_response(
        url=(
            f"{_BASE}/registros/E50k/wfs?service=WFS&version=2.0.0&request=GetFeature"
            "&typeNames=E50k%3Avw_censo_palmicultor&count=2&outputFormat=application%2Fjson"
        ),
        text=json.dumps(feature_json),
    )

    result = await sipa_geoportal_client.get_layer_features(
        "registros/E50k/vw_censo_palmicultor", count=2
    )

    assert result["capa"] == "registros/E50k/vw_censo_palmicultor"
    assert result["total_features_en_capa"] == 4381
    assert result["features_devueltas"] == 1
    feature = result["features"][0]
    assert feature["id"] == "vw_censo_palmicultor.1"
    assert feature["tipo_geometria"] == "MultiPoint"
    assert feature["propiedades"]["provincia"] == "ESMERALDAS"
    # Coordinates are dropped, not the whole geometry block.
    assert "coordinates" not in feature


@pytest.mark.asyncio
async def test_get_layer_features_caps_count_at_max(httpx_mock):
    _mock_all_endpoints(httpx_mock)
    httpx_mock.add_response(
        url=(
            f"{_BASE}/registros/E50k/wfs?service=WFS&version=2.0.0&request=GetFeature"
            f"&typeNames=E50k%3Avw_censo_porcicola&count={sipa_geoportal_client.MAX_FEATURE_COUNT}"
            "&outputFormat=application%2Fjson"
        ),
        text=json.dumps({"type": "FeatureCollection", "features": [], "totalFeatures": 900}),
    )

    result = await sipa_geoportal_client.get_layer_features(
        "registros/E50k/vw_censo_porcicola", count=999
    )

    assert result["features_devueltas"] == 0
    assert f"count={sipa_geoportal_client.MAX_FEATURE_COUNT}" in result["url_consulta"]


@pytest.mark.asyncio
async def test_get_layer_features_raises_for_raster_only_layer(httpx_mock):
    _mock_all_endpoints(httpx_mock)

    with pytest.raises(ValueError, match="solo WMS"):
        await sipa_geoportal_client.get_layer_features(
            "tematicas/Rraster/ma002_carbono_organico_suelos"
        )


@pytest.mark.asyncio
async def test_get_layer_features_raises_for_wfs_disabled_layer(httpx_mock):
    _mock_all_endpoints(httpx_mock)

    with pytest.raises(ValueError, match="solo WMS"):
        await sipa_geoportal_client.get_layer_features(
            "sigtierras/catastro_rural/vw_predios_jun2023"
        )


@pytest.mark.asyncio
async def test_get_layer_features_raises_for_unknown_layer(httpx_mock):
    _mock_all_endpoints(httpx_mock)

    with pytest.raises(ValueError, match="no encontrada"):
        await sipa_geoportal_client.get_layer_features("registros/E50k/no_existe")


@pytest.mark.asyncio
async def test_get_layer_features_surfaces_wfs_exception_report(httpx_mock):
    # A layer that passes the catalog's wfs_disponible check but GeoServer
    # itself rejects at GetFeature time -- confirms the XML ExceptionReport
    # fallback parsing (same pattern as helpers/inamhi_client.py).
    _mock_all_endpoints(httpx_mock)
    httpx_mock.add_response(
        url=(
            f"{_BASE}/registros/E50k/wfs?service=WFS&version=2.0.0&request=GetFeature"
            "&typeNames=E50k%3Avw_registro_avicola&count=5&outputFormat=application%2Fjson"
        ),
        text=_WFS_GETFEATURE_EXCEPTION_XML,
    )

    with pytest.raises(ValueError, match="Feature type E50k:vw_registro_avicola unknown"):
        await sipa_geoportal_client.get_layer_features("registros/E50k/vw_registro_avicola")


@pytest.mark.asyncio
async def test_empty_catalog_is_not_cached(httpx_mock):
    empty_wms = """<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Capability><Layer><Title>Empty</Title></Layer></Capability>
</WMS_Capabilities>
"""
    # No WFS mocks here: _fetch_endpoint skips the WFS request entirely when
    # a store's WMS capabilities have no layers, so nothing would consume them.
    for cat, store in _TEST_ENDPOINTS:
        httpx_mock.add_response(
            url=f"{_BASE}/{cat}/{store}/wms?service=WMS&version=1.3.0&request=GetCapabilities",
            text=empty_wms,
        )

    first = await sipa_geoportal_client.search_capas()
    assert first["total_en_catalogo"] == 0

    _mock_all_endpoints(httpx_mock)
    second = await sipa_geoportal_client.search_capas()
    assert second["total_en_catalogo"] == 7
