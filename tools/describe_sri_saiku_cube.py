from mcp.server.fastmcp import FastMCP

from helpers import sri_saiku_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_describe_sri_saiku_cube_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def describe_sri_saiku_cube(cube_id: str, format: str = "text") -> str:
        """
        Describir un cubo Saiku público del SRI: dimensiones, jerarquías,
        niveles, medidas y metadatos OLAP.

        Usa solo rutas de descubrimiento de lectura. No consulta filas ni
        devuelve la configuración Oracle de las fuentes.

        Args:
            cube_id: Identificador devuelto por list_sri_saiku_cubes
            format: text | json
        """
        try:
            data = await sri_saiku_client.describe_cube(cube_id)
        except Exception as exc:
            return render_output(
                {"error": str(exc), "cube_id": cube_id},
                format,
                text_builder=lambda result: (
                    f"Error al describir el cubo Saiku '{result['cube_id']}': "
                    f"{result['error']}"
                ),
            )

        def to_text(result: dict) -> str:
            cube = result["cube"]
            metadata = result.get("metadata") or {}
            parts = [
                f"Cubo Saiku del SRI: {cube.get('cube')}",
                f"cube_id: {cube.get('cube_id')}",
                "",
                "Secciones devueltas:",
            ]
            for section, value in metadata.items():
                if isinstance(value, list):
                    parts.append(f"- {section}: {len(value)} elemento(s)")
                elif isinstance(value, dict):
                    parts.append(f"- {section}: objeto con {len(value)} clave(s)")
                else:
                    parts.append(f"- {section}: disponible")
            parts.extend(["", f"Fuente: {result['source']} facultada para lectura"])
            return "\n".join(parts)

        return render_output(data, format, text_builder=to_text)
