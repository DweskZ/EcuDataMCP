from mcp.server.fastmcp import FastMCP

from helpers.format_out import render_output
from helpers.geo_data import (
    find_cantones,
    find_parroquias,
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
        canton: str = "",
        nivel: str = "auto",
        format: str = "text",
    ) -> str:
        """
        Look up Ecuador DPA geography: provinces, cantons and parroquias (INEC codes).

        - nivel='provincia' | 'canton' | 'parroquia' | 'auto'
        - For parroquias, filter with canton= and/or provincia= (recommended)

        Args:
            query: Name or code (e.g. "Pichincha", "Cuenca", "Tumbaco", "170150")
            region: Optional natural region for provinces/cantons
            provincia: Optional province filter
            canton: Optional canton filter (useful for parroquias)
            nivel: auto | provincia | canton | parroquia
            format: text | json
        """
        nivel_norm = (nivel or "auto").strip().lower()
        if nivel_norm not in {"auto", "provincia", "canton", "parroquia"}:
            nivel_norm = "auto"

        provs: list[dict] = []
        cants: list[dict] = []
        parrs: list[dict] = []

        if nivel_norm in {"auto", "provincia"}:
            if query.strip() or region.strip():
                provs = find_provincias(query=query.strip(), region=region.strip())
            elif nivel_norm == "provincia":
                provs = list_provincias()

        if nivel_norm in {"auto", "canton"}:
            if query.strip() or provincia.strip() or region.strip():
                cants = find_cantones(
                    query=query.strip(),
                    provincia=provincia.strip(),
                    region=region.strip(),
                )
            elif nivel_norm == "canton":
                cants = list_cantones()

        # Avoid dumping all 1000+ parroquias unless filtered.
        wants_parroquias = nivel_norm in {"auto", "parroquia"} and (
            query.strip()
            or canton.strip()
            or provincia.strip()
            or nivel_norm == "parroquia"
        )
        if wants_parroquias:
            if nivel_norm == "parroquia" and not (
                query.strip() or canton.strip() or provincia.strip()
            ):
                empty = {
                    "error": "filtro_requerido",
                    "hint": "Usa query, canton o provincia para listar parroquias",
                }
                return render_output(
                    empty,
                    format,
                    text_builder=lambda d: (
                        "Para parroquias indica query, canton= o provincia=. "
                        "Ej: query='Tumbaco', canton='Quito', provincia='Pichincha'."
                    ),
                )
            parrs = find_parroquias(
                query=query.strip(),
                canton=canton.strip(),
                provincia=provincia.strip(),
            )

        if (
            nivel_norm == "auto"
            and not query.strip()
            and not provincia.strip()
            and not canton.strip()
            and not region.strip()
        ):
            provs = list_provincias()
            cants = []
            parrs = []

        payload = {
            "nivel": nivel_norm,
            "provincias": provs,
            "cantones": cants[:50],
            "cantones_total": len(cants),
            "parroquias": parrs[:50],
            "parroquias_total": len(parrs),
        }

        if not provs and not cants and not parrs:
            empty = {
                "error": "sin_resultados",
                "query": query,
                "region": region,
                "provincia": provincia,
                "canton": canton,
                "nivel": nivel_norm,
            }
            return render_output(
                empty,
                format,
                text_builder=lambda _: (
                    f"No se encontraron ubicaciones para query='{query}' "
                    f"provincia='{provincia}' canton='{canton}' region='{region}'. "
                    "Ejemplos: Pichincha, Cuenca, Tumbaco, 170150, nivel='parroquia'."
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
                    + (
                        f", mostrando {len(shown)}"
                        if data["cantones_total"] > len(shown)
                        else ""
                    )
                    + "):"
                )
                for c in shown:
                    pop = c.get("poblacion")
                    pop_txt = (
                        f", pob≈{int(pop):,}" if isinstance(pop, (int, float)) else ""
                    )
                    parts.append(
                        f"- {c['codigo']} {c['nombre']} ({c['provincia']}"
                        f", {c.get('region', '')}{pop_txt})"
                    )
            if data["parroquias"]:
                parts.append("")
                shown_p = data["parroquias"]
                parts.append(
                    f"Parroquias ({data['parroquias_total']}"
                    + (
                        f", mostrando {len(shown_p)}"
                        if data["parroquias_total"] > len(shown_p)
                        else ""
                    )
                    + "):"
                )
                for row in shown_p:
                    parts.append(
                        f"- {row['codigo']} {row['nombre']} "
                        f"({row.get('canton', '')}, {row.get('provincia', '')})"
                    )
            parts.append("")
            parts.append(
                "Tip: usa estos nombres/códigos en search_datasets, search_contratos "
                "o search_eventos_riesgo."
            )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
