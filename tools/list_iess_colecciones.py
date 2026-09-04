from mcp.server.fastmcp import FastMCP

from helpers import iess_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_iess_colecciones_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_iess_colecciones(format: str = "text") -> str:
        """
        List IESS's (Instituto Ecuatoriano de Seguridad Social) three
        document-archive collections (iess.gob.ec) — Boletines
        Estadísticos, Estudios Actuariales, and Informes de Auditoría —
        with the years/counts each currently has published. Call
        get_iess_archivos(coleccion, anio=...) next to get one
        collection's actual documents (título, url, formato).

        Args:
            format: text | json
        """
        boletines, actuariales, auditoria = (
            await iess_client.list_boletines(),
            await iess_client.list_estudios_actuariales(),
            await iess_client.list_auditoria_anios(),
        )

        anios_boletines = sorted(
            {y for b in boletines["boletines"] for y in b["anios"]}
        )
        result = {
            "colecciones": [
                {
                    "coleccion": "boletines",
                    "nombre": "Boletines Estadísticos",
                    "total_documentos": boletines["total"],
                    "anio_min": min(anios_boletines) if anios_boletines else None,
                    "anio_max": max(anios_boletines) if anios_boletines else None,
                    "url_fuente": boletines["url_fuente"],
                },
                {
                    "coleccion": "estudios_actuariales",
                    "nombre": "Estudios Actuariales",
                    "total_documentos": actuariales["total"],
                    "anios_disponibles": actuariales["anios_disponibles"],
                    "url_fuente": actuariales["url_fuente"],
                },
                {
                    "coleccion": "informes_auditoria",
                    "nombre": "Informes de Auditoría",
                    "total_documentos": auditoria["total_documentos"],
                    "anios": auditoria["anios"],
                    "url_fuente": auditoria["url_fuente"],
                    "nota": (
                        "get_iess_archivos requiere anio para esta colección "
                        "(hasta 42 documentos por año, cada uno resuelto vía "
                        "su propia página de detalle)."
                    ),
                },
            ]
        }

        def to_text(data: dict) -> str:
            parts = ["IESS — Colecciones de documentos:", ""]
            for c in data["colecciones"]:
                parts.append(
                    f"- {c['coleccion']}: {c['nombre']} ({c['total_documentos']} documento(s))"
                )
                if c["coleccion"] == "boletines":
                    parts.append(f"   Años: {c['anio_min']}-{c['anio_max']}")
                elif c["coleccion"] == "estudios_actuariales":
                    parts.append(
                        f"   Años disponibles: {', '.join(str(a) for a in c['anios_disponibles'])}"
                    )
                else:
                    anios_str = ", ".join(
                        f"{a['anio']} ({a['total_documentos']})" for a in c["anios"]
                    )
                    parts.append(f"   Años (con conteo): {anios_str}")
                parts.append(f"   Fuente: {c['url_fuente']}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)
