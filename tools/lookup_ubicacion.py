from mcp.server.fastmcp import FastMCP

from helpers.format_out import render_output
from helpers.geo_data import (
    find_cantones,
    find_provincias,
    list_cantones,
    list_provincias,
)
from helpers.logging import log_tool


def register_lookup_ubicacion_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def lookup_ubicacion(
        query: str = "",
        region: str = "",
        provincia: str = "",
        nivel: str = "auto",
        format: str = "text",
    ) -> str:
        """
        Look up Ecuador DPA geography: provinces and cantons (INEC codes).

        - nivel='provincia': only provinces
        - nivel='canton': only cantons (optionally filter by provincia/region)
        - nivel='auto' (default): provinces if query matches one; otherwise cantons,
          or both lists when query is empty

        Args:
            query: Name or code (e.g. "Pichincha", "Cuenca", "1701", "09")
            region: Optional natural region: Sierra, Costa, Amazonía, Insular
            provincia: Optional province filter when searching cantons
            nivel: auto | provincia | canton
            format: text | json
        """
        nivel_norm = (nivel or "auto").strip().lower()
        if nivel_norm not in {"auto", "provincia", "canton"}:
            nivel_norm = "auto"

        provs: list[dict] = []
        cants: list[dict] = []

        if nivel_norm in {"auto", "provincia"}:
            if query.strip() or region.strip():
                provs = find_provincias(query=query.strip(), region=region.strip())
            elif nivel_norm == "provincia":
                provs = list_provincias()

        if nivel_norm in {"auto", "canton"}:
            # In auto mode, if we already matched provinces cleanly and query looks
            # like a province-only ask, still also search cantons when no province hit
            # or when query is empty / explicit canton intent.
            want_cantons = True
            if nivel_norm == "auto" and provs and len(query.strip()) >= 2:
                # also search cantons; useful for "Quito" which is a canton name
                pass
            if want_cantons:
                if query.strip() or provincia.strip() or region.strip():
                    cants = find_cantones(
                        query=query.strip(),
                        provincia=provincia.strip(),
                        region=region.strip(),
                    )
                elif nivel_norm == "canton":
                    cants = list_cantones()

        if nivel_norm == "auto" and not query.strip() and not provincia.strip() and not region.strip():
            provs = list_provincias()
            cants = []

        payload = {
            "nivel": nivel_norm,
            "provincias": provs,
            "cantones": cants[:50],
            "cantones_total": len(cants),
        }

        if not provs and not cants:
            empty = {
                "error": "sin_resultados",
                "query": query,
                "region": region,
                "provincia": provincia,
                "nivel": nivel_norm,
            }
            return render_output(
                empty,
                format,
                text_builder=lambda _: (
                    f"No se encontraron ubicaciones para query='{query}' "
                    f"provincia='{provincia}' region='{region}'. "
                    "Ejemplos: Pichincha, Cuenca, Guayas, 1701, nivel='canton'."
                ),
            )

        def to_text(data: dict) -> str:
            parts = [
                "División Político-Administrativa del Ecuador (códigos INEC)",
                f"Nivel: {data['nivel']}",
            ]
            if data["provincias"]:
                parts.append("")
                parts.append(f"Provincias ({len(data['provincias'])}):")
                for p in data["provincias"]:
                    parts.append(
                        f"- {p['codigo']} {p['nombre']} — capital: {p['capital']} ({p['region']})"
                    )
            if data["cantones"]:
                parts.append("")
                shown = data["cantones"]
                parts.append(
                    f"Cantones ({data['cantones_total']}"
                    + (f", mostrando {len(shown)}" if data["cantones_total"] > len(shown) else "")
                    + "):"
                )
                for c in shown:
                    pop = c.get("poblacion")
                    pop_txt = f", pob≈{int(pop):,}" if isinstance(pop, (int, float)) else ""
                    parts.append(
                        f"- {c['codigo']} {c['nombre']} ({c['provincia']}"
                        f", {c.get('region', '')}{pop_txt})"
                    )
            parts.append("")
            parts.append(
                "Tip: usa estos nombres/códigos en search_datasets, search_contratos "
                "o search_eventos_riesgo. Parroquias: busca datasets DPA INEC en CKAN."
            )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
