import asyncio
from typing import Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import ckan_client
from helpers.csv_reader import (
    format_table,
    sniff_content_type,
)
from helpers.format_out import render_structured
from helpers.geo_proxy import proxy_for
from helpers.logging import log_tool
from helpers.preview_dispatch import PREVIEWABLE_KINDS, preview_by_kind
from helpers.tool_meta import READ_ONLY
from helpers.user_agent import USER_AGENT
from tools.list_dataset_resources import detect_periodic_series
from tools.preview_resource_data import (
    classify_from_content_type,
    classify_resource_format,
)

# Bounds for the Content-Type sniff pass over resources with no usable
# format/extension (see the classification loop in investigate_dataset).
_MAX_SNIFFED_RESOURCES = 25
_SNIFF_CONCURRENCY = 5


async def _classify(res: dict) -> str:
    url = res.get("url") or ""
    fmt = (res.get("format") or "").upper()
    kind = classify_resource_format(fmt, url)
    if kind == "UNKNOWN" and url:
        # No shared session: sniff_content_type builds its own per URL, so
        # the project User-Agent and the geo proxy (proxy_for) apply.
        content_type = await sniff_content_type(url)
        kind = classify_from_content_type(content_type)
    return kind


def register_investigate_dataset_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Investigar un dataset en un solo paso",
        description=(
            "One-step shortcut: search CKAN, pick the top dataset and preview its "
            "first readable resource. Use the individual tools when the top hit "
            "isn't the right one."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def investigate_dataset(
        query: str,
        source: ckan_client.CkanSource = "nacional",
        preview_rows: int = 10,
        format: Literal["text", "json"] = "text",
    ) -> CallToolResult:
        """
        One-shot research shortcut: search for a dataset, list its resources,
        and preview the most promising one's actual data -- the
        search_datasets -> list_dataset_resources -> preview_resource_data
        workflow in a single call, for the common case of "find me data
        about X and show me what's in it".

        Picks the top-ranked search result and, among its resources, the
        first one in a format this server can actually parse into a table
        (CSV/JSON/XLS/XLSB/XLSX/ODS/ZIP/TARGZ), skipping unreadable ones
        (.rar, unrecognized formats) rather than previewing whichever
        resource happens to be listed first.

        Not a replacement for the individual tools: if the top search
        result isn't the right dataset, or you need a specific resource
        within it, use search_datasets/list_dataset_resources/
        preview_resource_data directly instead of re-running this.

        Args:
            query: Search keywords (e.g. "empleo", "SRI recaudación")
            source: "nacional" (default), "cuenca" (Cuenca municipal portal),
                    "latacunga" (Latacunga municipal portal), or "iadb" (IADB's
                    open-data portal, data.iadb.org — NOT Ecuador-only, a
                    regional/global catalog)
            preview_rows: Data rows to preview from the chosen resource (default: 10, max: 50)
            format: text | json
        """
        preview_rows = min(max(preview_rows, 1), 50)

        try:
            search = await ckan_client.search_datasets(query=query, rows=1, source=source)
        except Exception as e:
            raise ToolError(f"Error al buscar datasets: {e}") from e

        candidates = search.get("results") or []
        if not candidates:
            # Legitimate empty result (search matched zero datasets).
            return render_structured(
                {"error": "sin_resultados", "query": query},
                format,
                text_builder=lambda d: f"No se encontraron datasets para: '{d['query']}'",
            )

        dataset_stub = candidates[0]
        dataset_id = dataset_stub.get("id") or dataset_stub.get("name")
        site = ckan_client.site_url(source).rstrip("/")

        # The shared session only serves CKAN metadata calls; resource files
        # live on other hosts, so sniffing and previews build their own
        # per-URL clients (User-Agent + geo proxy for that host).
        session = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, proxy=proxy_for(site)
        )
        try:
            try:
                dataset = await ckan_client.get_dataset(dataset_id, source=source, session=session)
            except Exception as e:
                raise ToolError(f"Error al obtener el dataset: {e}") from e

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
                # Legitimate result: a fact about this dataset, not a failure.
                base_payload["error"] = "sin_recursos"
                return render_structured(
                    base_payload,
                    format,
                    text_builder=lambda d: (
                        f"Dataset encontrado: {d['dataset']['title']}\n"
                        f"{d['dataset']['url']}\n\n"
                        "Este dataset no tiene recursos (archivos) para previsualizar."
                    ),
                )

            chosen, kind = None, "UNKNOWN"
            candidates = [r for r in resources if r.get("id") and r.get("url")]
            # Pass 1, no network: the first resource whose declared format or
            # URL extension is previewable wins, in catalog order.
            for res in candidates:
                candidate_kind = classify_resource_format(
                    (res.get("format") or "").upper(), res.get("url") or ""
                )
                if candidate_kind in PREVIEWABLE_KINDS:
                    chosen, kind = res, candidate_kind
                    break
            if chosen is None:
                # Pass 2: Content-Type sniffs for the unlabelled ones, a few at
                # a time and only for the first _MAX_SNIFFED_RESOURCES -- a
                # dataset with 150 mislabelled files used to mean 150 serial
                # HEAD requests before anything was previewed.
                sniff_slots = asyncio.Semaphore(_SNIFF_CONCURRENCY)

                async def classify_bounded(res: dict) -> str:
                    async with sniff_slots:
                        try:
                            return await _classify(res)
                        except Exception:
                            return "UNKNOWN"

                sniffed = candidates[:_MAX_SNIFFED_RESOURCES]
                kinds = await asyncio.gather(*(classify_bounded(r) for r in sniffed))
                for res, candidate_kind in zip(sniffed, kinds, strict=True):
                    if candidate_kind in PREVIEWABLE_KINDS:
                        chosen, kind = res, candidate_kind
                        break

            if chosen is None:
                # Legitimate result: a fact about this dataset's resources,
                # not a failure.
                base_payload["error"] = "sin_recurso_previsualizable"
                base_payload["recursos"] = [
                    {"id": r.get("id"), "name": r.get("name"), "format": r.get("format")}
                    for r in resources
                    if r.get("id")
                ]
                return render_structured(
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
                preview = await preview_by_kind(kind, chosen["url"], preview_rows)
            except (ValueError, httpx.HTTPError) as e:
                raise ToolError(
                    f"Dataset encontrado: {base_payload['dataset']['title']} "
                    f"({base_payload['dataset']['url']}). No se pudo previsualizar "
                    f"'{chosen.get('name')}': recurso_no_legible: {e}"
                ) from e
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

        return render_structured(payload, format, text_builder=to_text)
