"""Single-step file-link catalogs behind one search tool.

Eleven tools each scraped one institution's page (or API) into a list of
direct file links and filtered it by free text: SRI datasets and tax
collection, MEF/SENAE fiscal workbooks, the Census 2022 microsite, MINEDEC
enrollment, SENESCYT statistics, MSP gazettes, CNIG gender-violence tables,
the Ministerio del Trabajo's annual bulletin and sectoral wage tables, and
ARCOTEL's two series. Same call, same result shape, so `fuente` now picks
the catalog. The clients are unchanged; this module normalizes each file to
titulo/url/formato (the convention list/get_archivo_seccion already uses)
and keeps any source-specific fields beside them.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import (
    arcotel_client,
    bce_precios_comex_client,
    bce_publicaciones_client,
    bce_remesas_client,
    censo_client,
    cnig_client,
    mef_fiscal_client,
    minedec_client,
    msp_gacetas_inmunoprevenibles_client,
    salarios_sectoriales_client,
    senescyt_client,
    sri_client,
    trabajo_boletin_anual_client,
)
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.text_utils import strip_accents
from helpers.tool_meta import READ_ONLY

Fuente = Literal[
    "sri_datasets",
    "sri_recaudacion",
    "mef",
    "senae",
    "censo",
    "minedec",
    "senescyt",
    "msp",
    "cnig",
    "trabajo_boletin",
    "salarios",
    "arcotel_boletines",
    "arcotel_mensuales",
    "bce_remesas",
    "bce_precios_comex",
    "bce_publicaciones",
]

# Clients that paginate themselves; the rest return every match and are
# sliced here.
_PAGINATED: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "sri_datasets": sri_client.search_files,
    "sri_recaudacion": sri_client.search_estadisticas_recaudacion,
    "censo": censo_client.search_censo_recursos,
}
_UNPAGINATED: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "mef": mef_fiscal_client.search_operaciones_spnf,
    "senae": mef_fiscal_client.search_senae_tributos,
    "minedec": minedec_client.search_matricula,
    "senescyt": senescyt_client.search_estadisticas,
    "msp": msp_gacetas_inmunoprevenibles_client.search_gacetas_inmunoprevenibles,
    "cnig": cnig_client.search_femicidios,
    "trabajo_boletin": trabajo_boletin_anual_client.search_boletines,
    "arcotel_boletines": arcotel_client.search_boletines_estadisticos,
    "arcotel_mensuales": arcotel_client.search_reportes_mensuales,
    "bce_remesas": bce_remesas_client.search_archivos,
    "bce_precios_comex": bce_precios_comex_client.search_archivos,
    "bce_publicaciones": bce_publicaciones_client.search_publicaciones,
}

# Keys the clients use for the same three things, first match wins.
_TITLE_KEYS = ("titulo", "label", "nombre")
_URL_KEYS = ("url", "url_descarga", "url_ver")
_FORMAT_KEYS = ("formato", "format")
_ALIASES = set(_TITLE_KEYS + _URL_KEYS + _FORMAT_KEYS)


def _first(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    return next((item[k] for k in keys if item.get(k)), None)


def _normalize_file(item: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "titulo": _first(item, _TITLE_KEYS),
        "url": _first(item, _URL_KEYS),
        "formato": _first(item, _FORMAT_KEYS),
    }
    normalized.update({k: v for k, v in item.items() if k not in _ALIASES})
    # Keep both links where a source has two (salarios: a viewer and a download).
    if item.get("url_ver") and item.get("url_descarga"):
        normalized["url_ver"] = item["url_ver"]
    return normalized


async def _search(fuente: str, query: str, limit: int, offset: int) -> dict[str, Any]:
    if fuente in _PAGINATED:
        result = await _PAGINATED[fuente](query=query, limit=limit, offset=offset)
        items = result.get("archivos") or result.get("recursos") or []
        total = result.get("total", len(items))
    else:
        if fuente == "salarios":
            # This client filters by year only; match `query` as text instead,
            # which also covers years since the titles carry them.
            result = await salarios_sectoriales_client.search_tablas_sectoriales(anio=None)
            items = result.get("tablas") or []
            if query:
                q = strip_accents(query)
                items = [
                    t
                    for t in items
                    if q in strip_accents(f"{t.get('titulo', '')} {t.get('anio', '')}")
                ]
        else:
            result = await _UNPAGINATED[fuente](query=query)
            items = next(
                (result[k] for k in ("archivos", "ediciones", "publicaciones") if isinstance(result.get(k), list)),
                [],
            )
        total = len(items)
        items = items[offset : offset + limit]

    nota = result.get("nota") or result.get("nota_cobertura")
    return {
        "fuente": fuente,
        "nombre_fuente": result.get("source"),
        "url_fuente": result.get("url_fuente") or result.get("url_indice") or result.get("source_url"),
        "total": total,
        "offset": offset,
        "archivos": [_normalize_file(item) for item in items],
        **({"nota": nota} if nota else {}),
    }


def register_search_archivos_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Buscar archivos publicados por una institución",
        description=(
            "File links from one institution's catalog, filtered by text: SRI, MEF, "
            "SENAE, Census 2022, MINEDEC, SENESCYT, MSP, CNIG, Trabajo, ARCOTEL and "
            "BCE (remesas, comex prices, latest publications). Links, not contents."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def search_archivos(
        fuente: Fuente,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Search one institution's catalog of published files (direct links).

        Every file has `titulo`, `url` and `formato`, plus the source's own
        fields (e.g. `anio`, `categoria`, `semana`, `tipo`, `periodo`).
        Returns links, not contents: download them directly or with
        download_resource / read_pdf (5 MB cap for those tools).

        Sources (`fuente`):
        - sri_datasets: ~130 SRI files outside CKAN (sri.gob.ec/datasets):
          RUC catastro by province, recaudación, ventas/compras, vehículos,
          electronic receipts, variable dictionaries.
        - sri_recaudacion: SRI "Estadísticas de Recaudación": monthly XLSX by
          tax, province/canton and activity, historical indicators, bulletin.
        - mef: MEF/MDEP "Operaciones SPNF" (GFSM) workbooks, monthly, current.
          For tariff revenue read row "1214 Arancelarios" (sheet GC).
        - senae: SENAE customs collection by ADVALOREM/FODINFA/IVA/ICE/
          TOTALES, 2012-2021 only. Arancelarios/ADVALOREM are the tariff
          alone, smaller than the press "recaudación aduanera" (which adds
          IVA and ICE at the border).
        - censo: Census 2022 microsite (censoecuador.gob.ec): microdata by
          sector, cantón and city block (CSV, SPSS, REDATAM), 2010/2001
          recoded to 2022 geography, dictionaries, methodology. Files can be
          hundreds of MB.
        - minedec: MINEDEC basic-education enrollment registry 2009-present
          (start/end-of-year XLSX of 30-140 MB, metadata, dictionary).
        - senescyt: SENESCYT SIAU higher-education and CTI reports; "wpdm"
          links have no extension (formato DESCONOCIDO).
        - msp: MSP weekly vaccine-preventable disease gazettes, 2019 to date;
          `tipo` separates the general bulletin from disease companions.
        - cnig: CNIG gender-violence PDFs incl. the femicide matrix (snapshot
          to April 2023, not a live feed).
        - trabajo_boletin: Ministerio del Trabajo annual labor-market
          bulletin; only the 2020-2022 editions are known.
        - salarios: sectoral minimum-wage tables 2020-2025 (no 2026 table
          published); entries may be titled by the year they were signed.
        - arcotel_boletines: ARCOTEL annual/topical telecom bulletins
          2015-2024 (PDF).
        - arcotel_mensuales: ARCOTEL monthly statistics reports 2017-2026
          (PDF).
        - bce_remesas: BCE worker-remittance files: historical series,
          methodology note and, since July 2025, microdata-based monthly
          databases. "histórica" and "BDD" files are different series.
        - bce_precios_comex: BCE foreign-trade price indices by import use
          category and export product (oil, shrimp, banana, cacao...); BCEData
          only has the three aggregates.
        - bce_publicaciones: BCE's ~30 most recent reports and bulletins
          (rolling window, newest first, with `fecha`); an editorial feed, not
          data series.

        Args:
            fuente: Catalog to search; see the list above.
            query: Free text matched (accent-insensitive) against each file's
                title and source-specific fields. Empty returns all files.
            limit: Max files returned (1-100, default 50).
            offset: Pagination offset over the matched files.
            format: text | json
        """
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)
        try:
            result = await _search(fuente, query, limit, offset)
        except ValueError as e:
            raise ToolError(f"Error: {e}") from e
        except Exception as e:
            raise ToolError(f"Error al buscar archivos de {fuente}: {e}") from e

        def to_text(data: dict) -> str:
            shown = len(data["archivos"])
            parts = [
                f"{data.get('nombre_fuente') or data['fuente']} — {data['total']} archivo(s)"
                + (f", mostrando {shown} desde {data['offset']}" if shown < data["total"] else ""),
            ]
            if data.get("url_fuente"):
                parts.append(f"Fuente: {data['url_fuente']}")
            if data.get("nota"):
                parts.append(f"Nota: {data['nota']}")
            parts.append("")
            if not data["archivos"]:
                parts.append("No se encontraron archivos.")
            for a in data["archivos"]:
                contexto = ", ".join(
                    str(a[k])
                    for k in ("anio", "periodo", "categoria", "semana", "tipo", "fecha")
                    if a.get(k)
                )
                parts.append(
                    f"- {a['titulo']} [{a.get('formato') or '?'}]"
                    + (f" ({contexto})" if contexto else "")
                )
                parts.append(f"   {a['url']}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)
