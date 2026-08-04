import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Awaitable, Callable

import uvicorn
from mcp.server.fastmcp import FastMCP

from helpers.env_config import get_mcp_host, get_mcp_port
from helpers.logging import MAIN_LOGGER_NAME, UVICORN_LOGGING_CONFIG, setup_logging
from tools import register_tools

setup_logging()

SERVER_START_TIME = datetime.now(timezone.utc)
VERSION = "0.1.0"

logger = logging.getLogger(MAIN_LOGGER_NAME)

mcp = FastMCP(
    "Ecuador Datos Abiertos MCP",
    stateless_http=True,
)
register_tools(mcp)


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

if __name__ == "__main__":
    host = get_mcp_host()
    port = get_mcp_port()

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
