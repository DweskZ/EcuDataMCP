from mcp.server.fastmcp import FastMCP

from helpers import anda_client
from helpers.format_out import render_output
from helpers.logging import log_tool

_MAX_TEXT_CHARS = 800


def _trim(text: str, n: int = _MAX_TEXT_CHARS) -> str | None:
    clean = " ".join((text or "").split())
    if not clean:
        return None
    return clean[:n] + "..." if len(clean) > n else clean


def register_get_anda_survey_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_anda_survey_info(idno: str, format: str = "text") -> str:
        """
        Get full metadata for one ANDA (INEC) survey/census by its idno.

        Get the idno from search_anda results — it's the string identifier
        (e.g. "IDD-ECU-INEC-CGTPE-DECON-ENESEM-2023-v1.3"), not the numeric id.

        Returns scope/abstract, variable count, whether microdata is actually
        downloadable, confidentiality terms, and a contact email for requesting
        restricted data when it isn't.

        Args:
            idno: Survey identifier from search_anda (the "idno" field)
            format: text | json
        """
        try:
            dataset = await anda_client.get_survey(idno)
        except Exception as e:
            return render_output(
                {"error": str(e), "idno": idno},
                format,
                text_builder=lambda d: f"Error al obtener la encuesta: {d['error']}",
            )

        study_desc = dataset.get("metadata", {}).get("study_desc", {})
        study_info = study_desc.get("study_info", {})
        dataset_use = study_desc.get("data_access", {}).get("dataset_use", {})

        conf_dec = dataset_use.get("conf_dec") or []
        contacts = dataset_use.get("contact") or []

        payload = {
            "id": dataset.get("id"),
            "idno": dataset.get("idno"),
            "titulo": dataset.get("title"),
            "anio_inicio": dataset.get("year_start"),
            "anio_fin": dataset.get("year_end"),
            "entidad": dataset.get("authoring_entity"),
            "microdatos_disponibles": anda_client.has_microdata(dataset),
            "variables": dataset.get("varcount"),
            "vistas": dataset.get("total_views"),
            "descargas": dataset.get("total_downloads"),
            "resumen": _trim(study_info.get("abstract", "")),
            "confidencialidad": _trim(conf_dec[0].get("txt", "")) if conf_dec else None,
            "contacto_email": contacts[0].get("email") if contacts else None,
            "url": (
                f"https://anda.inec.gob.ec/anda5/index.php/catalog/{dataset['id']}"
                if dataset.get("id")
                else None
            ),
        }

        def to_text(data: dict) -> str:
            parts = [
                f"Encuesta: {data.get('titulo', 'Sin título')}",
                f"idno: {data['idno']}",
                f"ID: {data.get('id')}",
            ]
            anio_inicio, anio_fin = data.get("anio_inicio"), data.get("anio_fin")
            if anio_inicio:
                rango = (
                    f"{anio_inicio} - {anio_fin}"
                    if anio_fin and anio_fin != anio_inicio
                    else str(anio_inicio)
                )
                parts.append(f"Año: {rango}")
            if data.get("entidad"):
                parts.append(f"Entidad: {data['entidad']}")

            microdatos = "sí" if data["microdatos_disponibles"] else "no (solo agregados)"
            parts.append(f"Microdatos disponibles: {microdatos}")
            if data.get("variables"):
                parts.append(f"Variables documentadas: {data['variables']}")
            if data.get("vistas") or data.get("descargas"):
                parts.append(
                    f"Vistas: {data.get('vistas', 0)} · Descargas: {data.get('descargas', 0)}"
                )

            if data.get("resumen"):
                parts.append("")
                parts.append(f"Resumen: {data['resumen']}")
            if data.get("confidencialidad"):
                parts.append("")
                parts.append(f"Confidencialidad: {data['confidencialidad']}")
            if data.get("contacto_email"):
                parts.append("")
                parts.append(f"Contacto para solicitar datos: {data['contacto_email']}")
            if data.get("url"):
                parts.append("")
                parts.append(f"URL: {data['url']}")
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
