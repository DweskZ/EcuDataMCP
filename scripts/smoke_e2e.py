"""End-to-end smoke test against a running MCP HTTP server."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from helpers.smoke_status import GEOBLOCKED_SOURCES, assess_response

# Tool output routinely contains non-ASCII text (accents, →, ⚠...) from
# real government sources; on Windows the console defaults to cp1252,
# which raises on those and would abort the whole run mid-loop, hiding
# every check after the one that happened to fail. utf-8 with `replace`
# keeps a crash from ever being about console encoding.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MCP_URL = "http://127.0.0.1:8000/mcp"
HEALTH_URL = "http://127.0.0.1:8000/health"
FIXED_RUC = "1790016919001"


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


async def call_tool(client: httpx.AsyncClient, name: str, args: dict) -> tuple[str, bool]:
    """Return (text, is_error) -- the tool result's own MCP ``isError`` flag.

    A tool failure still comes back as a normal (non-protocol-error) MCP
    result with ``isError: true``, so it must be threaded through explicitly
    rather than guessed from the text: see assess_response's docstring.
    """
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
    result = data.get("result", {})
    content = result.get("content", [])
    text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
    return text, bool(result.get("isError"))


async def check_tool(
    client: httpx.AsyncClient, name: str, args: dict, required: list[str]
) -> tuple[str, str | None]:
    """Run a check twice when a known live source is temporarily degraded."""
    assessment = None
    for attempt in range(2):
        text, is_error = await call_tool(client, name, args)
        assessment = assess_response(text, required, is_error=is_error)
        if assessment.status != "degraded" or attempt:
            break
        await asyncio.sleep(1)
    assert assessment is not None
    if assessment.status == "ok":
        print(f"  OK       {name}")
    elif is_geo_skipped(assessment.source):
        print(f"  SKIPPED  {name} [{assessment.source}]: geo-blocked, no tunnel")
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


def chain_step(
    text: str, required: list[str] | None = None, is_error: bool = False
) -> str:
    """Assert one chain step through the same classifier the flat checks use.

    Each chain used to hand-roll a Traceback/`Error:` check, so a known
    upstream degradation (the recurring datosabiertos.gob.ec 403) failed the
    whole workflow even though `check_tool` classifies the identical response
    as degraded. Routing both paths through `assess_response` keeps a real
    source change failing while a known outage only degrades.
    """
    assessment = assess_response(text, required or [], is_error=is_error)
    if assessment.status == "degraded":
        raise DegradedChain(assessment.source or "unknown", assessment.detail)
    if assessment.status == "failed":
        raise AssertionError(assessment.detail)
    return text


async def call_chain_step(
    client: httpx.AsyncClient, name: str, args: dict, required: list[str] | None = None
) -> str:
    """call_tool + chain_step, threading the real isError flag between them."""
    text, is_error = await call_tool(client, name, args)
    return chain_step(text, required, is_error=is_error)


def is_geo_skipped(source: str | None) -> bool:
    """A geo-blocked source is expected to fail when no LatAm tunnel is set."""
    return source in GEOBLOCKED_SOURCES and not os.getenv("ECUADOR_MCP_GEO_PROXY")


def write_summary(
    total: int, failed: int, degraded: set[str], skipped: set[str]
) -> None:
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
        f"- Skipped (geo-blocked, no tunnel): {', '.join(sorted(skipped)) or 'none'}",
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
            ("lookup_ubicacion", {"query": "Pichincha"}, ["17", "Pichincha"]),
            ("lookup_ubicacion", {"query": "Cuenca", "nivel": "canton"}, ["0101", "Cuenca"]),
            (
                "lookup_ubicacion",
                {"query": "Tumbaco", "nivel": "parroquia", "format": "json"},
                ["170150", "Tumbaco", "parroquias"],
            ),
            (
                "search_datasets",
                {"sort": "recent", "page_size": 3, "format": "json"},
                ['"results"'],
            ),
            ("list_categories", {"format": "json"}, ['"categories"', "salud"]),
            ("list_instituciones", {"query": "SRI", "format": "json"}, ['"institucion_id"', "SRI"]),
            ("search_datasets", {"query": "salud", "page_size": 2}, ["dataset"]),
            ("search_tramites", {"query": "pasaporte", "format": "json"}, ["tramite_id", "pasaporte"]),
            ("search_regulaciones", {"query": "datos", "format": "json"}, ["regulacion_id"]),
            ("get_regulacion_info", {"regulacion_id": "2990", "format": "json"}, ["regulacion"]),
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
            (
                "search_archivos",
                {"fuente": "sri_datasets", "query": "recaudacion", "limit": 3},
                [],
            ),
            (
                "search_archivos",
                {"fuente": "sri_recaudacion", "query": "recaudacion", "limit": 3},
                [],
            ),
            ("search_sri_ruc", {"razon_social": "BANCO", "max_resultados": 3}, []),
            ("search_indicadores_bce", {"query": "inflacion", "limit": 5}, []),
            ("search_bce_iem", {"query": "inflacion", "limit": 5}, []),
            ("search_archivos", {"fuente": "bce_publicaciones", "limit": 3}, []),
            ("search_bce_paginas", {"catalogo": "indices", "query": "petrolero"}, []),
            ("search_archivos", {"fuente": "bce_remesas", "limit": 3}, []),
            ("list_catalogo", {"fuente": "bce_diarios"}, ["Riesgo", "serie"]),
            (
                "get_cenace_tablero",
                {"tablero": "produccion_tiempo_real"},
                ["PRODUCCIÓN", "HIDRÁULICA"],
            ),
            ("get_cenace_boletin", {"mes": "ultimo"}, ["TRANSACCIONES COMERCIALES"]),
            (
                "get_capa_geo_datos",
                {"fuente": "arconel", "capa": "balance_energia", "filtro": "Anio = 2024"},
                ["EnergiaDisponibleSistema"],
            ),
            (
                "get_capa_geo_datos",
                {
                    "fuente": "arconel",
                    "capa": "produccion_centrales",
                    "sumar": "EnergiaNeta",
                    "agrupar": "AnioProduccion",
                    "filtro": "AnioProduccion >= 2025",
                },
                ["suma_EnergiaNeta"],
            ),
            ("search_capas_geo", {"fuente": "celec"}, ["snt_linea_transmision"]),
            ("search_cortes", {"distribuidora": "elecgalapagos"}, ["Mantenimientos"]),
            ("search_cortes", {"distribuidora": "emelnorte"}, ["Suspensión"]),
            ("get_cortes_horarios", {"distribuidora": "eeasa", "archivo": "vigentes"}, []),
            ("get_archivo_seccion", {"fuente": "arconel", "seccion": "regulaciones"}, ["ARCONEL"]),
            ("list_archivo_secciones", {"fuente": "cenace"}, ["Informes de Gestión"]),
            ("search_sismos", {"limit": 3}, []),
            ("search_informes_igepn", {"anio": 2022, "grupo": "sismico", "limit": 3}, []),
            ("search_companias", {"query": "BANCO", "limit": 3}, []),
            ("search_auditores", {"query": "AUDIT", "limit": 3}, []),
            ("search_ranking", {"limit": 3}, []),
            ("list_archivo_secciones", {"fuente": "sipa"}, ["SIPA", "economico"]),
            ("list_archivo_secciones", {"fuente": "superbancos"}, ["boletines_financieros"]),
            (
                "get_archivo_seccion",
                {"fuente": "superbancos", "seccion": "indicadores_solidez"},
                # Any year folder proves the OneDrive tree was crawled; a
                # fixed year flakes while the site rebuilds that folder and
                # rots every January.
                ["Año 20"],
            ),
            ("search_archivos", {"fuente": "msp", "query": "vectoriales 2026", "limit": 3}, []),
            ("get_archivo_seccion", {"fuente": "bvg", "seccion": "historicos"}, ["BVG_Acciones"]),
            ("list_archivo_secciones", {"fuente": "bvq"}, ["cotizaciones_historicas"]),
            ("list_catalogo", {"fuente": "sut"}, ["indicador"]),
            ("list_catalogo", {"fuente": "contraloria"}, ["Contraloría"]),
            ("search_anda", {"query": "empleo", "limit": 3}, []),
            ("search_biinec_extras", {"query": "ambiental"}, []),
            ("search_siniestros_ant", {"anio": 2025, "con_archivos": 1}, []),
            ("search_archivos", {"fuente": "censo", "query": "poblacion", "limit": 3}, []),
            ("search_inec_estadisticas", {"query": "empleo", "limit": 3}, []),
            ("search_inec_publicaciones", {"query": "empleo", "limit": 3}, []),
            # -- tools with no ID to discover: closed enums or optional-only
            # arguments, so they can be called flat.
            ("list_aip_aerodromos", {"format": "json"}, []),
            ("get_aip_aerodromo", {"designador": "SEQM", "format": "json"}, ["SEQM"]),
            ("get_aviso_aeronautico", {"tipo": "sigmet", "format": "json"}, []),
            ("search_bce_calendario", {"limit": 3}, []),
            ("search_capas_geo", {"fuente": "inamhi", "format": "json"}, []),
            ("search_capas_geo", {"fuente": "mag", "format": "json"}, []),
            ("search_capas_geo", {"fuente": "igm", "query": "poblado"}, ["nacional_2024:poblado_p_2024"]),
            (
                "get_capa_geo_datos",
                {"fuente": "igm", "capa": "nacional_2024:poblado_p_2024", "count": 2},
                ["poblado"],
            ),
            ("search_archivos", {"fuente": "turismo", "limit": 3}, ["Turismo"]),
            ("search_archivos", {"fuente": "fedexpor", "limit": 3}, ["Expordata"]),
            ("search_archivos", {"fuente": "arcotel_series", "query": "1.1.1"}, ["Lineas activas"]),
            ("search_archivos", {"fuente": "msp_precios", "limit": 2}, ["precios"]),
            ("search_archivos", {"fuente": "mit_vias"}, ["mit.gob.ec"]),
            ("search_archivos", {"fuente": "minedec_bases", "query": "csv 2024-2025"}, ["2024-2025"]),
            ("search_capas_geo", {"fuente": "msp"}, ["indicadores_ssr"]),
            (
                "get_capa_geo_datos",
                {"fuente": "msp", "capa": "egresos_hospitalarios", "sumar": "EGRESOS", "agrupar": "AÑO"},
                ["suma_EGRESOS"],
            ),
            ("search_archivos", {"fuente": "aeade", "query": "ventas", "limit": 3}, ["ventas"]),
            ("list_catalogo", {"fuente": "cfn"}, ["estadisticas"]),
            (
                "query_sut_indicador",
                {
                    "fuente": "cfn",
                    "indicador": "estadisticas",
                    "campos": ["Garantias FNG.nombre_provincia", "Medidas FNG.Monto Garantizado (USD) [medida]"],
                    "limite": 5,
                    "format": "json",
                },
                ["nombre_provincia"],
            ),
            (
                "get_serie_internacional",
                {
                    "fuente": "ember",
                    "indicador": "by_source/total",
                    "frecuencia": "M",
                    "desde": "2024-09",
                    "hasta": "2024-12",
                    "format": "json",
                },
                ["Hydropower"],
            ),
            ("search_cepalstat_indicadores", {"query": "poblacion"}, []),
            ("search_cortes", {"distribuidora": "eeq", "format": "json"}, []),
            ("search_cortes", {"distribuidora": "centrosur", "format": "json"}, []),
            ("search_infomies_bases_mensuales", {"serie": "anc", "format": "json"}, []),
            ("search_infomies_boletines_zonales", {"format": "json"}, []),
            ("search_sgr_sitreps", {"format": "json"}, []),
            ("get_category_info", {"category": "sal", "format": "json"}, []),
            ("get_iess_archivos", {"coleccion": "boletines", "format": "json"}, []),
            (
                "get_serie_internacional",
                {"fuente": "wdi", "indicador": "NY.GDP.MKTP.CD", "ultimos": 3, "format": "json"},
                [],
            ),
            ("get_sipa_resumen_indicadores", {"anio": 2024, "format": "json"}, []),
            # -- fixed public RUC (Corporación Favorita, a large company that
            # is in every registry these tools read), so the lookups never
            # depend on a search ranking that shifts over time.
            ("get_sri_ruc_info", {"ruc": FIXED_RUC, "format": "json"}, [FIXED_RUC]),
            (
                "get_certificado_cumplimiento_patronal",
                {"identificacion": FIXED_RUC, "format": "json"},
                [],
            ),
            ("get_compania_info", {"ruc": FIXED_RUC, "format": "json"}, []),
            ("get_financials", {"expediente_or_ruc": FIXED_RUC, "desde": 2023, "format": "json"}, []),
        ]

        print("== tools ==")
        failed = 0
        degraded: set[str] = set()
        skipped: set[str] = set()
        for name, args, must in checks:
            try:
                status, source = await check_tool(client, name, args, must)
                if status == "degraded" and source:
                    (skipped if is_geo_skipped(source) else degraded).add(source)
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
            ("ckan: search -> dataset/resource info -> query", chain_ckan_info(client)),
            ("tramites: search -> info -> estadisticas", chain_tramites(client)),
            ("instituciones: list -> info", chain_instituciones(client)),
            ("organizations: search -> info", chain_organizations(client)),
            ("ckan: search -> series pattern -> download", chain_ckan_download(client)),
            ("bce: search -> indicador", chain_bce_indicador(client)),
            ("bce: iem -> table", chain_bce_iem(client)),
            ("bce: diarios -> indicador", chain_bce_diario(client)),
            ("bce: paginas -> archivos", chain_bce_paginas(client)),
            ("cepalstat: search -> indicador", chain_cepalstat(client)),
            ("contraloria: list -> informe", chain_contraloria(client)),
            ("arconel: list -> reporte", chain_arconel(client)),
            ("inec: estadistica -> files -> zip", chain_inec_estadistica(client)),
            ("inec: publicacion -> archivos", chain_inec_publicacion(client)),
            ("sgr: sitreps -> archivos -> pdf", chain_sgr_pdf(client)),
            ("anda: search -> info -> microdata", chain_anda(client)),
            ("supercias: auditores -> auditor", chain_auditor(client)),
            ("sercop: search -> contrato", chain_contrato(client)),
        ]:
            chains += 1
            try:
                await coro
                print(f"  OK   {label}")
            except DegradedChain as exc:
                if is_geo_skipped(exc.source):
                    skipped.add(exc.source)
                    print(f"  SKIPPED  {label} [{exc.source}]: geo-blocked, no tunnel")
                else:
                    degraded.add(exc.source)
                    print(f"  DEGRADED {label} [{exc.source}]: {str(exc)[:160]}")
            except Exception as exc:
                failed += 1
                print(f"  FAIL {label}: {exc}")

        print("== done ==")
        total = len(checks) + chains
        print(f"failed={failed}/{total}; degraded={len(degraded)}; skipped={len(skipped)}")
        write_summary(total, failed, degraded, skipped)
        return 1 if failed else 0


async def chain_sut(client: httpx.AsyncClient) -> None:
    listing = json.loads(
        await call_chain_step(client, "list_catalogo", {"fuente": "sut", "format": "json"})
    )
    indicador = listing["indicadores"][0]["indicador"]
    schema = json.loads(
        await call_chain_step(
            client, "get_sut_indicador_schema", {"indicador": indicador, "format": "json"}
        )
    )
    campos = schema.get("campos") or []
    if not campos:
        raise AssertionError(f"get_sut_indicador_schema returned no fields for {indicador}")
    await call_chain_step(
        client,
        "query_sut_indicador",
        {"indicador": indicador, "campos": campos[:1], "limite": 3, "format": "json"},
    )


async def chain_superbancos(client: httpx.AsyncClient) -> None:
    listing = json.loads(
        await call_chain_step(
            client, "list_archivo_secciones", {"fuente": "superbancos", "format": "json"}
        )
    )
    seccion = listing["secciones"][0]["id"]
    await call_chain_step(
        client,
        "get_archivo_seccion",
        {"fuente": "superbancos", "seccion": seccion, "format": "json"},
    )


async def chain_igepn(client: httpx.AsyncClient) -> None:
    resultado = json.loads(
        await call_chain_step(
            client,
            "search_informes_igepn",
            {"anio": 2022, "grupo": "volcanico", "limit": 1, "format": "json"},
        )
    )
    informes = resultado.get("informes") or []
    if not informes:
        raise AssertionError("search_informes_igepn returned no reports for 2022/volcanico")
    informe = informes[0]
    await call_chain_step(
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


async def chain_ckan_preview(client: httpx.AsyncClient) -> None:
    search = json.loads(
        await call_chain_step(
            client,
            "search_datasets",
            {"query": "SRI recaudacion", "page_size": 5, "format": "json"},
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
            await call_chain_step(
                client,
                "list_dataset_resources",
                {"dataset_id": dataset_id, "format": "json"},
            )
        )
        resources = listing.get("resources") or []
        resource = next(
            (r for r in resources if (r.get("format") or "").lower() in tabular_formats),
            resources[0] if resources else None,
        )
        if resource is None:
            continue

        await call_chain_step(
            client,
            "preview_resource_data",
            {"resource_id": resource["id"], "rows": 3, "format": "json"},
        )
        return

    raise AssertionError(
        "no dataset among the top 5 'SRI recaudacion' results had a previewable resource"
    )


async def first_result(
    client: httpx.AsyncClient, name: str, args: dict, key: str
) -> str:
    """Call a search tool and return the first row's ``key``, failing if none."""
    search = json.loads(await call_chain_step(client, name, {**args, "format": "json"}))
    rows = search.get("results") or []
    if not rows or not rows[0].get(key):
        raise AssertionError(f"{name} returned no row with '{key}' for {args}")
    return str(rows[0][key])


