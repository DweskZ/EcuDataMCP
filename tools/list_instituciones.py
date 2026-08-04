from mcp.server.fastmcp import FastMCP

from helpers import gobec_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_instituciones_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_instituciones(
        query: str = "", page: int = 1, format: str = "text"
    ) -> str:
        """
        List or search public institutions registered on Ecuador's gob.ec portal.

        If a query is provided, searches across all institutions by name or acronym.
        Without a query, returns a paginated list.

        Common institutions: SRI (ID: 8), Registro Civil (ID: 23), ANT (ID: 62),
        Cancillería (ID: 16), IESS (ID: 5), Ministerio de Salud, INEC, BCE.

        Args:
            query: Optional search term (e.g. "SRI", "salud", "rentas")
            page: Page number (1-based, default: 1, only used without query)
            format: text | json
        """
        try:
            if query:
                instituciones = await gobec_client.find_institucion(query)
            else:
                api_page = max(page - 1, 0)
                instituciones = await gobec_client.list_instituciones(page=api_page)
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al listar instituciones: {d['error']}",
            )

        rows = instituciones[:30]
        payload = {
            "query": query or None,
            "page": page,
            "total": len(instituciones),
            "showing": len(rows),
            "results": [
                {
                    "institucion_id": inst.get("institucion_id"),
                    "nombre": inst.get("institucion", inst.get("nombre", "Sin nombre")),
                    "siglas": inst.get("siglas") or None,
                    "sector": inst.get("sector"),
                    "website": inst.get("website"),
                    "url": inst.get("url"),
                }
                for inst in rows
            ],
        }

        if not instituciones:
            return render_output(
                payload,
                format,
                text_builder=lambda d: (
                    "No se encontraron instituciones"
                    + (f" para: '{d['query']}'" if d.get("query") else "")
                ),
            )

        def to_text(data: dict) -> str:
            parts = []
            if data.get("query"):
                parts.append(f"Instituciones que coinciden con '{data['query']}':")
            else:
                parts.append(
                    f"Instituciones públicas del Ecuador (página {data['page']}):"
                )
            parts.append(f"Mostrando {data['showing']} resultados\n")
            for i, inst in enumerate(data["results"], 1):
                nombre = inst["nombre"]
                siglas = inst.get("siglas")
                label = f"{nombre} ({siglas})" if siglas else nombre
                parts.append(f"{i}. {label}")
                parts.append(f"   ID: {inst.get('institucion_id', '?')}")
                if inst.get("sector"):
                    parts.append(f"   Sector: {inst['sector']}")
                if inst.get("website"):
                    parts.append(f"   Web: {inst['website']}")
                if inst.get("url"):
                    parts.append(f"   Portal: {inst['url']}")
                parts.append("")
            parts.append(
                "Tip: Usa search_tramites(institution_id='ID') para ver los trámites "
                "de una institución."
            )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
