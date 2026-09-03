from mcp.server.fastmcp import FastMCP

from helpers import sipa_geoportal_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_sipa_geoportal_capa_datos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_sipa_geoportal_capa_datos(
        layer_id: str, count: int = 5, format: str = "text"
    ) -> str:
        """
        Fetch a small, bounded sample of a WFS-enabled Ministry of Agriculture
        geoportal layer's real feature attributes (via WFS GetFeature, JSON
        output) -- confirms and previews what a vector layer actually contains.

        Use search_sipa_geoportal_capas first to find layer ids and check
        wfs_disponible=True (raster-only stores, e.g. tematicas/Rraster or
        fisiografia/Rraster, and stores with WFS explicitly disabled
        server-side, e.g. sigtierras/catastro_rural or agroestadistica/
        tipologias_territorio_hih, have no attribute data and will raise an
        error here). This is a sample tool, not a spatial query engine: no
        bbox/CQL filtering, no reprojection, geometry coordinates are
        dropped from the output (only the geometry type is kept) to keep
        the response small.

        Args:
            layer_id: Layer id as returned by search_sipa_geoportal_capas,
                the "categoria/store/name" triple, e.g.
                "demarcacion/E25k/vw_hg000_zae_cafe_arabigo",
                "agroestadistica/riesgos_agroclimaticos/vw_02c3_multiriesgo_forestal".
            count: Number of features to fetch (1-20, default 5).
            format: text | json
        """
        try:
            result = await sipa_geoportal_client.get_layer_features(layer_id, count=count)
        except Exception as e:
            return render_output(
                {"error": str(e), "capa": layer_id},
                format,
                text_builder=lambda d: (
                    f"Error al consultar la capa '{d['capa']}' del geoportal MAG: {d['error']}"
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
