from datetime import UTC, datetime, timedelta

import pytest

from helpers import bce_calendario_client

# Real header/row shape confirmed live 2026-09-09 from
# https://contenido.bce.fin.ec/documentos/CalendarioEstadistico/calendario_publicaciones.csv
# -- UTF-8 with a BOM, semicolon-delimited, dates as D/M/YYYY (not
# zero-padded). RESPONSABLE/CORREO DEL RESPONSABLE are present in the real
# file but this client deliberately never reads them (see module docstring).
_HEADER = (
    "CALENDARIO;TIPO DE PUBLICACIÓN;NOMBRE DE LA PUBLICACIÓN;"
    "OPERACIÓN ESTADÍSTICA A LA QUE PERTENECE ;SUBGERENCIA RESPONSABLE DEL PRODUCTO;"
    "GESTIÓN RESPONSABLE DEL PRODUCTO;PERIODICIDAD;PERÍODO DE REFERENCIA;FECHA DE CORTE;"
    "FECHA;DÍA;MES;RESPONSABLE;CORREO DEL RESPONSABLE;Valida Fecha;Observaciones;"
    "CALENDARIO INEC;Categoría de Publicaciones;Enlace"
)

_TODAY = datetime.now(UTC).date()
_YESTERDAY = (_TODAY - timedelta(days=1)).strftime("%d/%m/%Y")
_TOMORROW = (_TODAY + timedelta(days=1)).strftime("%d/%m/%Y")


def _row(
    fecha: str,
    nombre: str = "Reporte de la Información Estadística Mensual (IEM)",
    tipo: str = "Reporte de datos",
    periodicidad: str = "Mensual",
    categoria: str = "Información Estadística Mensual (IEM)",
    observaciones: str = "",
    enlace: str = "https://contenido.bce.fin.ec/iem-publicaciones/",
) -> str:
    return (
        f"Calendario de Publicaciones Estadísticas;{tipo};{nombre};;"
        "Subgerencia de Información Estadística - SIE;Gestión Interna;"
        f"{periodicidad};última información disponible;;{fecha};miércoles;Enero;"
        "SIE;sie@bce.ec;;"
        f"{observaciones};No;{categoria};{enlace}"
    )


_CSV_BODY = "\n".join(
    [
        _HEADER,
        _row(_YESTERDAY, nombre="Reporte de la Información Estadística Mensual (IEM)"),
        _row(
            _TOMORROW,
            nombre="Reporte del IMAEc",
            categoria="Cuentas Nacionales",
            periodicidad="Mensual",
            observaciones="Considerando el PIB",
        ),
        _row(
            "31/12/2026",
            nombre="Boletín de Cuentas Nacionales Trimestrales",
            categoria="Cuentas Nacionales",
            periodicidad="Trimestral",
        ),
    ]
)
_CSV_BYTES = ("﻿" + _CSV_BODY).encode("utf-8")


@pytest.fixture(autouse=True)
def clear_cache():
    bce_calendario_client.clear_cache()
    yield
    bce_calendario_client.clear_cache()


@pytest.mark.asyncio
async def test_search_calendario_parses_bom_and_dates(httpx_mock):
    httpx_mock.add_response(url=bce_calendario_client._CSV_URL, content=_CSV_BYTES)

    result = await bce_calendario_client.search_calendario()

    assert result["total"] == 3
    assert result["total_calendario"] == 3
    fechas = [p["fecha"] for p in result["publicaciones"]]
    assert fechas == sorted(fechas)  # sorted ascending by fecha
    assert "2026-12-31" in fechas
    entry = next(p for p in result["publicaciones"] if p["fecha"] == "2026-12-31")
    assert entry["nombre"] == "Boletín de Cuentas Nacionales Trimestrales"
    assert entry["categoria"] == "Cuentas Nacionales"
    assert entry["periodicidad"] == "Trimestral"
    assert entry["enlace"] == "https://contenido.bce.fin.ec/iem-publicaciones/"
    # RESPONSABLE/CORREO DEL RESPONSABLE are never surfaced.
    assert "responsable" not in entry
    assert "correo_del_responsable" not in entry


@pytest.mark.asyncio
async def test_search_calendario_filters_by_query_and_categoria(httpx_mock):
    httpx_mock.add_response(url=bce_calendario_client._CSV_URL, content=_CSV_BYTES)

    result = await bce_calendario_client.search_calendario(query="imaec")

    assert result["total"] == 1
    assert result["publicaciones"][0]["nombre"] == "Reporte del IMAEc"

    result2 = await bce_calendario_client.search_calendario(categoria="cuentas nacionales")
    assert result2["total"] == 2


@pytest.mark.asyncio
async def test_search_calendario_filters_by_periodicidad_and_date_range(httpx_mock):
    httpx_mock.add_response(url=bce_calendario_client._CSV_URL, content=_CSV_BYTES)

    result = await bce_calendario_client.search_calendario(periodicidad="Trimestral")
    assert result["total"] == 1
    assert result["publicaciones"][0]["fecha"] == "2026-12-31"

    result2 = await bce_calendario_client.search_calendario(hasta="2026-06-01")
    assert result2["total"] < 3


@pytest.mark.asyncio
async def test_search_calendario_solo_proximas_excludes_past_dates(httpx_mock):
    httpx_mock.add_response(url=bce_calendario_client._CSV_URL, content=_CSV_BYTES)

    result = await bce_calendario_client.search_calendario(solo_proximas=True)

    fechas = [p["fecha"] for p in result["publicaciones"]]
    today = _TODAY.isoformat()
    assert all(f >= today for f in fechas)
    assert _YESTERDAY.split("/")[::-1] != fechas  # sanity: yesterday's entry excluded
    assert result["total"] == 2


@pytest.mark.asyncio
async def test_empty_csv_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=bce_calendario_client._CSV_URL, content=_HEADER.encode("utf-8"))
    httpx_mock.add_response(url=bce_calendario_client._CSV_URL, content=_CSV_BYTES)

    first = await bce_calendario_client.search_calendario()
    assert first["total_calendario"] == 0

    second = await bce_calendario_client.search_calendario()
    assert second["total_calendario"] == 3
