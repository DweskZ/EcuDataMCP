"""The geoportals (INAMHI, MAG, ARCONEL, CELEC) behind one search/query pair.

INAMHI's hydrometeorology geoportal and the Ministry of Agriculture's
"Geoportal del Agro" each had a layer-catalog search and a WFS feature
sampler with identical result shapes. `fuente` now picks the geoportal;
each layer carries `capa`, the id get_capa_geo_datos takes (INAMHI's
workspace-qualified name, MAG's categoria/store/name triple, a short curated
id for the ArcGIS sources). ARCONEL and CELEC are ArcGIS REST services
(helpers/arcgis_client.py) whose layers are mostly tables, so for them
get_capa_geo_datos also takes a `filtro` and an `offset` and returns up to
500 rows.
"""

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import arcgis_client, inamhi_client, sipa_geoportal_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY

Fuente = Literal["inamhi", "mag", "arconel", "celec"]

_NOMBRES = {
    "inamhi": "Geoportal INAMHI",
    "mag": "Geoportal MAG (agro)",
    "arconel": "ARCONEL (ArcGIS, SISDAT)",
    "celec": "CELEC EP (ArcGIS)",
}
_ARCGIS = ("arconel", "celec")


async def _search(fuente: str, query: str, solo_wfs: bool, categoria: str) -> dict[str, Any]:
    if fuente in _ARCGIS:
        result = await arcgis_client.search_capas(fuente, query=query)
        return {**result, "fuente": fuente}
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


async def _sample(fuente: str, capa: str, count: int, filtro: str, offset: int) -> dict[str, Any]:
    if fuente in _ARCGIS:
        result = await arcgis_client.get_layer_features(
            fuente, capa, count=count, filtro=filtro, offset=offset
        )
        return {**result, "fuente": fuente}
    if filtro or offset:
        raise ValueError("filtro y offset solo aplican a las fuentes arconel y celec.")
    client = inamhi_client if fuente == "inamhi" else sipa_geoportal_client
    result = await client.get_layer_features(capa, count=count)
    return {**result, "fuente": fuente}


