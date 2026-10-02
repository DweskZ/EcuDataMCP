"""BCE's page-based publication archives behind one search/read pair.

BCE's "índice" publication series and its Cuentas Nacionales pages each
had a search (list pages) and a read (one page's files) tool, with the
same two steps and the same page/file shapes. `catalogo` now picks the
archive. Files are normalized to titulo/url/formato; the índices' own
year/period fields are kept.
"""

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import bce_cuentas_nacionales_client, bce_indices_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY

Catalogo = Literal["indices", "cuentas_nacionales"]

_NOMBRES = {
    "indices": "Índices de Publicaciones (BCE)",
    "cuentas_nacionales": "Cuentas Nacionales (BCE)",
}


def _normalize_file(item: dict[str, Any]) -> dict[str, Any]:
    titulo = item.get("label") or " ".join(
        str(x) for x in (item.get("anio"), item.get("periodo"), item.get("fecha_texto")) if x
    )
    rest = {k: v for k, v in item.items() if k not in ("label", "format", "formato")}
    return {"titulo": titulo, "formato": item.get("formato") or item.get("format"), **rest}


async def _search(catalogo: str, query: str) -> dict[str, Any]:
    if catalogo == "indices":
        result = await bce_indices_client.search_indices(query=query)
    else:
        result = await bce_cuentas_nacionales_client.search_cuentas_nacionales(query=query)
    return {**result, "catalogo": catalogo}


async def _get_archivos(catalogo: str, pagina_id: str, anio: int, max_archivos: int) -> dict[str, Any]:
    if catalogo == "indices":
        result = await bce_indices_client.get_archivo(
            pagina_id=pagina_id, anio=anio, max_archivos=max_archivos
        )
    else:
        result = await bce_cuentas_nacionales_client.get_archivo(
            pagina_id=pagina_id, max_archivos=max_archivos
        )
    archivos = [_normalize_file(a) for a in result.get("archivos") or []]
    return {**result, "catalogo": catalogo, "archivos": archivos}


def register_bce_paginas_tools(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Buscar páginas de publicaciones del BCE",
        description=(
            "BCE publication pages with file archives: indices (sector bulletins, "
            "price and confidence indices, FX, balance of payments; some back to "
            "2004) or cuentas_nacionales (annual, quarterly, regional accounts, "
            "input-output, IMAEC). Next: get_bce_pagina_archivos(pagina_id)."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def search_bce_paginas(
        catalogo: Catalogo,
        query: str = "",
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        List the BCE's page-based publication archives of one catalog.

        - indices: one page per named publication series (petroleum, mining
          and cement bulletins, trade price indices, EMOE/confidence, FX
          buy/sell, balance of payments, weekly monetary and remittance
          bulletins...), each with a year-by-year or week-by-week file
          archive. Distinct from BCEData/IEM (numeric series) and from
          search_archivos(fuente='bce_publicaciones') (rolling ~30 recent items).
        - cuentas_nacionales: national-accounts publication packages
          (annual, quarterly, regional, retropolation back to 1965,
          input-output and social-accounting matrices, 2007=100 series,
          bioeconomy satellite account, IMAEC), with TOU, CEI, MEI and
          methodology documents found nowhere else in this server.

        Returns page summaries; pass a page's `pagina_id` to
        get_bce_pagina_archivos for its files.

        Args:
            catalogo: indices or cuentas_nacionales.
            query: Free text matched (accent-insensitive) against the page's
                title, category or id. Empty returns all pages.
            format: text | json
        """
        try:
            result = await _search(catalogo, query)
        except Exception as e:
            raise ToolError(f"Error al consultar {_NOMBRES[catalogo]}: {e}") from e

        def to_text(data: dict) -> str:
            paginas = data.get("paginas") or []
            parts = [
                (
                    f"{_NOMBRES[data['catalogo']]} — {data['total']} resultado(s) de "
                    f"{data['total_paginas']} páginas"
                ),
                "",
            ]
            if not paginas:
                parts.append("Sin resultados.")
            for i, p in enumerate(paginas, 1):
                rango = p.get("rango_anios")
                detalle = [
                    p.get("categoria") or p.get("cadencia"),
                    f"{rango[0]}–{rango[1]}" if rango else None,
                    f"{p.get('total_archivos')} archivo(s)",
                ]
                parts.append(f"{i}. {p.get('titulo')} [{', '.join(d for d in detalle if d)}]")
                parts.append(f"   pagina_id: {p.get('pagina_id')}")
                parts.append(f"   {p.get('url')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

    @mcp.tool(
        title="Ver archivos de una página de publicaciones del BCE",
        description=(
            "Files of one BCE publication page (pagina_id from search_bce_paginas): "
            "title, URL and format, most recent first. anio filters the indices "
            "catalog by year."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_bce_pagina_archivos(
        catalogo: Catalogo,
        pagina_id: str,
        anio: int = 0,
        max_archivos: int = 30,
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Read one BCE publication page's file list.

        Each file has `titulo`, `url` and `formato`. For indices it also
        carries `anio`, `periodo` (quarter, month or week) and, for weekly
        series, `fecha_texto`. Returns links, not contents.

        Args:
            catalogo: indices or cuentas_nacionales.
            pagina_id: The page's `pagina_id` from search_bce_paginas.
            anio: Only for catalogo="indices": restrict to one year (0 = all).
            max_archivos: Cap on returned files, 1-200 (most recent first); use
                anio to reach further back.
            format: text | json
        """
        try:
            result = await _get_archivos(catalogo, pagina_id, anio, max_archivos)
        except Exception as e:
            raise ToolError(f"Error al leer la página '{pagina_id}' del BCE: {e}") from e

        def to_text(data: dict) -> str:
            pagina = data.get("pagina") or {}
            archivos = data["archivos"]
            parts = [
                f"{pagina.get('titulo')} ({pagina.get('cadencia') or pagina.get('categoria') or '?'})",
                (
                    f"{data['archivos_mostrados']} de {data['total_archivos']} archivo(s)"
                    + (" [truncado]" if data.get("truncado") else "")
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin archivos para ese filtro.")
            for a in archivos:
                parts.append(f"- {a['titulo']} [{a.get('formato')}]")
                parts.append(f"   {a['url']}")
            parts += ["", f"Fuente: {pagina.get('url')}"]
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)
