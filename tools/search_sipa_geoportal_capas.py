from mcp.server.fastmcp import FastMCP

from helpers import sipa_geoportal_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_sipa_geoportal_capas_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_sipa_geoportal_capas(
        query: str = "", solo_wfs: bool = False, categoria: str = "", format: str = "text"
    ) -> str:
        """
        Search the Ministry of Agriculture's geoportal (geoportal.agricultura.gob.ec,
        "Geoportal del Agro Ecuatoriano") layer catalog -- a GeoServer instance
        exposing Ecuador's agriculture spatial layers via WMS/WFS.

        277 layers confirmed live across 24 endpoints in 8 categories:
        registros (censos/registros administrativos, e.g. censo palmicultor,
        porcícola, avícola), demarcacion (zonificación agroecológica,
        económica-agroecológica, zonificación de pastos), infraestructura
        (industrias y servicios del agro), tematicas (inventario de
        recursos naturales, redes comerciales), cobertura (cobertura y uso
        de la tierra, estimaciones de cultivos), fisiografia (geomorfología,
        pendientes, relieve), sigtierras (catastro rural, cobertura de
        tierra, geomorfología, geopedología, zonificaciones -- SIGTIERRAS'
        national rural land program), and agroestadistica (riesgos
        agroclimáticos por cultivo, tipologías de territorio). 257 of the
        277 also expose WFS (real per-feature attribute data, confirmed
        live to return substantial results, e.g. a zonificación
        agroecológica layer with ~725,000 features and 20+ real attributes
        per polygon); the other 20 are WMS-only, either pure-raster stores
        or stores with WFS explicitly disabled server-side -- notably the
        rural cadastre (sigtierras/catastro_rural: predios, construcciones)
        and agroestadistica/tipologias_territorio_hih, both confirmed
        WFS-disabled ("Service WFS is disabled"). Filter to solo_wfs=True
        to see only the queryable ones. Use get_sipa_geoportal_capa_datos(id)
        to sample a WFS-enabled layer's actual attribute values.

        Args:
            query: Free text matched (accent-insensitive) against the
                layer's id, name, title, or abstract, e.g. "catastro",
                "zonificacion", "riesgo", "palmicultor". Empty returns all
                layers.
            solo_wfs: If True, only return layers with WFS (attribute data)
                available.
            categoria: Optional exact filter on one of the 8 top-level
                categories (registros, demarcacion, infraestructura,
                tematicas, cobertura, fisiografia, sigtierras,
                agroestadistica). Empty returns all categories.
            format: text | json
        """
        try:
            result = await sipa_geoportal_client.search_capas(
                query=query, solo_wfs=solo_wfs, categoria=categoria
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar el catálogo de capas del geoportal MAG: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            capas = data.get("capas") or []
            parts = [
                (
                    f"Geoportal MAG — {data['total']} capa(s) de {data['total_en_catalogo']} "
                    f"en el catálogo ({data['total_con_wfs']} con WFS/atributos)"
                ),
                f"Categorías: {', '.join(data.get('categorias') or [])}",
                "",
            ]
            if not capas:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for c in capas:
                wfs_tag = "WFS" if c.get("wfs_disponible") else "solo WMS"
                parts.append(f"- {c['id']} [{wfs_tag}]")
                if c.get("title") and c["title"] != c["name"]:
                    parts.append(f"  {c['title']}")
                if c.get("abstract"):
                    parts.append(f"  {c['abstract']}")
            parts.append("")
            parts.append(f"Fuente: {data.get('source')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)
