from unicodedata import category, normalize

from mcp.server.fastmcp import FastMCP

from helpers import gobec_client
from helpers.gobec_client import _clean_html
from helpers.logging import log_tool


def _strip_accents(text: str) -> str:
    """Remove diacritical marks: inscripción → inscripcion, cédula → cedula."""
    nfkd = normalize("NFKD", text)
    return "".join(c for c in nfkd if category(c) != "Mn")


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
        query: str = "", institution_id: str = "", page: int = 1
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
        """
        # Auto-detect institution from common keywords
        if query and not institution_id:
            keyword_to_inst = {
                "ruc": "8", "sri": "8", "impuesto": "8", "factura": "8",
                "tributar": "8", "retención": "8", "retenciones": "8",
                "cedula": "23", "cédula": "23", "partida": "23",
                "nacimiento": "23", "registro civil": "23", "defunción": "23",
                "licencia": "62", "conducir": "62", "matricula": "62",
                "vehicul": "62", "ant": "62",
                "pasaporte": "16", "apostilla": "16", "visa": "16",
                "iess": "5", "seguro social": "5", "pensión": "5",
                "fondo de reserva": "5",
            }
            q_lower = query.lower()
            for keyword, inst_id in keyword_to_inst.items():
                if keyword in q_lower:
                    institution_id = inst_id
                    break

        query_words = [_strip_accents(w.lower()) for w in query.split() if len(w) >= 2] if query else []

        try:
            if query_words and institution_id:
                # Fetch ALL pages and filter to find the best matches
                all_tramites: list[dict] = []
                for api_page in range(10):  # Max 10 pages
                    batch = await gobec_client.search_tramites(
                        institution_id=institution_id, page=api_page
                    )
                    if not batch:
                        break
                    all_tramites.extend(batch)

                filtered = [t for t in all_tramites if _matches_query(t, query_words)]
                tramites = filtered
                total_scanned = len(all_tramites)
            elif query_words and not institution_id:
                # No institution: scan several pages and filter client-side
                all_tramites: list[dict] = []
                for api_page in range(5):
                    batch = await gobec_client.search_tramites(page=api_page)
                    if not batch:
                        break
                    all_tramites.extend(batch)
                filtered = [t for t in all_tramites if _matches_query(t, query_words)]
                tramites = filtered
                total_scanned = len(all_tramites)
            else:
                # No query: just paginate normally
                api_page = max(page - 1, 0)
                tramites = await gobec_client.search_tramites(
                    institution_id=institution_id, page=api_page
                )
                total_scanned = len(tramites)
        except Exception as e:
            return f"Error al buscar trámites: {e}"

        if not tramites:
            msg_parts = ["No se encontraron trámites"]
            if query:
                msg_parts.append(f"que coincidan con '{query}'")
            if institution_id:
                msg_parts.append(f"en la institución ID {institution_id}")
            if query_words and total_scanned > 0:
                msg_parts.append(f"(se revisaron {total_scanned} trámites en total)")
            return " ".join(msg_parts) + "."

        parts = []
        if query and institution_id:
            parts.append(
                f"Trámites que coinciden con '{query}' en institución ID {institution_id}:"
            )
            parts.append(
                f"Encontrados: {len(tramites)} de {total_scanned} trámites revisados\n"
            )
        elif institution_id:
            parts.append(f"Trámites de la institución (ID: {institution_id}), página {page}:")
            parts.append(f"Mostrando {min(len(tramites), 20)} resultados\n")
        elif query:
            parts.append(f"Trámites que coinciden con '{query}':")
            parts.append(f"Encontrados: {len(tramites)}\n")
        else:
            parts.append(f"Trámites (página {page}):")
            parts.append(f"Mostrando {min(len(tramites), 20)} resultados\n")

        for i, t in enumerate(tramites[:20], 1):
            nombre = t.get("nombre", "Sin nombre")
            parts.append(f"{i}. {nombre}")
            parts.append(f"   ID: {t.get('tramite_id', '?')}")
            if t.get("codigo"):
                parts.append(f"   Código: {t['codigo']}")
            if t.get("url"):
                parts.append(f"   URL: {t['url']}")
            desc = _clean_html(t.get("descripcion", ""))
            if desc:
                parts.append(f"   Descripción: {desc[:250]}...")
            parts.append("")

        if len(tramites) > 20:
            parts.append(f"... y {len(tramites) - 20} más.")

        return "\n".join(parts)
