# ============================================================
# Generate the source-to-tool catalog
# Author: Daniel Sanchez
# Purpose: Write docs/CATALOG.md from resources/catalog.py (sources and the
#          tools each one lists) and the @mcp.tool descriptions in tools/*.py,
#          and report drift between the two.
# Inputs:  resources/catalog.py, tools/*.py
# Outputs: docs/CATALOG.md (omitted with --check)
# ============================================================
# Usage: uv run python scripts/generate_catalog.py [--check]
#   --check  write nothing; exit 1 if the catalog lists a tool that does not
#            exist, a public tool is missing from every source, or
#            docs/CATALOG.md is out of date.

# %% 0. Setup
import ast
import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from resources.catalog import _all_fuentes

TOOLS_DIR = ROOT / "tools"
EXTRACTOR = ROOT / "web" / "scripts" / "extract_tool_signatures.py"
OUT_PATH = ROOT / "docs" / "CATALOG.md"

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("generate_catalog")


def load_extractor() -> ModuleType:
    # The site's extractor already parses tools/*.py; reuse it rather than
    # keep a second AST walker in step with it.
    spec = importlib.util.spec_from_file_location("extract_tool_signatures", EXTRACTOR)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {EXTRACTOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# %% 1. Read inputs
extractor = load_extractor()
descriptions: dict[str, str] = {}
for py_file in sorted(TOOLS_DIR.glob("*.py")):
    if py_file.name == "__init__.py":
        continue
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for func in extractor.find_tool_funcs(tree):
        descriptions[func.name] = extractor.decorator_description(func) or ""

fuentes = _all_fuentes()["fuentes"]

# %% 2. Check inputs
public_tools = set(descriptions) - extractor.MAINTENANCE_TOOLS
listed_tools = {tool for fuente in fuentes for tool in fuente["tools"]}
nonexistent = sorted(listed_tools - set(descriptions))
unlisted = sorted(public_tools - listed_tools)

# %% 3. Prepare catalog
lines = [
    "# Catálogo de fuentes y tools",
    "",
    "Generado por `scripts/generate_catalog.py` desde `resources/catalog.py` y las",
    "descripciones de `tools/*.py`; no editar a mano.",
    "",
    f"{len(fuentes)} fuentes, {len(public_tools)} tools públicas.",
    "",
]
for fuente in fuentes:
    lines.append(f"## {fuente['nombre']}")
    lines.append("")
    lines.append(f"- Id: `{fuente['id']}`")
    if fuente.get("base"):
        lines.append(f"- Base: {fuente['base']}")
    lines.append("")
    for tool in fuente["tools"]:
        lines.append(f"- `{tool}`: {descriptions.get(tool) or 'sin descripción'}")
    lines.append("")
catalog = "\n".join(lines).rstrip() + "\n"

# %% 4. Check results
problems = []
if nonexistent:
    problems.append(f"Listed in resources/catalog.py but no such tool: {nonexistent}")
if unlisted:
    problems.append(f"Public tools missing from every source: {unlisted}")

# %% 5. Write outputs
check_only = "--check" in sys.argv
if check_only:
    current = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else ""
    if current != catalog:
        problems.append(f"{OUT_PATH.relative_to(ROOT)} is out of date")
else:
    OUT_PATH.write_text(catalog, encoding="utf-8", newline="\n")
    logger.info("Wrote %s", OUT_PATH.relative_to(ROOT))

for problem in problems:
    logger.error(problem)
sys.exit(1 if problems and check_only else 0)
