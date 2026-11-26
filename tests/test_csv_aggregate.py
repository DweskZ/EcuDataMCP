import json
import socket
from decimal import Decimal

import pytest
from mcp.server.mcpserver import MCPServer

from helpers import csv_aggregate
from helpers.csv_aggregate import aggregate_bytes, parse_number
from tools.aggregate_csv import register_aggregate_csv_tool

URL = "https://www.sri.gob.ec/descargar/sri_ventas_2018.csv"

# Shaped like the SRI's 2017-2024 files: pipe-delimited, decimal comma.
_PIPE = (
    "AÑO|MES|CODIGO_SECTOR_N1|PROVINCIA|CANTON|TOTAL_VENTAS|TOTAL_COMPRAS\r\n"
    "2018|1|G|PICHINCHA|QUITO|1983956804,4900|1036053994,9100\r\n"
    "2018|2|G|PICHINCHA|QUITO|100,5000|50,2500\r\n"
    "2018|2|C|AZUAY|CUENCA|2119670,9200|1191057,1300\r\n"
    "2018|10|S|GALÁPAGOS|SANTA CRUZ|,0000|2747,5100\r\n"
    "2018|10|S|GALÁPAGOS|ISABELA|321111,6300|180174,8500\r\n"
).encode()

# Shaped like the 2025 file: BOM, comma-delimited, quoted decimal commas, and
# TOTAL_VENTAS ahead of TOTAL_COMPRAS.
_COMMA = (
    "AÑO,MES,CODIGO_SECTOR_N1,PROVINCIA,CANTON,TOTAL_VENTAS,TOTAL_COMPRAS\r\n"
    '2025,1,9,PICHINCHA,QUITO,"36631,46","57964,49"\r\n'
    '2025,1,A,AZUAY,SEVILLA DE ORO,0,"2314,5"\r\n'
    '2025,2,A,AZUAY,SEVILLA DE ORO,"10,5",0\r\n'
).encode("utf-8-sig")


def _agg(raw, **kwargs):
    kwargs.setdefault("group_by", [])
    kwargs.setdefault("sum_columns", [])
    kwargs.setdefault("filters", {})
    return aggregate_bytes(raw, **kwargs)


# -- numbers ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("194488,1500", Decimal("194488.15")),
        ("194488.1500", Decimal("194488.15")),
        (",0000", Decimal(0)),
        ("1.234,56", Decimal("1234.56")),
        ("1,234.56", Decimal("1234.56")),
        ("1,234,567", Decimal(1234567)),
        ("1.234.567", Decimal(1234567)),
        ("-12,5", Decimal("-12.5")),
        ("$ 1 200,50", Decimal("1200.50")),
        ("0", Decimal(0)),
    ],
)
def test_parse_number_reads_both_decimal_marks(text, expected):
    assert parse_number(text) == expected


@pytest.mark.parametrize("text", ["", "  ", "n/d", "-", "NaN", "Infinity", "12%", "(5)"])
def test_parse_number_returns_none_for_what_is_not_a_number(text):
    assert parse_number(text) is None


# -- grouping -----------------------------------------------------------------


def test_groups_a_pipe_file_with_decimal_commas():
    result = _agg(_PIPE, group_by=["PROVINCIA"], sum_columns=["TOTAL_VENTAS"])

    rows = {row[0]: row for row in result["rows"]}
    assert result["headers"] == ["PROVINCIA", "filas", "TOTAL_VENTAS"]
    assert result["delimitador"] == "|"
    assert rows["PICHINCHA"][1] == 2
    assert rows["PICHINCHA"][2] == pytest.approx(1983956804.49 + 100.5)
    assert rows["AZUAY"][1:] == [1, 2119670.92]
    assert rows["GALÁPAGOS"][1:] == [2, 321111.63]
    assert result["filas_leidas"] == result["filas_coinciden"] == 5
    assert result["totales"]["filas"] == 5
    assert result["totales"]["TOTAL_VENTAS"] == pytest.approx(
        1983956804.49 + 100.5 + 2119670.92 + 321111.63
    )


