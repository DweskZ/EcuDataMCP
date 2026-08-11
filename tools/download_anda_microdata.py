from mcp.server.fastmcp import FastMCP

from helpers import anda_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_download_anda_microdata_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def download_anda_microdata(idno: str, format: str = "text") -> str:
        """
        Get direct download links for an ANDA survey's microdata files.

        Automates ANDA's one-click usage-terms step (research/statistical use
        only, no re-identifying respondents, cite the source — see
        get_anda_survey_info for the full text) to reveal the file list. Check
        get_anda_survey_info first: aggregate-only surveys (microdatos_disponibles
        false) have no files here.

        Returns direct URLs, not the file contents — the files are typically
        multi-MB ZIPs (SPSS .sav inside), too large to embed in a tool result.
        Download them with the returned URL.

        Args:
            idno: Survey identifier from search_anda (the "idno" field)
            format: text | json
        """
        try:
            dataset = await anda_client.get_survey(idno)
            survey_id = dataset.get("id")
            if not survey_id:
                raise ValueError(f"No se encontró ninguna encuesta con idno '{idno}' en ANDA.")

            if not anda_client.has_microdata(dataset):
                return render_output(
                    {"idno": idno, "titulo": dataset.get("title"), "archivos": []},
                    format,
                    text_builder=lambda d: (
                        f"'{d['titulo']}' no tiene microdatos descargables, solo agregados. "
                        "Usa get_anda_survey_info para ver el contacto y solicitar acceso."
                    ),
                )

            files = await anda_client.list_microdata_files(survey_id)
        except Exception as e:
            return render_output(
                {"error": str(e), "idno": idno},
                format,
                text_builder=lambda d: f"Error al obtener los archivos: {d['error']}",
            )

        payload = {
            "idno": idno,
            "titulo": dataset.get("title"),
            "total_archivos": len(files),
            "archivos": files,
        }

        def to_text(data: dict) -> str:
            if not data["archivos"]:
                return (
                    f"No se encontraron archivos de microdatos para '{data['titulo']}' "
                    "(la página de descarga no devolvió links; puede necesitar revisión manual)."
                )
            parts = [
                f"Archivos de microdatos para: {data['titulo']}",
                (
                    "Uso sujeto a los términos de ANDA (fines estadísticos/investigación, "
                    "no reidentificar encuestados, citar la fuente — ver get_anda_survey_info)."
                ),
                "",
            ]
            for f in data["archivos"]:
                parts.append(f"- {f['filename']}")
                parts.append(f"  {f['url']}")
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
