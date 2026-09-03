from mcp.server.fastmcp import FastMCP

from helpers import sipa_resumen_indicadores_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_sipa_resumen_indicadores_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_sipa_resumen_indicadores(anio: int, format: str = "text") -> str:
        """
        List the direct monthly PDF links for one year of SIPA's (Ministerio
        de Agricultura) "Resumen de Indicadores" report — reached from the
        "Indicadores Sectoriales" tablero dinámico page
        (sipa.agricultura.gob.ec/index.php/sipa-estadisticas/tablero-dinamico/indicadores-sectoriales)
        via its "Resumen de Indicadores" icon.

        Confirmed live 2018-2026. Each year is a separate page; the earliest
        (2018) is at the bare URL with no year suffix. Filename conventions
        differ across years, so URLs always come straight from the scraped
        page, never constructed. The other items reachable from the same
        "Indicadores Sectoriales" page ("Indicador Agroeconómico",
        "Indicador Agrosocial", the rice "Rendimientos Objetivos"
        dashboard) are genuine Tableau Server embeds (bi.mag.gob.ec), and
        "Panorama Agroeconómico", "Atlas Agroeconómico", and "Hoja de
        Balance de Alimentos" are each a JS flipbook (fliphtml5.com) with no
        direct file found — none of those are covered by this tool.

        Args:
            anio: Year, e.g. 2025. Earliest confirmed live: 2018.
            format: text | json
        """
        try:
            result = await sipa_resumen_indicadores_client.get_resumen_indicadores(anio)
        except ValueError as e:
            return render_output(
                {"error": str(e), "anio": anio},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "anio": anio},
                format,
                text_builder=lambda d: (
                    f"Error al obtener el Resumen de Indicadores de SIPA: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            meses = data.get("meses") or []
            parts = [
                f"SIPA — Resumen de Indicadores {data.get('anio')}",
                f"URL: {data.get('url')}",
                "",
            ]
            if not meses:
                parts.append("No se encontraron archivos para este año.")
            else:
                parts.append(f"{len(meses)} mes(es):")
                for m in meses:
                    parts.append(f"- {m.get('mes')} [{m.get('formato')}]")
                    parts.append(f"   {m.get('url')}")
            anios_disponibles = data.get("anios_disponibles") or []
            if anios_disponibles:
                parts.append("")
                parts.append(
                    "Años vistos en la navegación de esta página (puede no estar "
                    "completa): " + ", ".join(str(a) for a in anios_disponibles)
                )
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)
