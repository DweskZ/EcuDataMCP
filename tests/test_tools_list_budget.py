"""tools/list stays small: short descriptions, full reference on demand.

docs/MCP_ARCHITECTURE.md phase 4: tools/list is sent into every
conversation's context before the user's first question. It measured
~199k characters (~50k tokens) with full docstrings as descriptions; the
full text now lives behind ecuador://herramientas/{nombre}, and each
parameter carries a one-sentence description from its docstring's Args.
These tests fail when a new tool (or a longer description) pushes it back
up, or a parameter goes undocumented.
"""

import asyncio
import inspect

from mcp.types import ListToolsResult

import main
from helpers.logging import TOOL_DOCS
from helpers.mcp_server import param_descriptions, strip_schema_titles

# Wire size (the JSON the server actually sends). ~95k after the phase 4 cut
# plus per-parameter descriptions; the margin allows new tools, not a
# return to long descriptions.
TOOLS_LIST_BUDGET_CHARS = 110_000
DESCRIPTION_MAX_CHARS = 350


def _tools():
    return asyncio.run(main.mcp.list_tools())


def test_tools_list_fits_the_context_budget():
    wire = ListToolsResult(tools=_tools()).model_dump_json(by_alias=True, exclude_none=True)
    assert len(wire) <= TOOLS_LIST_BUDGET_CHARS, f"tools/list is {len(wire):,} characters"


def test_every_parameter_has_a_description():
    # Glama's tool-definition score fell from 4.5 to 3.5 when parameters
    # were left undocumented in the schema ("schema description coverage 0%").
    missing = [
        f"{t.name}.{name}"
        for t in _tools()
        for name, prop in (t.input_schema.get("properties") or {}).items()
        if not prop.get("description")
    ]
    assert not missing, f"parameters without a description: {missing}"


def test_every_description_is_a_short_summary():
    long = {t.name: len(t.description) for t in _tools() if len(t.description) > DESCRIPTION_MAX_CHARS}
    assert not long, f"descriptions over {DESCRIPTION_MAX_CHARS} chars: {long}"


def test_every_tool_has_a_full_reference():
    missing = [t.name for t in _tools() if not TOOL_DOCS.get(t.name)]
    assert not missing, f"tools without a docstring reference: {missing}"


def test_reference_resource_serves_the_full_docstring():
    contents = asyncio.run(main.mcp.read_resource("ecuador://herramientas/search_archivos"))
    text = contents[0].content
    assert text == TOOL_DOCS["search_archivos"]
    assert len(text) > len(
        next(t for t in _tools() if t.name == "search_archivos").description
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


def test_param_descriptions_take_the_first_sentence_of_each_arg():
    doc = """Summary.

    Args:
        query: Free text (e.g. "salud"). Empty returns all.
        anio: Year, e.g. 2025.
            Continued on a second line.
        format: text | json
    """

    assert param_descriptions(inspect.cleandoc(doc)) == {
        "query": 'Free text (e.g. "salud").',
        "anio": "Year, e.g. 2025.",
        "format": "text | json",
    }
