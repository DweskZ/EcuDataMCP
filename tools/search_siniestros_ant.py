from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import ant_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_search_siniestros_ant_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Buscar siniestros de tránsito (ANT)",
        description=(
            "Find Ecuador road-crash (siniestros de tránsito) data from ANT "
            "records: INEC quarterly/annual releases with XLSX/CSV microdata "
            "plus CKAN datasets (SPPAT deaths, ANT). ant.gob.ec is unreachable."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def search_siniestros_ant(
        query: str = "",
        anio: int = 0,
        limit: int = 10,
        con_archivos: int = 2,
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Search siniestros de tránsito (road crashes, deaths, injuries) whose
        source is the Agencia Nacional de Tránsito. ant.gob.ec itself does not
        accept connections from this server, so results come from INEC
        ("Siniestros de Tránsito" trimestral/anual, built on ANT records, with
        tabulados, open-data ZIP, dictionary and technical note) and from the
        CKAN portal (INEC ANET 2019, SPPAT fallecidos 2016-2021, ANT's own
        datasets). Next: download_resource / preview_resource_data / read_pdf
        on a file URL, or get_inec_publicacion_archivos with a publication id.

        Args:
            query: Optional words that must appear in the title (e.g. "trimestre")
            anio: Year filter on the title (0 = all years)
            limit: Max items per source (default 10, max 30)
            con_archivos: Attach file links to this many newest INEC releases
                (default 2, max 5; 0 = none)
            format: text | json
        """
        try:
            result = await ant_client.search_siniestros(
                query=query, anio=anio, limit=limit, con_archivos=con_archivos
            )
        except Exception as e:
            raise ToolError(f"Error al buscar siniestros de tránsito: {e}") from e

        def to_text(data: dict) -> str:
            parts = ["Siniestros de tránsito (ANT) — publicaciones INEC:"]
            posts = data["publicaciones_inec"]
            if not posts:
                parts.append("  Sin coincidencias.")
            for p in posts:
                parts.append(f"- [{p['id']}] {p['titulo']} ({p['fecha_publicacion']})")
                parts.append(f"  {p['url']}")
                for f in p.get("archivos", []):
                    parts.append(f"    · {f['format']}: {f['label']} — {f['url']}")
            parts.append("")
            parts.append("Datasets CKAN:")
            if not data["datasets_ckan"]:
                parts.append("  Sin coincidencias.")
            for d in data["datasets_ckan"]:
                parts.append(f"- {d['titulo']} (id: {d['id']}, {d['organizacion']})")
                for r in d["recursos"][:4]:
                    parts.append(f"    · {r['formato']}: {r['nombre']} — {r['url']}")
            for aviso in data["avisos"]:
                parts.append(f"Aviso: {aviso}")
            parts.append("")
            parts.append(data["nota"])
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)
