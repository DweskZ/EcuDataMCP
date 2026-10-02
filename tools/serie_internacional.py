"""International sources with Ecuador data behind one tool.

World Bank WDI, IRENA's electricity statistics and XM Colombia's hourly
interconnection flows each answer "give me a series for Ecuador" but take
different filters. One tool with a `fuente` selector keeps tools/list small
(the same pattern as search_archivos); the per-source clients are separate.
"""

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import irena_client, wdi_client, xm_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY

Fuente = Literal["wdi", "irena", "xm"]


def _year(value: str, name: str) -> int | None:
    if not value:
        return None
    try:
        return int(value[:4])
    except ValueError as e:
        raise ValueError(f"`{name}` debe ser un año (AAAA) para esta fuente.") from e


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
    if not p["desde"] or not p["hasta"]:
        raise ValueError("xm requiere `desde` y `hasta` (AAAA-MM-DD, máximo 366 días).")
    return {
        "fuente": "xm",
        **await xm_client.get_intercambio(
            p["desde"], p["hasta"], sentido=p["sentido"], agregacion=p["agregacion"]
        ),
    }


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
        title="Series internacionales con datos de Ecuador (WDI, IRENA, XM)",
        description=(
            "World Bank WDI indicators (wdi: set indicador, or query to search the "
            "catalog), IRENA capacity/generation by technology (irena), or hourly "
            "Colombia-Ecuador electricity flows since 2003 (xm). Defaults to Ecuador."
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

        Args:
            fuente: wdi, irena or xm.
            indicador: wdi only: WDI code. Empty with `query` searches instead.
            query: wdi only: catalog search text, used when indicador is empty.
            pais: wdi/irena: ISO3 code (irena also accepts the English name).
                Ignored by xm. Default ECU.
            desde: Start: a year (AAAA) for wdi/irena, a date (AAAA-MM-DD) for xm.
            hasta: End, same format as desde. xm allows at most 366 days.
            tecnologia: irena only: technology label substring (solar, hydro,
                Total Renewable...). Empty returns all technologies.
            tipo: irena only: generacion (GWh), capacidad (MW) or ambos.
            conexion: irena only: All, On-grid or Off-grid.
            sentido: xm only: exportaciones (Colombia to Ecuador) or
                importaciones (Ecuador to Colombia).
            agregacion: xm only: dia or mes.
            limit: wdi catalog search only: maximum indicators (1-200).
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
        }
        try:
            result = await _run(fuente, params)
        except Exception as e:
            raise ToolError(f"Error al consultar {fuente}: {e}") from e
        return render_structured(result, format, text_builder=_to_text)
