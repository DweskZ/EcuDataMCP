"""End-to-end smoke test against a running MCP HTTP server."""

from __future__ import annotations

import asyncio
import json
import sys

import httpx

# Tool output routinely contains non-ASCII text (accents, →, ⚠...) from
# real government sources; on Windows the console defaults to cp1252,
# which raises on those and would abort the whole run mid-loop, hiding
# every check after the one that happened to fail. utf-8 with `replace`
# keeps a crash from ever being about console encoding.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MCP_URL = "http://127.0.0.1:8000/mcp"
HEALTH_URL = "http://127.0.0.1:8000/health"


def parse_sse(text: str) -> dict | None:
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except json.JSONDecodeError:
                continue
    return None


async def mcp_post(client: httpx.AsyncClient, payload: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    session_id = getattr(client, "_session_id", "")
    if session_id:
        headers["mcp-session-id"] = session_id
    resp = await client.post(MCP_URL, json=payload, headers=headers, timeout=90.0)
    resp.raise_for_status()
    if "text/event-stream" in resp.headers.get("content-type", ""):
        data = parse_sse(resp.text)
        if not data:
            raise ValueError(resp.text[:300])
        return data
    return resp.json()


async def initialize(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        MCP_URL,
        json={
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "smoke-e2e", "version": "0.4.1"},
            },
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        timeout=20.0,
    )
    resp.raise_for_status()
    client._session_id = resp.headers.get("mcp-session-id", "")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if client._session_id:
        headers["mcp-session-id"] = client._session_id
    await client.post(
        MCP_URL,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=headers,
        timeout=10.0,
    )


async def call_tool(client: httpx.AsyncClient, name: str, args: dict) -> str:
    data = await mcp_post(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        },
    )
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    content = data.get("result", {}).get("content", [])
    return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")


def ok(label: str, text: str) -> None:
    if "Traceback" in text[:200]:
        raise AssertionError(f"{label}: traceback in response")
    stripped = text.strip()
    if stripped.startswith(("Error:", "ERROR:")):
        print(f"  WARN {label}: {text[:160]}")
        return
    if stripped.startswith("{"):
        # format="json" tools return an {"error": ...} payload on failure
        # instead of an "Error:"-prefixed string -- catch those too, or a
        # tool that silently starts erroring reads as a passing smoke test.
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and "error" in payload:
            print(f"  WARN {label}: {text[:160]}")
            return
    print(f"  OK   {label} ({len(text)} chars)")


