"""Regressions surfaced by the 2026-10-17 live smoke run on main.

- gob.ec answers /regulaciones/{id} with a one-element list, which the
  stricter get_regulacion treated as "not found".
- A BCE daily-indicator row without "Fecha" crashed list_indicadores.
- Supercías hosts drop datacenter connections; the classifier had no entry
  for the resulting ConnectTimeout wording, so the smoke run failed on them.
"""

from __future__ import annotations

import pytest

from helpers import bce_indicadores_diarios_client as bce
from helpers import gobec_client
from helpers.smoke_status import GEOBLOCKED_SOURCES, assess_response, degraded_source


async def test_get_regulacion_accepts_single_matching_list_record(monkeypatch):
    async def fake_fetch(url, params=None, session=None):
        return [{"regulacion_id": "5051", "regulacion": "Reglamento 0080"}]

    monkeypatch.setattr(gobec_client, "_fetch_json", fake_fetch)

    result = await gobec_client.get_regulacion("5051")

    assert result == {"regulacion_id": "5051", "regulacion": "Reglamento 0080"}


async def test_get_regulacion_collection_list_is_still_not_found(monkeypatch):
    async def fake_fetch(url, params=None, session=None):
        return [
            {"regulacion_id": "1", "regulacion": "A"},
            {"regulacion_id": "2", "regulacion": "B"},
        ]

    monkeypatch.setattr(gobec_client, "_fetch_json", fake_fetch)

    assert await gobec_client.get_regulacion("8") is None


async def test_get_institucion_accepts_single_matching_list_record(monkeypatch):
    async def fake_fetch(url, params=None, session=None):
        return [{"institucion_id": "8", "institucion": "Ministerio X"}]

    monkeypatch.setattr(gobec_client, "_fetch_json", fake_fetch)

    assert (await gobec_client.get_institucion("8"))["institucion"] == "Ministerio X"


async def test_list_indicadores_tolerates_row_without_fecha(httpx_mock):
    rows = [
        {"Código Variable Dinámica": "val_ind_0003", "Indicador": "Riesgo País",
         "Fecha": "2026-10-01", "Valor": 1.0, "Periodicidad": "D", "Medida": "pb"},
        {"Código Variable Dinámica": "val_ind_0003", "Indicador": "Riesgo País",
         "Fecha": None, "Valor": 2.0, "Periodicidad": "D", "Medida": "pb"},
        {"Código Variable Dinámica": "val_ind_0003", "Indicador": "Riesgo País",
         "Fecha": "2026-10-03", "Valor": 3.0, "Periodicidad": "D", "Medida": "pb"},
    ]
    httpx_mock.add_response(url=f"{bce._BASE}/datos_formulario.json", json={"x": rows})
    for archivo in bce.list_archivos():
        if archivo == "datos_formulario.json":
            continue
        httpx_mock.add_response(url=f"{bce._BASE}/{archivo}", status_code=404)

    catalog = await bce.list_indicadores()

    entry = next(c for c in catalog if c["codigo"] == "val_ind_0003")
    assert entry["n_datos"] == 3
    assert entry["fecha_desde"] == "2026-10-01"
    assert entry["fecha_hasta"] == "2026-10-03"


@pytest.mark.parametrize(
    "text",
    [
        (
            "Error al consultar el directorio de Supercías: No se pudo conectar a "
            "mercadodevalores.supercias.gob.ec (ConnectTimeout). Si el servidor corre "
            "fuera de Ecuador (por ejemplo en Render), el sitio suele descartar esas conexiones."
        ),
        (
            "La base de datos financiera de Supercías no existe todavía (descarga ~356 MB, "
            "15-20 minutos la primera vez). El último intento de construcción falló "
            "(2026-10-17T12:57:49+00:00): RuntimeError: No se pudo conectar a "
            "appscvsmovil.supercias.gob.ec (ConnectTimeout). Se reintentará automáticamente más tarde."
        ),
    ],
)
def test_supercias_connect_timeout_is_a_known_geoblock(text):
    assert degraded_source(text) == "supercias_geoblock"
    assert "supercias_geoblock" in GEOBLOCKED_SOURCES
    assert assess_response(text, [], is_error=True).status == "degraded"


def test_infomies_connect_timeout_is_a_known_geoblock():
    text = (
        "Error al consultar infoMIES: No se pudo conectar a "
        "info.desarrollohumano.gob.ec (ConnectTimeout). Si el servidor corre fuera "
        "de Ecuador (por ejemplo en Render), el sitio suele descartar esas conexiones."
    )
    assert degraded_source(text) == "infomies_geoblock"
    assert "infomies_geoblock" in GEOBLOCKED_SOURCES
    assert assess_response(text, [], is_error=True).status == "degraded"
