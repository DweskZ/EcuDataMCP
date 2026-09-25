from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from helpers import ineval_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_list_ineval_familias_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Listar familias de evaluación de INEVAL", annotations=READ_ONLY)
    @log_tool
    async def list_ineval_familias(format: Literal["text", "json"] = "text") -> dict[str, Any]:
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
        payload = {"total": len(familias), "familias": familias}

        def to_text(data: dict) -> str:
            rows = data["familias"]
            parts = [f"Familias de evaluación Ineval — {len(rows)} familia(s):", ""]
            for f in rows:
                parts.append(f"- {f['familia']}: {f['nombre']}")
                parts.append(f"  {f['url']}")
            return "\n".join(parts)

        return render_structured(payload, format, text_builder=to_text)
