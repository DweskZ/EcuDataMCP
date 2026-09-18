"""User-Agent sent to every official source.

The version part used to be a third hardcoded literal (it sat at 0.5.0 while
the real version moved to 0.8.9), so every source saw a wrong client version.
helpers/version.py is the single source of truth -- see its docstring.
"""

from helpers.version import get_version

USER_AGENT = f"ecuador-mcp/{get_version()} (https://github.com/DweskZ/EcuDataMCP)"
