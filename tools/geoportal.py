"""The geoportals (INAMHI, MAG, IGM, ARCONEL, CELEC) behind one search/query pair.

INAMHI's hydrometeorology geoportal and the Ministry of Agriculture's
"Geoportal del Agro" each had a layer-catalog search and a WFS feature
sampler with identical result shapes. `fuente` now picks the geoportal;
each layer carries `capa`, the id get_capa_geo_datos takes (INAMHI's
workspace-qualified name, MAG's categoria/store/name triple, a short curated
id for the ArcGIS sources). ARCONEL and CELEC are ArcGIS REST services
(helpers/arcgis_client.py) whose layers are mostly tables, so for them
get_capa_geo_datos also takes a `filtro` and an `offset` and returns up to
500 rows, or server-side sums with `sumar`/`agrupar`.
"""

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import arcgis_client, igm_client, inamhi_client, sipa_geoportal_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.result_types import ResultadoBusqueda, ResultadoTabla
from helpers.tool_meta import READ_ONLY

Fuente = Literal["inamhi", "mag", "igm", "arconel", "celec", "msp"]

_NOMBRES = {
    "inamhi": "Geoportal INAMHI",
    "mag": "Geoportal MAG (agro)",
    "igm": "Geoportal IGM (cartografía oficial)",
    "arconel": "ARCONEL (ArcGIS, SISDAT)",
    "celec": "CELEC EP (ArcGIS)",
    "msp": "Ministerio de Salud Pública (ArcGIS)",
}
_ARCGIS = ("arconel", "celec", "msp")


async def _search(fuente: str, query: str, solo_wfs: bool, categoria: str) -> dict[str, Any]:
    if fuente in _ARCGIS:
        result = await arcgis_client.search_capas(fuente, query=query)
        return {**result, "fuente": fuente}
    if fuente == "inamhi":
        result = await inamhi_client.search_capas(query=query, solo_wfs=solo_wfs)
        id_key = "name"
    elif fuente == "igm":
        result = await igm_client.search_capas(query=query, servicio=categoria)
        id_key = "name"
    else:
        result = await sipa_geoportal_client.search_capas(
            query=query, solo_wfs=solo_wfs, categoria=categoria
        )
        id_key = "id"
    capas = [{"capa": c[id_key], **c} for c in result.get("capas") or []]
    return {**result, "fuente": fuente, "capas": capas}


async def _sample(
    fuente: str,
    capa: str,
    count: int,
    filtro: str,
    offset: int,
    agrupar: str = "",
    sumar: str = "",
) -> dict[str, Any]:
    if fuente in _ARCGIS:
        result = await arcgis_client.get_layer_features(
            fuente, capa, count=count, filtro=filtro, offset=offset, agrupar=agrupar, sumar=sumar
        )
        return {**result, "fuente": fuente}
    if filtro or offset or agrupar or sumar:
        raise ValueError(
            "filtro, offset, agrupar y sumar solo aplican a las fuentes arconel, celec y msp."
        )
    client = {"inamhi": inamhi_client, "igm": igm_client}.get(fuente, sipa_geoportal_client)
    result = await client.get_layer_features(capa, count=count)
    return {**result, "fuente": fuente}


