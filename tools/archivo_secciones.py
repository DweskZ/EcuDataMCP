"""Institutional document archives behind one list/get pair.

ARCSA, Superbancos, SEPS, INEVAL, the SGR and SENESCYT libraries, SIPA and
the Guayaquil and Quito stock exchanges (BVG, BVQ) each publish a fixed set of sections (categories, families, modules) whose
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
    bvg_client,
    bvq_client,
    ineval_client,
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
    "arcsa", "superbancos", "seps", "ineval", "sgr", "senescyt", "sipa", "bvg", "bvq"
]

_NOMBRES = {
    "arcsa": "ARCSA — Base de Registros Emitidos",
    "superbancos": "Superintendencia de Bancos — estadísticas",
    "seps": "SEPS — estadísticas SFPS/EPS",
    "ineval": "INEVAL — bases de datos de evaluaciones",
    "sgr": "SGR — Biblioteca",
    "senescyt": "Educación Superior — Biblioteca",
    "sipa": "SIPA (MAG) — estadísticas agropecuarias",
    "bvg": "Bolsa de Valores de Guayaquil — estadísticas históricas",
    "bvq": "Bolsa de Valores de Quito — estadísticas",
}

# Sources whose list call scrapes a page and returns {"categorias": [...]}.
_CATEGORIA_LISTS = {
    "arcsa": arcsa_client.list_categorias,
    "sgr": sgr_publicaciones_client.list_biblioteca_categorias,
    "senescyt": senescyt_biblioteca_client.list_biblioteca_categorias,
}
# Sources with a fixed, in-code section list keyed by `id_key`.
_STATIC_LISTS = {
    "superbancos": (superbancos_client.list_secciones, "seccion"),
    "seps": (seps_client.list_secciones, "seccion"),
    "ineval": (ineval_client.list_familias, "familia"),
    "sipa": (sipa_client.list_modulos, "modulo"),
    "bvg": (bvg_client.list_secciones, "seccion"),
    "bvq": (bvq_client.list_secciones, "seccion"),
}
_GETTERS = {
    "arcsa": arcsa_client.get_categoria_archivos,
    "superbancos": superbancos_client.get_seccion_archivos,
    "seps": seps_client.get_seccion_archivos,
    "ineval": ineval_client.get_familia_archivos,
    "sgr": sgr_publicaciones_client.get_biblioteca_categoria_archivos,
    "senescyt": senescyt_biblioteca_client.get_biblioteca_categoria_archivos,
    "sipa": sipa_client.get_modulo_archivos,
    "bvg": bvg_client.get_seccion_archivos,
    "bvq": bvq_client.get_seccion_archivos,
}


async def _list_secciones(fuente: str) -> dict[str, Any]:
    if fuente in _CATEGORIA_LISTS:
        result = await _CATEGORIA_LISTS[fuente]()
        secciones = [
            {"id": c["id"], "nombre": c["nombre"], "total_archivos": c["total_archivos"]}
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
            "List the sections of one institution's document archive: ARCSA "
            "sanitary registry, Superbancos and SEPS statistics, INEVAL "
            "evaluation datasets, SGR and Educación Superior libraries, SIPA "
            "agricultural statistics, or the Guayaquil (bvg) and Quito (bvq) "
            "stock exchanges' historical trading files. Next: get_archivo_seccion(fuente, seccion)."
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
        - bvg: Bolsa de Valores de Guayaquil (4 sections: historicos,
          dividendos, valoracion, ofertas_publicas). Trade-by-trade
          history since 2019 (acciones, obligaciones, papel comercial,
          titularizaciones, bonos del Estado, notas de crédito, cetes),
          dividends since 2002, repo-eligible securities, public offers.
        - bvq: Bolsa de Valores de Quito (10 sections: cotizaciones
          históricas, emisiones, renta variable, sector público, boletines
          al cierre/semanales/por valor, valoración, emisores). Public
          files only; the Infolab bulletins need a login.

        Returns each section's `id` (pass it to get_archivo_seccion),
        `nombre`, and either its page `url` or `total_archivos`.

        Args:
            fuente: One of arcsa, superbancos, seps, ineval, sgr, senescyt, sipa,
                bvg, bvq.
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
                    f" ({s['total_archivos']} archivo(s))" if "total_archivos" in s else ""
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
        - bvg, bvq: XLSX/XLS (a few PDFs on bvq). Each file adds `modificado`
          (HTTP Last-Modified, ISO UTC) and `tamano_bytes`: the exchanges
          overwrite the same URL, so check `modificado` for freshness (bvg
          trading files and bvq cotizaciones are rebuilt each trading day;
          dividends, bulletins and some emisiones files are older). bvq
          titles come from file names (the page's buttons have no text).
          bvg workbooks fail in preview_resource_data (invalid stylesheet
          for openpyxl): download the URL instead.

        Files are often several MB: download the URL directly instead of
        using preview_resource_data or download_resource (5 MB cap).

        Args:
            fuente: One of arcsa, superbancos, seps, ineval, sgr, senescyt, sipa,
                bvg, bvq.
            seccion: A section `id` from list_archivo_secciones.
            format: text | json
        """
        try:
            result = await _get_seccion(fuente, seccion)
        except ValueError as e:
            raise ToolError(f"Error: {e}") from e
        except Exception as e:
            raise ToolError(f"Error al obtener la sección {seccion} de {fuente}: {e}") from e

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
                detalle = [str(a.get("formato"))]
                if a.get("tamano_bytes"):
                    detalle.append(f"{a['tamano_bytes'] / 1_048_576:.1f} MB")
                if a.get("modificado"):
                    detalle.append(f"modificado {a['modificado'][:10]}")
                parts.append(f"- {etiqueta} [{', '.join(detalle)}]")
                if a.get("descripcion"):
                    parts.append(f"   {a['descripcion']}")
                parts.append(f"   {a.get('url')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)