async def chain_ckan_info(client: httpx.AsyncClient) -> None:
    dataset_id = await first_result(
        client, "search_datasets", {"query": "SRI recaudacion", "page_size": 3}, "name"
    )
    await call_chain_step(client, "get_dataset_info", {"dataset_id": dataset_id, "format": "json"})
    await call_chain_step(client, "investigate_dataset", {"query": "SRI recaudacion", "preview_rows": 3, "format": "json"})
    listing = json.loads(
        await call_chain_step(
            client, "list_dataset_resources", {"dataset_id": dataset_id, "format": "json"}
        )
    )
    resources = listing.get("resources") or []
    if not resources:
        raise AssertionError(f"dataset {dataset_id} has no resources")
    resource_id = resources[0]["id"]
    await call_chain_step(client, "get_resource_info", {"resource_id": resource_id, "format": "json"})

    # Most CKAN uploads are never loaded into the DataStore. The resource was
    # just confirmed to exist, so the tool's "sin DataStore" refusal (pointing
    # to preview_resource_data) is the documented answer, not a failure.
    text, is_error = await call_tool(
        client, "query_resource_data", {"resource_id": resource_id, "rows": 3, "format": "json"}
    )
    if not (is_error and "sin DataStore" in text):
        chain_step(text, is_error=is_error)


