import tomllib
from pathlib import Path

from helpers.user_agent import USER_AGENT
from helpers.version import get_version


def test_get_version_matches_pyproject():
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    assert get_version() == pyproject["project"]["version"]


def test_user_agent_reports_the_running_version():
    assert USER_AGENT == (
        f"ecuador-mcp/{get_version()} (https://github.com/DweskZ/EcuDataMCP)"
    )
