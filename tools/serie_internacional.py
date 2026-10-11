"""International sources with Ecuador data behind one tool.

World Bank WDI, IRENA's electricity statistics, XM Colombia's hourly
interconnection flows, UN Comtrade, the IMF, WHO, ILOSTAT and UNHCR each
answer "give me a series for Ecuador" but take different filters. One tool
with a `fuente` selector keeps tools/list small (the same pattern as
search_archivos); the per-source clients are separate.
"""

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import (
    comtrade_client,
    ilo_client,
    imf_client,
    irena_client,
    unhcr_client,
    wdi_client,
    who_client,
    xm_client,
)
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY

Fuente = Literal["wdi", "irena", "xm", "comtrade", "imf", "who", "ilo", "unhcr"]


def _year(value: str, name: str) -> int | None:
    if not value:
        return None
    try:
        return int(value[:4])
    except ValueError as e:
        raise ValueError(f"`{name}` debe ser un año (AAAA) para esta fuente.") from e


async def _sdmx(client: Any, name: str, p: dict[str, Any]) -> dict[str, Any]:
    if not p["indicador"]:
        return {"fuente": name, **await client.search_flujos(p["query"], p["limit"])}
    return {
        "fuente": name,
        **await client.get_serie(
            p["indicador"],
            clave=p["clave"],
            pais=p["pais"],
            desde=p["desde"],
            hasta=p["hasta"],
            ultimos=p["ultimos"],
        ),
    }


async def _run(fuente: str, p: dict[str, Any]) -> dict[str, Any]:
    if fuente == "wdi":
        if p["indicador"]:
            return {
                "fuente": "wdi",
                **await wdi_client.get_indicador(
                    p["indicador"],
                    pais=p["pais"],
                    desde=_year(p["desde"], "desde"),
                    hasta=_year(p["hasta"], "hasta"),
                ),
            }
        return {"fuente": "wdi", **await wdi_client.search_indicadores(p["query"], p["limit"])}
    if fuente == "irena":
        return {
            "fuente": "irena",
            **await irena_client.get_electricidad(
                pais=p["pais"],
                tecnologia=p["tecnologia"],
                tipo=p["tipo"],
                conexion=p["conexion"],
                desde=_year(p["desde"], "desde"),
                hasta=_year(p["hasta"], "hasta"),
            ),
        }
    if fuente == "comtrade":
        return {
            "fuente": "comtrade",
            **await comtrade_client.get_comercio(
                pais=p["pais"],
                periodo=p["periodo"] or p["desde"],
                socio=p["socio"],
                cmd=p["cmd"],
                flujo=p["flujo"],
                frecuencia=p["frecuencia"],
            ),
        }
    if fuente == "imf":
        return await _sdmx(imf_client, "imf", p)
    if fuente == "ilo":
        return await _sdmx(ilo_client, "ilo", p)
    if fuente == "who":
        if p["indicador"]:
            return {
                "fuente": "who",
                **await who_client.get_indicador(
                    p["indicador"],
                    pais=p["pais"],
                    desde=_year(p["desde"], "desde"),
                    hasta=_year(p["hasta"], "hasta"),
                ),
            }
        return {"fuente": "who", **await who_client.search_indicadores(p["query"], p["limit"])}
    if fuente == "unhcr":
        return {
            "fuente": "unhcr",
            **await unhcr_client.get_poblacion(
                pais=p["pais"],
                origen=p["socio"],
                desde=_year(p["desde"], "desde"),
                hasta=_year(p["hasta"], "hasta"),
            ),
        }
    if not p["desde"] or not p["hasta"]:
        raise ValueError("xm requiere `desde` y `hasta` (AAAA-MM-DD, máximo 366 días).")
    return {
        "fuente": "xm",
        **await xm_client.get_intercambio(
            p["desde"], p["hasta"], sentido=p["sentido"], agregacion=p["agregacion"]
        ),
    }


_SDMX_NAME = {"imf": "FMI", "ilo": "OIT ILOSTAT"}


