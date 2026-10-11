"""Institutional document archives behind one list/get pair.

ARCSA, Superbancos, SEPS, INEVAL, the SGR and SENESCYT libraries and SIPA
each publish a fixed set of sections (categories, families, modules) whose
pages list downloadable files. They used to be 14 tools, one list/get pair
per institution, with the same two-step flow and the same file-listing
shape; `fuente` now picks the institution instead (the same pattern as
`source=` on the CKAN tools). The per-source clients are unchanged.
"""

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import (
    arcsa_client,
    ineval_client,
    ministerio_energia_client,
    petroecuador_client,
    senescyt_biblioteca_client,
    seps_client,
    sgr_publicaciones_client,
    sipa_client,
    superbancos_client,
)
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY

Fuente = Literal[
    "arcsa",
    "superbancos",
    "seps",
    "ineval",
    "sgr",
    "senescyt",
    "sipa",
    "petroecuador",
    "energia",
]

_NOMBRES = {
    "arcsa": "ARCSA — Base de Registros Emitidos",
    "superbancos": "Superintendencia de Bancos — estadísticas",
    "seps": "SEPS — estadísticas SFPS/EPS",
    "ineval": "INEVAL — bases de datos de evaluaciones",
    "sgr": "SGR — Biblioteca",
    "senescyt": "Educación Superior — Biblioteca",
    "sipa": "SIPA (MAG) — estadísticas agropecuarias",
    "petroecuador": "EP Petroecuador — Cifras Institucionales",
    "energia": "Ministerio de Ambiente y Energía — hidrocarburos, minería y BEN",
}

# Sources whose list call scrapes a page and returns {"categorias": [...]}.
_CATEGORIA_LISTS = {
    "arcsa": arcsa_client.list_categorias,
    "sgr": sgr_publicaciones_client.list_biblioteca_categorias,
    "senescyt": senescyt_biblioteca_client.list_biblioteca_categorias,
    "petroecuador": petroecuador_client.list_categorias,
    "energia": ministerio_energia_client.list_secciones,
}
# Sources with a fixed, in-code section list keyed by `id_key`.
_STATIC_LISTS = {
    "superbancos": (superbancos_client.list_secciones, "seccion"),
    "seps": (seps_client.list_secciones, "seccion"),
    "ineval": (ineval_client.list_familias, "familia"),
    "sipa": (sipa_client.list_modulos, "modulo"),
}
_GETTERS = {
    "arcsa": arcsa_client.get_categoria_archivos,
    "superbancos": superbancos_client.get_seccion_archivos,
    "seps": seps_client.get_seccion_archivos,
    "ineval": ineval_client.get_familia_archivos,
    "sgr": sgr_publicaciones_client.get_biblioteca_categoria_archivos,
    "senescyt": senescyt_biblioteca_client.get_biblioteca_categoria_archivos,
    "energia": ministerio_energia_client.get_seccion_archivos,
    "sipa": sipa_client.get_modulo_archivos,
    "petroecuador": petroecuador_client.get_categoria_archivos,
}


async def _list_secciones(fuente: str) -> dict[str, Any]:
    if fuente in _CATEGORIA_LISTS:
        result = await _CATEGORIA_LISTS[fuente]()
        secciones = [
            {
                "id": c["id"],
                "nombre": c["nombre"],
                "total_archivos": c["total_archivos"],
            }
            for c in result["categorias"]
        ]
        url_fuente = result.get("url_fuente")
    else:
        lister, id_key = _STATIC_LISTS[fuente]
        secciones = [
            {"id": s[id_key], "nombre": s["nombre"], "url": s["url"]} for s in lister()
        ]
        url_fuente = None
    return {
        "fuente": fuente,
        "nombre_fuente": _NOMBRES[fuente],
        "url_fuente": url_fuente,
        "total": len(secciones),
        "secciones": secciones,
    }


