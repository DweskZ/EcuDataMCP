import json

import httpx
from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.csv_reader import format_table
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_query_resource_data_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def query_resource_data(
        resource_id: str,
        query: str = "",
        filters_json: str = "",
        rows: int = 20,
        offset: int = 0,
        sort: str = "",
        format: str = "text",
    ) -> str:
        """
        Query a tabular resource via CKAN DataStore without downloading the full file.

        Prefer this over preview_resource_data when the resource is in the DataStore
        (most CSV resources on the portal). Supports full-text query, JSON filters,
        sorting and pagination.

        Args:
            resource_id: Resource UUID (from list_dataset_resources)
            query: Optional full-text search across datastore fields
            filters_json: Optional JSON object of exact field filters,
                          e.g. '{"provincia":"Pichincha"}'
            rows: Number of records to return (default 20, max 100)
            offset: Pagination offset (default 0)
            sort: Optional sort expression, e.g. "anio desc"
            format: text | json
        """
        rows = min(max(rows, 1), 100)
        offset = max(offset, 0)

        filters = None
        if filters_json.strip():
            try:
                parsed = json.loads(filters_json)
            except json.JSONDecodeError as e:
                return render_output(
                    {"error": "filters_json_invalido", "detail": str(e)},
                    format,
                    text_builder=lambda d: (
                        f"Error: filters_json no es JSON válido: {d['detail']}"
                    ),
                )
            if not isinstance(parsed, dict):
                return render_output(
                    {"error": "filters_json_debe_ser_objeto"},
                    format,
                    text_builder=lambda _: (
                        "Error: filters_json debe ser un objeto JSON (diccionario)."
                    ),
                )
            filters = parsed

        try:
            result = await ckan_client.datastore_search(
                resource_id=resource_id,
                filters=filters,
                q=query,
                limit=rows,
                offset=offset,
                sort=sort,
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return render_output(
                    {
                        "error": "not_found_or_no_datastore",
                        "resource_id": resource_id,
                    },
                    format,
                    text_builder=lambda d: (
                        f"Error: recurso '{d['resource_id']}' no encontrado o sin DataStore. "
                        "Prueba preview_resource_data para descargar el archivo."
                    ),
                )
            return render_output(
                {"error": f"HTTP {e.response.status_code}", "detail": str(e)},
                format,
                text_builder=lambda d: f"Error: {d['error']} - {d['detail']}",
            )
        except ValueError as e:
            return render_output(
                {"error": "datastore_error", "detail": str(e)},
                format,
                text_builder=lambda d: (
                    f"Error de DataStore: {d['detail']}. "
                    "Si el recurso no está indexado, usa preview_resource_data."
                ),
            )
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al consultar DataStore: {d['error']}",
            )

        records = result.get("records") or []
        fields = result.get("fields") or []
        total = result.get("total", len(records))
        headers = [
            f.get("id") for f in fields if f.get("id") and f.get("id") != "_id"
        ]
        if not headers and records:
            headers = [k for k in records[0] if k != "_id"]

        payload = {
            "resource_id": resource_id,
            "total": total,
            "offset": offset,
            "rows": len(records),
            "query": query or None,
            "filters": filters,
            "sort": sort or None,
            "headers": headers,
            "records": [
                {h: rec.get(h) for h in headers} for rec in records
            ],
        }

        if not records:
            return render_output(
                payload,
                format,
                text_builder=lambda d: (
                    f"DataStore vacío o sin coincidencias para resource_id={d['resource_id']}. "
                    f"Total reportado: {d['total']}."
                ),
            )

        def to_text(data: dict) -> str:
            table_rows = [
                [str(rec.get(h, ""))[:80] for h in data["headers"]]
                for rec in data["records"]
            ]
            parts = [
                f"DataStore query — resource_id: {data['resource_id']}",
                f"Total registros: {data['total']}",
                f"Mostrando: {data['rows']} (offset={data['offset']})",
            ]
            if data.get("query"):
                parts.append(f"Query: {data['query']}")
            if data.get("filters"):
                parts.append(
                    f"Filters: {json.dumps(data['filters'], ensure_ascii=False)}"
                )
            if data.get("sort"):
                parts.append(f"Sort: {data['sort']}")
            parts.append("")
            parts.append(format_table(data["headers"], table_rows))
            parts.append("")
            parts.append(
                "Tip: ajusta offset/rows para paginar, o usa filters_json para filtros exactos."
            )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