def _to_text(data: dict) -> str:
    src = data["fuente"]
    if src == "wdi" and "indicadores" in data:
        parts = [
            (
                f"WDI — {data['total']} indicador(es) de {data['total_catalogo']} "
                f"(mostrando {len(data['indicadores'])})"
            ),
            "",
        ]
        parts += [f"- {i['indicador']}: {i['nombre']}" for i in data["indicadores"]]
    elif src == "wdi":
        parts = [
            f"WDI — {data.get('nombre') or data['indicador']} ({data['indicador']}), {data['pais']}",
            f"{data['total_registros']} año(s) con dato, {data['anios_sin_dato']} sin dato",
            "",
        ]
        parts += [f"- {r['anio']}: {r['valor']}" for r in data["serie"]]
    elif src == "irena":
        parts = [
            f"IRENA — {data['pais']}: {data['total_registros']} registro(s) ({data['tabla']})",
            "",
        ]
        parts += [
            f"- {r['tecnologia']} | {r['tipo']} | {r['anio']}: {r['valor']}"
            for r in data["registros"][:300]
        ]
        if data["total_registros"] > 300:
            parts.append(f"... y {data['total_registros'] - 300} más (usa format=json)")
    elif src == "comtrade":
        parts = [
            f"UN Comtrade — reportero {data['reportero']}, {data['total_registros']} registro(s)",
        ]
        if data["truncado_500"]:
            parts.append("Aviso: la vista previa pública topa en 500 filas; acota socio/cmd.")
        parts.append("")
        parts += [
            f"- {r['periodo']} | {r['flujo']} | socio {r['socio_codigo']} | HS {r['producto_hs']}: "
            f"USD {r['valor_usd']}"
            for r in data["registros"][:300]
        ]
    elif src in ("imf", "ilo") and "flujos" in data:
        parts = [
            (
                f"{_SDMX_NAME[src]} — {data['total']} flujo(s) de {data['total_catalogo']} "
                f"(mostrando {len(data['flujos'])})"
            ),
            "",
        ]
        parts += [f"- {f['flujo']}: {f['nombre']}" for f in data["flujos"]]
    elif src in ("imf", "ilo"):
        dims = ".".join(d["id"] for d in data["dimensiones"])
        parts = [
            (
                f"{_SDMX_NAME[src]} — {data['flujo']} ({data.get('titulo') or 'sin título'}), "
                f"clave {data['clave_consulta']}"
            ),
            f"{data['total_series']} serie(s); orden de dimensiones: {dims}",
            "",
        ]
        for serie in data["series"][:60]:
            label = " | ".join(d["nombre"] for d in serie["dimensiones"].values())
            obs = ", ".join(f"{o['periodo']}: {o['valor']}" for o in serie["observaciones"][-6:])
            parts.append(f"- {serie['clave']} — {label}\n    {obs}")
        if data["total_series"] > 60:
            parts.append(f"... y {data['total_series'] - 60} serie(s) más (acota la clave)")
    elif src == "who" and "indicadores" in data:
        parts = [
            (
                f"OMS GHO — {data['total']} indicador(es) de {data['total_catalogo']} "
                f"(mostrando {len(data['indicadores'])})"
            ),
            "",
        ]
        parts += [f"- {i['indicador']}: {i['nombre']}" for i in data["indicadores"]]
    elif src == "who":
        parts = [
            (
                f"OMS GHO — {data.get('nombre') or data['indicador']} ({data['indicador']}), "
                f"{data['pais']}"
            ),
            f"{data['total_registros']} registro(s)",
            "",
        ]
        parts += [
            f"- {r['anio']} | {r['desglose'] or 'total'}: {r['valor']}" for r in data["serie"][:300]
        ]
        if data["total_registros"] > 300:
            parts.append(f"... y {data['total_registros'] - 300} más (usa format=json)")
    elif src == "unhcr":
        parts = [
            (
                f"ACNUR — población en {data['pais']}: {data['total_registros']} registro(s) "
                f"({data['paginas_leidas']}/{data['paginas_totales']} páginas)"
            ),
        ]
        if data["truncado"]:
            parts.append("Aviso: resultado truncado al tope de páginas; acota con desde/hasta o socio.")
        parts.append("")
        parts += [
            f"- {r['anio']} | {r['origen']}: refugiados {r['refugiados']}, "
            f"solicitantes de asilo {r['solicitantes_asilo']}, "
            f"otras necesitadas de protección "
            f"{r['otras_personas_necesitan_proteccion_internacional']}"
            for r in data["registros"][:300]
        ]
    else:
        parts = [
            f"XM — {data['sentido']}, {data['desde']} a {data['hasta']}: {data['total_gwh']} GWh",
            "",
        ]
        parts += [f"- {p}: {v} GWh" for p, v in list(data["total_por_periodo"].items())[:400]]
    parts += ["", f"Fuente: {data.get('url_fuente')}"]
    return "\n".join(parts)


