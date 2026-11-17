from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import anda_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.result_types import ResultadoArchivos
from helpers.tool_meta import READ_ONLY


def _next_step(links: list[dict[str, str]]) -> str | None:
    """Point at the in-server tool that lists the files behind an external link."""
    hosts = " ".join(link["url"] for link in links)
    if "censoecuador.gob.ec" in hosts:
        return (
            'search_archivos(fuente="censo", query="...") lista las bases de datos '
            "del Censo 2022 (CSV/SPSS/REDATAM por cantón, sector y manzana), los "
            "diccionarios y los tabulados (p. ej. query=\"tecnolog\" para TIC)."
        )
    if "ecuadorencifras.gob.ec" in hosts:
        return (
            "get_inec_estadistica_files / search_inec_estadisticas listan los archivos "
            "publicados en ecuadorencifras.gob.ec."
        )
    return None


def register_download_anda_microdata_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Descargar microdatos de una encuesta ANDA",
        description=(
            "Links to an ANDA survey's microdata, with tipo_acceso (directo, "
            "enlace_externo, registro, solicitud, ninguno); accepts ANDA's research-use "
            "terms. External links point to other INEC sites. Check get_anda_survey_info first."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def download_anda_microdata(
        idno: str, format: Literal["text", "json"] = "text"
    ) -> Annotated[CallToolResult, ResultadoArchivos]:
        """
        Get the download links for an ANDA survey's microdata, and say how it is served.

        Automates ANDA's one-click usage-terms step (research/statistical use
        only, no re-identifying respondents, cite the source — see
        get_anda_survey_info for the full text) to reveal the file list. Check
        get_anda_survey_info first: aggregate-only surveys (microdatos_disponibles
        false) have no files here.

        `tipo_acceso` is read from the study's real download page, not from the
        catalog flag: `directo` (files hosted by ANDA, in `archivos`),
        `enlace_externo` (ANDA only links to another site, in
        `enlaces_externos`: e.g. the 2022 Census points to censoecuador.gob.ec),
        `registro` (ANDA login needed), `solicitud` (request to INEC) or
        `ninguno`. A study can be flagged "direct" by the catalog and still have
        no attached file; `total_archivos: 0` with `enlace_externo` means the
        data is elsewhere, follow `siguiente_paso`.

        Returns URLs, not file contents — ANDA files are typically multi-MB ZIPs
        (SPSS .sav inside), too large to embed in a tool result.

        Args:
            idno: Survey idno or numeric id from search_anda (the "idno" or "id" field)
            format: text | json
        """
        try:
            dataset = await anda_client.get_survey(idno)
            survey_id = dataset.get("id")
            if not survey_id:
                raise ValueError(f"No se encontró ninguna encuesta con idno '{idno}' en ANDA.")

            if not anda_client.has_microdata(dataset):
                return render_structured(
                    {
                        "idno": idno,
                        "titulo": dataset.get("title"),
                        "tipo_acceso": anda_client.ACCESS_NONE,
                        "total_archivos": 0,
                        "archivos": [],
                        "enlaces_externos": [],
                    },
                    format,
                    text_builder=lambda d: (
                        f"'{d['titulo']}' no tiene microdatos descargables, solo agregados. "
                        "Usa get_anda_survey_info para ver el contacto y solicitar acceso."
                    ),
                )

            access = await anda_client.get_microdata_access(survey_id)
        except Exception as e:
            raise ToolError(f"Error al obtener los archivos: {e}") from e

        files = access["archivos"]
        links = access["enlaces_externos"]
        payload = {
            "idno": idno,
            "titulo": dataset.get("title"),
            "tipo_acceso": access["tipo_acceso"],
            "total_archivos": len(files),
            "archivos": files,
            "total_enlaces_externos": len(links),
            "enlaces_externos": links,
        }
        if access.get("nota"):
            payload["motivo"] = access["nota"]
        siguiente = _next_step(links)
        if siguiente:
            payload["siguiente_paso"] = siguiente

        def to_text(data: dict) -> str:
            tipo = data["tipo_acceso"]
            if not data["archivos"] and not data["enlaces_externos"]:
                return (
                    f"No hay archivos de microdatos descargables en ANDA para '{data['titulo']}' "
                    f"(tipo_acceso: {tipo}). {data.get('motivo', '')}".strip()
                )
            parts = [
                f"Microdatos de: {data['titulo']} (tipo_acceso: {tipo})",
                (
                    "Uso sujeto a los términos de ANDA (fines estadísticos/investigación, "
                    "no reidentificar encuestados, citar la fuente — ver get_anda_survey_info)."
                ),
                "",
            ]
            if data.get("motivo"):
                parts += [data["motivo"], ""]
            if data["archivos"]:
                parts.append("Archivos alojados en ANDA:")
                for f in data["archivos"]:
                    parts.append(f"- {f['filename']}")
                    parts.append(f"  {f['url']}")
            if data["enlaces_externos"]:
                parts.append("Enlaces externos (no son descargas directas de ANDA):")
                for link in data["enlaces_externos"]:
                    parts.append(f"- {link['nombre']}")
                    parts.append(f"  {link['url']}")
            if data.get("siguiente_paso"):
                parts += ["", f"Siguiente paso: {data['siguiente_paso']}"]
            return "\n".join(parts)

        return render_structured(payload, format, text_builder=to_text)
