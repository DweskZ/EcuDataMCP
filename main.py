import argparse
import json
import logging
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from helpers import usage
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
from helpers.geo_proxy import hide_geoblocked
from helpers.http_security import with_http_security
from helpers.logging import MAIN_LOGGER_NAME, UVICORN_LOGGING_CONFIG, setup_logging
from helpers.mcp_server import EcuadorMCPServer
from helpers.supercias_financials import ensure_financials_db_fresh, financials_status
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

Convenciones comunes a los tools (no se repiten en cada descripción):
- `format="json"` devuelve el resultado estructurado; `format="text"`
  (default) un resumen legible.
- `source` en los tools CKAN: `nacional` (datosabiertos.gob.ec, default),
  `cuenca` y `latacunga` (portales municipales) o `iadb` (BID; regional,
  no solo Ecuador).
- Los tools que "devuelven enlaces" no traen el contenido: descarga la URL
  directamente o usa `download_resource`/`read_pdf`/`preview_resource_data`
  (tope de 5 MB).
- La descripción de cada tool es un resumen; la referencia completa
  (alcance, parámetros, límites de la fuente) está en el recurso
  `ecuador://herramientas/{nombre}`.

Si un tool falla de forma rara (error inexplicable, resultados incompletos o
contradictorios con la fuente oficial, un id devuelto por un tool que otro no
acepta), pregunta a la persona si quiere reportarlo: los mantenedores lo
agradecen mucho. Si acepta, redacta el reporte con la plantilla
`.github/ISSUE_TEMPLATE/tool-problem.yml` (tool, llamada exacta, resultado,
resultado esperado, evidencia de la fuente) y entrégaselo para que lo
publique en https://github.com/DweskZ/EcuDataMCP/issues/new?template=tool-problem.yml
— no lo envíes sin su confirmación.
""".strip()

mcp = EcuadorMCPServer(
    "Ecuador Datos Abiertos MCP",
    title="EcuDataMCP",
    description=(
        "Ecuador's open government data for AI assistants: CKAN, SRI, BCE, "
        "INEC, Supercias, SERCOP and more."
    ),
    instructions=SERVER_INSTRUCTIONS,
    version=VERSION,
    website_url="https://github.com/DweskZ/EcuDataMCP",
)

# MCP_PROFILE (default "public") splits the public read-only tools from the
# two that write local operator artifacts (audit_bce_catalog,
# compare_bce_sources) -- see docs/MCP_ARCHITECTURE.md's public/maintenance
# profile split. "all" registers both, as every deployment did before 0.10.
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
                        "supercias_financials": financials_status(),
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

            # Per-tool call/error/latency counters for this process (see
            # helpers/usage.py); like /health, outside the /mcp auth.
            if path == "/usage":
                body = json.dumps(usage.snapshot()).encode("utf-8")
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
        mcp.streamable_http_app(
            stateless_http=True,
            # The SDK only trusts loopback Host headers unless told the bind
            # host; without it a non-loopback deploy answers 421.
            host=get_mcp_host(),
        ),
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

    if transport == "stdio":
        logger.info(
            "Starting Ecuador MCP server v%s (stdio, profile=%s)", VERSION, MCP_PROFILE
        )
        mcp.run(transport="stdio")
        return

    # Self-heals the Supercías financials DB (search_ranking/get_financials)
    # without the operator running the build by hand -- non-blocking, so a
    # missing/stale DB never delays startup. HTTP only: a stdio server lives
    # for one client session (and directory checks, `uvx` trials and Docker
    # `run -i` each start a fresh one), so starting a ~356 MB download there
    # on every launch wasted it on sessions that never ask for financials.
    # Over stdio the first financials query starts the build instead
    # (supercias_financials._check_db_fresh). Skipped when the financials
    # tools are hidden as geoblocked: the download could only fail there.
    if not hide_geoblocked():
        ensure_financials_db_fresh()

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

    # Imported here, not at module top: stdio launches never need it, and it
    # adds ~0.3 s to startup.
    import uvicorn

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
