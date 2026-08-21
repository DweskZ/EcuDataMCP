import argparse
import json
import logging
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import uvicorn
from mcp.server.fastmcp import FastMCP

from helpers.env_config import get_mcp_host, get_mcp_port, get_transport
from helpers.logging import MAIN_LOGGER_NAME, UVICORN_LOGGING_CONFIG, setup_logging
from prompts import register_prompts
from resources import register_resources
from tools import register_tools

setup_logging()

SERVER_START_TIME = datetime.now(UTC)
VERSION = "0.6.0"

logger = logging.getLogger(MAIN_LOGGER_NAME)

mcp = FastMCP(
    "Ecuador Datos Abiertos MCP",
    stateless_http=True,
)
register_tools(mcp)
register_prompts(mcp)
register_resources(mcp)


def with_health_endpoint(
    inner_app: Callable[[dict, Callable, Callable], Awaitable[None]],
) -> Callable[[dict, Callable, Callable], Awaitable[None]]:
    async def app(
        scope: dict, receive: Callable, send: Callable
    ) -> None:
        if scope["type"] == "http":
            path: str = scope.get("path", "")

            if path == "/health":
                body = json.dumps(
                    {
                        "status": "ok",
                        "uptime_since": SERVER_START_TIME.isoformat(),
                        "version": VERSION,
                    }
                ).encode("utf-8")
                headers = [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("utf-8")),
                ]
                await send(
                    {"type": "http.response.start", "status": 200, "headers": headers}
                )
                await send({"type": "http.response.body", "body": body})
                return

        await inner_app(scope, receive, send)

    return app


asgi_app = with_health_endpoint(mcp.streamable_http_app())


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ecuador open data MCP server")
    parser.add_argument(
        "--transport",
        choices=("http", "stdio"),
        default=None,
        help="Transport mode (default: MCP_TRANSPORT or http)",
    )
    parser.add_argument("--host", default=None, help="HTTP bind host")
    parser.add_argument("--port", type=int, default=None, help="HTTP bind port")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    transport = args.transport or get_transport()

    if transport == "stdio":
        logger.info("Starting Ecuador MCP server v%s (stdio)", VERSION)
        mcp.run(transport="stdio")
        return

    host = args.host or get_mcp_host()
    port = args.port or get_mcp_port()

    logger.info(
        "Starting Ecuador MCP server v%s on %s:%d",
        VERSION, host, port,
    )
    logger.info("CKAN API: www.datosabiertos.gob.ec")
    logger.info("GobEC API: gob.ec/api/v1")
    logger.info("MCP endpoint: http://%s:%d/mcp", host, port)
    logger.info("Health check: http://%s:%d/health", host, port)

    uvicorn.run(
        asgi_app,
        host=host,
        port=port,
        log_level="info",
        log_config=UVICORN_LOGGING_CONFIG,
    )


if __name__ == "__main__":
    main(sys.argv[1:])
