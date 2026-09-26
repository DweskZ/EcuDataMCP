from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import centrosur_cortes_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY

_TEXT_ROWS = 40
_TEXT_SECTORES = 220


def register_get_centrosur_cortes_horarios_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Horarios de cortes de luz por sector (Centrosur)", annotations=READ_ONLY
    )
    @log_tool
    async def get_centrosur_cortes_horarios(
        url: str, query: str = "", format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        Parse one of Centrosur's (Azuay, Cañar, Morona Santiago) scheduled
        power-cut PDFs into rows: date text as published, time blocks
        without power, province, canton, zone, and the sectors affected.
        Get the `url` from `search_centrosur_cortes`.

        Coverage is uneven because the archive is: the Oct 2023 tables and
        the Apr 2024 schedule parse to rows; the Sep 2024 file is a scan
        with no text (returned with a note, no rows — it would need OCR);
        one file is actually an EEQ (Quito) schedule uploaded by mistake,
        parsed as such and flagged in `nota`. When a canton comes from a
        merged table cell rather than the row's own label it is marked
        `canton_inferido: true` — those can be off near span boundaries.

        Args:
            url: PDF URL from search_centrosur_cortes.
            query: Free text matched (accent-insensitive) against canton,
                zone and sectors, e.g. "Gualaceo". Empty returns every row.
            format: text | json
        """
        try:
            result = await centrosur_cortes_client.get_centrosur_cortes_horarios(
                url=url, query=query
            )
        except ValueError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(
                f"Error al procesar el horario de cortes de Centrosur: {e}"
            ) from e

        def to_text(data: dict) -> str:
            filas = data["filas"]
            parts = [
                (
                    f"Centrosur — horario de cortes — {data['total']} fila(s) de "
                    f"{data['total_en_archivo']} ({data['paginas']} páginas)"
                ),
                "",
            ]
            if data.get("nota"):
                parts += [f"Nota: {data['nota']}", ""]
            if data["filas_canton_inferido"]:
                parts += [
                    (
                        f"Aviso: {data['filas_canton_inferido']} fila(s) con cantón "
                        "inferido de una celda combinada (marcadas con *)."
                    ),
                    "",
                ]
            if not filas:
                parts.append("Sin resultados.")
            for f in filas[:_TEXT_ROWS]:
                horario = " / ".join(f["horario"]) or "horario no reconocido"
                lugar = f.get("subestacion") or " / ".join(
                    x
                    for x in (
                        f.get("provincia"),
                        (f.get("canton") or "")
                        + ("*" if f.get("canton_inferido") else ""),
                        f.get("zona"),
                    )
                    if x
                )
                sectores = f["sectores"]
                if len(sectores) > _TEXT_SECTORES:
                    sectores = sectores[:_TEXT_SECTORES] + "…"
                parts.append(
                    f"p{f['pagina']} · {f['fecha_texto']} · {horario} · {lugar}"
                )
                parts.append(f"   {sectores}")
            if len(filas) > _TEXT_ROWS:
                parts.append(
                    f"... y {len(filas) - _TEXT_ROWS} filas más (usa query para acotar, "
                    "o format=json)"
                )
            parts.append("")
            parts.append(f"Fuente: {data['url']}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)