async def chain_tramites(client: httpx.AsyncClient) -> None:
    tramite_id = await first_result(client, "search_tramites", {"query": "pasaporte"}, "tramite_id")
    await call_chain_step(client, "get_tramite_info", {"tramite_id": tramite_id, "format": "json"})
    await call_chain_step(client, "get_tramite_estadisticas", {"tramite_id": tramite_id, "format": "json"})


async def chain_instituciones(client: httpx.AsyncClient) -> None:
    institucion_id = await first_result(client, "list_instituciones", {"query": "SRI"}, "institucion_id")
    await call_chain_step(client, "get_institucion_info", {"institucion_id": institucion_id, "format": "json"})


async def chain_organizations(client: httpx.AsyncClient) -> None:
    organization_id = await first_result(client, "search_organizations", {"query": "sri", "page_size": 3}, "name")
    await call_chain_step(client, "get_organization_info", {"organization_id": organization_id, "format": "json"})


async def first_item(
    client: httpx.AsyncClient, name: str, args: dict, list_key: str
) -> dict:
    """Call a tool and return the first element of ``list_key``, failing if empty."""
    data = json.loads(await call_chain_step(client, name, {**args, "format": "json"}))
    rows = data.get(list_key) or []
    if not rows:
        raise AssertionError(f"{name} returned no '{list_key}' for {args}")
    return rows[0]


