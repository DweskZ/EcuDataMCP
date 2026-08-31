import pytest

from helpers import bce_indicadores_diarios_client as bce

_FORMULARIO_URL = f"{bce._BASE}/datos_formulario.json"

_FORMULARIO_JSON = {
    "view_ind_formulario": [
        {
            "Indicador": "Riesgo País",
            "Código Variable Dinámica": "val_ind_0003",
            "Fecha": "2026-08-26",
            "Carga": "2026-08-29",
            "Periodicidad": "D",
            "Valor": "419",
            "Medida": "Puntos Básicos",
            "Segmento": "Indicadores Económicos",
        },
        {
            "Indicador": "Riesgo País",
            "Código Variable Dinámica": "val_ind_0003",
            "Fecha": "2026-08-27",
            "Carga": "2026-08-29",
            "Periodicidad": "D",
            "Valor": "414",
            "Medida": "Puntos Básicos",
            "Segmento": "Indicadores Económicos",
        },
        {
            "Indicador": "Riesgo País",
            "Código Variable Dinámica": "val_ind_0003",
            "Fecha": "2026-08-28",
            "Carga": "2026-08-29",
            "Periodicidad": "D",
            "Valor": "410",
            "Medida": "Puntos Básicos",
            "Segmento": "Indicadores Económicos",
        },
        {
            "Indicador": "Precio del Oro",
            "Código Variable Dinámica": "val_ind_0004",
            "Fecha": "2026-08-28",
            "Carga": "2026-08-29",
            "Periodicidad": "D",
            "Valor": "4455.11",
            "Medida": "USD / Onza Troy",
            "Segmento": "Indicadores Económicos",
        },
    ]
}


@pytest.fixture(autouse=True)
def clear_cache():
    bce._files_cache.clear()
    yield
    bce._files_cache.clear()


def test_list_archivos_returns_fixed_set():
    archivos = bce.list_archivos()

    assert "datos_formulario.json" in archivos
    assert len(archivos) == 9


@pytest.mark.asyncio
async def test_get_indicador_diario_rejects_unknown_archivo():
    with pytest.raises(ValueError, match="no reconocido"):
        await bce.get_indicador_diario("no-existe.json", "val_ind_0003")


@pytest.mark.asyncio
async def test_get_indicador_diario_rejects_unknown_codigo(httpx_mock):
    httpx_mock.add_response(url=_FORMULARIO_URL, json=_FORMULARIO_JSON)

    with pytest.raises(ValueError, match="no encontrado"):
        await bce.get_indicador_diario("datos_formulario.json", "val_ind_9999")


@pytest.mark.asyncio
async def test_get_indicador_diario_returns_most_recent_window_and_full_range(httpx_mock):
    httpx_mock.add_response(url=_FORMULARIO_URL, json=_FORMULARIO_JSON)

    result = await bce.get_indicador_diario("datos_formulario.json", "val_ind_0003", ultimos_n=2)

    assert result["indicador"] == "Riesgo País"
    assert result["periodicidad"] == "D"
    assert result["rango_completo"] == {"desde": "2026-08-26", "hasta": "2026-08-28", "n_datos": 3}
    # Only the 2 most recent, even though the series has 3 points --
    # rango_completo above is how a caller learns there's more.
    assert result["datos"] == [
        {"fecha": "2026-08-27", "valor": "414"},
        {"fecha": "2026-08-28", "valor": "410"},
    ]


@pytest.mark.asyncio
async def test_get_indicador_diario_filters_by_date_range(httpx_mock):
    httpx_mock.add_response(url=_FORMULARIO_URL, json=_FORMULARIO_JSON)

    result = await bce.get_indicador_diario(
        "datos_formulario.json", "val_ind_0003", desde="2026-08-27", hasta="2026-08-27"
    )

    assert result["datos"] == [{"fecha": "2026-08-27", "valor": "414"}]


