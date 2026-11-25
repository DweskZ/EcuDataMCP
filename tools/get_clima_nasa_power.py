from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import nasa_power_client
from helpers.format_out import render_structured
from helpers.geo_data import canton_centroide, find_cantones
from helpers.logging import log_tool
from helpers.result_types import ResultadoSerie
from helpers.text_utils import strip_accents
from helpers.tool_meta import READ_ONLY

_MAX_TEXT_ROWS = 400


def _resolve_canton(canton: str, provincia: str) -> dict[str, Any]:
    """One canton from a name or INEC code; an ambiguous name lists the candidates."""
    query = canton.strip()
    matches = find_cantones(query=query, provincia=provincia.strip())
    exact = [
        c
        for c in matches
        if strip_accents(c["nombre"]) == strip_accents(query)
        or c["codigo"] == query.zfill(len(c["codigo"]))
    ]
    found = exact or matches
    if not found:
        raise ValueError(
            f"No encontré el cantón '{canton}'. Búscalo con lookup_ubicacion(nivel='canton')."
        )
    if len(found) > 1:
        options = ", ".join(f"{c['nombre']} ({c['provincia']}, {c['codigo']})" for c in found[:8])
        raise ValueError(
            f"'{canton}' coincide con {len(found)} cantones: {options}. "
            "Indica `provincia` o el código INEC de 4 dígitos."
        )
    return found[0]


def _locate(
    canton: str, provincia: str, latitud: float | None, longitud: float | None
) -> tuple[float, float, dict[str, Any] | None]:
    if (latitud is None) != (longitud is None):
        raise ValueError("Indica `latitud` y `longitud` juntas.")
    if latitud is not None and longitud is not None:
        if canton.strip():
            raise ValueError("Usa `canton` o `latitud`/`longitud`, no ambos.")
        return latitud, longitud, None
    if not canton.strip():
        raise ValueError("Indica un `canton` (nombre o código INEC) o `latitud` y `longitud`.")
    found = _resolve_canton(canton, provincia)
    centroid = canton_centroide(found["codigo"])
    if centroid is None:
        raise ValueError(
            f"El cantón {found['nombre']} ({found['codigo']}) no tiene centroide en la tabla "
            "local; pasa `latitud` y `longitud`."
        )
    return centroid["latitud"], centroid["longitud"], {
        "codigo": found["codigo"],
        "nombre": found["nombre"],
        "provincia": found["provincia"],
    }


def _text(data: dict[str, Any]) -> str:
    point = data["punto"]
    place = data.get("canton")
    where = (
        f"{place['nombre']} ({place['provincia']}), centroide {point['latitud']}, {point['longitud']}"
        if place
        else f"{point['latitud']}, {point['longitud']}"
    )
    lines = [
        f"NASA POWER — clima {data['frecuencia']} en {where}; altitud de la celda {point['elevacion_m']} m",
        (
            f"{data['desde']} a {data['hasta']}: {data['total_registros']} período(s), "
            f"último con dato {data['ultimo_periodo_con_dato']}"
        ),
        "",
    ]
    units = {v["clave"]: v["unidad"] for v in data["variables"]}
    for row in data["registros"][:_MAX_TEXT_ROWS]:
        values = ", ".join(
            f"{k} {row[k]} {units[k]}" if row[k] is not None else f"{k} sin dato" for k in units
        )
        lines.append(f"- {row['periodo']}: {values}")
    if data["total_registros"] > _MAX_TEXT_ROWS:
        lines.append(f"... y {data['total_registros'] - _MAX_TEXT_ROWS} más (usa format=json)")
    lines += ["", "Resumen del período:"]
    for clave, item in data["resumen"].items():
        extra = f", acumulado {item['acumulado_mm']} mm" if "acumulado_mm" in item else ""
        lines.append(
            f"- {clave}: media {item['media']}, mín {item['minimo']}, máx {item['maximo']} "
            f"{item['unidad']}{extra}"
        )
    lines += ["", data["nota"], f"Fuente: {data['url_fuente']}"]
    return "\n".join(lines)


def register_get_clima_nasa_power_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Clima por cantón o coordenada (NASA POWER)",
        description=(
            "Daily or monthly rainfall, temperature, humidity, wind and solar radiation for an "
            "Ecuadorian canton (its centroid) or a latitude/longitude, 1981 to a few days ago, "
            "from NASA POWER. A satellite and model grid, not weather stations."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_clima_nasa_power(
        canton: str = "",
        provincia: str = "",
        latitud: float | None = None,
        longitud: float | None = None,
        desde: str = "",
        hasta: str = "",
        frecuencia: Literal["mensual", "diaria"] = "mensual",
        variables: str = "lluvia,temperatura",
        format: Literal["text", "json"] = "text",
    ) -> Annotated[CallToolResult, ResultadoSerie]:
        """
        Climate series from NASA POWER for a canton or a point in Ecuador.

        NASA POWER computes meteorology from satellites and weather models on a
        grid with cells of tens of kilometres, so a canton gets the value of the
        cell around its centroid, not a station reading. The centroid is the
        geometric centre of the canton's polygon: for a coastal canton it can
        fall in the sea, and a canton with a valley and a páramo gets one value
        for both. For a precise place pass `latitud` and `longitud`. Use it for
        trends, seasonality and comparing regions; stations are more exact at
        one site.

        - frecuencia='mensual' (default): one value per month; rain in mm/day
          (a monthly mean), with the period's total in `resumen.acumulado_mm`.
          Default period: the last two full years plus the current one.
        - frecuencia='diaria': one value per day, at most 366 days per call.
          Default period: the last 30 days. The latest days are empty
          (NASA publishes with a lag of a few days) and are dropped from the
          end of `registros`; `ultimo_periodo_con_dato` says where it stops.
        - Variables (`variables`, comma-separated): lluvia (mm/día),
          temperatura, temp_max, temp_min (°C), humedad (%), viento (m/s),
          radiacion (MJ/m²/día). Default: lluvia,temperatura.
        - Data starts on 1981-01-01. `desde`/`hasta` accept AAAA, AAAA-MM or
          AAAA-MM-DD; `hasta` is held to today.
        - Sevilla Don Bosco (1413) and Juval (9006) have no centroid in the local
          table: pass their coordinates.

        Args:
            canton: Canton name or 4-digit INEC code (e.g. "Quito", "1701"). Use this or latitud/longitud.
            provincia: Optional province to tell apart cantons that share a name (Bolívar, Sucre...).
            latitud: Latitude in decimal degrees (south is negative), with longitud, instead of canton.
            longitud: Longitude in decimal degrees (west is negative), with latitud, instead of canton.
            desde: Start of the period: AAAA, AAAA-MM or AAAA-MM-DD. From 1981.
            hasta: End of the period, same format. Default today.
            frecuencia: mensual or diaria.
            variables: Comma-separated: lluvia, temperatura, temp_max, temp_min, humedad, viento, radiacion.
            format: text | json
        """
        try:
            lat, lon, place = _locate(canton, provincia, latitud, longitud)
            result = await nasa_power_client.get_clima(
                lat, lon, desde=desde, hasta=hasta, frecuencia=frecuencia, variables=variables
            )
        except Exception as e:
            raise ToolError(f"Error al consultar NASA POWER: {e}") from e
        if place:
            result = {"canton": place, **result}
        return render_structured(result, format, text_builder=_text)
