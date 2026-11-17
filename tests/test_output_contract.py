"""Every public tool publishes an outputSchema and fills the metadatos envelope.

docs/MCP_ARCHITECTURE.md § Fases 5 y 6: the return annotation
Annotated[CallToolResult, <family>] (helpers/result_types.py) makes the SDK
publish and validate a schema, and helpers/response_contract.py fills
metadatos for tools that do not build it themselves.
"""

import asyncio

import main
from helpers.mcp_server import compact_output_schema
from helpers.response_contract import (
    CONTRACT_VERSION,
    current_tool,
    ensure_response_metadata,
    with_response_metadata,
)


def test_every_public_tool_publishes_an_output_schema():
    tools = asyncio.run(main.mcp.list_tools())
    missing = [t.name for t in tools if not t.output_schema]
    assert missing == []
    for tool in tools:
        assert tool.output_schema["required"] == ["metadatos"], tool.name


def test_generic_envelope_reads_provenance_from_the_payload():
    result = ensure_response_metadata(
        {"source": "SGR", "url_fuente": "https://example.test", "total": 2},
        "search_sgr_sitreps",
    )
    meta = result["metadatos"]
    assert meta["contrato"] == CONTRACT_VERSION
    assert meta["fuente"] == "SGR"
    assert meta["url_fuente"] == "https://example.test"
    assert meta["fecha_corte"] is None
    assert meta["esquema"] == {
        "nombre": "ecudatamcp.search_sgr_sitreps",
        "campos_principales": ["source", "url_fuente", "total"],
    }


def test_generic_envelope_keeps_a_partial_block_and_a_full_one():
    partial = ensure_response_metadata({"filas": [], "metadatos": {"truncado": {"filas_omitidas": 3}}})
    assert partial["metadatos"]["truncado"] == {"filas_omitidas": 3}
    assert partial["metadatos"]["contrato"] == CONTRACT_VERSION

    full = with_response_metadata(
        {"total": 1},
        source="BCE",
        source_url=None,
        freshness="boletin_mensual",
        schema_name="bce.iem",
        schema_fields=["total"],
    )
    assert ensure_response_metadata(full, "otro") is full


def test_current_tool_is_reset_after_a_call():
    assert current_tool.get() is None


def test_compact_schema_inlines_refs_and_drops_noise():
    schema = {
        "$defs": {"M": {"title": "M", "type": "object", "properties": {"x": {"type": "string"}}}},
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "metadatos": {"$ref": "#/$defs/M"},
            "total": {"description": "n", "title": "Total"},
        },
        "required": ["metadatos"],
    }
    assert compact_output_schema(schema) == {
        "type": "object",
        "properties": {
            "metadatos": {
                "type": "object",
                "required": ["contrato"],
                "properties": {"contrato": {"const": CONTRACT_VERSION}},
            },
            "total": {},
        },
        "required": ["metadatos"],
    }


def test_a_silent_timeout_is_named_in_the_tool_error():
    import httpx
    import pytest
    from mcp.server.mcpserver.exceptions import ToolError

    from helpers.logging import log_tool

    @log_tool
    async def lenta():
        try:
            raise httpx.ReadTimeout("")
        except httpx.ReadTimeout as e:
            raise ToolError(f"Error al consultar la fuente: {e}") from e

    with pytest.raises(ToolError, match=r"fuente: ReadTimeout \(la fuente no respondió"):
        asyncio.run(lenta())
