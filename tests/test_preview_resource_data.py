import json

import httpx
from mcp.server.fastmcp import FastMCP

import tools.preview_resource_data as preview_resource_data_module
from helpers import ckan_client
from tools.preview_resource_data import (
    classify_from_content_type,
    classify_resource_format,
    register_preview_resource_data_tool,
)


def _make_tool():
    mcp = FastMCP("test")
    register_preview_resource_data_tool(mcp)
    return mcp._tool_manager.get_tool("preview_resource_data").fn


# -- classify_resource_format ------------------------------------------------


def test_classify_by_extension_wins_over_conflicting_declared_format():
    # Real case found during e2e verification: SRI declares CSV in CKAN but
    # actually serves the resource as .tar.gz.
    assert (
        classify_resource_format("CSV", "https://x/sri_activos_2025.tar.gz") == "TARGZ"
    )
    # Real case found during e2e verification: MPCEIP declares CSV in CKAN
    # but the resource is actually .xlsx.
    assert classify_resource_format("CSV", "https://x/precios_cacao.xlsx") == "XLSX"


def test_classify_rar_by_extension_even_if_declared_csv():
    assert classify_resource_format("CSV", "https://x/archivo.rar") == "RAR"


def test_classify_falls_back_to_declared_format_without_recognizable_extension():
    assert classify_resource_format("RAR", "https://x/download?id=123") == "RAR"
    assert classify_resource_format("ZIP", "https://x/download?id=123") == "ZIP"
    assert classify_resource_format("XLS", "https://x/download?id=123") == "XLS"
    assert classify_resource_format("JSON", "https://x/download?id=123") == "JSON"
    assert classify_resource_format("CSV", "https://x/download?id=123") == "CSV"
    # No format declared and no recognizable extension: same "assume CSV"
    # default the tool has always used (empty format is treated as CSV).
    assert classify_resource_format("", "https://x/download?id=123") == "CSV"
    assert classify_resource_format("7Z", "https://x/download?id=123") == "UNKNOWN"


def test_classify_zip_by_extension_even_if_declared_csv():
    assert classify_resource_format("CSV", "https://x/archivo.zip") == "ZIP"


def test_classify_plain_csv():
    assert classify_resource_format("CSV", "https://x/datos.csv") == "CSV"
    assert classify_resource_format("", "https://x/datos.csv") == "CSV"


def test_classify_legacy_xls_distinct_from_xlsx():
    assert classify_resource_format("", "https://x/reporte.xls") == "XLS"
    assert classify_resource_format("", "https://x/reporte.xlsx") == "XLSX"


def test_classify_json_and_geojson():
    assert classify_resource_format("", "https://x/datos.json") == "JSON"
    assert classify_resource_format("", "https://x/mapa.geojson") == "JSON"


# -- classify_from_content_type ----------------------------------------------


def test_classify_from_content_type_strips_charset_param():
    assert classify_from_content_type("text/csv; charset=utf-8") == "CSV"


def test_classify_from_content_type_maps_common_mimes():
    assert classify_from_content_type("application/json") == "JSON"
    assert classify_from_content_type("application/zip") == "ZIP"
    assert classify_from_content_type("application/gzip") == "TARGZ"
    assert (
        classify_from_content_type(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        == "XLSX"
    )
    assert classify_from_content_type("application/vnd.ms-excel") == "XLS"


def test_classify_from_content_type_unknown_or_missing():
    assert classify_from_content_type("application/octet-stream") == "UNKNOWN"
    assert classify_from_content_type(None) == "UNKNOWN"
    assert classify_from_content_type("") == "UNKNOWN"


# -- dispatch through the tool ------------------------------------------------


async def test_sri_tar_gz_declared_csv_is_routed_to_targz_parser(monkeypatch):
    async def fake_get_resource(resource_id, session=None):
        return {
            "url": "https://sri.example/sri_activos_2025.tar.gz",
            "format": "CSV",
            "name": "SRI activos",
        }

    calls = []

    async def fake_preview_targz(url, max_rows=20, session=None):
        calls.append(url)
        return {
            "headers": ["ruc", "total"],
            "rows": [["1234567890001", "100"]],
            "total_rows_in_preview": 1,
            "format": "tar_gz",
            "member_name": "sri_activos_2025.csv",
        }

    async def fail_preview_csv(*args, **kwargs):
        raise AssertionError("preview_csv should not be called for a .tar.gz resource")

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)
    monkeypatch.setattr(preview_resource_data_module, "preview_targz", fake_preview_targz)
    monkeypatch.setattr(preview_resource_data_module, "preview_csv", fail_preview_csv)

    tool = _make_tool()
    result = await tool(resource_id="abc123", format="json")
    payload = json.loads(result)
    assert payload["headers"] == ["ruc", "total"]
    assert payload["member_name"] == "sri_activos_2025.csv"
    assert calls == ["https://sri.example/sri_activos_2025.tar.gz"]


async def test_zip_declared_csv_is_routed_to_zip_parser(monkeypatch):
    async def fake_get_resource(resource_id, session=None):
        return {
            "url": "https://x/precios_cacao.zip",
            "format": "CSV",
            "name": "Precios cacao",
        }

    calls = []

    async def fake_preview_zip(url, max_rows=20, session=None):
        calls.append(url)
        return {
            "headers": ["producto", "precio"],
            "rows": [["cacao", "174.77"]],
            "total_rows_in_preview": 1,
            "format": "zip",
            "member_name": "precios_cacao.csv",
        }

    async def fail_preview_csv(*args, **kwargs):
        raise AssertionError("preview_csv should not be called for a .zip resource")

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)
    monkeypatch.setattr(preview_resource_data_module, "preview_zip", fake_preview_zip)
    monkeypatch.setattr(preview_resource_data_module, "preview_csv", fail_preview_csv)

    tool = _make_tool()
    result = await tool(resource_id="abc123", format="json")
    payload = json.loads(result)
    assert payload["headers"] == ["producto", "precio"]
    assert payload["member_name"] == "precios_cacao.csv"
    assert calls == ["https://x/precios_cacao.zip"]


