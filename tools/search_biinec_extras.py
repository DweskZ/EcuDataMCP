from mcp.server.fastmcp import FastMCP

from helpers.biinec_extras import BIINEC_URL, search_extras
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_biinec_extras_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_biinec_extras(query: str = "", format: str = "text") -> str:
        """
        Check INEC's BIINEC ("Banco de Datos Abiertos") for data not found in
        search_anda or search_inec_estadisticas.

        Last resort for INEC queries: BIINEC (aplicaciones3.ecuadorencifras.gob.ec)
        mostly duplicates ANDA and Ecuador en Cifras, so this does NOT scrape or
        search BIINEC live — it's a small, manually-verified list of the handful
        of registries confirmed to exist only there (environmental/administrative
        modules, e.g. hazardous waste in health facilities, ENEMDU/ECV
        environmental modules). If your query matches nothing here, that does
        NOT mean BIINEC has nothing — it means it wasn't worth automating; search
        the site's own search box directly instead.

        Args:
            query: Free text matched against the registry's name/description
                (accent-insensitive). Empty returns the full curated list.
            format: text | json
        """
        matches = search_extras(query)

        payload = {
            "query": query or None,
            "total": len(matches),
            "resultados": matches,
            "biinec_url": BIINEC_URL,
        }

        def to_text(data: dict) -> str:
            resultados = data.get("resultados") or []
            if not resultados:
                return (
                    f"No hay nada en la lista curada de BIINEC para '{data['query']}'. "
                    "Esto NO significa que BIINEC no tenga el dato — solo que no está en "
                    "este conjunto pequeño y verificado a mano. Búscalo directamente en "
                    f"{data['biinec_url']} (cuadro de búsqueda arriba, o navega por rama: "
                    "Sociodemográficas y Sociales / Económicas / Ambiente y Otras "
                    "Estadísticas)."
                )
            parts = [f"{len(resultados)} registro(s) exclusivo(s) de BIINEC encontrados:", ""]
            for i, r in enumerate(resultados, 1):
                parts.append(f"{i}. {r['nombre']}")
                parts.append(f"   Rama: {r['rama']} > {r['categoria']}")
                parts.append(f"   {r['descripcion']}")
                if r.get("anios_vistos"):
                    parts.append(f"   Años vistos: {', '.join(r['anios_vistos'])}")
                if r.get("formatos_confirmados"):
                    parts.append(f"   Formatos confirmados: {', '.join(r['formatos_confirmados'])}")
                parts.append(f"   Verificado: {r.get('verificado')}")
                parts.append("")
            parts.append(
                f"No hay descarga directa: entra a {data['biinec_url']}, selecciona la rama y "
                "categoría de arriba, busca el nombre exacto en la tabla de operaciones, "
                "elige año y período, y usa el botón Descargar junto al archivo que necesites."
            )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
