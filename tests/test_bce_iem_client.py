from __future__ import annotations

import io

import openpyxl
import pytest

from helpers import bce_iem_client
from helpers.cache import TtlCache

_INDEX_HTML = """
<a href="m2091062026.html">No. 2091 Mayo 2026</a>
<a href="m2092062026.html">No. 2092 Junio 2026</a>
"""

_BULLETIN_HTML = """
<h2>3. ESTADÍSTICAS DEL SECTOR EXTERNO</h2>
<p>3.1.1 <a href="Catalogo/IEMensual/m2091/IEM-431-e.xlsx">Producto Interno Bruto (PIB): Enfoque del Gasto</a></p>
<p>3.1.2 <a href="Catalogo/IEMensual/m2091/IEM-432-e.xlsx">Exportaciones FOB por Producto Principal</a></p>
<a href="Catalogo/IEMensual/m2091/IEM2091.zip">ZIP completo</a>
"""


_PARSED_BULLETINS = bce_iem_client._parse_bulletins(_INDEX_HTML)
_NEW_BULLETIN_URL = _PARSED_BULLETINS[0]["url"]
_OLD_BULLETIN_URL = _PARSED_BULLETINS[1]["url"]
_PARSED_TABLES = bce_iem_client._parse_tables(_BULLETIN_HTML, _PARSED_BULLETINS[0])
_PIB_TABLE_URL = _PARSED_TABLES[0]["url"]


@pytest.fixture(autouse=True)
def _reset_cache():
    bce_iem_client._catalog_cache = TtlCache(ttl_seconds=60)
    bce_iem_client._bulletins_cache = TtlCache(ttl_seconds=60)
    bce_iem_client._bulletin_tables_cache = TtlCache(ttl_seconds=60, max_entries=512)
    bce_iem_client._bulletin_fetch_locks = {}
    yield


def _xlsx() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Cuadro"
    sheet.append(["Producto Interno Bruto", None, None])
    sheet.append([])
    sheet.append(["Período", 2024, 2025])
    sheet.append(["Variable", "(prev)", "(prev)"])
    sheet.append(["Millones USD", None, None])
    sheet.append(["PIB", 123.4, 130.2])
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def _long_xlsx() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Nombre de la tabla"])
    sheet.append([])
    sheet.append(["Año", "Indicador", "Valor"])
    sheet.append([2024, "PIB", 100])
    sheet.append([2025, "PIB", 110])
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def _wide_xlsx_with_gap() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Período", 2024, 2025])
    sheet.append(["Variable", "(prev)", "(prev)"])
    sheet.append(["Millones USD", None, None])
    sheet.append(["PIB", 123.4, 130.2])
    sheet.append(["PIB Nuevo", 50.0, None])
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def test_parse_bulletins_picks_newest_and_resolves_urls():
    bulletins = bce_iem_client._parse_bulletins(_INDEX_HTML)

    assert [item["numero"] for item in bulletins] == [2092, 2091]
    assert bulletins[0]["url"].endswith("m2092062026.html")


def test_parse_tables_keeps_real_link_not_guessed_bulletin_directory():
    bulletin = bce_iem_client._parse_bulletins(_INDEX_HTML)[0]
    tables = bce_iem_client._parse_tables(_BULLETIN_HTML, bulletin)

    assert [table["table_id"] for table in tables] == ["iem-431-e", "iem-432-e"]
    assert tables[0]["url"].endswith("IEMensual/m2091/IEM-431-e.xlsx")
    assert tables[0]["boletin_numero"] == 2092


def test_merge_historical_tables_keeps_all_versions():
    bulletin_1 = {"numero": 2092, "mes": 6, "anio": 2026, "url": "new"}
    bulletin_2 = {"numero": 2091, "mes": 5, "anio": 2026, "url": "old"}
    tables = bce_iem_client._parse_tables(_BULLETIN_HTML, bulletin_1)
    tables += bce_iem_client._parse_tables(_BULLETIN_HTML, bulletin_2)

    merged = bce_iem_client._merge_historical_tables(tables)

    assert len(merged) == 2
    assert merged[0]["boletines_disponibles"] == 2
    assert [version["boletin_numero"] for version in merged[0]["versiones"]] == [
        2092,
        2091,
    ]


def test_extract_wide_series_returns_none_when_range_not_covered():
    workbook = openpyxl.load_workbook(io.BytesIO(_xlsx()), read_only=True, data_only=True)
    result = bce_iem_client._extract_wide_series(workbook.active, "1990", "1990", 20)
    workbook.close()

    assert result is None