def register_geoportal_tools(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Buscar capas de un geoportal (INAMHI, MAG, IGM, ARCONEL, CELEC o MSP)",
        description=(
            "Search layers of a geoportal: inamhi (rainfall normals, anomalies, "
            "watersheds), mag (agro zoning, land cover, rural cadastre), igm "
            "(official base cartography 1:1M/1:50k/1:25k), arconel (energy balance, "
            "billing, production by plant 1999-2026, lighting, grid) or celec "
            "(plants, transmission) or msp (health facilities, indicators)."
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
    ) -> Annotated[CallToolResult, ResultadoBusqueda]:
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
        - igm: Instituto Geográfico Militar, www.geoportaligm.gob.ec, 737
          open WFS layers of official base cartography: 68 national 1:1M
          (nacional_2024: boundaries, settlements, roads, rivers, contours,
          EEZ), 505 at 1:50,000 and 164 at 1:25,000. The reserved
          igm_reservada workspace is left out. `categoria` picks the scale:
          nacional, 50k or 25k.
        - arconel: ARCONEL's SISDAT layers on ArcGIS (12 curated):
          balance_energia (energy available, technical/non-technical losses
          and billed energy by distributor and month, Jan 1999-Apr 2024),
          facturacion (customers, billed MWh/USD, collection and subsidies
          by distributor, month and consumption group, 1999-2025),
          produccion_centrales and combustibles_centrales (gross/net MWh and
          fuel use by plant and month, Jan 1999-Aug 2026; May-Dec 2024 is
          missing at the source), alumbrado_publico (luminaires by
          distributor, province and lamp type), centrales (355 plants),
          centrales_sisdat (730-plant register), lineas_transmision,
          subestaciones, subestaciones_distribucion, lineas_subtransmision,
          areas_servicio.
        - msp: Ministerio de Salud Pública's ArcGIS Online layers (9 curated):
          establecimientos_rpis (6,411 public-network facilities, 71 fields),
          establecimientos_msp, indicadores_ssr (18 sexual and reproductive
          health indicators by canton, year and age band, 2018-2026),
          atenciones and egresos_hospitalarios by facility and year (2019
          on), fecundidad, vacunacion_covid_cantonal (Dec 2022), areas_eais,
          categorizacion_distritos. Same filtro/sumar/agrupar as arconel.
        - celec: CELEC EP's ArcGIS portal, curated to its 40 generation plants
          and the March 2025 transmission network (snt_*). Its Survey123
          forms and results are excluded on purpose.

        Each layer carries `capa`, the id to pass to get_capa_geo_datos.
        GeoServer layers carry `wfs_disponible` (raster/WMS-only layers have
        no attribute data); every ArcGIS layer is queryable.

        Args:
            fuente: inamhi, mag, igm, arconel, celec or msp.
            query: Free text matched (accent-insensitive) against the layer's
                id, name, title or abstract. Empty returns all layers.
            solo_wfs: Only return layers with WFS (attribute data). Ignored
                for arconel, celec and msp.
            categoria: mag: one of its 8 categories. igm: scale (nacional, 50k
                or 25k). Ignored for the other sources.
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
            "GeoServer (inamhi, mag, igm): a sample of up to 20 features. ArcGIS "
            "(arconel, celec, msp): up to 500 rows with a SQL filtro and offset, or "
            "server-side sums by group (sumar, agrupar)."
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
        agrupar: str = "",
        sumar: str = "",
        format: Literal["text", "json"] = "text",
    ) -> Annotated[CallToolResult, ResultadoTabla]:
        """
        Fetch one geoportal layer's feature attributes.

        inamhi, mag, igm: WFS GetFeature (JSON), a small sample to confirm what a
        vector layer contains; no filters. Layers without WFS (rasters such
        as INAMHI's wrf_tiempo_* grids, or MAG stores with WFS disabled)
        raise an error.

        arconel, celec, msp: an ArcGIS REST query. `filtro` is a SQL where clause
        on the layer's fields (listed in `campos`), e.g. "Anio = 2024 AND
        IdMes = 4" or "Empresa LIKE 'CNEL%'"; `total_features_en_capa` is
        the count matching it and `hay_mas` says whether to page on with
        `offset`. Dates come back as ISO dates. With `sumar` the server
        adds up those numeric fields per `agrupar` group instead of
        returning rows, e.g. capa="produccion_centrales",
        sumar="EnergiaNeta", agrupar="AnioProduccion,TipoCentral" gives
        yearly net MWh by plant type in one call; `filas` is the rows per
        group and `grupos` is paged with count/offset.

        Geometry coordinates are dropped from the output; only the geometry
        type is kept.

        Args:
            fuente: inamhi, mag, igm, arconel, celec or msp.
            capa: The layer's `capa` from search_capas_geo (INAMHI:
                "geonode:..." name; IGM: "workspace:name", e.g.
                nacional_2024:poblado_p_2024; MAG: "categoria/store/name"; ArcGIS: the
                short id, e.g. balance_energia).
            count: Features to fetch: 1-20 for inamhi/mag/igm, 1-500 for
                arconel/celec/msp (default 5).
            filtro: arconel/celec/msp only: SQL where clause; empty for all rows.
            offset: arconel/celec/msp only: rows (or groups) to skip when paging.
            agrupar: arconel/celec/msp only: comma-separated fields to group by;
                needs `sumar`.
            sumar: arconel/celec/msp only: comma-separated numeric fields to sum.
            format: text | json
        """
        try:
            result = await _sample(fuente, capa, count, filtro, offset, agrupar, sumar)
        except Exception as e:
            raise ToolError(f"Error al consultar la capa '{capa}' de {fuente}: {e}") from e

        def to_text(data: dict) -> str:
            if "grupos" in data:
                parts = [
                    f"{data['capa']} ({data.get('titulo')}) — suma de "
                    f"{', '.join(data['sumar'])}"
                    + (f" por {', '.join(data['agrupar'])}" if data["agrupar"] else "")
                    + f": {data['grupos_devueltos']} de {data['total_grupos']} grupo(s)"
                ]
                if data.get("filtro") and data["filtro"] != "1=1":
                    parts.append(f"Filtro: {data['filtro']}")
                if data.get("hay_mas"):
                    siguiente = data["offset"] + data["grupos_devueltos"]
                    parts.append(f"Hay más grupos: repite con offset={siguiente}.")
                parts.append("")
                for g in data["grupos"]:
                    parts.append("- " + ", ".join(f"{k}: {v}" for k, v in g.items()))
                parts += ["", f"Consulta: {data.get('url_consulta')}"]
                return "\n".join(parts)
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
