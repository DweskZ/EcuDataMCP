import httpx
from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.csv_reader import (
    format_table,
    preview_csv,
    preview_json,
    preview_ods,
    preview_targz,
    preview_xls,
    preview_xlsx,
    preview_zip,
    sniff_content_type,
)
from helpers.format_out import render_output
from helpers.logging import log_tool
from tools.list_dataset_resources import detect_periodic_series
from tools.preview_resource_data import (
    classify_from_content_type,
    classify_resource_format,
)

# Prefer previewing a resource whose format we can actually parse into a
# table over one search ranks higher but we'd just bounce off (RAR/UNKNOWN).
_PREVIEWABLE_KINDS = {"CSV", "JSON", "XLS", "XLSX", "ODS", "ZIP", "TARGZ"}

_PREVIEW_DISPATCH = {
    "TARGZ": preview_targz,
    "ZIP": preview_zip,
    "XLS": preview_xls,
    "XLSX": preview_xlsx,
    "ODS": preview_ods,
    "JSON": preview_json,
    "CSV": preview_csv,
}


async def _classify(res: dict, session: httpx.AsyncClient) -> str:
    url = res.get("url") or ""
    fmt = (res.get("format") or "").upper()
    kind = classify_resource_format(fmt, url)
    if kind == "UNKNOWN" and url:
        content_type = await sniff_content_type(url, session=session)
        kind = classify_from_content_type(content_type)
    return kind


def register_investigate_dataset_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def investigate_dataset(
        query: str,
        source: str = "nacional",
        preview_rows: int = 10,
        format: str = "text",
    ) -> str:
        """
        One-shot research shortcut: search for a dataset, list its resources,
        and preview the most promising one's actual data -- the
        search_datasets -> list_dataset_resources -> preview_resource_data
        workflow in a single call, for the common case of "find me data
        about X and show me what's in it".

        Picks the top-ranked search result and, among its resources, the
        first one in a format this server can actually parse into a table
        (CSV/JSON/XLS/XLSX/ODS/ZIP/TARGZ), skipping unreadable ones
        (.rar, unrecognized formats) rather than previewing whichever
        resource happens to be listed first.

        Not a replacement for the individual tools: if the top search
        result isn't the right dataset, or you need a specific resource
        within it, use search_datasets/list_dataset_resources/
        preview_resource_data directly instead of re-running this.

        Args:
            query: Search keywords (e.g. "empleo", "SRI recaudación")
            source: "nacional" (default) or "cuenca" (Cuenca municipal portal)
            preview_rows: Data rows to preview from the chosen resource (default: 10, max: 50)
            format: text | json
        """
        preview_rows = min(max(preview_rows, 1), 50)

        try:
            search = await ckan_client.search_datasets(query=query, rows=1, source=source)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query},
                format,
                text_builder=lambda d: f"Error al buscar datasets: {d['error']}",
            )

        candidates = search.get("results") or []
        if not candidates:
            return render_output(
                {"error": "sin_resultados", "query": query},
                format,
                text_builder=lambda d: f"No se encontraron datasets para: '{d['query']}'",
            )

        dataset_stub = candidates[0]
        dataset_id = dataset_stub.get("id") or dataset_stub.get("name")
        site = ckan_client.site_url(source).rstrip("/")

        session = httpx.AsyncClient()
        try:
            try:
                dataset = await ckan_client.get_dataset(dataset_id, source=source, session=session)
            except Exception as e:
                return render_output(
                    {"error": str(e), "dataset_id": dataset_id},
                    format,
                    text_builder=lambda d: f"Error al obtener el dataset: {d['error']}",
                )

            resources = dataset.get("resources") or []
            base_payload = {
                "query": query,
                "total_datasets_encontrados": search.get("count", len(candidates)),
                "dataset": {
                    "id": dataset.get("id", dataset_id),
                    "title": dataset.get("title"),
                    "url": f"{site}/dataset/{dataset.get('name', dataset_id)}",
                    "total_recursos": len(resources),
                },
                "posible_serie_periodica": bool(detect_periodic_series(resources)),
            }

            if not resources:
                base_payload["error"] = "sin_recursos"
                return render_output(
                    base_payload,
                    format,
                    text_builder=lambda d: (
                        f"Dataset encontrado: {d['dataset']['title']}\n"
                        f"{d['dataset']['url']}\n\n"
                        "Este dataset no tiene recursos (archivos) para previsualizar."
                    ),
                )

            chosen, kind = None, "UNKNOWN"
            for res in resources:
                if not res.get("id") or not res.get("url"):
                    continue
                candidate_kind = await _classify(res, session)
                if candidate_kind in _PREVIEWABLE_KINDS:
                    chosen, kind = res, candidate_kind
                    break

            if chosen is None:
                base_payload["error"] = "sin_recurso_previsualizable"
                base_payload["recursos"] = [
                    {"id": r.get("id"), "name": r.get("name"), "format": r.get("format")}
                    for r in resources
                    if r.get("id")
                ]
                return render_output(
                    base_payload,
                    format,
                    text_builder=lambda d: (
                        f"Dataset encontrado: {d['dataset']['title']}\n"
                        f"{d['dataset']['url']}\n\n"
                        "Ninguno de sus recursos tiene un formato previsualizable "
                        "aquí. Usa list_dataset_resources para verlos todos, o "
                        "download_resource/read_pdf según el formato."
                    ),
                )

            try:
                preview = await _PREVIEW_DISPATCH[kind](
                    chosen["url"], max_rows=preview_rows, session=session
                )
            except (ValueError, httpx.HTTPError) as e:
                base_payload["error"] = f"recurso_no_legible: {e}"
                base_payload["resource"] = {"id": chosen.get("id"), "name": chosen.get("name")}
                return render_output(
                    base_payload,
                    format,
                    text_builder=lambda d: (
                        f"Dataset encontrado: {d['dataset']['title']}\n"
                        f"{d['dataset']['url']}\n\n"
                        f"No se pudo previsualizar '{d['resource']['name']}': {d['error']}"
                    ),
                )
        finally:
            await session.aclose()

        payload = {
            **base_payload,
            "resource": {
                "id": chosen.get("id"),
                "name": chosen.get("name"),
                "format": preview.get("format", kind),
                "url": chosen.get("url"),
            },
            "headers": preview["headers"],
            "rows": preview["rows"],
            "total_rows_in_preview": preview["total_rows_in_preview"],
            "truncated": preview.get("truncated", False),
        }

        def to_text(data: dict) -> str:
            ds = data["dataset"]
            res = data["resource"]
            parts = [
                f"Dataset ({data['total_datasets_encontrados']} encontrados para '{data['query']}'): {ds['title']}",
                ds["url"],
                f"Recurso previsualizado: {res['name']} ({res['format']}) — {data['total_rows_in_preview']} fila(s)",
                "",
                format_table(data["headers"], data["rows"]),
            ]
            if data.get("truncated"):
                parts.append("")
                parts.append(f"⚠ Archivo truncado. Descarga completa: {res['url']}")
            if data.get("posible_serie_periodica"):
                parts.append("")
                parts.append(
                    "ℹ Este dataset parece publicar una serie periódica (varios "
                    "archivos con nombres casi idénticos). Antes de sumar o "
                    "comparar valores entre ellos, usa "
                    f"detect_series_pattern(\"{ds['id']}\") para saber si cada "
                    "archivo nuevo reemplaza a los anteriores o los complementa."
                )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