async def chain_ckan_download(client: httpx.AsyncClient) -> None:
    dataset_id = await first_result(
        client, "search_datasets", {"query": "SRI recaudacion", "page_size": 3}, "name"
    )
    # "sin_serie_detectada" is a valid answer for a single-year dataset, not
    # a failure, so it is accepted before the generic classifier sees its
    # "error" key.
    text, is_error = await call_tool(
        client, "detect_series_pattern", {"dataset_id": dataset_id, "format": "json"}
    )
    try:
        no_series = json.loads(text).get("error") == "sin_serie_detectada"
    except (json.JSONDecodeError, AttributeError):
        no_series = False
    if not no_series:
        chain_step(text, is_error=is_error)
    resource = await first_item(
        client, "list_dataset_resources", {"dataset_id": dataset_id}, "resources"
    )
    # The SRI files are often over the 5 MB cap; refusing them with the
    # direct link is the tool working as documented, not a failure.
    text, is_error = await call_tool(
        client, "download_resource", {"resource_id": resource["id"], "format": "json"}
    )
    if not (is_error and "supera el límite de 5 MB" in text):
        chain_step(text, is_error=is_error)


async def chain_bce_indicador(client: httpx.AsyncClient) -> None:
    indicador = await first_item(
        client, "search_indicadores_bce", {"query": "inflacion", "limit": 1}, "indicadores"
    )
    await call_chain_step(
        client,
        "get_indicador_bce",
        {"id_grupo": int(indicador["id_grupo"]), "desde": "2025-01", "format": "json"},
    )