def register_geoportal_tools(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Buscar capas de un geoportal (INAMHI, MAG, ARCONEL o CELEC)",
        description=(
            "Search layers of a geoportal: inamhi (rainfall normals and anomalies, "
            "WRF grids, watersheds), mag (agro zoning, land cover, agricultural "
            "censuses, rural cadastre), arconel (distributor energy balance and "
            "billing 1999-2025, power plants, grid) or celec (CELEC plants, "
            "transmission network)."
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
    ) -> CallToolResult:
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
        - arconel: ARCONEL's SISDAT layers on ArcGIS (6 curated):
          balance_energia (energy available, technical/non-technical losses
          and billed energy by distributor and month, Jan 1999-Apr 2024),
          facturacion (customers, billed MWh/USD, collection and subsidies
          by distributor, month and consumption group, 1999-2025), centrales
          (355 plants), lineas_transmision, subestaciones, areas_servicio.
          Per-plant monthly production lives on ARCONEL's own ArcGIS server,
          which did not answer in October 2026, and is not listed.
        - celec: CELEC EP's ArcGIS portal, curated to its 40 generation plants
          and the March 2025 transmission network (snt_*). Its Survey123
          forms and results are excluded on purpose.

        Each layer carries `capa`, the id to pass to get_capa_geo_datos.
        GeoServer layers carry `wfs_disponible` (raster/WMS-only layers have
        no attribute data); every ArcGIS layer is queryable.

        Args:
            fuente: inamhi, mag, arconel or celec.
            query: Free text matched (accent-insensitive) against the layer's
                id, name, title or abstract. Empty returns all layers.
            solo_wfs: Only return layers with WFS (attribute data). Ignored
                for arconel and celec.
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
            resumen = (
                f"{_NOMBRES[data['fuente']]} — {data['total']} capa(s) de "
                f"{data['total_en_catalogo']} en el catálogo"
            )
            if "total_con_wfs" in data:
                resumen += f" ({data['total_con_wfs']} con WFS/atributos)"
            parts = [resumen]
            if data.get("categorias"):
                parts.append(f"Categorías: {', '.join(data['categorias'])}")
            parts.append("")
            if not capas:
                parts.append("Sin resultados.")
            for c in capas:
                if c.get("tipo_servicio"):
                    tag = c["tipo_servicio"]
                else:
                    tag = "WFS" if c.get("wfs_disponible") else "solo WMS"
                parts.append(f"- {c['capa']} [{tag}]")
                title = c.get("title") or c.get("titulo")
                if title and title != c.get("name"):
                    parts.append(f"  {title}")
                if c.get("abstract") or c.get("descripcion"):
                    parts.append(f"  {c.get('abstract') or c.get('descripcion')}")
            parts += ["", f"Fuente: {data.get('url_wms_capabilities') or data.get('source')}"]
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

    @mcp.tool(
        title="Ver datos de una capa de geoportal",
        description=(
            "Attributes of a layer from search_capas_geo, geometry dropped. "
            "GeoServer (inamhi, mag): a sample of up to 20 features. ArcGIS "
            "(arconel, celec): up to 500 rows with a SQL filtro and offset."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_capa_geo_datos(
        fuente: Fuente,
        capa: str,
        count: int = 5,
        filtro: str = "",
        offset: int = 0,
        format: Literal["text", "json"] = "text",
    ) -> CallToolResult:
        """
        Fetch one geoportal layer's feature attributes.

        inamhi, mag: WFS GetFeature (JSON), a small sample to confirm what a
        vector layer contains; no filters. Layers without WFS (rasters such
        as INAMHI's wrf_tiempo_* grids, or MAG stores with WFS disabled)
        raise an error.

        arconel, celec: an ArcGIS REST query. `filtro` is a SQL where clause
        on the layer's fields (listed in `campos`), e.g. "Anio = 2024 AND
        IdMes = 4" or "Empresa LIKE 'CNEL%'"; `total_features_en_capa` is
        the count matching it and `hay_mas` says whether to page on with
        `offset`. Dates come back as ISO dates.

        Geometry coordinates are dropped from the output; only the geometry
        type is kept.

        Args:
            fuente: inamhi, mag, arconel or celec.
            capa: The layer's `capa` from search_capas_geo (INAMHI:
                "geonode:..." name; MAG: "categoria/store/name"; ArcGIS: the
                short id, e.g. balance_energia).
            count: Features to fetch: 1-20 for inamhi/mag, 1-500 for
                arconel/celec (default 5).
            filtro: arconel/celec only: SQL where clause; empty for all rows.
            offset: arconel/celec only: rows to skip when paging.
            format: text | json
        """
        try:
            result = await _sample(fuente, capa, count, filtro, offset)
        except Exception as e:
            raise ToolError(f"Error al consultar la capa '{capa}' de {fuente}: {e}") from e

        def to_text(data: dict) -> str:
            features = data.get("features") or []
            parts = [
                (
                    f"{data['capa']} ({data.get('titulo')}) — {data['features_devueltas']} "
                    f"feature(s) de cerca de {data.get('total_features_en_capa')} en la capa"
                ),
            ]
            if data.get("filtro") and data["filtro"] != "1=1":
                parts.append(f"Filtro: {data['filtro']}")
            if data.get("hay_mas"):
                siguiente = data["offset"] + data["features_devueltas"]
                parts.append(f"Hay más filas: repite con offset={siguiente}.")
            parts.append("")
            if not features:
                parts.append("Sin features devueltas.")
            for f in features:
                parts.append(f"- {f.get('id')} [{f.get('tipo_geometria')}]")
                for k, v in (f.get("propiedades") or {}).items():
                    parts.append(f"    {k}: {v}")
            parts += ["", f"Consulta: {data.get('url_consulta')}"]
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)
