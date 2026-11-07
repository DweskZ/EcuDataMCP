from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import inec_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.result_types import ResultadoArchivos
from helpers.tool_meta import READ_ONLY


def register_get_inec_estadistica_files_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Ver archivos de un tema estadístico del INEC",
        description=(
            "File links (bulletins, methodology, historical series) on one INEC "
            "topic page from search_inec_estadisticas. For a ZIP, next: "
            "list_zip_contents, then read_zip_member."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_inec_estadistica_files(
        url: str, year: int | None = None, format: Literal["text", "json"] = "text"
    ) -> Annotated[CallToolResult, ResultadoArchivos]:
        """
        List the direct file links published on one INEC statistical topic page.

        Get the url from search_inec_estadisticas. Returns technical bulletins,
        methodology, and historical series as direct PDF/XLSX/CSV/ZIP links —
        not the file contents. Historical microdata pages (general deaths
        1990-2015, 2017, 2018, 2019) are listed by search_inec_estadisticas
        under "defunciones". Use read_pdf on a .pdf link; for a .zip link,
        list_zip_contents shows its files and read_zip_member reads one of
        them as a table without downloading the archive (e.g. ENDI's
        tabulados ZIP). Download other tabular files yourself. When a topic page lists no files itself
        (e.g. ENDI), the files of the per-round landing pages it links to are
        merged in and those pages are named in "paginas_relacionadas".

        Args:
            url: A topic URL from search_inec_estadisticas's "url" field
                (must be on ecuadorencifras.gob.ec)
            year: Optional reference year; keeps only that year's files (each
                file carries a "year" parsed from its name or folder)
            format: text | json
        """
        try:
            result = await inec_client.get_topic_files(url, year=year)
        except ValueError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(f"Error al obtener la página del tema: {e}") from e

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [f"Tema: {data.get('titulo')}", f"URL: {data.get('url')}", ""]
            if not archivos:
                parts.append("No se encontraron archivos descargables en esta página.")
                return "\n".join(parts)
            related = data.get("paginas_relacionadas") or []
            if related:
                parts.append("Archivos tomados de páginas relacionadas:")
                parts.extend(f"- {u}" for u in related)
                parts.append("")
            parts.append(f"{len(archivos)} archivo(s):")
            for i, f in enumerate(archivos, 1):
                parts.append(
                    f"{i}. {f.get('label')} [{f.get('format')}]"
                    + (f" {f['year']}" if f.get("year") else "")
                )
                parts.append(f"   {f.get('url')}")
            if any((f.get("format") or "").upper() == "ZIP" for f in archivos):
                parts.append("")
                parts.append(
                    "Para un .zip: list_zip_contents(url) muestra sus archivos y "
                    "read_zip_member(url, member) lee uno como tabla sin bajar el .zip."
                )
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)
