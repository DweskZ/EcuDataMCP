from mcp.server.fastmcp import FastMCP

from helpers import ineval_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_ineval_familias_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_ineval_familias(format: str = "text") -> str:
        """
        List INEVAL (Instituto Nacional de Evaluación Educativa) evaluation
        families with a real "Bases de Datos" download page
        (evaluaciones.evaluacion.gob.ec/BI/) — a completely different
        institution from SENESCYT/MINEDUC.

        Nine families are published: Ser Bachiller (2013-2020, merged with
        ENES for university admissions in 2017), Ser Estudiante (plus the
        "en la Infancia", "en la Mitad del Mundo", and "Galápagos"
        variants), Ser Maestro (plus "Recategorización"), Ser Profesional,
        and Llece (the international ERCE/SERCE/TERCE evaluation rounds).

        IMPORTANT: the site's top navigation also links to informational
        pages (e.g. "historico-ser-bachiller") that share the family name
        but carry no downloads at all — only the family keys returned here
        (sourced from the site's own "Categoría Bases de Datos" hub) point
        at pages with real files. Follow up with
        get_ineval_familia_archivos(familia) for one family's file listing.

        Args:
            format: text | json
        """
        familias = ineval_client.list_familias()

        def to_text(data: list[dict]) -> str:
            parts = [f"Familias de evaluación Ineval — {len(data)} familia(s):", ""]
            for f in data:
                parts.append(f"- {f['familia']}: {f['nombre']}")
                parts.append(f"  {f['url']}")
            return "\n".join(parts)

        return render_output(familias, format, text_builder=to_text)
