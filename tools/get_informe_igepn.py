import httpx
from mcp.server.fastmcp import FastMCP

from helpers import igepn_informes_client
from helpers.format_out import render_output
from helpers.logging import log_tool
from helpers.pdf_reader import MAX_PAGES_PER_CALL, extract_text_from_bytes


def register_get_informe_igepn_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_informe_igepn(
        nombre: str,
        volcan: str = "",
        grupo: str = "",
        anio: int = 0,
        pages: str = "",
        format: str = "text",
    ) -> str:
        """
        Download and extract text from one IG-EPN report found via
        search_informes_igepn. IG-EPN has no stable per-report URL (each
        download is a session-bound form submit), so this re-locates the
        report by exact name/year/group and streams its PDF directly --
        pass `volcan` to disambiguate when two reports share the same name
        on the same day (happens for volcanic daily reports).

        Args:
            nombre: Exact report name from search_informes_igepn (e.g. "Informe Diario 2022-071")
            volcan: Volcano name, only needed to disambiguate a duplicate nombre
            grupo: "sismico" | "volcanico" | "" (both) -- same value used to find it
            anio: Report year (0 = current year) -- same value used to find it
            pages: Page range, 1-indexed (e.g. "3", "1-5"). Empty = whole document, capped at 20 pages/call
            format: text | json
        """
        try:
            raw, matched_nombre = await igepn_informes_client.download_informe(
                nombre, volcan=volcan, grupo=grupo, anio=anio
            )
        except ValueError as e:
            return render_output(
                {"error": str(e), "nombre": nombre},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )
        except httpx.HTTPError as e:
            return render_output(
                {"error": f"download_failed: {e}", "nombre": nombre},
                format,
                text_builder=lambda d: f"Error al descargar el informe: {d['error']}",
            )

        try:
            result = extract_text_from_bytes(raw, pages=pages)
        except ValueError as e:
            return render_output(
                {"error": str(e), "nombre": nombre},
                format,
                text_builder=lambda d: f"Error al leer el PDF: {d['error']}",
            )

        if result["total_pages"] == 0 or not any(p["text"] for p in result["pages"]):
            return render_output(
                {
                    "error": "sin_texto_extraible",
                    "nombre": matched_nombre,
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
            "nombre": matched_nombre,
            "total_pages": result["total_pages"],
            "pages": result["pages"],
            "pages_capped": result["pages_capped"],
        }

        def to_text(data: dict) -> str:
            parts = [
                f"Informe IG-EPN: {data['nombre']}",
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

        return render_output(payload, format, text_builder=to_text)
