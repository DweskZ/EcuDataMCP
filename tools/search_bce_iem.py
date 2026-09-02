import logging

from mcp.server.fastmcp import FastMCP

from helpers import bce_iem_client
from helpers.format_out import render_output
from helpers.logging import MAIN_LOGGER_NAME, log_tool
from helpers.response_contract import with_response_metadata

logger = logging.getLogger(MAIN_LOGGER_NAME)


def register_search_bce_iem_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_bce_iem(
        query: str = "",
        limit: int = 20,
        offset: int = 0,
        historico: bool = False,
        desde_anio: int = 0,
        hasta_anio: int = 0,
        guardar_catalogo: bool = False,
        hash_archivos: bool = False,
        max_hash_archivos: int = 5000,
        format: str = "text",
    ) -> str:
        """Search individual Excel tables in the BCE's latest IEM bulletin.

        Use this for detailed BCE tables not conveniently available through
        search_indicadores_bce/BCEData: trade by country, debt, public
        finance by government level, oil, GDP breakdowns, and more. It lists
        tables from the current monthly bulletin; use get_bce_iem_table with
        a returned table_id to inspect one official XLSX file. Set
        historico=true (or provide desde_anio/hasta_anio) to search across
        all matching monthly bulletin pages; this is slower on the first call
        because the archive pages must be read.
        Set guardar_catalogo=true to persist the complete catalog assembled by
        this search under IEM_CATALOG_DIR (or data/iem_catalog_snapshots by
        default). Pagination still keeps the MCP response bounded.
        Set hash_archivos=true for an operator-style SHA-256 audit of the
        discovered XLSX files. This downloads complete files, so it is
        deliberately opt-in and bounded by max_hash_archivos.
        """
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)
        try:
            result = await bce_iem_client.search_tables(
                query,
                limit,
                offset,
                historico,
                desde_anio,
                hasta_anio,
                guardar_catalogo,
                hash_archivos,
                max_hash_archivos,
            )
        except Exception as exc:
            logger.exception("search_bce_iem failed (query=%r)", query)
            return render_output(
                {"error": str(exc)},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        def to_text(data: dict) -> str:
            bulletin = data["boletin"]
            tables = data["tablas"]
            parts = [
                f"BCE IEM — boletín {bulletin['numero']} ({bulletin['titulo']})",
                f"{data['total']} tabla(s) encontrada(s); mostrando {len(tables)}.",
                "",
            ]
            if data.get("boletines_descubiertos"):
                parts.insert(
                    1,
                    (
                        f"Archivo descubierto: {data['boletines_descubiertos']} boletines; "
                        f"del No. {data.get('primer_boletin')} al No. "
                        f"{data.get('ultimo_boletin')}."
                    ),
                )
                if data.get("numeros_faltantes"):
                    parts.insert(
                        2,
                        "Números faltantes detectados: "
                        + ", ".join(map(str, data["numeros_faltantes"][:30]))
                        + ("…" if len(data["numeros_faltantes"]) > 30 else "."),
                    )
            if data.get("historico"):
                parts.insert(
                    1,
                    f"Búsqueda histórica: {data.get('boletines_consultados', '?')} boletines.",
                )
                if data.get("boletines_sin_tablas"):
                    parts.insert(
                        2,
                        f"Boletines omitidos sin XLSX individual: {data['boletines_sin_tablas']}.",
                    )
            for index, table in enumerate(tables, 1):
                parts.extend(
                    [
                        f"{index}. {table['titulo']}",
                        f"   table_id: {table['table_id']}",
                        (
                            f"   boletines disponibles: {table['boletines_disponibles']}"
                            if table.get("boletines_disponibles")
                            else ""
                        ),
                        f"   {table['seccion']}" if table["seccion"] else "",
                        "",
                    ]
                )
            if not tables:
                parts.append("Sin resultados.")
            else:
                parts.append("Usa get_bce_iem_table(table_id=...) para leer una tabla.")
            if data.get("catalogo_guardado"):
                parts.append(
                    "Catálogo completo guardado: "
                    + data["catalogo_guardado"]["archivo"]
                )
            if data.get("hash_archivos"):
                audit = data["hash_archivos"]
                parts.append(
                    "Auditoría SHA-256: "
                    f"{audit['archivos_exitosos']}/{audit['archivos_consultados']} "
                    "archivos calculados."
                )
            return "\n".join(part for part in parts if part is not None)

        bulletin = result["boletin"]
        result = with_response_metadata(
            result,
            source=result["source"],
            source_url=result["url_fuente"],
            freshness="boletin_mensual",
            schema_name="bce_iem_catalogo_v1",
            schema_fields=["boletin", "total", "tablas", "historico"],
            consulted_at=result["catalogado_en"],
            published_at=f"{bulletin.get('anio')}-{bulletin.get('mes'):02d}"
            if bulletin.get("anio") and bulletin.get("mes") else None,
        )
        return render_output(result, format, text_builder=to_text)
