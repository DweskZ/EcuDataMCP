from mcp.server.fastmcp import FastMCP

from helpers import ineval_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_ineval_familia_archivos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_ineval_familia_archivos(familia: str, format: str = "text") -> str:
        """
        List the direct download links published on one INEVAL evaluation
        family's "Bases de Datos" page.

        Get the familia key from list_ineval_familias. Returns each file's
        grupo (Llece's ERCE/SERCE/TERCE round, or the standalone-button
        section like "Fichas metodológicas vigentes" — None for most
        entries), periodo (the accordion panel's year label, e.g. "Año
        lectivo 2024-2025" or "Año 2019" — None for standalone-button
        entries, which carry no year context), titulo (dataset name, e.g.
        "Micro", "Factores Asociados estudiantes" — or the button's own
        label), direct URL, and formato (e.g. CSV, SAV, XLSX, SINTAXIS,
        METADATO, DICCIONARIO, or DESCONOCIDO for standalone buttons whose
        format isn't stated on the page) — not the file contents.

        GET on the URL returns the file directly (no login, no CAPTCHA);
        some IDs 308-redirect to a static archivosPD/uploads/... URL
        instead — both work through a redirect-following client. Files can
        be several MB (one PDF manual confirmed at 3.8 MB); download the
        URL directly instead of routing it through preview_resource_data or
        download_resource, which cap at 5 MB.

        Args:
            familia: A family key from list_ineval_familias, e.g.
                "ser_bachiller", "ser_estudiante", "llece".
            format: text | json
        """
        try:
            result = await ineval_client.get_familia_archivos(familia)
        except ValueError as e:
            return render_output(
                {"error": str(e), "familia": familia},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "familia": familia},
                format,
                text_builder=lambda d: f"Error al obtener la familia Ineval: {d['error']}",
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [f"Familia Ineval: {data.get('nombre')}", f"URL: {data.get('url')}", ""]
            if not archivos:
                parts.append("No se encontraron archivos descargables en esta página.")
                return "\n".join(parts)
            parts.append(f"{len(archivos)} archivo(s):")
            for a in archivos:
                etiqueta = " / ".join(p for p in (a.get("grupo"), a.get("periodo"), a.get("titulo")) if p)
                parts.append(f"- {etiqueta} [{a.get('formato')}]")
                parts.append(f"   {a.get('url')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)
