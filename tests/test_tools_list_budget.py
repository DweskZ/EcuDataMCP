"""tools/list stays small: short descriptions, full reference on demand.

docs/MCP_ARCHITECTURE.md phase 4: tools/list is sent into every
conversation's context before the user's first question. It measured
~199k characters (~50k tokens) with full docstrings as descriptions; the
full text now lives behind ecuador://herramientas/{nombre}. These tests
fail when a new tool (or a longer description) pushes it back up.
"""

import asyncio
import json

import main
from helpers.logging import TOOL_DOCS
from helpers.mcp_server import strip_schema_titles

# Measured at 66k after the phase 4 cut; the margin allows new tools, not
# a return to long descriptions.
TOOLS_LIST_BUDGET_CHARS = 80_000
DESCRIPTION_MAX_CHARS = 350


def _tools():
    return asyncio.run(main.mcp.list_tools())


def test_tools_list_fits_the_context_budget():
    size = sum(
        len(json.dumps(t.model_dump(mode="json", by_alias=True, exclude_none=True)))
        for t in _tools()
    )
    assert size <= TOOLS_LIST_BUDGET_CHARS, f"tools/list is {size:,} characters"


def test_every_description_is_a_short_summary():
    long = {t.name: len(t.description) for t in _tools() if len(t.description) > DESCRIPTION_MAX_CHARS}
    assert not long, f"descriptions over {DESCRIPTION_MAX_CHARS} chars: {long}"


def test_every_tool_has_a_full_reference():
    missing = [t.name for t in _tools() if not TOOL_DOCS.get(t.name)]
    assert not missing, f"tools without a docstring reference: {missing}"


def test_reference_resource_serves_the_full_docstring():
    contents = asyncio.run(main.mcp.read_resource("ecuador://herramientas/search_mef_fiscal"))
    text = contents[0].content
    assert text == TOOL_DOCS["search_mef_fiscal"]
    assert len(text) > len(
        next(t for t in _tools() if t.name == "search_mef_fiscal").description
    )


def test_strip_schema_titles_keeps_a_property_named_title():
    schema = {
        "title": "fArguments",
        "type": "object",
        "properties": {
            "title": {"title": "Title", "type": "string"},
            "query": {"title": "Query", "type": "string"},
        },
    }
    assert strip_schema_titles(schema) == {
        "type": "object",
        "properties": {"title": {"type": "string"}, "query": {"type": "string"}},
    }