def test_groups_a_bom_comma_file_with_quoted_decimal_commas():
    result = _agg(_COMMA, group_by=["provincia"], sum_columns=["total_compras", "total_ventas"])

    rows = {row[0]: row for row in result["rows"]}
    assert result["delimitador"] == ","
    assert result["headers"] == ["PROVINCIA", "filas", "TOTAL_COMPRAS", "TOTAL_VENTAS"]
    assert rows["PICHINCHA"][1:] == [1, 57964.49, 36631.46]
    assert rows["AZUAY"][1:] == [2, 2314.5, 10.5]


def test_totals_are_exact_where_floats_drift():
    raw = b"g|v\n" + b"a|0,1\n" * 10
    result = _agg(raw, group_by=["g"], sum_columns=["v"])

    assert result["rows"][0][2] == 1.0
    assert sum([0.1] * 10) != 1.0


def test_column_names_ignore_case_and_accents():
    result = _agg(_PIPE, group_by=["ano", "Codigo Sector N1"], sum_columns=["total ventas"])

    assert result["headers"][:2] == ["AÑO", "CODIGO_SECTOR_N1"]
    assert result["grupos"] == 3


def test_no_group_by_gives_one_total_row():
    result = _agg(_PIPE, sum_columns=["TOTAL_COMPRAS"])

    assert result["grupos"] == 1
    assert result["rows"][0][:2] == [5, pytest.approx(1036053994.91 + 50.25 + 1191057.13 + 2747.51 + 180174.85)]


def test_no_group_and_no_sum_only_counts_rows():
    result = _agg(_PIPE, filters={"PROVINCIA": ["Azuay"]})

    assert result["headers"] == ["filas"]
    assert result["rows"] == [[1]]
    assert result["totales"] == {"filas": 1}


# -- filters ------------------------------------------------------------------


def test_filters_match_a_list_of_values_without_case_or_accents():
    result = _agg(
        _PIPE,
        group_by=["PROVINCIA"],
        sum_columns=["TOTAL_VENTAS"],
        filters={"provincia": ["galapagos", "AZUAY"]},
    )

    assert {row[0] for row in result["rows"]} == {"GALÁPAGOS", "AZUAY"}
    assert result["filas_leidas"] == 5
    assert result["filas_coinciden"] == 3


def test_a_numeric_filter_matches_the_number_not_the_spelling():
    raw = b"mes|v\n01|5\n1|6\n2|7\n10|8\n"
    result = _agg(raw, group_by=["mes"], sum_columns=["v"], filters={"mes": ["1", "10"]})

    assert {row[0]: row[2] for row in result["rows"]} == {"01": 5.0, "1": 6.0, "10": 8.0}


def test_two_filters_must_both_hold():
    result = _agg(
        _PIPE,
        sum_columns=["TOTAL_VENTAS"],
        filters={"PROVINCIA": ["PICHINCHA"], "MES": ["2"]},
    )

    assert result["rows"] == [[1, 100.5]]


# -- cells that are not numbers ------------------------------------------------


def test_blank_and_text_cells_are_counted_not_totalled():
    raw = b"g,v\na,5\na,\na,n/d\na,2\n"
    result = _agg(raw, group_by=["g"], sum_columns=["v"])

    assert result["rows"] == [["a", 4, 7.0]]
    assert result["celdas_vacias"] == {"v": 1}
    assert result["celdas_no_numericas"] == {"v": 1}


def test_short_rows_and_blank_lines_do_not_break_the_read():
    raw = b"g,v\na,5\n\nb\n,,,\na,1\n"
    result = _agg(raw, group_by=["g"], sum_columns=["v"], order_by="g")

    assert result["rows"] == [["a", 2, 6.0], ["b", 1, 0.0]]
    assert result["celdas_vacias"] == {"v": 1}


# -- ordering and limit -------------------------------------------------------


def test_default_order_is_the_first_total_biggest_first():
    result = _agg(_PIPE, group_by=["PROVINCIA"], sum_columns=["TOTAL_VENTAS", "TOTAL_COMPRAS"])

    assert [row[0] for row in result["rows"]] == ["PICHINCHA", "AZUAY", "GALÁPAGOS"]