async def _get_seccion(fuente: str, seccion: str) -> dict[str, Any]:
    result = await _GETTERS[fuente](seccion)
    archivos = result.get("archivos") or []
    seccion_id = next(
        (result[k] for k in ("id", "seccion", "familia", "modulo") if result.get(k)),
        seccion,
    )
    return {
        "fuente": fuente,
        "nombre_fuente": _NOMBRES[fuente],
        "id": seccion_id,
        "nombre": result.get("nombre"),
        "url": result.get("url") or result.get("url_fuente"),
        "descripcion": result.get("descripcion") or None,
        "total": len(archivos),
        "archivos": archivos,
    }


def register_archivo_secciones_tools(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Listar secciones de un archivo institucional",
        description=(
            "List the sections of one institution's document archive (ARCSA, "
            "Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, "
            "Petroecuador, Energy Ministry). fuente values and sections are "
            "in the docstring. "
            "Next: get_archivo_seccion(fuente, seccion)."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def list_archivo_secciones(
        fuente: Fuente, format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        List the sections of one institution's document archive.

        Sources (`fuente`):
        - arcsa: ARCSA "Base de Registros Emitidos"
          (controlsanitario.gob.ec/base-de-datos/), the live sanitary
          registry (food, medicines, cosmetics, medical devices...), 27
          categories. Different from the ARCSA CKAN datasets, which only
          cover suspended/cancelled records.
        - superbancos: Superintendencia de Bancos statistics (4 sections:
          boletines_financieros, servicios_financieros,
          informacion_historica, calendario_estadistico). No CKAN
          organization exists. boletines_financieros and
          servicios_financieros add the page's OneDrive folders to the
          static tables.
        - seps: SEPS statistics (estadisticas.seps.gob.ec), 22 SFPS
          sections (cooperatives: financial statements, deposits, credit,
          rates, risk ratings) plus 4 EPS sections. seps.gob.ec itself
          blocks automated access.
        - ineval: INEVAL evaluation datasets, 9 families (ser_bachiller,
          ser_estudiante and variants, ser_maestro, ser_profesional,
          llece). Only these keys have real download pages.
        - sgr: SGR Biblioteca (gestionderiesgos.gob.ec/biblioteca/),
          ~1,660 documents in 19 categories (resolutions, contingency
          plans, threat maps). Not event reports: see search_sgr_sitreps.
        - senescyt: Educación Superior Biblioteca
          (educacion.gob.ec/edusuperior/biblioteca/), ~1,259 documents in
          17 categories (PAC, LOES/SNNA normativa, acuerdos, auditorías).
        - sipa: SIPA, Ministerio de Agricultura (4 modules: economico,
          productivo, social, censos). Distinct from MPCEIP.
        - petroecuador: EP Petroecuador "Cifras Institucionales"
          (eppetroecuador.ec/?p=3721), 8 sections: estados financieros,
          informes estadísticos mensuales y anuales (2006 onward, PDF),
          exploración y producción (daily field production, well
          nomenclature), comercialización (prices, subsidy value,
          dispatches), refinación, comercialización internacional (WTI),
          gestión de riesgos.
        - energia: Ministerio de Ambiente y Energía (ambienteyenergia.gob.ec,
          which absorbed Energía y Minas, MERNNR and Hidrocarburos), 4
          sections read from its WordPress media library: hydrocarbon
          statistics (crudo/derivados yearbooks 2002-2024), mining exports
          and tax revenue, 2020-21 weekly mining reports, and the Balance
          Energético Nacional. The old ARCERNNR and recursosyenergia hosts
          are dead; electricity regulation is in get_arconel_reporte.

        Returns each section's `id` (pass it to get_archivo_seccion),
        `nombre`, and either its page `url` or `total_archivos`.

        Args:
            fuente: One of arcsa, superbancos, seps, ineval, sgr, senescyt,
                sipa, petroecuador, energia.
            format: text | json
        """
        try:
            result = await _list_secciones(fuente)
        except Exception as e:
            raise ToolError(f"Error al listar las secciones de {fuente}: {e}") from e

        def to_text(data: dict) -> str:
            parts = [f"{data['nombre_fuente']} — {data['total']} sección(es):", ""]
            for s in data["secciones"]:
                extra = (
                    f" ({s['total_archivos']} archivo(s))"
                    if "total_archivos" in s
                    else ""
                )
                parts.append(f"- {s['id']}: {s['nombre']}{extra}")
                if s.get("url"):
                    parts.append(f"  {s['url']}")
            if data.get("url_fuente"):
                parts.extend(["", f"Fuente: {data['url_fuente']}"])
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

    @mcp.tool(
        title="Ver archivos de una sección de un archivo institucional",
        description=(
            "List the downloadable files (title, URL, format) in one section "
            "from list_archivo_secciones. Returns links, not file contents; "
            "download large files directly (preview/download tools cap at 5 MB)."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_archivo_seccion(
        fuente: Fuente, seccion: str, format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        List the files published in one section of an institutional archive.

        Each file has `titulo`, `url` and `formato`, plus source-specific
        context when the page provides it: `grupo`/`periodo` (Superbancos,
        SEPS, INEVAL tables and accordions), `subgrupo` (nested categories
        in ARCSA and the SGR/SENESCYT libraries), `descripcion` and
        `numero` (SIPA). Returns links, not contents.

        Per-source caveats:
        - arcsa, sgr, senescyt: `seccion` may be the category id or its
          nombre (accent/case-insensitive). Links carry no extension, so
          formato is DESCONOCIDO. A real share of SGR links 404; treat the
          SGR listing as a catalog, not a guarantee.
        - superbancos: coverage is whatever the portal uploaded (static
          tables plus OneDrive folders), not a guaranteed monthly series.
        - seps: some links go through a download-monitor redirect
          (formato DESCONOCIDO) that resolves to the same static files.
        - ineval: some ids 308-redirect to a static file; both work.
        - sipa: XLSX/XLS files, some over 40 MB.
        - petroecuador: `seccion` is the id or nombre. Mostly PDFs; links
          through download.php redirect to the current PDF (formato
          DESCONOCIDO). The "Producción de Campo BPPD" title embeds the
          day's figure and effective date as the page publishes it.
          Reports are PDFs, not tables: read them with read_pdf.

        Files are often several MB: download the URL directly instead of
        using preview_resource_data or download_resource (5 MB cap).

        Args:
            fuente: One of arcsa, superbancos, seps, ineval, sgr, senescyt,
                sipa, petroecuador, energia.
            seccion: A section `id` from list_archivo_secciones.
            format: text | json
        """
        try:
            result = await _get_seccion(fuente, seccion)
        except ValueError as e:
            raise ToolError(f"Error: {e}") from e
        except Exception as e:
            raise ToolError(
                f"Error al obtener la sección {seccion} de {fuente}: {e}"
            ) from e

        def to_text(data: dict) -> str:
            parts = [f"{data['nombre_fuente']} — {data['nombre']} ({data['id']})"]
            if data.get("url"):
                parts.append(f"URL: {data['url']}")
            if data.get("descripcion"):
                parts.append(data["descripcion"])
            parts.append("")
            archivos = data["archivos"]
            if not archivos:
                parts.append("No se encontraron archivos descargables en esta sección.")
                return "\n".join(parts)
            parts.append(f"{len(archivos)} archivo(s):")
            for a in archivos:
                etiqueta = " / ".join(
                    str(p)
                    for p in (
                        a.get("subgrupo"),
                        a.get("grupo"),
                        a.get("periodo"),
                        a.get("titulo"),
                    )
                    if p
                )
                parts.append(f"- {etiqueta} [{a.get('formato')}]")
                if a.get("descripcion"):
                    parts.append(f"   {a['descripcion']}")
                parts.append(f"   {a.get('url')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)
