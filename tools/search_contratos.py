from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP

from helpers import sercop_client
from helpers.logging import log_tool


def register_search_contratos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_contratos(
        query: str,
        year: int = 0,
        page: int = 1,
        buyer: str = "",
        supplier: str = "",
    ) -> str:
        """
        Search Ecuador public procurement procedures (SERCOP / OCDS open data).

        Useful for journalists, researchers and citizens looking for contracts,
        tenders, buyers or suppliers. Requires a keyword of at least 3 characters.
        Year defaults to the current calendar year.

        Args:
            query: Keyword (min 3 chars), e.g. "medicinas", "vialidad", "software"
            year: Contract year (2015–current). 0 = current year
            page: Results page (1-based)
            buyer: Optional buyer/institution keyword (min 3 chars)
            supplier: Optional supplier keyword (min 3 chars)
        """
        query = (query or "").strip()
        if len(query) < 3:
            return "Error: query debe tener al menos 3 caracteres (requisito de la API SERCOP)."

        year = year or datetime.now(UTC).year
        page = max(page, 1)

        try:
            result = await sercop_client.search_contracts(
                search=query,
                year=year,
                page=page,
                buyer=buyer,
                supplier=supplier,
            )
        except Exception as e:
            return (
                f"Error al buscar contratos en SERCOP: {e}. "
                "La API a veces responde 429 (rate limit); reintenta en unos segundos."
            )

        data = result.get("data") or []
        total = result.get("total", len(data))
        pages = result.get("pages", "?")

        if not data:
            return (
                f"No se encontraron contratos para '{query}' en {year}. "
                "Prueba otro año, buyer o supplier."
            )

        parts = [
            f"Contratos públicos (SERCOP/OCDS) — '{query}' — año {year}",
            f"Total: {total} | Página {result.get('page', page)}/{pages}",
            f"Mostrando {len(data)} resultados\n",
        ]
        for i, item in enumerate(data[:20], 1):
            title = item.get("title") or item.get("ocid") or "Sin título"
            parts.append(f"{i}. {title}")
            if item.get("ocid"):
                parts.append(f"   OCID: {item['ocid']}")
            if item.get("description"):
                desc = str(item["description"]).replace("\n", " ").strip()
                parts.append(f"   Descripción: {desc[:220]}")
            if item.get("buyerName"):
                parts.append(f"   Comprador: {item['buyerName']}")
            if item.get("single_provider"):
                parts.append(f"   Proveedor: {item['single_provider']}")
            if item.get("internal_type"):
                parts.append(f"   Tipo: {item['internal_type']}")
            if item.get("date"):
                parts.append(f"   Fecha: {item['date']}")
            parts.append("")

        parts.append(
            "Tip: Usa get_contrato_info(ocid='...') para el expediente OCDS completo."
        )
        return "\n".join(parts)