def test_default_order_without_totals_is_the_biggest_count():
    result = _agg(_PIPE, group_by=["PROVINCIA"])

    assert result["rows"][-1] == ["AZUAY", 1]
    assert result["rows"][0][1] == 2


def test_a_group_column_sorts_ascending_and_numbers_sort_as_numbers():
    result = _agg(_PIPE, group_by=["MES"], sum_columns=["TOTAL_VENTAS"], order_by="MES")

    assert [row[0] for row in result["rows"]] == ["1", "2", "10"]

    result = _agg(_PIPE, group_by=["MES"], sum_columns=["TOTAL_VENTAS"], order_by="mes desc")

    assert [row[0] for row in result["rows"]] == ["10", "2", "1"]


def test_order_by_a_total_ascending():
    result = _agg(
        _PIPE, group_by=["PROVINCIA"], sum_columns=["TOTAL_VENTAS"], order_by="total_ventas asc"
    )

    assert result["rows"][0][0] == "GALÁPAGOS"


def test_limit_cuts_the_rows_but_not_the_totals():
    result = _agg(_PIPE, group_by=["PROVINCIA"], sum_columns=["TOTAL_VENTAS"], limit=1)

    assert len(result["rows"]) == 1
    assert result["grupos"] == 3
    assert result["truncated"] is True
    assert result["totales"]["filas"] == 5


# -- errors and encodings -----------------------------------------------------


def test_an_unknown_column_lists_the_real_ones():
    with pytest.raises(ValueError, match="TOTAL_VENTAS") as exc:
        _agg(_PIPE, group_by=["PROVINCIAS"])

    assert "'PROVINCIAS'" in str(exc.value)


def test_an_unknown_filter_column_and_order_column_are_refused():
    with pytest.raises(ValueError, match="filters_json"):
        _agg(_PIPE, filters={"REGION": ["x"]})
    with pytest.raises(ValueError, match="order_by"):
        _agg(_PIPE, group_by=["PROVINCIA"], order_by="nope")


def test_an_empty_file_is_refused():
    with pytest.raises(ValueError, match="vacío"):
        _agg(b"")


def test_a_windows_1252_file_keeps_its_accents():
    raw = "prov;v\nGalápagos;1,5\nGalápagos;2,5\n".encode("cp1252")
    result = _agg(raw, group_by=["prov"], sum_columns=["v"])

    assert result["delimitador"] == ";"
    assert result["rows"] == [["Galápagos", 2, 4.0]]


def test_skip_rows_jumps_over_a_title_block():
    raw = b"Reporte de ventas\nFuente: SRI\ng,v\na,1\na,2\n"
    result = _agg(raw, group_by=["g"], sum_columns=["v"], skip_rows=2)

    assert result["rows"] == [["a", 2, 3.0]]


def test_a_quoted_field_with_a_newline_stays_one_row():
    raw = b'g,v\n"a\nb",5\nc,1\n'
    result = _agg(raw, group_by=["g"], sum_columns=["v"], order_by="v desc")

    assert result["filas_leidas"] == 2
    assert result["rows"][0] == ["a\nb", 1, 5.0]


def test_too_many_groups_is_refused(monkeypatch):
    monkeypatch.setattr(csv_aggregate, "MAX_GROUPS", 2)

    with pytest.raises(ValueError, match="grupos distintos"):
        _agg(_PIPE, group_by=["MES"])


# -- download -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    csv_aggregate._cache.clear()
    yield
    csv_aggregate._cache.clear()


async def _url(**kwargs):
    kwargs.setdefault("group_by", ["PROVINCIA"])
    kwargs.setdefault("sum_columns", ["TOTAL_VENTAS"])
    kwargs.setdefault("filters", {})
    return await csv_aggregate.aggregate_url(URL, **kwargs)


async def test_reads_the_whole_file_and_answers_a_repeat_from_memory(httpx_mock):
    httpx_mock.add_response(url=URL, content=_PIPE)

    first = await _url()
    second = await _url()

    assert first["bytes_leidos"] == len(_PIPE)
    assert first["rows"][0][0] == "PICHINCHA"
    assert second == first
    assert len(httpx_mock.get_requests()) == 1


