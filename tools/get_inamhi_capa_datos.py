from mcp.server.fastmcp import FastMCP

from helpers import inamhi_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_inamhi_capa_datos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_inamhi_capa_datos(
        layer_name: str, count: int = 5, format: str = "text"
    ) -> str:
        """
        Fetch a small, bounded sample of a WFS-enabled INAMHI geoportal layer's
        real feature attributes (via WFS GetFeature, JSON output) -- confirms
        and previews what a vector layer actually contains.

        Use search_inamhi_capas first to find layer names and check
        wfs_disponible=True (raster-only layers, e.g. the wrf_tiempo_*
        weather-model grids or the precipitation climate-normal grids, have
        no attribute data and will raise an error here). This is a sample
        tool, not a spatial query engine: no bbox/CQL filtering, no
        reprojection, geometry coordinates are dropped from the output
        (only the geometry type is kept) to keep the response small.

        Args:
            layer_name: Layer name as returned by search_inamhi_capas,
                including the "geonode:" workspace prefix, e.g.
                "geonode:regiones_precip", "geonode:cuencas_inamhi".
            count: Number of features to fetch (1-20, default 5).
            format: text | json
        """
        try:
            result = await inamhi_client.get_layer_features(layer_name, count=count)
        except Exception as e:
            return render_output(
                {"error": str(e), "capa": layer_name},
                format,
                text_builder=lambda d: (
                    f"Error al consultar la capa '{d['capa']}' de INAMHI: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            features = data.get("features") or []
            parts = [
                (
                    f"{data['capa']} ({data.get('titulo')}) — {data['features_devueltas']} "
                    f"feature(s) de cerca de {data.get('total_features_en_capa')} en la capa"
                ),
                "",
            ]
            if not features:
                parts.append("Sin features devueltas.")
                return "\n".join(parts)
            for f in features:
                parts.append(f"- {f.get('id')} [{f.get('tipo_geometria')}]")
                for k, v in (f.get("propiedades") or {}).items():
                    parts.append(f"    {k}: {v}")
            parts.append("")
            parts.append(f"Consulta: {data.get('url_consulta')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)
