import pytest

from helpers import sri_ruc_client

_INFO_HTML = """
<html><body>
<table>
<tr><th>Fecha :</th><td>31-08-2026</td></tr>
<tr><th>Razón Social:</th><td>SANCHEZ PAZMIÑO DANIEL HERNAN</td></tr>
<tr><th>RUC:</th><td>1718647215001</td></tr>
<tr><th>Nombre Comercial:</th><td></td></tr>
<tr><th>Estado del Contribuyente en el RUC</th><td>Activo</td></tr>
<tr><th>Tipo de Contribuyente</th><td>Persona Natural</td></tr>
<tr><th>Obligado a llevar Contabilidad</th><td>NO</td></tr>
<tr><th>Actividad Económica Principal</th><td>ACTIVIDADES DE SERVICIOS DIVERSOS.</td></tr>
<tr><th>Fecha de inicio de actividades</th><td>21-09-2020</td></tr>
<tr><th>Fecha actualización</th><td>15-09-2023</td></tr>
<tr><th>Categoria Mi PYMES</th><td>No declarado</td></tr>
</table>
</body></html>
"""

_ESTABLISHMENTS_HTML = """
<html><body>
<table>
<tr><th>No. de Establecimiento</th><th>Nombre Comercial</th>
<th>Ubicación del Establecimiento</th><th>Estado del Establecimiento</th></tr>
<tr><td>001</td><td>DANIEL SANCHEZ</td>
<td>PICHINCHA / QUITO / VIA SAN JUAN</td><td>Abierto</td></tr>
</table>
</body></html>
"""


@pytest.mark.asyncio
async def test_get_ruc_info_parses_registry_and_establishments(httpx_mock):
    httpx_mock.add_response(
        url=f"{sri_ruc_client.SRI_RUC_INFO_URL}?ruc=1718647215001",
        html=_INFO_HTML,
    )
    httpx_mock.add_response(
        url=f"{sri_ruc_client.SRI_RUC_ESTABLECIMIENTOS_URL}?ruc=1718647215001",
        html=_ESTABLISHMENTS_HTML,
    )

    result = await sri_ruc_client.get_ruc_info("1718647215001")

    assert result["razon_social"] == "SANCHEZ PAZMIÑO DANIEL HERNAN"
    assert result["estado"] == "Activo"
    assert result["incluye_declaraciones_individuales"] is False
    assert result["establecimientos"] == [
        {
            "numero": "001",
            "nombre_comercial": "DANIEL SANCHEZ",
            "ubicacion": "PICHINCHA / QUITO / VIA SAN JUAN",
            "estado": "Abierto",
        }
    ]


@pytest.mark.asyncio
async def test_get_ruc_info_can_skip_establishments(httpx_mock):
    httpx_mock.add_response(
        url=f"{sri_ruc_client.SRI_RUC_INFO_URL}?ruc=1718647215001",
        html=_INFO_HTML,
    )

    result = await sri_ruc_client.get_ruc_info(
        "1718647215001", include_establecimientos=False
    )

    assert "establecimientos" not in result
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_get_ruc_info_returns_none_when_registry_has_no_taxpayer(httpx_mock):
    httpx_mock.add_response(
        url=f"{sri_ruc_client.SRI_RUC_INFO_URL}?ruc=1718647215001",
        html="<html><body>No se encontró información</body></html>",
    )

    assert await sri_ruc_client.get_ruc_info("1718647215001") is None


@pytest.mark.asyncio
async def test_get_ruc_info_rejects_non_13_digit_ruc():
    with pytest.raises(ValueError, match="13 dígitos"):
        await sri_ruc_client.get_ruc_info("123")


