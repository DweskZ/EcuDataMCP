import json

import httpx
from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.csv_reader import format_table
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
        """
        rows = min(max(rows, 1), 100)
        offset = max(offset, 0)

        filters = None
        if filters_json.strip():
            try:
                parsed = json.loads(filters_json)
            except json.JSONDecodeError as e:
                return f"Error: filters_json no es JSON válido: {e}"
            if not isinstance(parsed, dict):
                return "Error: filters_json debe ser un objeto JSON (diccionario)."
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
                return (
                    f"Error: recurso '{resource_id}' no encontrado o sin DataStore. "
                    "Prueba preview_resource_data para descargar el archivo."
                )
            return f"Error: HTTP {e.response.status_code} - {e}"
        except ValueError as e:
            return (
                f"Error de DataStore: {e}. "
                "Si el recurso no está indexado, usa preview_resource_data."
            )
        except Exception as e:
            return f"Error al consultar DataStore: {e}"

        records = result.get("records") or []
        fields = result.get("fields") or []
        total = result.get("total", len(records))
        headers = [
            f.get("id")
            for f in fields
            if f.get("id") and f.get("id") != "_id"
        ]
        if not headers and records:
            headers = [k for k in records[0] if k != "_id"]

        if not records:
            return (
                f"DataStore vacío o sin coincidencias para resource_id={resource_id}. "
                f"Total reportado: {total}."
            )

        table_rows = [
            [str(rec.get(h, ""))[:80] for h in headers] for rec in records
        ]
        parts = [
            f"DataStore query — resource_id: {resource_id}",
            f"Total registros: {total}",
            f"Mostrando: {len(records)} (offset={offset})",
        ]
        if query:
            parts.append(f"Query: {query}")
        if filters:
            parts.append(f"Filters: {json.dumps(filters, ensure_ascii=False)}")
        if sort:
            parts.append(f"Sort: {sort}")
        parts.append("")
        parts.append(format_table(headers, table_rows))
        parts.append("")
        parts.append(
            "Tip: ajusta offset/rows para paginar, o usa filters_json para filtros exactos."
        )
        return "\n".join(parts)
