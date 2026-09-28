"""The two GeoServer geoportals (INAMHI, MAG) behind one search/sample pair.

INAMHI's hydrometeorology geoportal and the Ministry of Agriculture's
"Geoportal del Agro" each had a layer-catalog search and a WFS feature
sampler with identical result shapes. `fuente` now picks the geoportal;
each layer carries `capa`, the id get_capa_geo_datos takes (INAMHI's
workspace-qualified name, MAG's categoria/store/name triple).
"""

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import inamhi_client, sipa_geoportal_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY

Fuente = Literal["inamhi", "mag"]

_NOMBRES = {"inamhi": "Geoportal INAMHI", "mag": "Geoportal MAG (agro)"}


async def _search(fuente: str, query: str, solo_wfs: bool, categoria: str) -> dict[str, Any]:
    if fuente == "inamhi":
        result = await inamhi_client.search_capas(query=query, solo_wfs=solo_wfs)
        id_key = "name"
    else:
        result = await sipa_geoportal_client.search_capas(
            query=query, solo_wfs=solo_wfs, categoria=categoria
        )
        id_key = "id"
    capas = [{"capa": c[id_key], **c} for c in result.get("capas") or []]
    return {**result, "fuente": fuente, "capas": capas}


async def _sample(fuente: str, capa: str, count: int) -> dict[str, Any]:
    client = inamhi_client if fuente == "inamhi" else sipa_geoportal_client
    result = await client.get_layer_features(capa, count=count)
    return {**result, "fuente": fuente}


def register_geoportal_tools(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Buscar capas de un geoportal (INAMHI o MAG)",
        description=(
            "Search layers of a GeoServer geoportal: inamhi (rainfall normals and "
            "anomalies, WRF forecast grids, watersheds) or mag (agro zoning, land "
            "cover, agricultural censuses, rural cadastre, agroclimatic risk). "
            "solo_wfs=true keeps layers with attribute data."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def search_capas_geo(
        fuente: Fuente,
        query: str = "",
        solo_wfs: bool = False,
        categoria: str = "",
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Search one geoportal's layer catalog (WMS/WFS).

        - inamhi: geoservicios.inamhi.gob.ec, 222 layers: monthly/annual
          precipitation normals (1985-2015), ~180 dated daily rainfall
          anomaly composites, WRF model grids, watersheds and boundaries.
          Polygon-aggregated, not per-station series: raw INAMHI station
          data isn't exposed there. 199 layers have WFS.
        - mag: geoportal.agricultura.gob.ec, 277 layers in 8 categorias
          (registros, demarcacion, infraestructura, tematicas, cobertura,
          fisiografia, sigtierras, agroestadistica). 257 have WFS; the rural
          cadastre (sigtierras/catastro_rural) and
          agroestadistica/tipologias_territorio_hih have WFS disabled.

        Each layer carries `capa`, the id to pass to get_capa_geo_datos, and
        `wfs_disponible`; raster/WMS-only layers have no attribute data.

        Args:
            fuente: inamhi or mag.
            query: Free text matched (accent-insensitive) against the layer's
                id, name, title or abstract. Empty returns all layers.
            solo_wfs: Only return layers with WFS (attribute data).
            categoria: Only for fuente="mag": one of its 8 categories. Ignored
                for inamhi.
            format: text | json
        """
        try:
            result = await _search(fuente, query, solo_wfs, categoria)
        except Exception as e:
            raise ToolError(f"Error al consultar el catálogo de capas de {fuente}: {e}") from e

        def to_text(data: dict) -> str:
            capas = data["capas"]
            parts = [
                (
                    f"{_NOMBRES[data['fuente']]} — {data['total']} capa(s) de "
                    f"{data['total_en_catalogo']} en el catálogo "
                    f"({data['total_con_wfs']} con WFS/atributos)"
                ),
            ]
            if data.get("categorias"):
                parts.append(f"Categorías: {', '.join(data['categorias'])}")
            parts.append("")
            if not capas:
                parts.append("Sin resultados.")
            for c in capas:
                wfs_tag = "WFS" if c.get("wfs_disponible") else "solo WMS"
                parts.append(f"- {c['capa']} [{wfs_tag}]")
                if c.get("title") and c["title"] != c.get("name"):
                    parts.append(f"  {c['title']}")
                if c.get("abstract"):
                    parts.append(f"  {c['abstract']}")
            parts += ["", f"Fuente: {data.get('url_wms_capabilities') or data.get('source')}"]
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

    @mcp.tool(
        title="Ver muestra de datos de una capa de geoportal",
        description=(
            "Sample up to 20 features' attributes from a WFS-enabled layer (capa "
            "from search_capas_geo). A preview, not a spatial query: no bbox or "
            "filters, and geometry is dropped."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_capa_geo_datos(
        fuente: Fuente,
        capa: str,
        count: int = 5,
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Fetch a small sample of one geoportal layer's feature attributes.

        Uses WFS GetFeature (JSON) to confirm what a vector layer actually
        contains. Layers without WFS (rasters such as INAMHI's wrf_tiempo_*
        grids, or MAG stores with WFS disabled) raise an error. Geometry
        coordinates are dropped from the output; only the geometry type is
        kept.

        Args:
            fuente: inamhi or mag.
            capa: The layer's `capa` from search_capas_geo (INAMHI:
                "geonode:..." name; MAG: "categoria/store/name").
            count: Number of features to fetch (1-20, default 5).
            format: text | json
        """
        try:
            result = await _sample(fuente, capa, count)
        except Exception as e:
            raise ToolError(f"Error al consultar la capa '{capa}' de {fuente}: {e}") from e

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
            for f in features:
                parts.append(f"- {f.get('id')} [{f.get('tipo_geometria')}]")
                for k, v in (f.get("propiedades") or {}).items():
                    parts.append(f"    {k}: {v}")
            parts += ["", f"Consulta: {data.get('url_consulta')}"]
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)
