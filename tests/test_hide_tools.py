"""ECUADOR_MCP_HIDE_TOOLS removes the named tools from a registered server."""

import asyncio
import logging

import pytest
from mcp.server.mcpserver import MCPServer

from helpers.logging import MAIN_LOGGER_NAME
from tools import register_tools


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("ECUADOR_MCP_HIDE_TOOLS", "ECUADOR_MCP_HIDE_GEOBLOCKED", "ECUADOR_MCP_GEO_PROXY"):
        monkeypatch.delenv(name, raising=False)


def _tool_names() -> set[str]:
    server = MCPServer("test")
    register_tools(server)
    return {tool.name for tool in asyncio.run(server.list_tools())}


def test_everything_is_registered_by_default():
    names = _tool_names()

    assert {"search_contratos", "get_resumen_compras", "search_sismos"} <= names


def test_named_tools_are_removed_and_the_rest_stay(monkeypatch):
    everything = _tool_names()
    monkeypatch.setenv("ECUADOR_MCP_HIDE_TOOLS", "search_contratos, get_resumen_compras")

    names = _tool_names()

    assert names == everything - {"search_contratos", "get_resumen_compras"}


def test_a_name_that_matches_no_tool_is_logged_and_the_others_still_apply(monkeypatch, caplog):
    monkeypatch.setenv("ECUADOR_MCP_HIDE_TOOLS", "search_contratos,search_contrato_typo")

    with caplog.at_level(logging.WARNING, logger=MAIN_LOGGER_NAME):
        names = _tool_names()

    assert "search_contratos" not in names
    assert "search_contrato_typo" in caplog.text


def test_a_tool_already_hidden_as_geoblocked_is_not_reported_unknown(monkeypatch, caplog):
    monkeypatch.setenv("ECUADOR_MCP_HIDE_GEOBLOCKED", "1")
    monkeypatch.setenv("ECUADOR_MCP_HIDE_TOOLS", "search_anda")

    with caplog.at_level(logging.WARNING, logger=MAIN_LOGGER_NAME):
        names = _tool_names()

    assert "search_anda" not in names
    assert "ECUADOR_MCP_HIDE_TOOLS names no registered tool" not in caplog.text
