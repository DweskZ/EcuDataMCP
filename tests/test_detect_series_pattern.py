import json

from mcp.server.fastmcp import FastMCP

import tools.detect_series_pattern as detect_series_pattern_module
from helpers import ckan_client
from tools.detect_series_pattern import (
    _find_period_columns,
    _locate_header_row,
    _period_keys,
    _pick_pair,
    _schema_mismatch,
    _strip_accents,
    register_detect_series_pattern_tool,
)


def _make_tool():
    mcp = FastMCP("test")
    register_detect_series_pattern_tool(mcp)
    return mcp._tool_manager.get_tool("detect_series_pattern").fn


# -- _strip_accents / _find_period_columns -----------------------------------


def test_strip_accents():
    assert _strip_accents("Año") == "Ano"
    assert _strip_accents("Período") == "Periodo"


def test_find_period_columns_matches_common_names():
    headers = ["Provincia", "Mes", "Monto", "Año"]
    assert _find_period_columns(headers) == [1, 3]


def test_find_period_columns_none_when_no_match():
    assert _find_period_columns(["Provincia", "Monto", "Beneficiarios"]) == []


# -- _period_keys --------------------------------------------------------


def test_period_keys_none_without_period_column():
    headers = ["Provincia", "Monto"]
    rows = [["Pichincha", "100"]]
    assert _period_keys(headers, rows) is None


def test_period_keys_single_column():
    headers = ["Fecha", "Monto"]
    rows = [["2026-01", "100"], ["2026-02", "200"], ["2026-01", "50"]]
    keys, cols = _period_keys(headers, rows)
    assert keys == {"2026-01", "2026-02"}
    assert cols == ["Fecha"]


def test_period_keys_composite_columns():
    headers = ["Provincia", "Mes", "Año", "Monto"]
    rows = [["Pichincha", "Enero", "2026", "100"], ["Guayas", "Enero", "2026", "50"]]
    keys, cols = _period_keys(headers, rows)
    assert keys == {"Enero|2026"}
    assert cols == ["Mes", "Año"]


# -- _locate_header_row -----------------------------------------------------
# Real case found live against IESS's Seguro de Desempleo dataset: the CSV
# leads with title/blank banner rows before the actual column headers.


def test_locate_header_row_skips_banner_rows():
    headers = ["", "", ""]
    rows = [
        ["Monto pagado y numero de beneficiarios 2026", "", ""],
        ["Mes", "Monto pagado", "Numero de Beneficiarios"],
        ["enero", "5603521.60", "2654"],
        ["febrero", "2855731.70", "1929"],
    ]
    located_headers, located_rows = _locate_header_row(headers, rows)
    assert located_headers == ["Mes", "Monto pagado", "Numero de Beneficiarios"]
    assert located_rows == [["enero", "5603521.60", "2654"], ["febrero", "2855731.70", "1929"]]


def test_locate_header_row_unchanged_when_row_zero_already_has_period_column():
    headers = ["Fecha", "Monto"]
    rows = [["2026-01", "100"]]
    assert _locate_header_row(headers, rows) == (headers, rows)


def test_locate_header_row_falls_back_when_nothing_found_within_scan_window():
    headers = ["", ""]
    rows = [["Provincia", "Monto"], ["Pichincha", "100"]]
    assert _locate_header_row(headers, rows) == (headers, rows)


# -- _schema_mismatch ---------------------------------------------------
# Real case found live: "Pagos Desempleo <mes> 2026" silently switches
# between a monthly cumulative-totals shape and a per-province/gender detail
# shape across consecutive months, despite the near-identical resource name.


def test_schema_mismatch_true_for_very_different_report_shapes():
    old = ["Mes", "Tipo Pago", "Provincia", "Genero", "Valor Pagado", "Numero Beneficiarios"]
    new = ["Mes", "Monto pagado", "Numero de Beneficiarios"]
    assert _schema_mismatch(old, new) is True


def test_schema_mismatch_false_for_same_report_shape():
    old = ["Mes", "Monto pagado", "Numero de Beneficiarios"]
    new = ["Mes", "Monto pagado", "Numero de Beneficiarios"]
    assert _schema_mismatch(old, new) is False


# -- _pick_pair ------------------------------------------------------------


def test_pick_pair_returns_two_most_recent_by_last_modified():
    resources = [
        {"name": "precios_semana_24.csv", "last_modified": "2026-06-10"},
        {"name": "precios_semana_25.csv", "last_modified": "2026-06-17"},
        {"name": "precios_semana_26.csv", "last_modified": "2026-06-24"},
        {"name": "diccionario.pdf", "last_modified": "2026-01-01"},
    ]
    newest, second = _pick_pair(resources)
    assert newest["name"] == "precios_semana_26.csv"
    assert second["name"] == "precios_semana_25.csv"


