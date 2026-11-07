import json

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import sercop_client
from helpers.sercop_client import summarize_rows
from tools.get_resumen_compras import register_get_resumen_compras_tool


def _row(buyer, amount, tipo="Subasta Inversa Electrónica", month=3, supplier=None, budget=None):
    return {
        "ocid": f"ocds-{buyer}-{amount}",
        "buyer": buyer,
        "amount": None if amount is None else f"{amount:.6f}",
        "budget": None if budget is None else str(budget),
        "internal_type": tipo,
        "month": month,
        "date": f"2025-{month:02d}-15T10:00:00-05:00",
        "suppliers": supplier,
    }


def test_summarize_rows_groups_by_buyer_and_totals():
    rows = [
        _row("GAD QUITO", 100.0, supplier="ACME", budget=120),
        _row("GAD QUITO", 50.5, tipo="Menor Cuantía", month=5, supplier="ACME"),
        _row("GAD QUITO", None, month=5),
        _row("EMAAP QUITO", 1000.0, supplier="AGUAS SA"),
    ]

    result = summarize_rows(rows)

    assert [c["comprador"] for c in result] == ["EMAAP QUITO", "GAD QUITO"]
    quito = result[1]
    assert quito["procesos"] == 3
    assert quito["procesos_con_monto"] == 2
    assert quito["monto_total"] == 150.5
    assert quito["presupuesto_total"] == 120.0
    assert quito["por_tipo"][0] == {"tipo": "Subasta Inversa Electrónica", "procesos": 2, "monto": 100.0}
    assert quito["por_mes"] == [
        {"mes": 3, "procesos": 1, "monto": 100.0},
        {"mes": 5, "procesos": 2, "monto": 50.5},
    ]
    assert quito["proveedores"] == [{"proveedor": "ACME", "procesos": 2, "monto": 150.5}]
    assert (quito["primera_fecha"], quito["ultima_fecha"]) == ("2025-03-15", "2025-05-15")


def test_summarize_rows_reads_the_month_from_the_date_when_missing():
    row = _row("X", 1.0)
    row["month"] = None
    row["date"] = "2025-11-02T00:00:00-05:00"

    assert summarize_rows([row])[0]["por_mes"] == [{"mes": 11, "procesos": 1, "monto": 1.0}]


@pytest.fixture
def fake_search(monkeypatch):
    calls = []

    async def search_contracts(search, year, page=1, buyer="", **kwargs):
        calls.append((search, year, page, buyer))
        if page == 3:
            raise RuntimeError("timeout")
        data = [_row("GAD QUITO", 10.0 * page), _row("GAD QUITO", None)]
        return {"total": 80, "page": page, "pages": 40, "data": data}

    monkeypatch.setattr(sercop_client, "search_contracts", search_contracts)
    return calls


async def test_summary_is_capped_and_reports_failed_pages(fake_search):
    result = await sercop_client.summarize_buyer("GAD QUITO", 2025)

    pages_read = {page for _, _, page, _ in fake_search}
    assert pages_read == set(range(1, sercop_client.SUMMARY_MAX_PAGES + 1))
    assert result["paginas_fallidas"] == [3]
    assert result["parcial"] is True
    assert result["procesos_leidos"] == 2 * (sercop_client.SUMMARY_MAX_PAGES - 1)
    assert fake_search[0] == ("GAD QUITO", 2025, 1, "GAD QUITO")


async def test_query_narrows_the_search_keyword(fake_search):
    await sercop_client.summarize_buyer("GAD QUITO", 2025, query="vialidad", max_pages=1)

    assert fake_search == [("vialidad", 2025, 1, "GAD QUITO")]


async def test_tool_returns_the_summary_as_json(fake_search):
    server = MCPServer("test")
    register_get_resumen_compras_tool(server)

    result = await server.call_tool(
        "get_resumen_compras", {"comprador": "GAD QUITO", "year": 2025, "format": "json"}
    )

    payload = json.loads(result.content[0].text)
    assert payload["compradores"][0]["comprador"] == "GAD QUITO"
    assert payload["metadatos"]["fuente"].startswith("SERCOP")


async def test_tool_rejects_short_keywords():
    server = MCPServer("test")
    register_get_resumen_compras_tool(server)

    with pytest.raises(ToolError, match="comprador"):
        await server.call_tool("get_resumen_compras", {"comprador": "ab"})
    with pytest.raises(ToolError, match="2015"):
        await server.call_tool("get_resumen_compras", {"comprador": "IESS", "year": 2010})