async def chain_bce_iem(client: httpx.AsyncClient) -> None:
    tabla = await first_item(
        client, "search_bce_iem", {"query": "inflacion", "limit": 1}, "tablas"
    )
    await call_chain_step(
        client, "get_bce_iem_table", {"table_id": tabla["table_id"], "rows": 3, "format": "json"}
    )


async def chain_bce_diario(client: httpx.AsyncClient) -> None:
    serie = await first_item(client, "list_catalogo", {"fuente": "bce_diarios"}, "catalogo")
    await call_chain_step(
        client,
        "get_bce_indicador_diario",
        {"archivo": serie["archivo"], "codigo": serie["codigo"], "ultimos_n": 3, "format": "json"},
    )


async def chain_bce_paginas(client: httpx.AsyncClient) -> None:
    pagina = await first_item(
        client, "search_bce_paginas", {"catalogo": "indices", "query": "petrolero"}, "paginas"
    )
    await call_chain_step(
        client,
        "get_bce_pagina_archivos",
        {"catalogo": "indices", "pagina_id": pagina["pagina_id"], "max_archivos": 3, "format": "json"},
    )


async def chain_cepalstat(client: httpx.AsyncClient) -> None:
    indicador = await first_item(
        client, "search_cepalstat_indicadores", {"query": "poblacion total"}, "indicadores"
    )
    await call_chain_step(
        client,
        "get_cepalstat_indicador",
        {"indicator_id": int(indicador["indicator_id"]), "format": "json"},
    )