async def main() -> int:
    async with httpx.AsyncClient() as client:
        print("== health ==")
        h = await client.get(HEALTH_URL, timeout=10.0)
        h.raise_for_status()
        print(" ", h.json())

        print("== initialize ==")
        client._session_id = ""
        await initialize(client)
        print("  session", getattr(client, "_session_id", "")[:16], "...")

        checks = [
            ("list_capabilities", {}, ["CKAN", "SERCOP"]),
            ("lookup_ubicacion", {"query": "Pichincha"}, ["17", "Pichincha"]),
            ("lookup_ubicacion", {"query": "Cuenca", "nivel": "canton"}, ["0101", "Cuenca"]),
            (
                "lookup_ubicacion",
                {"query": "Tumbaco", "nivel": "parroquia", "format": "json"},
                ["170150", "Tumbaco", "parroquias"],
            ),
            ("list_recent_datasets", {"page_size": 3, "format": "json"}, ['"results"']),
            ("list_categories", {"format": "json"}, ['"categories"', "salud"]),
            ("list_instituciones", {"query": "SRI", "format": "json"}, ['"institucion_id"', "SRI"]),
            ("search_datasets", {"query": "salud", "page_size": 2}, ["dataset"]),
            ("search_tramites", {"query": "pasaporte", "format": "json"}, ["tramite_id", "pasaporte"]),
            ("search_regulaciones", {"query": "datos", "format": "json"}, ["regulacion_id"]),
            ("get_regulacion_info", {"regulacion_id": "5051", "format": "json"}, ["regulacion"]),
            ("search_eventos_riesgo", {"provincia": "Pichincha", "limit": 3}, ["SGR", "Evento", "riesgo"]),
            ("list_sat_tsunami", {"limit": 3, "format": "json"}, ["stations"]),
            (
                "search_contratos",
                {"query": "agua", "year": 2024, "format": "json"},
                ["ocid", "results", "rate_limited", "error"],
            ),
            (
                "search_ecuador",
                {"query": "salud", "limit": 2, "format": "json"},
                ["datasets", "tramites"],
            ),
            # -- everything below has no fixed ID to assert against (a query
            # legitimately returning zero results is not a failure -- only
            # errors/tracebacks are), so `must` stays empty unless the tool
            # returns a fixed, non-query-dependent shape.
            ("search_organizations", {"query": "sri", "page_size": 3}, []),
            ("search_sri_datasets", {"query": "recaudacion", "limit": 3}, []),
            (
                "search_sri_estadisticas_recaudacion",
                {"query": "recaudacion", "limit": 3},
                [],
            ),
            ("search_sri_ruc", {"razon_social": "BANCO", "max_resultados": 3}, []),
            ("search_indicadores_bce", {"query": "inflacion", "limit": 5}, []),
            ("search_bce_iem", {"query": "inflacion", "limit": 5}, []),
            ("search_bce_remesas", {"query": ""}, []),
            ("audit_bce_catalog", {}, ["grupos", "series"]),
            ("list_bce_indicadores_diarios", {}, ["Riesgo", "serie"]),
            (
                "get_cenace_tablero",
                {"tablero": "produccion_tiempo_real"},
                ["PRODUCCIÓN", "HIDRÁULICA"],
            ),
            ("search_sismos", {"limit": 3}, []),
            ("search_informes_igepn", {"anio": 2022, "grupo": "sismico", "limit": 3}, []),
            ("search_companias", {"query": "BANCO", "limit": 3}, []),
            ("search_auditores", {"query": "AUDIT", "limit": 3}, []),
            ("search_ranking", {"limit": 3}, []),
            ("list_sipa_modulos", {}, ["SIPA", "económico"]),
            ("list_superbancos_secciones", {}, ["seccion"]),
            ("list_sut_indicadores", {}, ["indicador"]),
            ("list_contraloria_informes", {}, ["Contraloría"]),
            ("search_anda", {"query": "empleo", "limit": 3}, []),
            ("search_biinec_extras", {"query": "ambiental"}, []),
            ("search_censo_recursos", {"query": "poblacion", "limit": 3}, []),
            ("search_inec_estadisticas", {"query": "empleo", "limit": 3}, []),
            ("search_inec_publicaciones", {"query": "empleo", "limit": 3}, []),
        ]

        print("== tools ==")
        failed = 0
        for name, args, must in checks:
            try:
                text = await call_tool(client, name, args)
                if must and not any(m.lower() in text.lower() for m in must):
                    raise AssertionError(f"none of {must} found: {text[:240]}")
                ok(name, text)
            except Exception as exc:
                failed += 1
                print(f"  FAIL {name}: {exc}")

        # -- dynamic list -> get chains -----------------------------------
        # A handful of the trickiest integrations (undocumented internal
        # APIs/widgets, session-bound flows) are worth exercising end to
        # end -- list the catalog, then actually fetch one real item found
        # in it -- rather than just confirming the list call responds.
        # IDs are discovered live, not hardcoded, so this doesn't rot when
        # the underlying site's IDs change.
        print("== chains ==")
        chains = 0
        for label, coro in [
            ("sut: list -> schema", chain_sut(client)),
            ("superbancos: list -> archivos", chain_superbancos(client)),
            ("igepn: search -> informe", chain_igepn(client)),
        ]:
            chains += 1
            try:
                await coro
                print(f"  OK   {label}")
            except Exception as exc:
                failed += 1
                print(f"  FAIL {label}: {exc}")

        print("== done ==")
        total = len(checks) + chains
        print(f"failed={failed}/{total}")
        return 1 if failed else 0


async def chain_sut(client: httpx.AsyncClient) -> None:
    listing = json.loads(await call_tool(client, "list_sut_indicadores", {"format": "json"}))
    indicador = listing[0]["indicador"]
    schema = await call_tool(
        client, "get_sut_indicador_schema", {"indicador": indicador, "format": "json"}
    )
    if "Traceback" in schema[:200] or schema.strip().startswith(("Error:", "ERROR:")):
        raise AssertionError(schema[:200])


async def chain_superbancos(client: httpx.AsyncClient) -> None:
    listing = json.loads(
        await call_tool(client, "list_superbancos_secciones", {"format": "json"})
    )
    seccion = listing[0]["seccion"]
    archivos = await call_tool(
        client, "get_superbancos_seccion_archivos", {"seccion": seccion, "format": "json"}
    )
    if "Traceback" in archivos[:200] or archivos.strip().startswith(("Error:", "ERROR:")):
        raise AssertionError(archivos[:200])


async def chain_igepn(client: httpx.AsyncClient) -> None:
    resultado = json.loads(
        await call_tool(
            client,
            "search_informes_igepn",
            {"anio": 2022, "grupo": "volcanico", "limit": 1, "format": "json"},
        )
    )
    informes = resultado.get("informes") or []
    if not informes:
        raise AssertionError("search_informes_igepn returned no reports for 2022/volcanico")
    informe = informes[0]
    texto = await call_tool(
        client,
        "get_informe_igepn",
        {
            "nombre": informe["nombre"],
            "volcan": informe.get("volcan") or "",
            "grupo": "volcanico",
            "anio": 2022,
            "pages": "1",
            "format": "json",
        },
    )
    if "Traceback" in texto[:200] or texto.strip().startswith(("Error:", "ERROR:")):
        raise AssertionError(texto[:200])


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
