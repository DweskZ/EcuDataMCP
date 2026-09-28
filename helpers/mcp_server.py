"""MCPServer whose tools/list is small but still documents every parameter.

tools/list is sent into every conversation's context, so it's kept compact
(docs/MCP_ARCHITECTURE.md, phase 4): tools advertise short descriptions and
the full docstring is served on demand by ecuador://herramientas/{nombre}.
When listing tools this subclass also:

- drops the "title" pydantic gives every generated schema (each argument
  model, e.g. "search_mef_fiscalArguments", each property, e.g. "Query",
  and each output model) -- the property name is already the key;
- gives each parameter a one-sentence "description" taken from its entry in
  the docstring's Google-style Args section. Without it the schema had no
  parameter documentation at all once descriptions were shortened, and
  Glama's tool-definition score dropped from 4.5 to 3.5 on exactly that
  ("schema description coverage 0%").

Argument validation still uses the SDK's full models.
"""

from __future__ import annotations

import re
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import Tool as MCPTool

from helpers.logging import TOOL_DOCS

# Parameters shared by many tools get one short wording; the server
# instructions explain them in full once.
SHARED_PARAM_DESCRIPTIONS = {
    "format": "text summary (default) or json structured result.",
}
# `source` on the CKAN tools (see the server instructions).
CKAN_SOURCE_DESCRIPTION = "CKAN portal; nacional (default), cuenca, latacunga or iadb."
_MAX_PARAM_DESCRIPTION = 160

_ARGS_HEADER_RE = re.compile(r"^Args:\s*$", re.MULTILINE)
_PARAM_LINE_RE = re.compile(r"^ {4}(?P<name>\w+)(?: \([^)]*\))?:\s*(?P<text>.*)$")
# End of the first sentence, not fooled by "e.g." / "i.e." inside it.
_SENTENCE_END_RE = re.compile(r"(?<!e\.g)(?<!i\.e)\.(?=\s|$)")


def strip_schema_titles(schema: Any) -> Any:
    """Return a copy of a JSON schema without "title" annotations.

    Keys inside "properties"/"$defs" are names, not schema keywords, so a
    property that is itself called "title" survives.
    """
    if isinstance(schema, list):
        return [strip_schema_titles(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    stripped = {}
    for key, value in schema.items():
        if key == "title":
            continue
        if key in ("properties", "$defs", "definitions") and isinstance(value, dict):
            stripped[key] = {name: strip_schema_titles(sub) for name, sub in value.items()}
        else:
            stripped[key] = strip_schema_titles(value)
    return stripped


def _first_sentence(text: str) -> str:
    text = " ".join(text.split())
    match = _SENTENCE_END_RE.search(text)
    sentence = text[: match.end()] if match else text
    if len(sentence) > _MAX_PARAM_DESCRIPTION:
        sentence = sentence[: _MAX_PARAM_DESCRIPTION - 1].rsplit(" ", 1)[0] + "…"
    return sentence


def param_descriptions(doc: str) -> dict[str, str]:
    """First sentence of each parameter in a cleandoc'd docstring's Args."""
    header = _ARGS_HEADER_RE.search(doc)
    if header is None:
        return {}
    found: dict[str, list[str]] = {}
    current = None
    for line in doc[header.end() :].splitlines()[1:]:
        if line.strip() and not line.startswith(" "):
            break  # next top-level section
        param = _PARAM_LINE_RE.match(line)
        if param:
            current = param["name"]
            found[current] = [param["text"]]
        elif current and line.startswith(" " * 8):
            found[current].append(line.strip())
    return {name: _first_sentence(" ".join(parts)) for name, parts in found.items() if "".join(parts)}


def document_parameters(schema: dict[str, Any], doc: str) -> dict[str, Any]:
    """Add docstring-derived descriptions to properties that lack one."""
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return schema
    docs = param_descriptions(doc)
    for name, prop in properties.items():
        if not isinstance(prop, dict) or "description" in prop:
            continue
        if name == "source" and "iadb" in prop.get("enum", []):
            text = CKAN_SOURCE_DESCRIPTION
        else:
            text = SHARED_PARAM_DESCRIPTIONS.get(name) or docs.get(name)
        if text:
            prop["description"] = text
    return schema


class EcuadorMCPServer(MCPServer):
    async def list_tools(self) -> list[MCPTool]:
        tools = await super().list_tools()
        for tool in tools:
            schema = strip_schema_titles(tool.input_schema)
            tool.input_schema = document_parameters(schema, TOOL_DOCS.get(tool.name, ""))
            if tool.output_schema is not None:
                tool.output_schema = strip_schema_titles(tool.output_schema)
        return tools
