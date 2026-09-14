import argparse
import json
import logging
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import uvicorn
from mcp.server.mcpserver import MCPServer

from helpers.env_config import (
    get_mcp_auth_token,
    get_mcp_host,
    get_mcp_max_concurrent_requests,
    get_mcp_port,
    get_mcp_profile,
    get_mcp_rate_limit_requests,
    get_mcp_rate_limit_window_seconds,
    get_mcp_require_auth,
    get_mcp_ssl_certfile,
    get_mcp_ssl_keyfile,
    get_transport,
)
from helpers.http_security import with_http_security
from helpers.logging import MAIN_LOGGER_NAME, UVICORN_LOGGING_CONFIG, setup_logging
from helpers.supercias_financials import ensure_financials_db_fresh
from helpers.version import get_version
from prompts import register_prompts
from resources import register_resources
from tools import register_maintenance_tools, register_tools

setup_logging()

SERVER_START_TIME = datetime.now(UTC)
VERSION = get_version()

logger = logging.getLogger(MAIN_LOGGER_NAME)

SERVER_INSTRUCTIONS = """
Servidor MCP de datos abiertos del gobierno ecuatoriano (CKAN nacional y
municipal, gob.ec, SRI, BCE, Supercías, IESS/SENESCYT, SIPA, IG-EPN, SERCOP,
SGR, y más — ver el recurso `ecuador://fuentes` para el catálogo completo y
actualizado de fuentes y sus tools).

Entrada recomendada cuando no se sabe qué tool usar: `search_ecuador`, o los
prompts `explorar_datos` / `consultar_tramite` / `investigar_contrato` /
`buscar_regulacion` / `buscar_inec` / `monitorear_riesgos`.

Casi todos los tools aceptan `format="json"` además de `format="text"`
(default).
""".strip()

mcp = MCPServer("Ecuador Datos Abiertos MCP", instructions=SERVER_INSTRUCTIONS)

# MCP_PROFILE (default "all") splits the public read-only tools from the two
# that write local operator artifacts (audit_bce_catalog, compare_bce_sources)
# -- see docs/MCP_ARCHITECTURE.md's public/maintenance profile split. "all"
# reproduces the single-instance behavior this server had before profiles
# existed, so an unset MCP_PROFILE changes nothing for an existing deployment.
MCP_PROFILE = get_mcp_profile()
if MCP_PROFILE in ("public", "all"):
    register_tools(mcp)
if MCP_PROFILE in ("maintenance", "all"):
    register_maintenance_tools(mcp)
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


asgi_app = with_health_endpoint(
    with_http_security(
        mcp.streamable_http_app(stateless_http=True),
        auth_token=get_mcp_auth_token(),
        max_concurrent_requests=get_mcp_max_concurrent_requests(),
        rate_limit_requests=get_mcp_rate_limit_requests(),
        rate_limit_window_seconds=get_mcp_rate_limit_window_seconds(),
    )
)


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

    # Self-heals the Supercías financials DB (search_ranking/get_financials)
    # instead of requiring the operator to run
    # scripts/build_supercias_financials_db.py by hand before first use --
    # non-blocking, so a missing/stale DB never delays server startup.
    ensure_financials_db_fresh()

    if transport == "stdio":
        logger.info(
            "Starting Ecuador MCP server v%s (stdio, profile=%s)", VERSION, MCP_PROFILE
        )
        mcp.run(transport="stdio")
        return

    host = args.host if args.host is not None else get_mcp_host()
    port = args.port if args.port is not None else get_mcp_port()
    auth_token = get_mcp_auth_token()
    certfile = get_mcp_ssl_certfile()
    keyfile = get_mcp_ssl_keyfile()
    loopback = host in {"127.0.0.1", "localhost", "::1"}
    if get_mcp_require_auth() and not auth_token:
        raise RuntimeError("MCP_REQUIRE_AUTH está activo pero MCP_AUTH_TOKEN está vacío")
    if not loopback and not auth_token:
        logger.warning(
            "MCP HTTP endpoint is externally bound without MCP_AUTH_TOKEN; "
            "set a token before exposing it beyond a trusted network"
        )
    if bool(certfile) != bool(keyfile):
        raise RuntimeError(
            "MCP_SSL_CERTFILE y MCP_SSL_KEYFILE deben configurarse juntos"
        )

    logger.info(
        "Starting Ecuador MCP server v%s on %s:%d (profile=%s)",
        VERSION, host, port, MCP_PROFILE,
    )
    if auth_token:
        logger.info("MCP HTTP authentication: Bearer token enabled")
    logger.info(
        "MCP HTTP concurrency limit: %d",
        get_mcp_max_concurrent_requests(),
    )
    logger.info(
        "MCP per-client rate limit: %d requests / %.0f seconds",
        get_mcp_rate_limit_requests(),
        get_mcp_rate_limit_window_seconds(),
    )
    logger.info("CKAN API: www.datosabiertos.gob.ec")
    logger.info("GobEC API: gob.ec/api/v1")
    scheme = "https" if certfile else "http"
    logger.info("MCP endpoint: %s://%s:%d/mcp", scheme, host, port)
    logger.info("Health check: %s://%s:%d/health", scheme, host, port)

    uvicorn.run(
        asgi_app,
        host=host,
        port=port,
        log_level="info",
        log_config=UVICORN_LOGGING_CONFIG,
        ssl_certfile=certfile,
        ssl_keyfile=keyfile,
    )


if __name__ == "__main__":
    main(sys.argv[1:])
