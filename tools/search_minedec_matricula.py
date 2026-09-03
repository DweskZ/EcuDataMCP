from mcp.server.fastmcp import FastMCP

from helpers import minedec_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_minedec_matricula_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_minedec_matricula(query: str = "", format: str = "text") -> str:
        """
        List MINEDEC's (Ministerio de Educación, Deporte y Cultura) historical
        basic-education (K-12 / educación básica y bachillerato) enrollment
        registry files: "Registro Administrativo Histórico" 2009-present.

        This is a DIFFERENT ministry sub-domain from this project's existing
        SENESCYT/higher-education CKAN coverage (organization=ministerio-de-
        educacion) — that's universities/institutos técnicos, this is basic
        education matrícula. Returns direct XLSX links, not file contents —
        the registry files are 30-140 MB (too large to preview/download
        through this server), so fetch them yourself or via download_resource
        if you specifically need the bytes.

        Files: two large registry XLSX (start-of-year "Inicio" and
        end-of-year "Fin" snapshots), a metadata file for each, and one
        shared data dictionary. Note the Inicio/Fin files disagree slightly
        on the exact final year covered (confirmed live in the real
        filenames) — treat the file contents as authoritative over any
        year-range claim in this tool's output.

        Args:
            query: Free text matched (accent-insensitive) against the file's
                label, tipo ("registro"/"metadato"/"diccionario"), periodo
                ("inicio"/"fin"), or URL, e.g. "inicio", "diccionario",
                "metadato fin". Empty returns all files.
            format: text | json
        """
        try:
            result = await minedec_client.search_matricula(query=query)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar el Registro Administrativo del MINEDEC: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"Registro Administrativo Histórico MINEDEC (Educación Básica) — "
                    f"{data['total']} resultado(s) de {data['total_en_pagina']} archivos"
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, f in enumerate(archivos, 1):
                periodo = f" ({f['periodo']})" if f.get("periodo") else ""
                parts.append(f"{i}. {f.get('label')} [{f.get('tipo')}{periodo}, {f.get('format')}]")
                parts.append(f"   {f.get('url')}")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)
