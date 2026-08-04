from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP

from helpers import sercop_client
from helpers.format_out import render_output
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
        format: str = "text",
    ) -> str:
        """
        Search Ecuador public procurement procedures (SERCOP / OCDS open data).

        Useful for journalists, researchers and citizens looking for contracts,
        tenders, buyers or suppliers. Requires a keyword of at least 3 characters.
        Year defaults to the current calendar year and falls back to prior years
        when year=0. Results are cached ~10 minutes to reduce SERCOP 429s.

        Args:
            query: Keyword (min 3 chars), e.g. "medicinas", "vialidad", "software"
            year: Contract year (2015–current). 0 = current year + fallback
            page: Results page (1-based)
            buyer: Optional buyer/institution keyword (min 3 chars)
            supplier: Optional supplier keyword (min 3 chars)
            format: text | json
        """
        query = (query or "").strip()
        if len(query) < 3:
            return render_output(
                {"error": "query_corto", "min_chars": 3},
                format,
                text_builder=lambda _: (
                    "Error: query debe tener al menos 3 caracteres "
                    "(requisito de la API SERCOP)."
                ),
            )

        page = max(page, 1)
        pinned_year = year > 0
        year_arg = year if pinned_year else datetime.now(UTC).year
        fallback = 0 if pinned_year else 2

        try:
            result = await sercop_client.search_contracts(
                search=query,
                year=year_arg,
                page=page,
                buyer=buyer,
                supplier=supplier,
                fallback_years=fallback,
            )
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: (
                    f"Error al buscar contratos en SERCOP: {d['error']}. "
                    "La API a veces responde 429 (rate limit); reintenta en unos segundos."
                ),
            )

        data = result.get("data") or []
        resolved_year = result.get("_resolved_year", year_arg)
        payload = {
            "query": query,
            "year": resolved_year,
            "total": result.get("total", len(data)),
            "page": result.get("page", page),
            "pages": result.get("pages"),
            "results": data,
        }

        def to_text(p: dict) -> str:
            rows = p.get("results") or []
            if not rows:
                return (
                    f"No se encontraron contratos para '{p['query']}' en {p['year']}. "
                    "Prueba otro año, buyer o supplier."
                )
            parts = [
                f"Contratos públicos (SERCOP/OCDS) — '{p['query']}' — año {p['year']}",
                f"Total: {p['total']} | Página {p.get('page')}/{p.get('pages')}",
                f"Mostrando {min(len(rows), 20)} resultados\n",
            ]
            for i, item in enumerate(rows[:20], 1):
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

        return render_output(payload, format, text_builder=to_text)
