from mcp.server.fastmcp import FastMCP

from helpers import supercias_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_auditores_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_auditores(
        query: str = "",
        provincia: str = "",
        limit: int = 20,
        offset: int = 0,
        format: str = "text",
    ) -> str:
        """
        Search Ecuador's registry of authorized external auditors (Superintendencia de Compañías).

        Covers the 1,447 firms/individuals licensed to act as external
        auditors, with their authorization resolution number/date and
        contact details. Source is a daily-refreshed government export,
        cached up to 6h server-side.

        Args:
            query: Free text matched against auditor name or identificación
                (RUC/cédula), accent-insensitive
            provincia: Optional province filter, e.g. "PICHINCHA" (substring match)
            limit: Max results (default 20, max 100)
            offset: Pagination offset over the matched set
            format: text | json
        """
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)

        try:
            result = await supercias_client.search_auditores(
                query=query,
                provincia=provincia,
                limit=limit,
                offset=offset,
            )
        except Exception as e:
            return render_output(
                {
                    "error": str(e),
                    "query": query or None,
                    "provincia": provincia or None,
                },
                format,
                text_builder=lambda d: (
                    f"Error al consultar el listado de auditores externos: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            auditores = data.get("auditores") or []
            parts = [
                (
                    f"Auditores Externos — {data['total']} resultado(s) "
                    f"(mostrando {len(auditores)}, offset={data['offset']})"
                ),
                "",
            ]
            if not auditores:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, a in enumerate(auditores, 1):
                parts.append(f"{i}. {a.get('nombre')}")
                parts.append(f"   Identificación: {a.get('identificacion')}")
                if a.get("provincia") or a.get("canton"):
                    ubicacion = "  ·  ".join(
                        part
                        for part in (a.get("provincia"), a.get("canton"))
                        if part
                    )
                    parts.append(f"   {ubicacion}")
                if a.get("numero_de_resolucion"):
                    parts.append(
                        f"   Resolución: {a['numero_de_resolucion']} "
                        f"({a.get('fecha_de_resolucion')})"
                    )
                parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)
