from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import eeq_cortes_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY

_TEXT_ROWS = 40
_TEXT_SECTORES = 220


def register_get_eeq_cortes_horarios_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Horarios de cortes de luz por sector (EEQ, Quito)", annotations=READ_ONLY
    )
    @log_tool
    async def get_eeq_cortes_horarios(
        slug: str, query: str = "", format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        Parse one of Empresa Eléctrica Quito's scheduled power-cut PDFs
        (2023-2024 blackout crises) into structured rows: date text as
        published, time blocks without power (["07:30-10:30", ...]),
        substation, and the neighbourhoods/streets it feeds. Answers "when
        was <barrio> without power" in Quito.

        Get the `slug` from `search_eeq_cortes`. Each PDF page is one time
        block; multi-day PDFs repeat substations under each day's date
        (`fecha_texto`), and `sector_industrial` marks the pages for
        industrial customers. Parsed from the slide layout (positions of
        the text on the page), validated on all 26 archived PDFs
        (2026-09-25: 2,150 rows, none unassigned); the result reports rows
        it could not assign a substation or time to.

        Args:
            slug: File slug from search_eeq_cortes (e.g. "vsd",
                "29_04_2024"), or the file's full URL.
            query: Free text matched (accent-insensitive) against
                substation and sectors, e.g. "La Floresta". Empty returns
                every row.
            format: text | json
        """
        try:
            result = await eeq_cortes_client.get_eeq_cortes_horarios(
                slug=slug, query=query
            )
        except ValueError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(
                f"Error al procesar el horario de cortes de EEQ: {e}"
            ) from e

        def to_text(data: dict) -> str:
            filas = data["filas"]
            parts = [
                (
                    f"EEQ (Quito) — horario de cortes '{data['slug']}' — {data['total']} "
                    f"fila(s) de {data['total_en_archivo']} ({data['paginas']} páginas)"
                ),
                "",
            ]
            if data["filas_sin_subestacion"] or data["filas_sin_horario"]:
                parts.append(
                    f"Aviso: {data['filas_sin_subestacion']} fila(s) sin subestación y "
                    f"{data['filas_sin_horario']} sin horario reconocidos en el PDF."
                )
                parts.append("")
            if not filas:
                parts.append("Sin resultados.")
            for f in filas[:_TEXT_ROWS]:
                horario = " / ".join(f["horario"]) or "horario no reconocido"
                industrial = " [sector industrial]" if f["sector_industrial"] else ""
                sectores = f["sectores"]
                if len(sectores) > _TEXT_SECTORES:
                    sectores = sectores[:_TEXT_SECTORES] + "…"
                parts.append(
                    f"p{f['pagina']} · {f['fecha_texto']} · {horario}{industrial} · "
                    f"{f['subestacion'] or 'subestación no reconocida'}"
                )
                parts.append(f"   {sectores}")
            if len(filas) > _TEXT_ROWS:
                parts.append(
                    f"... y {len(filas) - _TEXT_ROWS} filas más (usa query para acotar, o format=json)"
                )
            parts.append("")
            parts.append(f"Fuente: {data['url']}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)
