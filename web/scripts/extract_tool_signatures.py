"""Extract (params, docstring summary, args_doc) from each tools/*.py via ast.

Mirrors the schema of web/data/tool_signatures.json: for each file, find the
function decorated with @mcp.tool() nested inside register_*_tool, pull its
parameter list (name/type/default) and split its docstring into a flat
`summary` (everything before "Args:") and `args_doc` (one line per
documented parameter).

This is the raw, English source that data/tools.json / en/data/tools.json
translate into the site's Spanish/English copy -- a manual step, not
automated. Re-run this after adding or changing a tool, diff the output
against the previous tool_signatures.json, and hand-port only what changed
into tools.json (both languages).

Usage: uv run python scripts/extract_tool_signatures.py
"""

import ast
import json
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
TOOLS_DIR = WEB.parent / "tools"
OUT_PATH = WEB / "data" / "tool_signatures.json"


def unparse_default(node):
    if node is None:
        return None
    return ast.unparse(node)


def unparse_type(node):
    if node is None:
        return None
    return ast.unparse(node).strip()


def is_mcp_tool(func: ast.AsyncFunctionDef) -> bool:
    for dec in func.decorator_list:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "tool":
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == "tool":
            return True
    return False


def find_tool_func(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and is_mcp_tool(node):
            return node
    return None


def extract_params(func: ast.AsyncFunctionDef):
    args = func.args
    defaults = [None] * (len(args.args) - len(args.defaults)) + list(args.defaults)
    params = []
    for arg, default in zip(args.args, defaults):
        params.append(
            {
                "name": arg.arg,
                "type": unparse_type(arg.annotation),
                "default": unparse_default(default),
            }
        )
    return params


def split_docstring(doc: str):
    if not doc:
        return "", {}
    doc = doc.strip("\n")
    lines = doc.split("\n")
    # dedent based on the minimum leading whitespace of non-empty lines after
    # the first (the first line has no leading indent in a triple-quoted str)
    body_lines = lines[1:] if len(lines) > 1 else []
    indents = [len(l) - len(l.lstrip()) for l in body_lines if l.strip()]
    dedent = min(indents) if indents else 0
    dedented = [lines[0]] + [l[dedent:] if len(l) >= dedent else l for l in body_lines]
    text = "\n".join(dedented).strip()

    m = re.search(r"\n\s*Args:\s*\n", text)
    if m:
        summary_part = text[: m.start()]
        args_part = text[m.end() :]
    else:
        summary_part = text
        args_part = ""

    # Collapse each paragraph's internal newlines/indentation into single
    # spaces, keep paragraph breaks (blank lines) as a single space too --
    # this matches the flat one-line "summary" style already in the file.
    summary = re.sub(r"\s+", " ", summary_part).strip()

    args_doc = {}
    if args_part:
        # Each top-level "name: description" entry, possibly wrapped onto
        # following more-indented lines.
        entry_re = re.compile(r"^(\s*)(\w+):\s?(.*)$")
        current_name = None
        current_lines = []
        base_indent = None
        for raw_line in args_part.split("\n"):
            if not raw_line.strip():
                continue
            indent = len(raw_line) - len(raw_line.lstrip())
            match = entry_re.match(raw_line)
            if match and (base_indent is None or indent <= base_indent):
                if current_name:
                    args_doc[current_name] = re.sub(
                        r"\s+", " ", " ".join(current_lines)
                    ).strip()
                base_indent = indent
                current_name = match.group(2)
                current_lines = [match.group(3)]
            elif current_name:
                current_lines.append(raw_line.strip())
        if current_name:
            args_doc[current_name] = re.sub(
                r"\s+", " ", " ".join(current_lines)
            ).strip()

    return summary, args_doc


def main():
    result = {}
    for py_file in sorted(TOOLS_DIR.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        func = find_tool_func(tree)
        if func is None:
            continue
        doc = ast.get_docstring(func) or ""
        summary, args_doc = split_docstring(doc)
        result[func.name] = {
            "file": py_file.name,
            "params": extract_params(func),
            "summary": summary,
            "args_doc": args_doc,
        }

    OUT_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Extracted {len(result)} tools -> {OUT_PATH}")


if __name__ == "__main__":
    main()
