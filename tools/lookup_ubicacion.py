from mcp.server.fastmcp import FastMCP

from helpers.geo_data import find_provincias, list_provincias
from helpers.logging import log_tool


def register_lookup_ubicacion_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def lookup_ubicacion(query: str = "", region: str = "") -> str:
        """
        Look up Ecuador provinces (División Político-Administrativa / códigos INEC).

        Returns province code, name, capital and natural region. Useful before
        filtering datasets or contracts by territory. Without query, lists all 24
        provinces. Optional region filter: Sierra, Costa, Amazonía, Insular.

        Args:
            query: Province name, capital or INEC code (e.g. "Pichincha", "Guayaquil", "09")
            region: Optional natural region filter
        """
        if query.strip() or region.strip():
            matches = find_provincias(query=query.strip(), region=region.strip())
        else:
            matches = list_provincias()

        if not matches:
            return (
                f"No se encontraron provincias para query='{query}' region='{region}'. "
                "Ejemplos: Pichincha, Guayas, Loja, Galápagos, region=Costa."
            )

        parts = [
            "División Político-Administrativa del Ecuador (provincias / códigos INEC)",
            f"Resultados: {len(matches)}\n",
        ]
        for p in matches:
            parts.append(
                f"{p['codigo']}. {p['nombre']} — capital: {p['capital']} ({p['region']})"
            )
        parts.append("")
        parts.append(
            "Tip: usa el nombre de provincia en search_datasets / search_contratos / "
            "search_ecuador para filtrar por territorio. Para cantones/parroquias "
            "busca datasets DPA del INEC en el portal de datos abiertos."
        )
        return "\n".join(parts)
