import json
import re

import httpx
import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import http_client, sercop_client
from helpers.cache import TtlCache
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


BASE = "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/search_ocds"


def _proc(n, amount="100.000000"):
    return {**_row("GAD QUITO", float(amount)), "ocid": f"ocds-x-{n:04d}", "id": n, "amount": amount}


def _page_resp(rows, total, pages):
    return {"total": total, "page": 1, "pages": pages, "data": rows}


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    http_client.reset_cooldowns()
    monkeypatch.setattr(sercop_client, "_summary_rows_cache", TtlCache(ttl_seconds=60))

    async def _no_sleep(_):
        return None

    monkeypatch.setattr(http_client.asyncio, "sleep", _no_sleep)
    yield
    http_client.reset_cooldowns()


def _serve(httpx_mock, universe, pages_by_call):
    """Answer every search_ocds call with the next scripted page, then repeat the last."""
    state = {"n": 0}
    total = len(universe)

    def respond(request):
        i = min(state["n"], len(pages_by_call) - 1)
        state["n"] += 1
        step = pages_by_call[i]
        if isinstance(step, int):
            return httpx.Response(step, headers={"Retry-After": "1"})
        return httpx.Response(
            200, json=_page_resp([universe[k] for k in step], total, -(-total // 2))
        )

    httpx_mock.add_callback(respond, url=re.compile(re.escape(BASE) + r".*"), is_reusable=True)
    return state


async def test_overlapping_pages_are_deduplicated_and_swept_until_complete(httpx_mock):
    # Unstable source: 6 processes, pages of 2 rows; the first sweep repeats 0
    # and misses 4 and 5, so the old code reported 6 rows read yet total != truth.
    universe = [_proc(i, str(100 * (i + 1))) for i in range(6)]
    _serve(httpx_mock, universe, [[0, 1], [0, 2], [0, 3], [4, 5], [1, 2], [3, 4]])

    result = await sercop_client.summarize_buyer("GAD QUITO", 2025)

    assert result["procesos_leidos"] == 6
    assert result["parcial"] is False
    assert result["monto_total"] == 2100.0
    assert result["procesos_con_monto"] == 6


async def test_two_runs_over_the_same_data_give_identical_output(httpx_mock):
    universe = [_proc(i, f"{10 + i}.10") for i in range(6)]
    # Same rows, different arrival order in each run.
    _serve(httpx_mock, universe, [[0, 1], [2, 3], [4, 5]])
    first = await sercop_client.summarize_buyer("GAD QUITO", 2025)
    httpx_mock.reset()
    _serve(httpx_mock, universe, [[5, 4], [3, 2], [1, 0]])
    second = await sercop_client.summarize_buyer("GAD QUITO", 2025)

    first.pop("solicitudes")
    second.pop("solicitudes")
    assert first == second
    assert first["parcial"] is False


async def test_a_429_is_retried_and_does_not_change_the_result(httpx_mock):
    universe = [_proc(i) for i in range(4)]
    _serve(httpx_mock, universe, [[0, 1], 429, [2, 3]])

    result = await sercop_client.summarize_buyer("GAD QUITO", 2025)

    assert result["procesos_leidos"] == 4
    assert result["parcial"] is False
    assert result["paginas_fallidas"] == []


async def test_a_hard_failure_is_reported_as_partial(httpx_mock):
    universe = [_proc(i) for i in range(4)]
    # Page 1 answers; every later call keeps returning 429 until the retries run out.
    _serve(httpx_mock, universe, [[0, 1]] + [429] * 40)

    result = await sercop_client.summarize_buyer("GAD QUITO", 2025)

    assert result["parcial"] is True
    assert result["procesos_leidos"] == 2
    assert result["total_en_fuente"] == 4
    assert result["paginas_fallidas"] == [2]


async def test_a_server_error_page_is_listed_and_never_claimed_complete(httpx_mock):
    universe = [_proc(i) for i in range(4)]
    _serve(httpx_mock, universe, [[0, 1]] + [500] * 40)

    result = await sercop_client.summarize_buyer("GAD QUITO", 2025, max_requests=6)

    assert result["parcial"] is True
    assert 2 in result["paginas_fallidas"]


async def test_page_cap_marks_the_summary_partial(httpx_mock):
    universe = [_proc(i) for i in range(8)]
    _serve(httpx_mock, universe, [[0, 1], [2, 3]])

    result = await sercop_client.summarize_buyer("GAD QUITO", 2025, max_pages=2)

    assert result["procesos_leidos"] == 4
    assert result["parcial"] is True


async def test_query_narrows_the_search_keyword(httpx_mock):
    universe = [_proc(i) for i in range(2)]
    _serve(httpx_mock, universe, [[0, 1]])

    await sercop_client.summarize_buyer("GAD QUITO", 2025, query="vialidad")

    params = httpx_mock.get_requests()[0].url.params
    assert params["search"] == "vialidad"
    assert params["buyer"] == "GAD QUITO"


@pytest.fixture
def fake_search(monkeypatch):
    async def summarize_buyer(buyer, year, query="", **kwargs):
        return {
            "comprador": buyer,
            "query": buyer,
            "year": year,
            "total_en_fuente": 2,
            "procesos_leidos": 2,
            "parcial": False,
            "paginas_fallidas": [],
            "solicitudes": 1,
            "monto_total": 10.0,
            "procesos_con_monto": 1,
            "compradores": summarize_rows([_row("GAD QUITO", 10.0), _row("GAD QUITO", None)]),
            "otros_compradores": 0,
        }

    monkeypatch.setattr(sercop_client, "summarize_buyer", summarize_buyer)


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


async def test_a_repeat_call_resumes_from_the_rows_already_collected(httpx_mock):
    universe = [_proc(i) for i in range(6)]
    _serve(httpx_mock, universe, [[0, 1], 500, 500, 500, 500, 500, 500, 500, 500])
    first = await sercop_client.summarize_buyer("GAD QUITO", 2025, max_requests=3)
    assert first["parcial"] is True

    httpx_mock.reset()
    _serve(httpx_mock, universe, [[0, 1], [2, 3], [4, 5]])
    second = await sercop_client.summarize_buyer("GAD QUITO", 2025)

    assert second["parcial"] is False
    assert second["procesos_leidos"] == 6
