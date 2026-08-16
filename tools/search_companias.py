from mcp.server.fastmcp import FastMCP

from helpers import supercias_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_companias_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_companias(
        query: str = "",
        provincia: str = "",
        situacion_legal: str = "",
        limit: int = 20,
        offset: int = 0,
        format: str = "text",
    ) -> str:
        """
        Search Ecuador's company registry (Superintendencia de Compañías).

        Covers 226k+ companies with legal status, incorporation date, legal
        representative, registered capital, economic activity (CIIU) and
        address. Source is a daily-refreshed government export, cached up to
        6h server-side — the first call after the cache expires can take
        ~30-40s to download and parse (~35 MB, 226k rows).

        Args:
            query: Free text matched against company name or RUC (accent-insensitive)
            provincia: Optional province filter, e.g. "PICHINCHA" (substring match)
            situacion_legal: Optional legal status filter, e.g. "ACTIVA", "DISOLUCIÓN"
            limit: Max results (default 20, max 100)
            offset: Pagination offset over the matched set
            format: text | json
        """
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)

        try:
            result = await supercias_client.search_companias(
                query=query,
                provincia=provincia,
                situacion_legal=situacion_legal,
                limit=limit,
                offset=offset,
            )
        except Exception as e:
            return render_output(
                {
                    "error": str(e),
                    "query": query or None,
                    "provincia": provincia or None,
                    "situacion_legal": situacion_legal or None,
                },
                format,
                text_builder=lambda d: (
                    f"Error al consultar el directorio de Supercías: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            companias = data.get("companias") or []
            parts = [
                (
                    f"Directorio de Compañías — {data['total']} resultado(s) "
                    f"(mostrando {len(companias)}, offset={data['offset']})"
                ),
                "",
            ]
            if not companias:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, c in enumerate(companias, 1):
                parts.append(f"{i}. {c.get('nombre')}")
                parts.append(f"   RUC: {c.get('ruc')}")
                parts.append(f"   Situación legal: {c.get('situacion_legal')}")
                tipo_provincia = [
                    f"Tipo: {c['tipo']}" if c.get("tipo") else "",
                    f"Provincia: {c['provincia']}" if c.get("provincia") else "",
                ]
                tipo_provincia = [part for part in tipo_provincia if part]
                if tipo_provincia:
                    parts.append("   " + "  ·  ".join(tipo_provincia))
                if c.get("representante"):
                    parts.append(
                        f"   Representante: {c['representante']} ({c.get('cargo')})"
                    )
                if c.get("capital_suscrito"):
                    parts.append(f"   Capital suscrito: {c['capital_suscrito']}")
                parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)
