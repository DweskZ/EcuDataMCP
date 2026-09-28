"""Scheduled power-cut archives (EEQ, Centrosur) behind one list/parse pair.

EEQ (Quito) and Centrosur (Azuay, Cañar, Morona Santiago) each had a
search tool (list the published schedule PDFs) and a parse tool (one PDF
into rows). Same two steps, and the rows share a core -- page, date text,
time blocks, sectors -- plus location fields (EEQ: substation; Centrosur:
province/canton/zone). `distribuidora` now picks the utility. The
energia-ecuador.com snapshot stays its own tool: one frozen page with a
different row shape, not an archive.
"""

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import centrosur_cortes_client, eeq_cortes_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY

Distribuidora = Literal["eeq", "centrosur"]

_NOMBRES = {
    "eeq": "EEQ (Quito)",
    "centrosur": "Centrosur (Azuay, Cañar, Morona Santiago)",
}
_TEXT_ROWS = 40
_TEXT_SECTORES = 220


async def _search(distribuidora: str, query: str) -> dict[str, Any]:
    if distribuidora == "eeq":
        result = await eeq_cortes_client.search_eeq_cortes(query=query)
        archivo_key = "slug"
    else:
        result = await centrosur_cortes_client.search_centrosur_cortes(query=query)
        archivo_key = "url"
    # `archivo` is what get_cortes_horarios takes, whichever key the
    # utility's client identifies files by.
    archivos = [{"archivo": a[archivo_key], **a} for a in result.get("archivos") or []]
    return {**result, "distribuidora": distribuidora, "archivos": archivos}


async def _get_horarios(distribuidora: str, archivo: str, query: str) -> dict[str, Any]:
    if distribuidora == "eeq":
        result = await eeq_cortes_client.get_eeq_cortes_horarios(slug=archivo, query=query)
    else:
        result = await centrosur_cortes_client.get_centrosur_cortes_horarios(url=archivo, query=query)
    return {**result, "distribuidora": distribuidora}