async def chain_contraloria(client: httpx.AsyncClient) -> None:
    informe = await first_item(client, "list_catalogo", {"fuente": "contraloria"}, "informes")
    await call_chain_step(
        client, "get_contraloria_informe", {"informe_id": informe["id"], "rows": 3, "format": "json"}
    )


async def chain_arconel(client: httpx.AsyncClient) -> None:
    tipo = await first_item(client, "list_catalogo", {"fuente": "arconel"}, "tipos")
    await call_chain_step(
        client,
        "get_arconel_reporte",
        {"tipo": tipo["tipo"], "anio": 2024, "max_paginas": 1, "format": "json"},
    )


async def chain_inec_estadistica(client: httpx.AsyncClient) -> None:
    tema = await first_item(
        client, "search_inec_estadisticas", {"query": "empleo", "limit": 1}, "temas"
    )
    files = json.loads(
        await call_chain_step(
            client, "get_inec_estadistica_files", {"url": tema["url"], "format": "json"}
        )
    )
    zips = [a["url"] for a in files.get("archivos") or [] if a["url"].lower().endswith(".zip")]
    if not zips:
        raise AssertionError(f"no ZIP among the files of {tema['url']}")
    listing = json.loads(
        await call_chain_step(
            client, "list_zip_contents", {"url": zips[0], "limit": 5, "format": "json"}
        )
    )
    members = [m["name"] for m in listing.get("members") or [] if not m["is_dir"]]
    if not members:
        raise AssertionError(f"list_zip_contents returned no files for {zips[0]}")

    # Not every member is tabular (PDF manuals, .sav microdata): a refusal
    # naming the supported formats is the tool working, not a failure.
    text, is_error = await call_tool(
        client,
        "read_zip_member",
        {"url": zips[0], "member": members[0], "rows": 3, "format": "json"},
    )
    if not (is_error and "Formatos soportados" in text):
        chain_step(text, is_error=is_error)


