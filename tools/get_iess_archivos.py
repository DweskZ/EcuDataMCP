from typing import Literal

from mcp.server.fastmcp import FastMCP

from helpers import iess_client
from helpers.format_out import render_output
from helpers.logging import log_tool

_COLECCIONES = ("boletines", "estudios_actuariales", "informes_auditoria")


def register_get_iess_archivos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_iess_archivos(
        coleccion: Literal["boletines", "estudios_actuariales", "informes_auditoria"],
        anio: int | None = None,
        query: str = "",
        format: str = "text",
    ) -> str:
        """
        List one IESS (Instituto Ecuatoriano de Seguridad Social) document
        collection's actual documents, each resolved to a direct download
        URL, título, and formato. Call list_iess_colecciones first to see
        what years/counts each collection has.

        Args:
            coleccion: "boletines" (Boletines Estadísticos, annual, 1978-
                2024 confirmed), "estudios_actuariales" (actuarial
                valuation studies per fund, published only for a handful of
                years so far), or "informes_auditoria" (audit reports,
                2007-2026 confirmed, folders by year).
            anio: Filter to one year. REQUIRED for "informes_auditoria" (a
                year can hold up to ~42 documents, each needing its own
                detail-page fetch to resolve — there's no cheap "all years"
                call). Optional for the other two collections, which are
                small enough to always resolve in full.
            query: Free text matched (accent-insensitive) against título
                (and descripción/grupo where the collection has one).
            format: text | json
        """
        if coleccion not in _COLECCIONES:
            return render_output(
                {
                    "error": f"coleccion '{coleccion}' no reconocida. Válidas: {_COLECCIONES}"
                },
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        try:
            if coleccion == "boletines":
                result = await iess_client.list_boletines(anio=anio, query=query)
                items_key = "boletines"
            elif coleccion == "estudios_actuariales":
                result = await iess_client.list_estudios_actuariales(
                    anio=anio, query=query
                )
                items_key = "documentos"
            else:
                if anio is None:
                    return render_output(
                        {
                            "error": (
                                "coleccion='informes_auditoria' requiere anio. "
                                "Use list_iess_colecciones para ver los años disponibles "
                                "(2007-2026 confirmado) y su conteo de documentos."
                            )
                        },
                        format,
                        text_builder=lambda d: f"Error: {d['error']}",
                    )
                result = await iess_client.get_auditoria_documentos(
                    anio=anio, query=query
                )
                items_key = "documentos"
        except ValueError as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        def to_text(data: dict) -> str:
            items = data.get(items_key) or []
            parts = [
                f"IESS — {coleccion} ({data.get('total', len(items))} documento(s)):",
                "",
            ]
            if not items:
                parts.append("No se encontraron documentos con esos filtros.")
                return "\n".join(parts)
            for item in items:
                etiqueta_partes = [
                    p for p in (item.get("grupo"), item.get("titulo")) if p
                ]
                etiqueta = " / ".join(etiqueta_partes)
                anios = item.get("anios") or ([item["anio"]] if "anio" in item else [])
                anios_str = f" ({', '.join(str(a) for a in anios)})" if anios else ""
                parts.append(
                    f"- {etiqueta}{anios_str} [{item.get('formato', 'DESCONOCIDO')}]"
                )
                if item.get("descripcion"):
                    parts.append(f"   {item['descripcion']}")
                parts.append(f"   {item.get('url') or '(sin URL resuelta)'}")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)
