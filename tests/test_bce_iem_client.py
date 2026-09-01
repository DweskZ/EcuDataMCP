from __future__ import annotations

import hashlib
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


def _monthly_xlsx() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Indicador mensual", None, None])
    sheet.append(["Mes", "Ene 2025", "Febrero 2025"])
    sheet.append(["Variable", "valor", "valor"])
    sheet.append(["PIB", 101, 102])
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


def test_merge_bulletins_prefers_latest_publication_for_duplicate_number():
    index = [{"numero": 2092, "url": "index-version"}]
    latest = [{"numero": 2092, "url": "latest-version"}, {"numero": 2093, "url": "new"}]

    merged = bce_iem_client._merge_bulletins(latest, index)

    assert [item["numero"] for item in merged] == [2093, 2092]
    assert merged[1]["url"] == "latest-version"


def test_parse_complete_files_catalogs_pdf_and_zip():
    bulletin = _PARSED_BULLETINS[0]

    files = bce_iem_client._parse_complete_files(
        '<a href="IEM2092.pdf">PDF completo</a>'
        '<a href="IEM2092.zip">ZIP completo</a>'
        '<a href="IEM-431-e.xlsx">Tabla</a>',
        bulletin,
    )

    assert [(item["tipo"], item["nombre"]) for item in files] == [
        ("pdf", "IEM2092.pdf"),
        ("zip", "IEM2092.zip"),
    ]


@pytest.mark.asyncio
async def test_fetch_bulletins_reconciles_latest_publications(httpx_mock):
    httpx_mock.add_response(url=bce_iem_client.IEM_INDEX_URL, html=_INDEX_HTML)
    httpx_mock.add_response(
        url=bce_iem_client.IEM_LATEST_PUBLICATIONS_URL,
        html='<a href="m2093072026.html">No. 2093 Julio 2026</a>',
    )

    bulletins = await bce_iem_client._fetch_bulletins()

    assert bulletins[0]["numero"] == 2093
    assert len(bulletins) == 3


@pytest.mark.asyncio
async def test_search_tables_can_persist_the_complete_catalog(httpx_mock, tmp_path, monkeypatch):
    monkeypatch.setenv("IEM_CATALOG_DIR", str(tmp_path))
    httpx_mock.add_response(url=bce_iem_client.IEM_INDEX_URL, html=_INDEX_HTML)
    httpx_mock.add_response(
        url=bce_iem_client.IEM_LATEST_PUBLICATIONS_URL, html=""
    )
    httpx_mock.add_response(url=_NEW_BULLETIN_URL, html=_BULLETIN_HTML)

    result = await bce_iem_client.search_tables(guardar_catalogo=True)

    assert result["catalogo_guardado"]["archivo"].endswith(".json")
    assert (tmp_path / "latest.json").exists()


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


def test_extract_monthly_wide_series_accepts_spanish_month_labels():
    workbook = openpyxl.load_workbook(
        io.BytesIO(_monthly_xlsx()), read_only=True, data_only=True
    )
    result = bce_iem_client._extract_wide_series(
        workbook.active, "2025-02", "2025-02", 20
    )
    workbook.close()

    assert result is not None
    assert result["periodos"] == ["Febrero 2025"]
    assert result["bloques"][0]["series"] == [
        {"nombre": "PIB", "valores": {"Febrero 2025": 102}}
    ]


def test_period_key_accepts_numeric_month_year_and_spanish_month():
    assert bce_iem_client._period_key("03/2025") == (2025, 3)
    assert bce_iem_client._period_key("Marzo 2025") == (2025, 3)
    assert bce_iem_client._period_key("II trimestre 2025") == (2025, 4)


def test_extract_matrix_series_preserves_descriptor_columns():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Código", "Descripción", 2024, 2025])
    sheet.append(["A", "PIB", 100, 110])

    result = bce_iem_client._extract_matrix_series(sheet, "2025", "2025", 20)

    assert result["formato"] == "series_matriz"
    assert result["columnas_descriptivas"] == ["Código", "Descripción"]
    assert result["bloques"][0]["series"] == [
        {"nombre": "A | PIB", "valores": {"2025": 110}}
    ]


@pytest.mark.asyncio
async def test_search_tables_indexes_latest_bulletin_and_filters(httpx_mock):
    httpx_mock.add_response(url=bce_iem_client.IEM_INDEX_URL, html=_INDEX_HTML)
    httpx_mock.add_response(
        url=bce_iem_client.IEM_LATEST_PUBLICATIONS_URL, html=""
    )
    httpx_mock.add_response(url=_NEW_BULLETIN_URL, html=_BULLETIN_HTML)

    result = await bce_iem_client.search_tables("exportaciones")

    assert result["boletin"]["numero"] == 2092
    assert result["total"] == 1
    assert result["tablas"][0]["table_id"] == "iem-432-e"


@pytest.mark.asyncio
async def test_search_tables_historical_merges_versions(httpx_mock):
    httpx_mock.add_response(url=bce_iem_client.IEM_INDEX_URL, html=_INDEX_HTML)
    httpx_mock.add_response(
        url=bce_iem_client.IEM_LATEST_PUBLICATIONS_URL, html=""
    )
    httpx_mock.add_response(url=_NEW_BULLETIN_URL, html=_BULLETIN_HTML)
    httpx_mock.add_response(url=_OLD_BULLETIN_URL, html=_BULLETIN_HTML)

    result = await bce_iem_client.search_tables("PIB", historico=True)

    assert result["historico"] is True
    assert result["boletines_consultados"] == 2
    assert result["boletines_sin_tablas"] == 0
    assert result["tablas"][0]["boletines_disponibles"] == 2


@pytest.mark.asyncio
async def test_get_table_returns_layout_preview(httpx_mock):
    xlsx = _xlsx()
    httpx_mock.add_response(url=bce_iem_client.IEM_INDEX_URL, html=_INDEX_HTML)
    httpx_mock.add_response(
        url=bce_iem_client.IEM_LATEST_PUBLICATIONS_URL, html=""
    )
    httpx_mock.add_response(url=_NEW_BULLETIN_URL, html=_BULLETIN_HTML)
    httpx_mock.add_response(url=_PIB_TABLE_URL, content=xlsx)

    result = await bce_iem_client.get_table("iem-431-e", desde="2025", max_rows=3)

    assert result["tabla"]["titulo"].startswith("Producto Interno")
    assert result["formato"] == "series_ancho"
    assert result["periodos"] == ["2025"]
    assert result["bloques"][0]["unidad"] == "Millones USD"
    assert result["bloques"][0]["series"] == [
        {"nombre": "PIB", "valores": {"2025": 130.2}}
    ]
    assert result["tabla"]["sha256"] == hashlib.sha256(xlsx).hexdigest()
