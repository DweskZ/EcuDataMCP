from functools import partial

from mcp.server.fastmcp import FastMCP

from helpers import gobec_client
from helpers.format_out import render_output
from helpers.gobec_client import _clean_html
from helpers.logging import log_tool
from helpers.text_utils import strip_accents

_strip_accents = partial(strip_accents, lower=False)


def _matches_query(tramite: dict, words: list[str]) -> bool:
    """Check if a trámite matches ALL query words in its name or description."""
    nombre = tramite.get("nombre", "").lower()
    codigo = tramite.get("codigo", "").lower()
    desc = _clean_html(tramite.get("descripcion", "")).lower()
    searchable = _strip_accents(f"{nombre} {codigo} {desc}")
    return all(w in searchable for w in words)


def register_search_tramites_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_tramites(
        query: str = "",
        institution_id: str = "",
        page: int = 1,
        format: str = "text",
    ) -> str:
        """
        Search for government procedures (trámites) on Ecuador's official portal gob.ec.

        Best approach: provide an institution_id to get that institution's trámites.
        Add a query to filter results by keyword (filters by name and description).

        When query is provided with institution_id, ALL pages of that institution's
        trámites are fetched and filtered, so you always get the most relevant results.

        Common institution IDs:
        - "8" = SRI (Servicio de Rentas Internas) — impuestos, RUC, facturación
        - "23" = Registro Civil — cédula, partidas de nacimiento
        - "62" = ANT — licencias de conducir, matriculación vehicular
        - "16" = Ministerio de Relaciones Exteriores — pasaportes, apostilla
        - "5" = IESS — seguro social, pensiones, fondos de reserva

        Use list_instituciones to find more institution IDs.

        Args:
            query: Keywords to filter results (e.g. "RUC", "inscripción RUC persona natural").
                   Each word must appear in the trámite name or description.
            institution_id: Institution ID (strongly recommended for relevant results)
            page: Page number (1-based, default: 1). Ignored when query is provided
                  (all pages are searched automatically).
            format: text | json
        """
        if query and not institution_id:
            keyword_to_inst = {
                "ruc": "8", "sri": "8", "impuesto": "8", "factura": "8",
                "tributar": "8", "retención": "8", "retenciones": "8",
                "declaracion": "8", "declaración": "8", "rimpe": "8",
                "cedula": "23", "cédula": "23", "partida": "23",
                "nacimiento": "23", "registro civil": "23", "defunción": "23",
                "matrimonio": "23", "identidad": "23",
                "licencia": "62", "conducir": "62", "matricula": "62",
                "vehicul": "62", "ant": "62", "revision tecnica": "62",
                "pasaporte": "16", "apostilla": "16", "visa": "16",
                "consulado": "16", "legalizacion": "16",
                "iess": "5", "seguro social": "5", "pensión": "5",
                "fondo de reserva": "5", "afiliacion": "5", "cesantia": "5",
            }
            q_lower = query.lower()
            for keyword, inst_id in keyword_to_inst.items():
                if keyword in q_lower:
                    institution_id = inst_id
                    break

        query_words = (
            [_strip_accents(w.lower()) for w in query.split() if len(w) >= 2]
            if query
            else []
        )

        try:
            if query_words and institution_id:
                all_tramites: list[dict] = []
                for api_page in range(10):
                    batch = await gobec_client.search_tramites(
                        institution_id=institution_id, page=api_page
                    )
                    if not batch:
                        break
                    all_tramites.extend(batch)
                tramites = [t for t in all_tramites if _matches_query(t, query_words)]
                total_scanned = len(all_tramites)
            elif query_words and not institution_id:
                all_tramites = []
                for api_page in range(5):
                    batch = await gobec_client.search_tramites(page=api_page)
                    if not batch:
                        break
                    all_tramites.extend(batch)
                tramites = [t for t in all_tramites if _matches_query(t, query_words)]
                total_scanned = len(all_tramites)
            else:
                api_page = max(page - 1, 0)
                tramites = await gobec_client.search_tramites(
                    institution_id=institution_id, page=api_page
                )
                total_scanned = len(tramites)
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al buscar trámites: {d['error']}",
            )

        payload = {
            "query": query,
            "institution_id": institution_id,
            "page": page,
            "total_scanned": total_scanned,
            "total": len(tramites),
            "results": [
                {
                    "tramite_id": t.get("tramite_id"),
                    "nombre": t.get("nombre"),
                    "codigo": t.get("codigo"),
                    "url": t.get("url"),
                    "descripcion": _clean_html(t.get("descripcion", ""))[:300],
                }
                for t in tramites[:20]
            ],
        }

        def to_text(data: dict) -> str:
            rows = data.get("results") or []
            if not rows:
                msg_parts = ["No se encontraron trámites"]
                if data.get("query"):
                    msg_parts.append(f"que coincidan con '{data['query']}'")
                if data.get("institution_id"):
                    msg_parts.append(f"en la institución ID {data['institution_id']}")
                if query_words and data.get("total_scanned", 0) > 0:
                    msg_parts.append(
                        f"(se revisaron {data['total_scanned']} trámites en total)"
                    )
                return " ".join(msg_parts) + "."

            parts: list[str] = []
            if data.get("query") and data.get("institution_id"):
                parts.append(
                    f"Trámites que coinciden con '{data['query']}' "
                    f"en institución ID {data['institution_id']}:"
                )
                parts.append(
                    f"Encontrados: {data['total']} de {data['total_scanned']} "
                    "trámites revisados\n"
                )
            elif data.get("institution_id"):
                parts.append(
                    f"Trámites de la institución (ID: {data['institution_id']}), "
                    f"página {data['page']}:"
                )
                parts.append(f"Mostrando {len(rows)} resultados\n")
            elif data.get("query"):
                parts.append(f"Trámites que coinciden con '{data['query']}':")
                parts.append(f"Encontrados: {data['total']}\n")
            else:
                parts.append(f"Trámites (página {data['page']}):")
                parts.append(f"Mostrando {len(rows)} resultados\n")

            for i, t in enumerate(rows, 1):
                parts.append(f"{i}. {t.get('nombre', 'Sin nombre')}")
                parts.append(f"   ID: {t.get('tramite_id', '?')}")
                if t.get("codigo"):
                    parts.append(f"   Código: {t['codigo']}")
                if t.get("url"):
                    parts.append(f"   URL: {t['url']}")
                if t.get("descripcion"):
                    parts.append(f"   Descripción: {t['descripcion']}...")
                parts.append("")
            if data["total"] > 20:
                parts.append(f"... y {data['total'] - 20} más.")
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