def test_extract_wide_series_keeps_row_with_no_data_in_selected_range():
    workbook = openpyxl.load_workbook(
        io.BytesIO(_wide_xlsx_with_gap()), read_only=True, data_only=True
    )
    result = bce_iem_client._extract_wide_series(workbook.active, "2025", "2025", 20)
    workbook.close()

    assert result is not None
    names = [series["nombre"] for series in result["bloques"][0]["series"]]
    assert names == ["PIB", "PIB Nuevo"]


@pytest.mark.asyncio
async def test_fetch_historical_tables_caps_unbounded_fanout(monkeypatch):
    bulletins = [
        {"numero": n, "mes": 1, "anio": 2000 + n, "url": f"http://x/{n}"}
        for n in range(bce_iem_client._MAX_HISTORICAL_BULLETINS + 20)
    ]

    async def fake_fetch(bulletin: dict) -> list[dict]:
        return [{"table_id": f"t{bulletin['numero']}"}]

    monkeypatch.setattr(bce_iem_client, "_fetch_tables_for_bulletin", fake_fetch)

    _, selected, loaded = await bce_iem_client._fetch_historical_tables(bulletins, 0, 0)

    assert len(selected) == bce_iem_client._MAX_HISTORICAL_BULLETINS
    assert loaded == bce_iem_client._MAX_HISTORICAL_BULLETINS


@pytest.mark.asyncio
async def test_fetch_historical_tables_respects_explicit_range_beyond_cap(monkeypatch):
    total = bce_iem_client._MAX_HISTORICAL_BULLETINS + 20
    bulletins = [
        {"numero": n, "mes": 1, "anio": 2000 + n, "url": f"http://x/{n}"}
        for n in range(total)
    ]

    async def fake_fetch(bulletin: dict) -> list[dict]:
        return [{"table_id": f"t{bulletin['numero']}"}]

    monkeypatch.setattr(bce_iem_client, "_fetch_tables_for_bulletin", fake_fetch)

    _, selected, loaded = await bce_iem_client._fetch_historical_tables(
        bulletins, 2000, 2000 + total - 1
    )

    assert len(selected) == total
    assert loaded == total


def test_extract_long_table_filters_rows_by_year():
    workbook = openpyxl.load_workbook(io.BytesIO(_long_xlsx()), read_only=True, data_only=True)
    result = bce_iem_client._extract_long_table(workbook.active, "2025", "2025", 20)
    workbook.close()

    assert result == {
        "formato": "tabla_larga",
        "encabezados": ["Año", "Indicador", "Valor"],
        "filas": [["2025", "PIB", "110"]],
        "filas_totales": 1,
        "truncada": False,
    }


@pytest.mark.asyncio
async def test_search_tables_indexes_latest_bulletin_and_filters(httpx_mock):
    httpx_mock.add_response(url=bce_iem_client.IEM_INDEX_URL, html=_INDEX_HTML)
    httpx_mock.add_response(url=_NEW_BULLETIN_URL, html=_BULLETIN_HTML)

    result = await bce_iem_client.search_tables("exportaciones")

    assert result["boletin"]["numero"] == 2092
    assert result["total"] == 1
    assert result["tablas"][0]["table_id"] == "iem-432-e"


@pytest.mark.asyncio
async def test_search_tables_historical_merges_versions(httpx_mock):
    httpx_mock.add_response(url=bce_iem_client.IEM_INDEX_URL, html=_INDEX_HTML)
    httpx_mock.add_response(url=_NEW_BULLETIN_URL, html=_BULLETIN_HTML)
    httpx_mock.add_response(url=_OLD_BULLETIN_URL, html=_BULLETIN_HTML)

    result = await bce_iem_client.search_tables("PIB", historico=True)

    assert result["historico"] is True
    assert result["boletines_consultados"] == 2
    assert result["boletines_sin_tablas"] == 0
    assert result["tablas"][0]["boletines_disponibles"] == 2


@pytest.mark.asyncio
async def test_get_table_returns_layout_preview(httpx_mock):
    httpx_mock.add_response(url=bce_iem_client.IEM_INDEX_URL, html=_INDEX_HTML)
    httpx_mock.add_response(url=_NEW_BULLETIN_URL, html=_BULLETIN_HTML)
    httpx_mock.add_response(url=_PIB_TABLE_URL, content=_xlsx())

    result = await bce_iem_client.get_table("iem-431-e", desde="2025", max_rows=3)

    assert result["tabla"]["titulo"].startswith("Producto Interno")
    assert result["formato"] == "series_ancho"
    assert result["periodos"] == ["2025"]
    assert result["bloques"][0]["unidad"] == "Millones USD"
    assert result["bloques"][0]["series"] == [
        {"nombre": "PIB", "valores": {"2025": 130.2}}
    ]