async def test_mpceip_xlsx_declared_csv_is_routed_to_xlsx_parser(monkeypatch):
    async def fake_get_resource(resource_id, session=None):
        return {
            "url": "https://mpceip.example/precios_cacao.xlsx",
            "format": "CSV",
            "name": "Precios cacao",
        }

    calls = []

    async def fake_preview_xlsx(url, max_rows=20, session=None):
        calls.append(url)
        return {
            "headers": ["producto", "precio"],
            "rows": [["cacao", "174.77"]],
            "total_rows_in_preview": 1,
        }

    async def fail_preview_csv(*args, **kwargs):
        raise AssertionError("preview_csv should not be called for a .xlsx resource")

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)
    monkeypatch.setattr(preview_resource_data_module, "preview_xlsx", fake_preview_xlsx)
    monkeypatch.setattr(preview_resource_data_module, "preview_csv", fail_preview_csv)

    tool = _make_tool()
    result = await tool(resource_id="abc123", format="json")
    payload = json.loads(result)
    assert payload["headers"] == ["producto", "precio"]
    assert calls == ["https://mpceip.example/precios_cacao.xlsx"]


async def test_rar_message_does_not_overclaim_unrar_requirement(monkeypatch):
    async def fake_get_resource(resource_id, session=None):
        return {"url": "https://x/archivo.rar", "format": "RAR", "name": "Archivo"}

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)

    tool = _make_tool()
    result = await tool(resource_id="abc123", format="text")
    assert "unrar" not in result
    assert "download_resource('abc123', format=\"json\")" in result


async def test_xls_is_routed_to_xls_parser(monkeypatch):
    async def fake_get_resource(resource_id, session=None):
        return {"url": "https://x/reporte.xls", "format": "XLS", "name": "Reporte"}

    calls = []

    async def fake_preview_xls(url, max_rows=20, session=None):
        calls.append(url)
        return {
            "headers": ["producto", "precio"],
            "rows": [["cacao", "174.77"]],
            "total_rows_in_preview": 1,
            "format": "xls",
        }

    async def fail_preview_csv(*args, **kwargs):
        raise AssertionError("preview_csv should not be called for a .xls resource")

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)
    monkeypatch.setattr(preview_resource_data_module, "preview_xls", fake_preview_xls)
    monkeypatch.setattr(preview_resource_data_module, "preview_csv", fail_preview_csv)

    tool = _make_tool()
    result = await tool(resource_id="abc123", format="json")
    payload = json.loads(result)
    assert payload["headers"] == ["producto", "precio"]
    assert calls == ["https://x/reporte.xls"]


async def test_resource_not_found_returns_error(monkeypatch):
    async def fake_get_resource(resource_id, session=None):
        request = httpx.Request("GET", "https://x/resource_show")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)

    tool = _make_tool()
    result = await tool(resource_id="missing", format="json")
    payload = json.loads(result)
    assert payload["error"] == "not_found"


async def test_resource_without_url_returns_error(monkeypatch):
    async def fake_get_resource(resource_id, session=None):
        return {"format": "CSV", "name": "Sin URL"}

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)

    tool = _make_tool()
    result = await tool(resource_id="abc123", format="json")
    payload = json.loads(result)
    assert payload["error"] == "sin_url"


# -- extensionless resource: content-type sniffing fallback ------------------


async def test_extensionless_resource_is_routed_via_sniffed_content_type(monkeypatch):
    async def fake_get_resource(resource_id, session=None):
        return {
            "url": "https://x/download?id=123",
            "format": "PDF",
            "name": "Sin extension",
        }

    async def fake_sniff_content_type(url, session=None):
        return "text/csv; charset=utf-8"

    calls = []

    async def fake_preview_csv(url, max_rows=20, session=None):
        calls.append(url)
        return {
            "headers": ["a", "b"],
            "rows": [["1", "2"]],
            "total_rows_in_preview": 1,
            "format": "csv",
        }

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)
    monkeypatch.setattr(
        preview_resource_data_module, "sniff_content_type", fake_sniff_content_type
    )
    monkeypatch.setattr(preview_resource_data_module, "preview_csv", fake_preview_csv)

    tool = _make_tool()
    result = await tool(resource_id="abc123", format="json")
    payload = json.loads(result)
    assert payload["headers"] == ["a", "b"]
    assert payload["sniffed_content_type"] is True
    assert calls == ["https://x/download?id=123"]


async def test_extensionless_resource_falls_back_when_sniff_is_inconclusive(monkeypatch):
    async def fake_get_resource(resource_id, session=None):
        return {
            "url": "https://x/download?id=123",
            "format": "PDF",
            "name": "Sin extension",
        }

    async def fake_sniff_content_type(url, session=None):
        return "application/octet-stream"

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)
    monkeypatch.setattr(
        preview_resource_data_module, "sniff_content_type", fake_sniff_content_type
    )

    tool = _make_tool()
    result = await tool(resource_id="abc123", format="json")
    payload = json.loads(result)
    assert payload["error"] == "formato_no_soportado"
