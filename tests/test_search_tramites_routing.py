import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import gobec_client
from tools.get_tramite_estadisticas import register_get_tramite_estadisticas_tool
from tools.get_tramite_info import register_get_tramite_info_tool
from tools.search_tramites import (
    _guess_institution,
    _matches_query,
    register_search_tramites_tool,
)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("inscripción RUC persona natural", "8"),
        ("licencia de conducir", "48"),
        ("matrícula vehicular", "48"),
        ("renovar pasaporte", "6"),
        ("fondo de reserva IESS", "163"),
        ("pensión jubilar", "163"),
        ("cédula de identidad", "23"),
        ("ANT turno", "48"),
        # Substrings of longer words must not route to an institution.
        ("instrucciones generales", ""),
        ("información importante", ""),
        ("revisar solicitud", ""),
        ("antecedentes penales", ""),
        ("", ""),
        # Accents, plurals and spacing the old substring test handled.
        ("vehículos", "48"),
        ("pensiones jubilares", "163"),
        ("afiliación voluntaria", "163"),
        ("cesantía", "163"),
        ("legalización de documentos", "6"),
        ("visas", "6"),
        ("visado", "6"),
        ("RUCs", "8"),
        ("(RUC)", "8"),
        ("ruc/rimpe", "8"),
        ("registro  civil", "23"),
        # First keyword in the query wins, not dict order.
        ("pasaporte con cédula", "6"),
        ("SRI y matrícula", "8"),
        ("fondos de reserva", "163"),
    ],
)
def test_guess_institution(query, expected):
    assert _guess_institution(query) == expected


def test_matches_query_uses_word_starts():
    tramite = {"nombre": "Devolución del IVA", "descripcion": "<p>construcción</p>"}
    assert not _matches_query(tramite, ["ruc"])
    assert _matches_query(tramite, ["construccion"])
    assert _matches_query(tramite, ["devolucion", "iva"])


def _tool(register, name):
    mcp = MCPServer("test")
    register(mcp)
    return mcp._tool_manager.get_tool(name).fn


@pytest.mark.asyncio
async def test_query_without_institution_uses_guessed_id_and_stops_on_empty_page(
    monkeypatch,
):
    calls = []
    pages = {
        0: [{"tramite_id": "1", "nombre": "Inscripción RUC", "descripcion": ""}],
        1: [{"tramite_id": "2", "nombre": "Devolución IVA", "descripcion": "construcción"}],
    }

    async def fake_search(institution_id="", page=0, session=None):
        calls.append((institution_id, page))
        return pages.get(page, [])

    monkeypatch.setattr(gobec_client, "search_tramites", fake_search)
    fn = _tool(register_search_tramites_tool, "search_tramites")

    result = await fn(query="RUC", format="json")

    assert [c[0] for c in calls] == ["8", "8", "8"]
    assert [c[1] for c in calls] == [0, 1, 2]
    assert result.structured_content["total"] == 1
    assert result.structured_content["total_scanned"] == 2


@pytest.mark.asyncio
async def test_search_error_is_wrapped_in_tool_error(monkeypatch):
    async def boom(**_kwargs):
        raise RuntimeError("gob.ec cortó")

    monkeypatch.setattr(gobec_client, "search_tramites", boom)
    fn = _tool(register_search_tramites_tool, "search_tramites")

    with pytest.raises(ToolError, match="Error al buscar trámites: gob.ec cortó"):
        await fn(query="RUC", institution_id="8")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("register", "name"),
    [
        (register_get_tramite_info_tool, "get_tramite_info"),
        (register_get_tramite_estadisticas_tool, "get_tramite_estadisticas"),
    ],
)
async def test_non_numeric_tramite_id_is_rejected(register, name):
    fn = _tool(register, name)

    with pytest.raises(ToolError, match="ID de trámite inválido"):
        await fn(tramite_id="abc")
