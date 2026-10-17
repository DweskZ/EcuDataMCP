import logging

from helpers.logging import log_tool


async def test_log_tool_does_not_log_argument_values_at_info(caplog):
    @log_tool
    async def sample_tool(ruc: str = "") -> dict:
        return {}

    with caplog.at_level(logging.INFO, logger="ecuador_mcp"):
        await sample_tool(ruc="1790012345001")

    assert "sample_tool" in caplog.text
    assert "ruc" in caplog.text
    assert "1790012345001" not in caplog.text
