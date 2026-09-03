from mcp.server.fastmcp import FastMCP

from helpers import inamhi_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_inamhi_capas_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_inamhi_capas(
        query: str = "", solo_wfs: bool = False, format: str = "text"
    ) -> str:
        """
        Search INAMHI's geoportal (geoservicios.inamhi.gob.ec) layer catalog --
        a GeoNode-backed GeoServer exposing Ecuador's meteorology/hydrology
        institute's spatial layers via WMS/WFS.

        222 layers confirmed live: monthly/annual precipitation climate
        normals (1985-2015), ~180 dated daily rainfall-anomaly composites
        ("anomalias_DDmonYYYY"), WRF numerical weather model output grids
        (precipitación, temperatura, humedad, presión, viento), watershed
        and administrative boundaries (cuencas, provincias, cantones,
        parroquias), and a handful of named regional layers. 199 of the 222
        also expose WFS (real per-feature attribute data, e.g. zonal
        precipitation/anomaly statistics per polygon); the other 23 are
        raster-only (map-tile/GetMap access only, no attribute data) --
        filter to solo_wfs=True to see only the queryable ones. Use
        get_inamhi_capa_datos(layer_name) to sample a WFS-enabled layer's
        actual attribute values.

        IMPORTANT: this catalog does NOT include a per-station raw
        precipitación/temperatura/caudal observation layer -- everything
        here is polygon-aggregated (zonal statistics, boundaries), not a
        station time series. If you need raw INAMHI station data, it isn't
        exposed via this geoportal today.

        Args:
            query: Free text matched (accent-insensitive) against the
                layer's name, title, or abstract, e.g. "precipitacion",
                "cuencas", "anomalias". Empty returns all layers.
            solo_wfs: If True, only return layers with WFS (attribute data)
                available.
            format: text | json
        """
        try:
            result = await inamhi_client.search_capas(query=query, solo_wfs=solo_wfs)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar el catálogo de capas de INAMHI: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            capas = data.get("capas") or []
            parts = [
                (
                    f"Geoportal INAMHI — {data['total']} capa(s) de {data['total_en_catalogo']} "
                    f"en el catálogo ({data['total_con_wfs']} con WFS/atributos)"
                ),
                "",
            ]
            if not capas:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for c in capas:
                wfs_tag = "WFS" if c.get("wfs_disponible") else "solo WMS (ráster)"
                parts.append(f"- {c['name']} [{wfs_tag}]")
                if c.get("title") and c["title"] != c["name"]:
                    parts.append(f"  {c['title']}")
                if c.get("abstract"):
                    parts.append(f"  {c['abstract']}")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_wms_capabilities')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)
