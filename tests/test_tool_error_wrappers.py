"""Tools that only caught ValueError let httpx errors reach the client as raw
English text; each now wraps any failure in a Spanish ToolError."""

import httpx
import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import (
    aviacion_client,
    cenace_client,
    iess_client,
    igepn_informes_client,
    sri_ruc_client,
    sut_powerbi_client,
)
from tools.get_cenace_tablero import register_get_cenace_tablero_tool
from tools.get_iess_archivos import register_get_iess_archivos_tool
from tools.get_informe_igepn import register_get_informe_igepn_tool
from tools.get_sut_indicador_schema import register_get_sut_indicador_schema_tool
from tools.list_aip_aerodromos import register_list_aip_aerodromos_tool
from tools.search_sri_ruc import register_search_sri_ruc_tool


def _tool(register, name):
    mcp = MCPServer("test")
    register(mcp)
    return mcp._tool_manager.get_tool(name).fn


async def _connect_error(*args, **kwargs):
    raise httpx.ConnectError("All connection attempts failed")


@pytest.mark.parametrize(
    ("register", "name", "module", "attr", "kwargs", "prefix"),
    [
        (
            register_search_sri_ruc_tool,
            "search_sri_ruc",
            sri_ruc_client,
            "search_by_razon_social",
            {"razon_social": "BANCO"},
            "Error al consultar el RUC en el SRI",
        ),
        (
            register_get_cenace_tablero_tool,
            "get_cenace_tablero",
            cenace_client,
            "get_tablero",
            {"tablero": "produccion"},
            "Error al consultar el tablero de CENACE",
        ),
        (
            register_get_sut_indicador_schema_tool,
            "get_sut_indicador_schema",
            sut_powerbi_client,
            "get_indicador_schema",
            {"indicador": "x"},
            "Error al consultar el esquema del indicador en Power BI",
        ),
        (
            register_list_aip_aerodromos_tool,
            "list_aip_aerodromos",
            aviacion_client,
            "list_aip_aerodromos",
            {},
            "Error al consultar el AIP de la DGAC",
        ),
        (
            register_get_iess_archivos_tool,
            "get_iess_archivos",
            iess_client,
            "list_boletines",
            {"coleccion": "boletines"},
            "Error al consultar los archivos del IESS",
        ),
        (
            register_get_informe_igepn_tool,
            "get_informe_igepn",
            igepn_informes_client,
            "download_informe",
            {"nombre": "Informe Diario 2022-071"},
            "Error al descargar el informe",
        ),
    ],
)
async def test_transport_errors_become_spanish_tool_errors(
    monkeypatch, register, name, module, attr, kwargs, prefix
):
    monkeypatch.setattr(module, attr, _connect_error)
    tool = _tool(register, name)

    with pytest.raises(ToolError) as excinfo:
        await tool(**kwargs)

    assert str(excinfo.value).startswith(prefix)
    assert "All connection attempts failed" in str(excinfo.value)


async def test_iess_argument_errors_keep_their_own_message():
    tool = _tool(register_get_iess_archivos_tool, "get_iess_archivos")

    with pytest.raises(ToolError, match="requiere anio"):
        await tool(coleccion="informes_auditoria")
