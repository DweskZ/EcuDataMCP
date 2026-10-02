"""Zero-argument catalog listings behind one tool.

ARCONEL's report builder, BCE's daily/monthly indicator widgets,
Contraloría's open-data documents, IESS's document collections and the SUT
Power BI dashboards each had a `list_*` tool that took no filters and
returned what the matching `get_*` tool needs next. `fuente` now picks the
catalog; the `get_*` tools are unchanged.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import (
    arconel_reportes_client,
    bce_indicadores_diarios_client,
    contraloria_client,
    iess_client,
    sut_powerbi_client,
)
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY

Fuente = Literal["arconel", "bce_diarios", "contraloria", "iess", "sut"]


async def _arconel() -> dict[str, Any]:
    return await arconel_reportes_client.list_arconel_reportes()


async def _bce_diarios() -> dict[str, Any]:
    catalog = await bce_indicadores_diarios_client.list_indicadores()
    return {"total": len(catalog), "catalogo": catalog}


async def _contraloria() -> dict[str, Any]:
    informes = await contraloria_client.list_informes()
    return {"total": len(informes), "informes": informes}


async def _sut() -> dict[str, Any]:
    indicadores = sut_powerbi_client.list_indicadores()
    return {"total": len(indicadores), "indicadores": indicadores}


async def _iess() -> dict[str, Any]:
    boletines = await iess_client.list_boletines()
    actuariales = await iess_client.list_estudios_actuariales()
    auditoria = await iess_client.list_auditoria_anios()
    anios_boletines = sorted({y for b in boletines["boletines"] for y in b["anios"]})
    return {
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


_SOURCES: dict[str, Callable[[], Awaitable[dict[str, Any]]]] = {
    "arconel": _arconel,
    "bce_diarios": _bce_diarios,
    "contraloria": _contraloria,
    "iess": _iess,
    "sut": _sut,
}


def _text_arconel(data: dict) -> str:
    parts = ["ARCONEL — reportes estadísticos disponibles", ""]
    seccion = None
    for t in data["tipos"]:
        if t["seccion"] != seccion:
            seccion = t["seccion"]
            parts.append(f"[{seccion}]")
        parts.append(f"  - {t['tipo']}")
    anios = data["anios"]
    parts.append("")
    parts.append(f"Años: {anios[-1]}-{anios[0]}" if anios else "Años: ninguno")
    parts.append(f"Grupos: {', '.join(data['grupos'])}")
    parts.append(f"Fuente: {data['url_fuente']}")
    return "\n".join(parts)


def _text_bce_diarios(data: dict) -> str:
    rows = data["catalogo"]
    parts = [f"Indicadores BCE (diarios/mensuales) — {len(rows)} serie(s):", ""]
    for c in rows:
        parts.append(
            f"- [{c['archivo']} / {c['codigo']}] {c['indicador']} "
            f"({c['periodicidad']}, {c['unidad']}): {c['fecha_desde']} → {c['fecha_hasta']} "
            f"({c['n_datos']} datos)"
        )
    return "\n".join(parts)


def _text_contraloria(data: dict) -> str:
    rows = data["informes"]
    parts = [f"Documentos de Datos Abiertos de la Contraloría — {len(rows)}:", ""]
    if not rows:
        parts.append("No se encontraron documentos.")
    for i in rows:
        parts.append(f"- id={i['id']}: {i['label']}")
        parts.append(f"  {i['url']}")
    return "\n".join(parts)


def _text_sut(data: dict) -> str:
    rows = data["indicadores"]
    parts = [f"Indicadores SUT (Power BI) — {len(rows)} dashboard(s):", ""]
    parts += [f"- {i['indicador']}: {i['nombre']}" for i in rows]
    return "\n".join(parts)


def _text_iess(data: dict) -> str:
    parts = ["IESS — Colecciones de documentos:", ""]
    for c in data["colecciones"]:
        parts.append(f"- {c['coleccion']}: {c['nombre']} ({c['total_documentos']} documento(s))")
        if c["coleccion"] == "boletines":
            parts.append(f"   Años: {c['anio_min']}-{c['anio_max']}")
        elif c["coleccion"] == "estudios_actuariales":
            parts.append(f"   Años disponibles: {', '.join(str(a) for a in c['anios_disponibles'])}")
        else:
            anios = ", ".join(f"{a['anio']} ({a['total_documentos']})" for a in c["anios"])
            parts.append(f"   Años (con conteo): {anios}")
        parts.append(f"   Fuente: {c['url_fuente']}")
    return "\n".join(parts)


_TEXT: dict[str, Callable[[dict], str]] = {
    "arconel": _text_arconel,
    "bce_diarios": _text_bce_diarios,
    "contraloria": _text_contraloria,
    "iess": _text_iess,
    "sut": _text_sut,
}


def register_list_catalogo_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Listar el catálogo de una fuente (ARCONEL, BCE, Contraloría, IESS, SUT)",
        description=(
            "List one source's catalog, the step before its get tool: arconel "
            "(get_arconel_reporte), bce_diarios (get_bce_indicador_diario), "
            "contraloria (get_contraloria_informe), iess (get_iess_archivos), "
            "sut (get_sut_indicador_schema, query_sut_indicador)."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def list_catalogo(
        fuente: Fuente,
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        List the catalog of one source that has no search filters.

        - arconel: ARCONEL electricity report types by section, years
          (1998 on) and company groups; run one with get_arconel_reporte.
        - bce_diarios: BCE daily/monthly indicator widgets outside BCEData
          (riesgo país daily since 2004, gold, WTI, bonds, payments, reserves,
          fiscal and external series); a `codigo` only means one thing within
          its `archivo`. Follow with get_bce_indicador_diario(archivo, codigo).
        - contraloria: Contraloría "Datos Abiertos" quarterly audit-report
          CSVs and annual control plans; follow with get_contraloria_informe.
        - iess: IESS document collections (statistical bulletins, actuarial
          studies, audit reports) with years and counts; follow with
          get_iess_archivos(coleccion, anio).
        - sut: Ministerio del Trabajo SUT Power BI dashboards (contracts since
          2015, labor demand, gender policy); follow with
          get_sut_indicador_schema, then query_sut_indicador.

        Args:
            fuente: Catalog to list; see the list above.
            format: text | json
        """
        try:
            result = await _SOURCES[fuente]()
        except Exception as e:
            raise ToolError(f"Error al listar el catálogo de {fuente}: {e}") from e
        return render_structured({"fuente": fuente, **result}, format, text_builder=_TEXT[fuente])