_RAZON_SOCIAL_CONTRIBUYENTES = [
    {
        "numeroRuc": "1790016919001",
        "razonSocial": "CORPORACION FAVORITA C.A.",
        "estadoContribuyenteRuc": "ACTIVO",
        "actividadEconomicaPrincipal": "VENTA AL POR MAYOR DE OTROS PRODUCTOS DIVERSOS.",
        "tipoContribuyente": "SOCIEDAD",
        "regimen": "GENERAL",
        "categoria": None,
        "obligadoLlevarContabilidad": "SI",
        "agenteRetencion": "SI",
        "contribuyenteEspecial": "SI",
        "informacionFechasContribuyente": {
            "fechaInicioActividades": "1957-11-30 00:00:00.0",
            "fechaCese": "",
            "fechaReinicioActividades": "",
            "fechaActualizacion": "2026-08-18 08:20:03.0",
        },
        "representantesLegales": [
            {"identificacion": "1701529958", "nombre": "WRIGHT DURAN BALLEN RONALD OWEN"}
        ],
        "motivoCancelacionSuspension": None,
        "contribuyenteFantasma": "NO",
        "transaccionesInexistente": "NO",
    },
    {
        "numeroRuc": "0791842165001",
        "razonSocial": "CORPORACION FAVORITA REMATES QUITO S.A.S.",
        "estadoContribuyenteRuc": "ACTIVO",
        "actividadEconomicaPrincipal": "VENTA AL POR MAYOR DE ARTICULOS DE FERRETERIA.",
        "tipoContribuyente": "SOCIEDAD",
        "regimen": "GENERAL",
        "categoria": None,
        "obligadoLlevarContabilidad": "SI",
        "agenteRetencion": "NO",
        "contribuyenteEspecial": "NO",
        "informacionFechasContribuyente": {
            "fechaInicioActividades": "2023-03-09 00:00:00.0",
            "fechaCese": "",
            "fechaReinicioActividades": "",
            "fechaActualizacion": "",
        },
        "representantesLegales": [
            {"identificacion": "0705339471", "nombre": "RAMIREZ RIOS JOHANNA CAROLINA"}
        ],
        "motivoCancelacionSuspension": None,
        "contribuyenteFantasma": "NO",
        "transaccionesInexistente": "NO",
    },
]


def _mock_razon_social_search(httpx_mock, texto: str, rucs: list[str], contribuyentes: list[dict]):
    base = sri_ruc_client.SRI_CATASTRO_BASE
    httpx_mock.add_response(
        url=f"{base}/cantidadObtenidaPorRazonSocial?razonSocial={texto}",
        json=len(rucs),
    )
    httpx_mock.add_response(
        url=f"{base}/numerosRucPorRazonSocialToken?razonSocial={texto}",
        json=rucs,
    )
    ruc_qs = "&".join(f"ruc={r}" for r in rucs)
    httpx_mock.add_response(
        url=f"{base}/obtenerPorNumerosRuc?{ruc_qs}",
        json=contribuyentes,
    )


@pytest.mark.asyncio
async def test_search_by_razon_social_returns_mapped_results(httpx_mock):
    _mock_razon_social_search(
        httpx_mock,
        "CORPORACION%20FAVORITA",
        ["1790016919001", "0791842165001"],
        _RAZON_SOCIAL_CONTRIBUYENTES,
    )

    result = await sri_ruc_client.search_by_razon_social("CORPORACION FAVORITA")

    assert result["total_reportado"] == 2
    assert result["nota"] is None
    assert len(result["resultados"]) == 2
    first = result["resultados"][0]
    assert first["ruc"] == "1790016919001"
    assert first["razon_social"] == "CORPORACION FAVORITA C.A."
    assert first["regimen"] == "GENERAL"
    assert first["fecha_inicio_actividades"] == "1957-11-30"
    assert first["representantes_legales"] == [
        {"identificacion": "1701529958", "nombre": "WRIGHT DURAN BALLEN RONALD OWEN"}
    ]


@pytest.mark.asyncio
async def test_search_by_razon_social_rejects_short_text():
    with pytest.raises(ValueError, match="al menos 4 caracteres"):
        await sri_ruc_client.search_by_razon_social("ab")


@pytest.mark.asyncio
async def test_search_by_razon_social_notes_the_100_cap(httpx_mock):
    rucs = [f"179000000{i:04d}001" for i in range(100)]
    # cantidadObtenidaPorRazonSocial reports the server's own 100-cap even
    # though we only fetch full detail for max_resultados of them.
    httpx_mock.add_response(
        url=f"{sri_ruc_client.SRI_CATASTRO_BASE}/cantidadObtenidaPorRazonSocial?razonSocial=BANCO",
        json=100,
    )
    httpx_mock.add_response(
        url=f"{sri_ruc_client.SRI_CATASTRO_BASE}/numerosRucPorRazonSocialToken?razonSocial=BANCO",
        json=rucs,
    )
    ruc_qs = "&".join(f"ruc={r}" for r in rucs[:3])
    httpx_mock.add_response(
        url=f"{sri_ruc_client.SRI_CATASTRO_BASE}/obtenerPorNumerosRuc?{ruc_qs}",
        json=_RAZON_SOCIAL_CONTRIBUYENTES[:1] * 3,
    )

    result = await sri_ruc_client.search_by_razon_social("BANCO", max_resultados=3)

    assert result["total_reportado"] == 100
    assert len(result["resultados"]) == 3
    assert "100 coincidencias" in result["nota"]