def register_cortes_tools(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Buscar cronogramas de cortes de luz",
        description=(
            "Scheduled power-cut PDFs of one utility: eeq (Quito, 2023-2024 "
            "blackout crises) or centrosur (Azuay, Cañar, Morona Santiago, 2023 on). "
            "Next: get_cortes_horarios with a file's archivo."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def search_cortes(
        distribuidora: Distribuidora,
        query: str = "",
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        List one electricity distributor's archive of scheduled power-cut PDFs.

        Regional, not national: each archive covers one concession area.
        Every file carries `archivo`, the id get_cortes_horarios takes.

        - eeq: Empresa Eléctrica Quito, 2023 and 2024 blackout crises.
          Mid-October to December 2024 is enumerated live from EEQ's site
          search; earlier files (Oct-Nov 2023, April/June 2024, Sep-early Oct
          2024) come from a fixed list recovered via search-engine indexing,
          so that period may have gaps (`origen` says which).
        - centrosur: Empresa Eléctrica Regional Centro Sur, 2023 onward,
          including the 2024 estiaje blackouts, enumerated from WordPress's
          media library API. A separate `CortesEstiaje/` folder of extra 2024
          PDFs is not covered (no way to enumerate it).

        CNEL has no recoverable archive. For the national 2024 portal see
        get_energia_ecuador_snapshot.

        Args:
            distribuidora: eeq or centrosur.
            query: Free text matched (accent-insensitive) against the file's
                period, date, title or URL, e.g. "noviembre", "2024-10".
                Empty returns all files.
            format: text | json
        """
        try:
            result = await _search(distribuidora, query)
        except Exception as e:
            raise ToolError(f"Error al consultar el archivo de cortes de {distribuidora}: {e}") from e

        def to_text(data: dict) -> str:
            archivos = data["archivos"]
            parts = [
                (
                    f"{_NOMBRES[data['distribuidora']]} — cortes de luz programados — "
                    f"{data['total']} resultado(s) de {data['total_en_archivo']} archivos"
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin resultados.")
            for i, a in enumerate(archivos[:100], 1):
                cuando = a.get("periodo") or a.get("titulo")
                fecha = a.get("fecha") or (
                    f"{a['anio']}-{a['mes']}" if a.get("anio") else "fecha desconocida"
                )
                parts.append(f"{i}. {cuando} [{fecha}] archivo={a['archivo']}")
                if a["archivo"] != a.get("url"):
                    parts.append(f"   {a['url']}")
            if len(archivos) > 100:
                parts.append(f"... y {len(archivos) - 100} más (usa query para acotar, o format=json)")
            parts += ["", f"Fuente: {data.get('url_fuente')}"]
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

    @mcp.tool(
        title="Horarios de cortes de luz por sector",
        description=(
            "Parse one power-cut PDF (archivo from search_cortes) into rows: date, "
            "time blocks without power, location (EEQ: substation; Centrosur: "
            "province/canton/zone) and sectors. query filters by place."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_cortes_horarios(
        distribuidora: Distribuidora,
        archivo: str,
        query: str = "",
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Parse one scheduled power-cut PDF into rows.

        Every row has `pagina`, `fecha_texto` (as published), `horario` (time
        blocks without power, e.g. ["07:30-10:30"]) and `sectores`, plus
        the utility's location fields.

        - eeq: rows by substation (`subestacion`), with `sector_industrial`
          marking industrial-customer pages. Parsed from the slide layout
          and validated on all 26 archived PDFs (2,150 rows); the result
          counts rows without a recognized substation or time block.
        - centrosur: rows by `provincia`, `canton`, `zona`. Cantons taken
          from a merged table cell are flagged `canton_inferido` (can be off
          near span boundaries). The Sep 2024 file is a scan with no text
          (returned with a note, no rows); one file is an EEQ schedule and
          is parsed as such (`nota` says so).

        Args:
            distribuidora: eeq or centrosur.
            archivo: The file's `archivo` from search_cortes (EEQ: slug or
                URL; Centrosur: PDF URL).
            query: Free text matched (accent-insensitive) against location
                and sectors, e.g. "La Floresta", "Gualaceo". Empty returns
                every row.
            format: text | json
        """
        try:
            result = await _get_horarios(distribuidora, archivo, query)
        except ValueError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(f"Error al procesar el horario de cortes de {distribuidora}: {e}") from e

        def to_text(data: dict) -> str:
            filas = data["filas"]
            parts = [
                (
                    f"{_NOMBRES[data['distribuidora']]} — horario de cortes — {data['total']} "
                    f"fila(s) de {data['total_en_archivo']} ({data['paginas']} páginas)"
                ),
                "",
            ]
            if data.get("nota"):
                parts += [f"Nota: {data['nota']}", ""]
            avisos = []
            if data.get("filas_sin_subestacion") or data.get("filas_sin_horario"):
                avisos.append(
                    f"{data.get('filas_sin_subestacion', 0)} fila(s) sin subestación y "
                    f"{data.get('filas_sin_horario', 0)} sin horario reconocidos"
                )
            if data.get("filas_canton_inferido"):
                avisos.append(
                    f"{data['filas_canton_inferido']} fila(s) con cantón inferido de una "
                    "celda combinada (marcadas con *)"
                )
            if avisos:
                parts += ["Aviso: " + "; ".join(avisos) + ".", ""]
            if not filas:
                parts.append("Sin resultados.")
            for f in filas[:_TEXT_ROWS]:
                horario = " / ".join(f["horario"]) or "horario no reconocido"
                industrial = " [sector industrial]" if f.get("sector_industrial") else ""
                lugar = f.get("subestacion") or " / ".join(
                    x
                    for x in (
                        f.get("provincia"),
                        (f.get("canton") or "") + ("*" if f.get("canton_inferido") else ""),
                        f.get("zona"),
                    )
                    if x
                )
                sectores = f["sectores"]
                if len(sectores) > _TEXT_SECTORES:
                    sectores = sectores[:_TEXT_SECTORES] + "…"
                parts.append(
                    f"p{f['pagina']} · {f['fecha_texto']} · {horario}{industrial} · "
                    f"{lugar or 'ubicación no reconocida'}"
                )
                parts.append(f"   {sectores}")
            if len(filas) > _TEXT_ROWS:
                parts.append(
                    f"... y {len(filas) - _TEXT_ROWS} filas más (usa query para acotar, o format=json)"
                )
            parts += ["", f"Fuente: {data['url']}"]
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)
