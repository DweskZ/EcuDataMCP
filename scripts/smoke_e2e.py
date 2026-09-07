"""End-to-end smoke test against a running MCP HTTP server."""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx

from helpers.smoke_status import assess_response

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


async def check_tool(
    client: httpx.AsyncClient, name: str, args: dict, required: list[str]
) -> tuple[str, str | None]:
    """Run a check twice when a known live source is temporarily degraded."""
    assessment = None
    for attempt in range(2):
        text = await call_tool(client, name, args)
        assessment = assess_response(text, required)
        if assessment.status != "degraded" or attempt:
            break
        await asyncio.sleep(1)
    assert assessment is not None
    if assessment.status == "ok":
        print(f"  OK       {name}")
    elif assessment.status == "degraded":
        print(f"  DEGRADED {name} [{assessment.source}]: {assessment.detail[:160]}")
    else:
        raise AssertionError(assessment.detail)
    return assessment.status, assessment.source


class DegradedChain(Exception):
    """A chain step blocked by a known external source, not by a regression."""

    def __init__(self, source: str, detail: str) -> None:
        super().__init__(detail)
        self.source = source


def chain_step(text: str, required: list[str] | None = None) -> str:
    """Assert one chain step through the same classifier the flat checks use.

    Each chain used to hand-roll a Traceback/`Error:` check, so a known
    upstream degradation (the recurring datosabiertos.gob.ec 403) failed the
    whole workflow even though `check_tool` classifies the identical response
    as degraded. Routing both paths through `assess_response` keeps a real
    source change failing while a known outage only degrades.
    """
    assessment = assess_response(text, required or [])
    if assessment.status == "degraded":
        raise DegradedChain(assessment.source or "unknown", assessment.detail)
    if assessment.status == "failed":
        raise AssertionError(assessment.detail)
    return text


def write_summary(total: int, failed: int, degraded: set[str]) -> None:
    """Write a compact GitHub Actions summary while keeping local runs plain."""
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [
        "## EcuDataMCP smoke",
        "",
        f"- Checks: {total}",
        f"- Hard failures: {failed}",
        f"- Degraded external sources: {', '.join(sorted(degraded)) or 'none'}",
    ]
    with open(path, "a", encoding="utf-8") as summary:
        summary.write("\n".join(lines) + "\n")


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
            ("search_bce_publicaciones", {"query": ""}, []),
            ("search_bce_indices", {"query": "petrolero"}, []),
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
        degraded: set[str] = set()
        for name, args, must in checks:
            try:
                status, source = await check_tool(client, name, args, must)
                if status == "degraded" and source:
                    degraded.add(source)
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
            ("ckan: search -> resources -> preview", chain_ckan_preview(client)),
        ]:
            chains += 1
            try:
                await coro
                print(f"  OK   {label}")
            except DegradedChain as exc:
                degraded.add(exc.source)
                print(f"  DEGRADED {label} [{exc.source}]: {str(exc)[:160]}")
            except Exception as exc:
                failed += 1
                print(f"  FAIL {label}: {exc}")

        print("== done ==")
        total = len(checks) + chains
        print(f"failed={failed}/{total}; degraded={len(degraded)}")
        write_summary(total, failed, degraded)
        return 1 if failed else 0


async def chain_sut(client: httpx.AsyncClient) -> None:
    listing = json.loads(
        chain_step(await call_tool(client, "list_sut_indicadores", {"format": "json"}))
    )
    indicador = listing[0]["indicador"]
    chain_step(
        await call_tool(
            client,
            "get_sut_indicador_schema",
            {"indicador": indicador, "format": "json"},
        )
    )


async def chain_superbancos(client: httpx.AsyncClient) -> None:
    listing = json.loads(
        chain_step(
            await call_tool(client, "list_superbancos_secciones", {"format": "json"})
        )
    )
    seccion = listing[0]["seccion"]
    chain_step(
        await call_tool(
            client,
            "get_superbancos_seccion_archivos",
            {"seccion": seccion, "format": "json"},
        )
    )


async def chain_igepn(client: httpx.AsyncClient) -> None:
    resultado = json.loads(
        chain_step(
            await call_tool(
                client,
                "search_informes_igepn",
                {"anio": 2022, "grupo": "volcanico", "limit": 1, "format": "json"},
            )
        )
    )
    informes = resultado.get("informes") or []
    if not informes:
        raise AssertionError("search_informes_igepn returned no reports for 2022/volcanico")
    informe = informes[0]
    chain_step(
        await call_tool(
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
    )


async def chain_ckan_preview(client: httpx.AsyncClient) -> None:
    search = json.loads(
        chain_step(
            await call_tool(
                client,
                "search_datasets",
                {"query": "SRI recaudacion", "page_size": 5, "format": "json"},
            )
        )
    )
    datasets = search.get("results") or []
    if not datasets:
        raise AssertionError("search_datasets returned no results for 'SRI recaudacion'")

    tabular_formats = {"csv", "xlsx", "xls", "ods"}
    for dataset in datasets:
        dataset_id = dataset.get("name") or dataset.get("id")
        if not dataset_id:
            continue
        listing = json.loads(
            chain_step(
                await call_tool(
                    client,
                    "list_dataset_resources",
                    {"dataset_id": dataset_id, "format": "json"},
                )
            )
        )
        resources = listing.get("resources") or []
        resource = next(
            (r for r in resources if (r.get("format") or "").lower() in tabular_formats),
            resources[0] if resources else None,
        )
        if resource is None:
            continue

        chain_step(
            await call_tool(
                client,
                "preview_resource_data",
                {"resource_id": resource["id"], "rows": 3, "format": "json"},
            )
        )
        return

    raise AssertionError(
        "no dataset among the top 5 'SRI recaudacion' results had a previewable resource"
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