def register_serie_internacional_tools(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Series internacionales con datos de Ecuador (WDI, IRENA, XM, Comtrade, FMI, OMS, OIT, ACNUR)",
        description=(
            "International series for Ecuador via `fuente`: wdi (World Bank), irena "
            "(electricity), xm (Colombia-Ecuador power flows), comtrade (UN bilateral "
            "trade), imf (IMF SDMX), who (health), ilo (ILOSTAT labour), unhcr "
            "(refugees/asylum). Without indicador/flow, wdi/who/imf/ilo list their "
            "catalog (set query)."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_serie_internacional(
        fuente: Fuente,
        indicador: str = "",
        query: str = "",
        pais: str = "ECU",
        desde: str = "",
        hasta: str = "",
        tecnologia: str = "",
        tipo: Literal["ambos", "generacion", "capacidad"] = "ambos",
        conexion: Literal["All", "On-grid", "Off-grid"] = "All",
        sentido: Literal["exportaciones", "importaciones"] = "exportaciones",
        agregacion: Literal["dia", "mes"] = "dia",
        limit: int = 30,
        periodo: str = "",
        socio: str = "",
        cmd: str = "TOTAL",
        flujo: str = "ambos",
        frecuencia: Literal["A", "M"] = "A",
        clave: str = "",
        ultimos: int = 0,
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Fetch a series from an international source, filtered to Ecuador.

        - wdi: World Bank World Development Indicators (1,400+ series, yearly).
          With `indicador` (e.g. EG.ELC.ACCS.ZS access to electricity,
          EG.ELC.LOSS.ZS grid losses, EG.USE.ELEC.KH.PC kWh per capita)
          returns the series; with only `query` (English) searches the
          catalog. Years without a value are dropped and counted.
        - irena: IRENASTAT electricity installed capacity (MW) and
          generation (GWh) by technology, 2000 to latest, on/off-grid.
        - xm: XM Colombia hourly energy on the Colombia-Ecuador
          interconnection, summed to days or months. Requires desde/hasta.
          Blank hours (no flow) count as zero. Shows the Oct-2024 suspension.
        - comtrade: UN Comtrade merchandise trade (USD) of Ecuador with a
          partner, ONE period per call (`periodo`), public preview capped at
          500 rows and ~1 request/2 s (retried automatically). Codes only,
          no names. Partner `socio` 0 = World (default).
        - imf: IMF SDMX (190 flows: CPI, balance of payments, fiscal,
          monetary...). `indicador` = flow id (empty + `query` lists flows).
          `clave` = SDMX key; dimension order differs per flow and the
          response lists it (`dimensiones`). Empty clave = whole country
          (prefix ECU), last `ultimos` observations (default 5).
        - who: WHO Global Health Observatory (~2,000 indicators, yearly,
          by sex/age). `indicador` e.g. WHOSIS_000001 (life expectancy at
          birth); empty + `query` (English) searches the catalog.
        - ilo: ILOSTAT labour statistics, same pattern as imf. `indicador`
          is a flow id (DF_ prefix optional, e.g. UNE_DEAP_SEX_AGE_RT
          unemployment by sex and age). Short keys are padded with
          wildcards. Empty `indicador` + `query` lists flows.
        - unhcr: UNHCR refugees and asylum seekers hosted in Ecuador per
          year (Venezuelans are the largest group), from `desde`/`hasta`.
          `socio` = origin ISO3 (VEN) or `todos` for a row per origin;
          empty = totals.

        Args:
            fuente: wdi, irena, xm, comtrade, imf, who, ilo or unhcr.
            indicador: wdi/who: indicator code. imf/ilo: dataflow id.
                Empty with `query` searches (wdi/who) or lists flows (imf/ilo).
            query: wdi/who/imf/ilo: catalog search text, used when
                indicador is empty.
            pais: wdi/irena/who/imf/ilo/unhcr: ISO3 code (irena also accepts
                the English name). comtrade: ISO3 or numeric M49 reporter.
                Ignored by xm. Default ECU.
            desde: Start: a year (AAAA) for wdi/irena/who/unhcr, a date
                (AAAA-MM-DD) for xm, a period (AAAA, AAAA-MM) for imf/ilo.
            hasta: End, same format as desde. xm allows at most 366 days.
            tecnologia: irena only: technology label substring (solar, hydro,
                Total Renewable...). Empty returns all technologies.
            tipo: irena only: generacion (GWh), capacidad (MW) or ambos.
            conexion: irena only: All, On-grid or Off-grid.
            sentido: xm only: exportaciones (Colombia to Ecuador) or
                importaciones (Ecuador to Colombia).
            agregacion: xm only: dia or mes.
            limit: catalog/flow listings only: maximum rows (1-200).
            periodo: comtrade only: one period, AAAA (frecuencia A) or
                AAAAMM (frecuencia M). Required.
            socio: comtrade: partner as ISO3 (USA, CHN, COL, PER, PAN, ESP,
                NLD, ITA...) or M49 number; empty = 0 (World). unhcr: origin.
            cmd: comtrade only: TOTAL or an HS code of 2, 4 or 6 digits.
            flujo: comtrade only: X (exports), M (imports) or ambos.
            frecuencia: comtrade only: A (annual) or M (monthly).
            clave: imf/ilo only: SDMX key, dot-separated (ECU.CPI._T.IX.M).
                Empty = pais.
            ultimos: imf/ilo only: last N observations per series. Default
                5 (imf) / 3 (ilo) when no desde/hasta.
            format: text | json
        """
        params = {
            "indicador": indicador,
            "query": query,
            "pais": pais,
            "desde": desde,
            "hasta": hasta,
            "tecnologia": tecnologia,
            "tipo": tipo,
            "conexion": conexion,
            "sentido": sentido,
            "agregacion": agregacion,
            "limit": limit,
            "periodo": periodo,
            "socio": socio,
            "cmd": cmd,
            "flujo": flujo,
            "frecuencia": frecuencia,
            "clave": clave,
            "ultimos": ultimos,
        }
        try:
            result = await _run(fuente, params)
        except Exception as e:
            raise ToolError(f"Error al consultar {fuente}: {e}") from e
        return render_structured(result, format, text_builder=_to_text)
