from mcp.server.mcpserver import MCPServer

from helpers import cepalstat_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_cepalstat_indicador_tool(mcp: MCPServer) -> None:
    @mcp.tool()
    @log_tool
    async def get_cepalstat_indicador(
        indicator_id: int, pais: str = "Ecuador", lang: str = "es", format: str = "text"
    ) -> str:
        """
        Fetch one CEPALSTAT indicator's observations, filtered to one
        country (Ecuador by default) so the response stays small — CEPAL's
        raw API returns every country in the region (and often the world)
        per indicator otherwise, confirmed live at ~2.5 MB unfiltered vs.
        ~85 KB filtered to one country.

        Get indicator_id from search_cepalstat_indicadores. Each returned
        record decodes CEPALSTAT's raw dimension ids into readable labels
        (e.g. "Sexo": "Mujeres", "Años": "1975") using that same
        indicator's own dimension catalog — not every indicator has the
        same dimensions (some are just country × year, others add sex,
        age group, etc.).

        Args:
            indicator_id: An "indicator_id" from search_cepalstat_indicadores.
            pais: Country to filter to (accent-insensitive, e.g. "Ecuador",
                "Peru"). Empty string fetches every country the indicator
                covers — can be a few MB for a rich indicator.
            lang: "es" (default) or "en"
            format: text | json
        """
        try:
            result = await cepalstat_client.get_indicador(indicator_id, pais=pais, lang=lang)
        except Exception as e:
            return render_output(
                {"error": str(e), "indicator_id": indicator_id, "pais": pais},
                format,
                text_builder=lambda d: (
                    f"Error al obtener el indicador {d['indicator_id']} de CEPALSTAT: "
                    f"{d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            meta = data.get("metadata") or {}
            registros = data.get("registros") or []
            parts = [
                (
                    f"CEPALSTAT — {meta.get('indicator_name', '(sin nombre)')} "
                    f"(indicator_id={data['indicator_id']})"
                ),
                (
                    f"Unidad: {meta.get('unit', '?')} | Tema: {meta.get('theme', '?')} | "
                    f"Área: {meta.get('area', '?')}"
                ),
            ]
            if data.get("pais_filtrado"):
                parts.append(f"Filtrado a: {data['pais_filtrado']}")
            parts.append(f"{data['total_registros']} registro(s):")
            parts.append("")
            if not registros:
                parts.append("Sin registros.")
            for r in registros[:100]:
                otros = {k: v for k, v in r.items() if k not in ("valor", "iso3", "source_id")}
                etiqueta = ", ".join(f"{k}={v}" for k, v in otros.items())
                parts.append(f"- {r.get('valor')} [{etiqueta}]")
            if len(registros) > 100:
                parts.append(f"... y {len(registros) - 100} más (usa format=json para verlos todos)")
            fuentes = data.get("fuentes") or []
            if fuentes:
                parts.append("")
                parts.append("Fuente(s): " + "; ".join(f.get("description", "") for f in fuentes))
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)