async def test_a_different_question_downloads_again(httpx_mock):
    httpx_mock.add_response(url=URL, content=_PIPE, is_reusable=True)

    await _url()
    await _url(group_by=["MES"])

    assert len(httpx_mock.get_requests()) == 2


async def test_a_file_over_the_cap_is_refused_not_summed_in_part(httpx_mock, monkeypatch):
    monkeypatch.setattr(csv_aggregate, "MAX_BYTES", 64)
    httpx_mock.add_response(url=URL, content=_PIPE)

    with pytest.raises(ValueError, match="incompleto"):
        await _url()


@pytest.mark.parametrize(
    "body",
    [b"PK\x03\x04rest", b"\x1f\x8bgzip", b"<html><body>Error</body></html>"],
)
async def test_a_zip_gzip_or_web_page_is_refused(httpx_mock, body):
    httpx_mock.add_response(url=URL, content=body)

    with pytest.raises(ValueError):
        await _url()


@pytest.mark.parametrize("name", ["datos.zip", "libro.XLSX", "reporte.pdf", "a.csv.gz"])
async def test_a_url_that_is_not_text_is_refused_before_downloading(httpx_mock, name):
    with pytest.raises(ValueError, match="Este archivo"):
        await csv_aggregate.aggregate_url(
            f"https://example.org/{name}", group_by=[], sum_columns=[], filters={}
        )

    assert httpx_mock.get_requests() == []


# -- the tool -----------------------------------------------------------------


def _server():
    server = MCPServer("test")
    register_aggregate_csv_tool(server)
    return server


async def test_tool_returns_groups_totals_and_the_columns_as_json(httpx_mock):
    httpx_mock.add_response(url=URL, content=_PIPE)

    result = await _server().call_tool(
        "aggregate_csv",
        {
            "url": URL,
            "group_by": "PROVINCIA",
            "sum_columns": "TOTAL_VENTAS",
            "filters_json": '{"MES": [1, 2]}',
            "format": "json",
        },
    )
    payload = json.loads(result.content[0].text)

    assert payload["headers"] == ["PROVINCIA", "filas", "TOTAL_VENTAS"]
    assert [row[0] for row in payload["rows"]] == ["PICHINCHA", "AZUAY"]
    assert payload["filas_coinciden"] == 3
    assert payload["filters"] == {"MES": ["1", "2"]}
    assert "TOTAL_COMPRAS" in payload["columnas"]
    assert payload["metadatos"]["contrato"] == "ecudatamcp.response.v1"


async def test_tool_text_shows_the_table_the_totals_and_the_warnings(httpx_mock):
    raw = b"g,v\na,5\na,\nb,2\n"
    httpx_mock.add_response(url=URL, content=raw)

    text = (
        await _server().call_tool(
            "aggregate_csv", {"url": URL, "group_by": "g", "sum_columns": "v"}
        )
    ).content[0].text

    assert "Filas leídas: 3" in text
    assert "Celdas vacías" in text
    assert "Totales sobre todas las filas que cumplen:" in text
    assert "- v: 7" in text
    assert "Columnas del archivo: g, v" in text


@pytest.mark.parametrize(
    ("filters_json", "message"),
    [
        ("{no", "no es JSON válido"),
        ("[1]", "objeto JSON"),
        ('{"MES": {"a": 1}}', "un valor o una lista"),
    ],
)
async def test_tool_refuses_bad_filters_before_downloading(httpx_mock, filters_json, message):
    with pytest.raises(Exception, match=message):
        await _server().call_tool("aggregate_csv", {"url": URL, "filters_json": filters_json})

    assert httpx_mock.get_requests() == []


async def test_tool_names_the_columns_when_one_is_not_found(httpx_mock):
    httpx_mock.add_response(url=URL, content=_PIPE)

    with pytest.raises(Exception, match="No hay una columna 'NOPE'"):
        await _server().call_tool("aggregate_csv", {"url": URL, "group_by": "NOPE"})