async def chain_inec_publicacion(client: httpx.AsyncClient) -> None:
    publicacion = await first_item(
        client, "search_inec_publicaciones", {"query": "empleo", "limit": 1}, "publicaciones"
    )
    await call_chain_step(
        client, "get_inec_publicacion_archivos", {"post": str(publicacion["id"]), "format": "json"}
    )


async def chain_sgr_pdf(client: httpx.AsyncClient) -> None:
    evento = await first_item(client, "search_sgr_sitreps", {}, "eventos")
    archivos = json.loads(
        await call_chain_step(
            client, "get_sgr_sitrep_archivos", {"evento_url": evento["url"], "format": "json"}
        )
    )
    pdfs = [a["url"] for a in archivos.get("archivos") or [] if a.get("formato") == "PDF"]
    if not pdfs:
        raise AssertionError(f"no PDF among the SITREPs of {evento['url']}")
    await call_chain_step(client, "read_pdf", {"url": pdfs[0], "pages": "1", "format": "json"})


async def chain_anda(client: httpx.AsyncClient) -> None:
    encuesta = await first_item(client, "search_anda", {"query": "empleo", "limit": 1}, "results")
    await call_chain_step(client, "get_anda_survey_info", {"idno": encuesta["idno"], "format": "json"})
    await call_chain_step(client, "download_anda_microdata", {"idno": encuesta["idno"], "format": "json"})


async def chain_auditor(client: httpx.AsyncClient) -> None:
    auditor = await first_item(client, "search_auditores", {"query": "AUDIT", "limit": 1}, "auditores")
    await call_chain_step(
        client, "get_auditor_info", {"identificacion": auditor["identificacion"], "format": "json"}
    )


async def chain_contrato(client: httpx.AsyncClient) -> None:
    search = json.loads(
        await call_chain_step(
            client, "search_contratos", {"query": "agua", "year": 2024, "format": "json"}
        )
    )
    # SERCOP's search index also lists stub processes (title and method null)
    # whose OCDS record was never published, so `record` finds nothing for
    # them. Only a fully described row is expected to have a record.
    contrato = next(
        (r for r in search.get("results") or [] if r.get("ocid") and r.get("title")),
        None,
    )
    if contrato is None:
        raise AssertionError("search_contratos returned no row with an ocid and a title")
    await call_chain_step(client, "get_contrato_info", {"ocid": contrato["ocid"], "format": "json"})
    # The per-buyer summary on that same row's buyer: the search found it, so
    # the summary must find at least one process.
    if contrato.get("buyer"):
        summary = json.loads(
            await call_chain_step(
                client,
                "get_resumen_compras",
                {"comprador": contrato["buyer"][:60], "year": 2024, "format": "json"},
            )
        )
        if not summary.get("procesos_leidos"):
            raise AssertionError(f"get_resumen_compras found nothing for {contrato['buyer']!r}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
