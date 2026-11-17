import re
import socket

import pytest

from helpers import ember_client, igm_client, turismo_client


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_DISK_CACHE", "0")

    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    for cache in (igm_client._catalog_cache, turismo_client._cache, ember_client._cache):
        cache.clear()
    yield
    for cache in (igm_client._catalog_cache, turismo_client._cache, ember_client._cache):
        cache.clear()


# -- IGM -------------------------------------------------------------------

_CAPS = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:WFS_Capabilities xmlns:wfs="http://www.opengis.net/wfs/2.0" xmlns="http://www.opengis.net/wfs/2.0"
  xmlns:ows="http://www.opengis.net/ows/1.1"><FeatureTypeList>
<FeatureType><Name>{ws}:poblado_p</Name><Title>Poblado {esc}</Title>
  <ows:WGS84BoundingBox><ows:LowerCorner>-92.0 -5.0</ows:LowerCorner><ows:UpperCorner>-75.0 2.0</ows:UpperCorner></ows:WGS84BoundingBox>
</FeatureType>
<FeatureType><Name>igm_reservada:secreto</Name><Title>Reservada</Title></FeatureType>
</FeatureTypeList></wfs:WFS_Capabilities>"""

_DESCRIBE = {
    "featureTypes": [
        {
            "typeName": "poblado_p",
            "properties": [
                {"name": "nam", "type": "xsd:string", "localType": "string"},
                {"name": "the_geom", "type": "gml:Point", "localType": "Point"},
                {"name": "nute", "type": "xsd:string", "localType": "string"},
            ],
        }
    ]
}


def _mock_igm(httpx_mock):
    for servicio, ws in (("nacional", "nacional_2024"), ("50k", "actualizada"), ("25k", "igm")):
        httpx_mock.add_response(
            url=re.compile(rf"https://www\.geoportaligm\.gob\.ec/{servicio}/wfs\?.*GetCapabilities"),
            content=_CAPS.format(ws=ws, esc=servicio).encode(),
            is_reusable=True,
        )


def test_parse_feature_types_drops_the_reserved_workspace():
    entries = igm_client.parse_feature_types(_CAPS.format(ws="igm", esc="x").encode(), "25k")

    assert [e["name"] for e in entries] == ["igm:poblado_p"]
    assert entries[0]["bbox_geografico"] == {"minx": -92.0, "miny": -5.0, "maxx": -75.0, "maxy": 2.0}


async def test_igm_search_filters_by_scale(httpx_mock):
    _mock_igm(httpx_mock)

    everything = await igm_client.search_capas("poblado")
    only_50k = await igm_client.search_capas("poblado", servicio="50k")

    assert everything["total"] == 3
    assert everything["por_servicio"] == {"nacional": 1, "50k": 1, "25k": 1}
    assert [c["name"] for c in only_50k["capas"]] == ["actualizada:poblado_p"]
    with pytest.raises(ValueError, match="servicio"):
        await igm_client.search_capas(servicio="10k")


async def test_igm_sample_asks_for_attributes_only(httpx_mock):
    _mock_igm(httpx_mock)
    httpx_mock.add_response(
        url=re.compile(r".*/nacional/wfs\?.*DescribeFeatureType.*"), json=_DESCRIBE
    )
    httpx_mock.add_response(
        url=re.compile(r".*/nacional/wfs\?.*GetFeature.*"),
        json={
            "features": [{"id": "p.1", "geometry": None, "properties": {"nam": "Tumbaco", "nute": "170150"}}],
            "numberMatched": 1340,
        },
    )

    result = await igm_client.get_layer_features("nacional_2024:poblado_p", count=50)

    get_feature = next(r for r in httpx_mock.get_requests() if "GetFeature" in str(r.url))
    assert get_feature.url.params["propertyName"] == "nam,nute"
    assert get_feature.url.params["count"] == "20"
    assert result["tipo_geometria"] == "Point"
    assert result["features"][0]["propiedades"]["nam"] == "Tumbaco"
    assert result["total_features_en_capa"] == 1340


async def test_igm_reserved_layer_says_so(httpx_mock):
    _mock_igm(httpx_mock)

    with pytest.raises(ValueError, match="reservada"):
        await igm_client.get_layer_features("igm_reservada:secreto")


# -- Turismo -----------------------------------------------------------------


def test_parse_media_keeps_bulletin_pdfs_with_their_period():
    items = [
        {"mime_type": "application/pdf", "date": "2026-11-05T12:00:00",
         "title": {"rendered": "Boletin Turismo Octubre 2026"},
         "source_url": "https://www.produccion.gob.ec/wp-content/uploads/2026/11/Boletin-Turismo-Octubre-2026.pdf"},
        {"mime_type": "application/pdf", "date": "2025-12-29T10:00:00",
         "title": {"rendered": "Boletin mensual turismo &#8211; diciembre 2025"},
         "source_url": "https://www.produccion.gob.ec/b-dic.pdf"},
        {"mime_type": "application/pdf", "date": "2026-07-02T10:00:00",
         "title": {"rendered": "Boletin Turismo Junio_2026"}, "source_url": "https://www.produccion.gob.ec/b-jun.pdf"},
        {"mime_type": "image/jpeg", "title": {"rendered": "CV Vice turismo"}, "source_url": "https://x/cv.jpg"},
        {"mime_type": "application/pdf", "title": {"rendered": "Informe de gestión"}, "source_url": "https://x/i.pdf"},
    ]

    boletines = turismo_client.parse_media(items)

    assert [b["periodo"] for b in boletines] == ["2026-10", "2026-06", "2025-12"]
    assert boletines[2]["titulo"] == "Boletin mensual turismo – diciembre 2025"
    assert {b["formato"] for b in boletines} == {"PDF"}


async def test_turismo_search_filters_by_text(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(r"https://www\.produccion\.gob\.ec/wp-json/wp/v2/media\?.*"),
        json=[
            {"mime_type": "application/pdf", "date": "2026-11-05T12:00:00",
             "title": {"rendered": "Boletin Turismo Octubre 2026"}, "source_url": "https://x/oct.pdf"},
            {"mime_type": "application/pdf", "date": "2026-10-12T12:00:00",
             "title": {"rendered": "Boletin Turismo Septiembre 2026"}, "source_url": "https://x/sep.pdf"},
        ],
    )

    result = await turismo_client.search_boletines("octubre")

    assert [a["url"] for a in result["archivos"]] == ["https://x/oct.pdf"]
    assert "read_pdf" in result["nota"]


# -- Ember -------------------------------------------------------------------


def test_catalog_lists_every_view_and_filters():
    assert len(ember_client.catalog()) == 56
    assert {r["indicador"] for r in ember_client.catalog("intensity")} == {"carbon_intensity/total"}


def test_parse_csv_with_and_without_code_column():
    period, cols, rows = ember_client.parse_csv("Entity,Code,Month,Hydropower\nEcuador,ECU,2024-11,1.01\n")
    assert (period, cols) == ("Month", ["Hydropower"])
    assert rows == [{"periodo": "2024-11", "entidad": "Ecuador", "valores": {"Hydropower": 1.01}}]

    _period, cols, rows = ember_client.parse_csv("Entity,Year,Solar,Oil\nEcuador,2024,,3.5\n")
    assert cols == ["Solar", "Oil"]
    assert rows[0]["valores"] == {"Solar": None, "Oil": 3.5}


async def test_ember_series_filters_by_period(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(r"https://ourworldindata\.org/grapher/electricity-mix\.csv\?.*metric=carbon_intensity.*tab=chart.*"),
        text="Entity,Code,Year,Carbon intensity\nEcuador,ECU,2023,195.42\nEcuador,ECU,2024,203.61\nEcuador,ECU,2025,159.02\n",
    )

    result = await ember_client.get_serie("carbon_intensity", desde="2024")

    assert [r["periodo"] for r in result["registros"]] == ["2024", "2025"]
    assert result["unidad"] == "gCO2/kWh"
    assert result["licencia"] == "CC BY 4.0"


async def test_monthly_by_source_is_assembled_from_single_sources(httpx_mock):
    def respond(request):
        import httpx

        source = request.url.params["source"]
        name = {"solar": "Solar", "wind": "Wind"}[source]
        return httpx.Response(200, text=f"Entity,Code,Month,{name}\nEcuador,ECU,2024-11,0.0{len(source)}\n")

    httpx_mock.add_callback(respond, url=re.compile(r".*electricity-mix\.csv\?.*frequency=monthly.*"), is_reusable=True)

    result = await ember_client.get_serie("by_source/solar_and_wind", frecuencia="M")

    assert result["columnas"] == ["Solar", "Wind"]
    assert result["registros"] == [
        {"periodo": "2024-11", "entidad": "Ecuador", "valores": {"Solar": 0.05, "Wind": 0.04}}
    ]


async def test_ember_rejects_unknown_views():
    with pytest.raises(ValueError, match="métricas"):
        await ember_client.get_serie("hydro")
    with pytest.raises(ValueError, match="no tiene la fuente"):
        await ember_client.get_serie("demand/hydro")
    with pytest.raises(ValueError, match="frecuencia"):
        await ember_client.get_serie("generation/hydro", frecuencia="Q")

