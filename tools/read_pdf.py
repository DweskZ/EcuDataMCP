from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.pdf_reader import MAX_PAGES_PER_CALL
from helpers.pdf_reader import read_pdf as extract_pdf_text
from helpers.tool_meta import READ_ONLY


def register_read_pdf_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Extraer texto de un PDF", annotations=READ_ONLY)
    @log_tool
    async def read_pdf(
        url: str,
        pages: str = "",
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Extract text from a PDF document at a direct URL.

        Useful for PDFs linked from other tools' results, e.g. get_regulacion_info's
        Registro Oficial file, or a dataset resource that turned out to be a PDF
        bulletin instead of a tabular file. No OCR: a scanned PDF with no embedded
        text layer will come back empty. Max download size: 5 MB (larger files
        return an explicit error instead of a partial read -- PDFs can't be
        parsed from a truncated download); max 20 pages extracted per call
        (call again with a different `pages` range for the rest).

        Args:
            url: Direct URL to the PDF file
            pages: Page range, 1-indexed (e.g. "3", "1-5", "1,4,9"). Empty means
                   the whole document, still capped at 20 pages per call.
            format: text | json
        """
        try:
            result = await extract_pdf_text(url, pages=pages)
        except ValueError as e:
            raise ToolError(f"Error: {e}") from e
        except httpx.HTTPError as e:
            raise ToolError(f"Error al descargar el archivo: download_failed: {e}") from e
        except Exception as e:
            raise ToolError(f"Error al procesar el PDF: {e}") from e

        if result["total_pages"] == 0 or not any(p["text"] for p in result["pages"]):
            # Legitimate result (the PDF has no extractable text, likely a
            # scanned image) rather than an execution failure -- same
            # precedent as get_informe_igepn.py's sin_texto_extraible case.
            return render_structured(
                {
                    "error": "sin_texto_extraible",
                    "url": url,
                    "total_pages": result["total_pages"],
                },
                format,
                text_builder=lambda d: (
                    f"El PDF tiene {d['total_pages']} página(s) pero no se pudo "
                    "extraer texto de ninguna (probablemente es un escaneo de "
                    "imágenes sin capa de texto; este tool no hace OCR)."
                    if d["total_pages"]
                    else "El PDF no tiene páginas."
                ),
            )

        payload = {
            "url": url,
            "total_pages": result["total_pages"],
            "pages": result["pages"],
            "pages_capped": result["pages_capped"],
        }

        def to_text(data: dict) -> str:
            parts = [
                f"PDF: {data['url']}",
                f"Total de páginas: {data['total_pages']}",
                f"Páginas extraídas: {len(data['pages'])}",
            ]
            if data.get("pages_capped"):
                parts.append(
                    f"⚠ Se pidieron más de {MAX_PAGES_PER_CALL} páginas; solo se "
                    f"extrajeron las primeras {MAX_PAGES_PER_CALL}. Llama de nuevo "
                    "con `pages` apuntando al resto (ej. \"21-40\")."
                )
            parts.append("")
            for p in data["pages"]:
                parts.append(f"--- Página {p['page']} ---")
                parts.append(p["text"] or "(sin texto extraíble en esta página)")
                parts.append("")
            return "\n".join(parts)

        return render_structured(payload, format, text_builder=to_text)