@pytest.mark.asyncio
async def test_get_indicador_diario_handles_files_with_no_valor_field(httpx_mock):
    # datos_ipc.json (Inflación) has no "Valor" field at all -- three
    # parallel series "Mensual"/"Anual"/"Acumulada" instead, confirmed
    # against the indicator's own widget JS (charts all three, not one).
    # Blindly reading row["Valor"] here silently returned None for every
    # observation until this was caught by inspecting the real file.
    ipc_url = f"{bce._BASE}/datos_ipc.json"
    ipc_json = {
        "view_ind_ipc": [
            {
                "Indicador": "Inflación",
                "Código Variable Dinámica": "val_var5",
                "Fecha": "2026-07-01",
                "Carga": "2026-08-01",
                "Periodicidad": "M",
                "Mensual": -0.09,
                "Anual": 1.39,
                "Acumulada": 1.3,
                "Medida": "Porcentaje",
                "Segmento": "Inflación",
            }
        ]
    }
    httpx_mock.add_response(url=ipc_url, json=ipc_json)

    result = await bce.get_indicador_diario("datos_ipc.json", "val_var5")

    assert result["datos"] == [
        {"fecha": "2026-07-01", "valores": {"Mensual": -0.09, "Anual": 1.39, "Acumulada": 1.3}}
    ]
    # And the common case is untouched: a single "Valor" field still comes
    # back as the simple {"fecha", "valor"} shape, not a "valores" dict.
    assert bce._datapoint(_FORMULARIO_JSON["view_ind_formulario"][0]) == {
        "fecha": "2026-08-26",
        "valor": "419",
    }


@pytest.mark.asyncio
async def test_get_indicador_diario_caps_window_at_max(httpx_mock):
    rows = [
        {
            "Indicador": "Riesgo País",
            "Código Variable Dinámica": "val_ind_0003",
            "Fecha": f"2020-01-{d:02d}" if d <= 31 else f"2020-02-{d - 31:02d}",
            "Carga": "2026-08-29",
            "Periodicidad": "D",
            "Valor": str(d),
            "Medida": "Puntos Básicos",
            "Segmento": "Indicadores Económicos",
        }
        for d in range(1, 401)
    ]
    httpx_mock.add_response(url=_FORMULARIO_URL, json={"view_ind_formulario": rows})

    result = await bce.get_indicador_diario("datos_formulario.json", "val_ind_0003", ultimos_n=10000)

    assert len(result["datos"]) == bce._MAX_VENTANA


@pytest.mark.asyncio
async def test_list_indicadores_discovers_catalog_from_data_not_hardcoded(httpx_mock):
    httpx_mock.add_response(url=_FORMULARIO_URL, json=_FORMULARIO_JSON)
    for archivo in bce.list_archivos():
        if archivo == "datos_formulario.json":
            continue
        httpx_mock.add_response(url=f"{bce._BASE}/{archivo}", status_code=404)

    catalog = await bce.list_indicadores()

    entries = {(c["archivo"], c["codigo"]): c for c in catalog}
    assert entries[("datos_formulario.json", "val_ind_0003")]["indicador"] == "Riesgo País"
    assert entries[("datos_formulario.json", "val_ind_0003")]["n_datos"] == 3
    assert entries[("datos_formulario.json", "val_ind_0004")]["indicador"] == "Precio del Oro"


@pytest.mark.asyncio
async def test_list_indicadores_tolerates_one_file_failing(httpx_mock, caplog):
    httpx_mock.add_response(url=_FORMULARIO_URL, json=_FORMULARIO_JSON)
    for archivo in bce.list_archivos():
        if archivo == "datos_formulario.json":
            continue
        httpx_mock.add_response(url=f"{bce._BASE}/{archivo}", status_code=500)

    with caplog.at_level("WARNING"):
        catalog = await bce.list_indicadores()

    assert any(c["archivo"] == "datos_formulario.json" for c in catalog)
    assert any("No se pudo leer" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_get_archivo_caches_and_dedupes_concurrent_calls(httpx_mock):
    httpx_mock.add_response(url=_FORMULARIO_URL, json=_FORMULARIO_JSON)

    import asyncio

    results = await asyncio.gather(
        bce.get_indicador_diario("datos_formulario.json", "val_ind_0003"),
        bce.get_indicador_diario("datos_formulario.json", "val_ind_0004"),
    )

    assert all(r["rango_completo"]["n_datos"] in (3, 1) for r in results)
    assert len(httpx_mock.get_requests()) == 1