def test_pick_pair_none_without_a_group():
    resources = [
        {"name": "reporte_anual.csv"},
        {"name": "diccionario.pdf"},
    ]
    assert _pick_pair(resources) is None


def test_pick_pair_prefers_period_in_name_over_misleading_last_modified():
    # Real case found live against MPCEIP's cacao dataset: the January 2023
    # resource's last_modified was later than September 2023's (a
    # correction/re-upload), so sorting by last_modified alone picked
    # January as "most recent" -- 8 months backwards. The month/year parsed
    # from the name is a better signal than the portal's own timestamp.
    resources = [
        {
            "name": "MPCEIP_PRECIO FOB_EXPORTACIONES CACAO_2023_ENERO.csv",
            "last_modified": "2024-01-08T21:06:12",
        },
        {
            "name": "MPCEIP_PRECIO FOB_EXPORTACIONES CACAO_2023_SEPTIEMBRE.csv",
            "last_modified": "2023-09-27T15:56:27",
        },
        {
            "name": "MPCEIP_PRECIO FOB_EXPORTACIONES CACAO_2023_AGOSTO.csv",
            "last_modified": "2023-09-07T19:01:47",
        },
    ]
    newest, second = _pick_pair(resources)
    assert newest["name"] == "MPCEIP_PRECIO FOB_EXPORTACIONES CACAO_2023_SEPTIEMBRE.csv"
    assert second["name"] == "MPCEIP_PRECIO FOB_EXPORTACIONES CACAO_2023_AGOSTO.csv"


# -- tool: end-to-end classification ----------------------------------------


def _resource(name, url, fmt="CSV"):
    return {"id": name, "name": name, "url": url, "format": fmt}


async def test_classifies_acumulado_when_newer_file_covers_older_periods(monkeypatch):
    res_new = _resource("pagos_junio.csv", "https://x/junio.csv")
    res_old = _resource("pagos_mayo.csv", "https://x/mayo.csv")

    async def fake_get_resource(resource_id, session=None):
        return res_new if resource_id == "pagos_junio.csv" else res_old

    async def fake_fetch_table(res, session):
        if res is res_new:
            return {
                "headers": ["Mes", "Monto"],
                "rows": [["Enero", "1"], ["Febrero", "2"], ["Marzo", "3"]],
                "truncated": False,
            }
        return {
            "headers": ["Mes", "Monto"],
            "rows": [["Enero", "1"], ["Febrero", "2"]],
            "truncated": False,
        }

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)
    monkeypatch.setattr(detect_series_pattern_module, "_fetch_table", fake_fetch_table)

    tool = _make_tool()
    result = await tool(
        dataset_id="d1",
        resource_id_new="pagos_junio.csv",
        resource_id_old="pagos_mayo.csv",
        format="json",
    )
    payload = json.loads(result)

    assert payload["classification"] == "acumulado"
    assert payload["overlap_count"] == 2
    assert payload["periods_old_count"] == 2
    assert payload["periods_new_count"] == 3


async def test_classifies_incremental_when_periods_dont_overlap(monkeypatch):
    res_new = _resource("semana_26.csv", "https://x/26.csv")
    res_old = _resource("semana_25.csv", "https://x/25.csv")

    async def fake_get_resource(resource_id, session=None):
        return res_new if resource_id == "semana_26.csv" else res_old

    async def fake_fetch_table(res, session):
        if res is res_new:
            return {
                "headers": ["Semana", "Precio"],
                "rows": [["26", "174.77"]],
                "truncated": False,
            }
        return {
            "headers": ["Semana", "Precio"],
            "rows": [["25", "168.15"]],
            "truncated": False,
        }

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)
    monkeypatch.setattr(detect_series_pattern_module, "_fetch_table", fake_fetch_table)

    tool = _make_tool()
    result = await tool(
        dataset_id="d1",
        resource_id_new="semana_26.csv",
        resource_id_old="semana_25.csv",
        format="json",
    )
    payload = json.loads(result)

    assert payload["classification"] == "incremental"
    assert payload["overlap_count"] == 0


async def test_classifies_indeterminado_without_period_column(monkeypatch):
    res_new = _resource("a.csv", "https://x/a.csv")
    res_old = _resource("b.csv", "https://x/b.csv")

    async def fake_get_resource(resource_id, session=None):
        return res_new if resource_id == "a.csv" else res_old

    async def fake_fetch_table(res, session):
        return {
            "headers": ["Provincia", "Monto"],
            "rows": [["Pichincha", "100"]],
            "truncated": False,
        }

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)
    monkeypatch.setattr(detect_series_pattern_module, "_fetch_table", fake_fetch_table)

    tool = _make_tool()
    result = await tool(
        dataset_id="d1", resource_id_new="a.csv", resource_id_old="b.csv", format="json"
    )
    payload = json.loads(result)

    assert payload["classification"] == "indeterminado"
    assert payload["reason"] == "sin_columna_periodo_detectada"


async def test_flags_schema_mismatch_instead_of_misreading_as_incremental(monkeypatch):
    # Real case found live: "Pagos Desempleo Junio 2026" (monthly cumulative
    # summary, month names) vs "Pagos Desempleo Mayo 2026" (per-province
    # detail, numeric month codes) -- both have a "Mes" column and 0% period
    # overlap, but the files aren't comparable at all; the honest answer is
    # "different report shape", not a confident "incremental".
    res_new = _resource("pagos_junio.csv", "https://x/junio.csv")
    res_old = _resource("pagos_mayo.csv", "https://x/mayo.csv")

    async def fake_get_resource(resource_id, session=None):
        return res_new if resource_id == "pagos_junio.csv" else res_old

    async def fake_fetch_table(res, session):
        if res is res_new:
            return {
                "headers": ["Mes", "Monto pagado", "Numero de Beneficiarios"],
                "rows": [["enero", "5603521.60", "2654"], ["junio", "4022338.64", "2561"]],
                "truncated": False,
            }
        return {
            "headers": [
                "Mes",
                "Tipo Pago",
                "Provincia",
                "Genero",
                "Valor Pagado",
                "Numero Beneficiarios",
            ],
            "rows": [["5", "Fijo", "AZUAY", "MASCULINO", "24737.71", "74"]],
            "truncated": False,
        }

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)
    monkeypatch.setattr(detect_series_pattern_module, "_fetch_table", fake_fetch_table)

    tool = _make_tool()
    result = await tool(
        dataset_id="d1",
        resource_id_new="pagos_junio.csv",
        resource_id_old="pagos_mayo.csv",
        format="json",
    )
    payload = json.loads(result)

    assert payload["classification"] == "indeterminado"
    assert payload["reason"] == "esquema_distinto_entre_archivos"
    assert payload["schema_mismatch"] is True


async def test_requires_both_ids_or_neither():
    tool = _make_tool()
    result = await tool(dataset_id="d1", resource_id_new="only-one", format="json")
    payload = json.loads(result)
    assert payload["error"] == "faltan_ids"


async def test_autodetects_pair_from_dataset_when_no_ids_given(monkeypatch):
    resources = [
        {
            "id": "r24",
            "name": "precios_semana_24.csv",
            "url": "https://x/24.csv",
            "format": "CSV",
            "last_modified": "2026-06-10",
        },
        {
            "id": "r25",
            "name": "precios_semana_25.csv",
            "url": "https://x/25.csv",
            "format": "CSV",
            "last_modified": "2026-06-17",
        },
        {
            "id": "r26",
            "name": "precios_semana_26.csv",
            "url": "https://x/26.csv",
            "format": "CSV",
            "last_modified": "2026-06-24",
        },
    ]

    async def fake_get_dataset(dataset_id, session=None):
        return {"resources": resources}

    async def fake_fetch_table(res, session):
        return {
            "headers": ["Semana", "Precio"],
            "rows": [[res["id"], "1"]],
            "truncated": False,
        }

    monkeypatch.setattr(ckan_client, "get_dataset", fake_get_dataset)
    monkeypatch.setattr(detect_series_pattern_module, "_fetch_table", fake_fetch_table)

    tool = _make_tool()
    result = await tool(dataset_id="d1", format="json")
    payload = json.loads(result)

    assert payload["resource_new"]["id"] == "r26"
    assert payload["resource_old"]["id"] == "r25"


async def test_no_series_detected_without_ids(monkeypatch):
    async def fake_get_dataset(dataset_id, session=None):
        return {"resources": [{"id": "r1", "name": "unico.csv"}]}

    monkeypatch.setattr(ckan_client, "get_dataset", fake_get_dataset)

    tool = _make_tool()
    result = await tool(dataset_id="d1", format="json")
    payload = json.loads(result)

    assert payload["error"] == "sin_serie_detectada"
