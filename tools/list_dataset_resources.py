import re

from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.format_out import render_output
from helpers.logging import log_tool

_DIGIT_RE = re.compile(r"\d+")


def _name_template(name: str) -> str:
    return _DIGIT_RE.sub("#", name.strip().lower())


def _detect_periodic_series(resources: list[dict]) -> list[str]:
    """Group resource names that differ only by digits (dates, week numbers, etc).

    Returns the names in the largest such group, if it has 3+ members — a
    soft signal the dataset publishes one file per period, where the caller
    still has to figure out whether each new file replaces or complements
    the previous ones before aggregating anything.
    """
    groups: dict[str, list[str]] = {}
    for res in resources:
        name = res.get("name") or ""
        if not name:
            continue
        groups.setdefault(_name_template(name), []).append(name)
    best = max(groups.values(), key=len, default=[])
    return best if len(best) >= 3 else []


def _format_size(size: int | None) -> str:
    if not size or not isinstance(size, (int, float)):
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.1f} GB"


def register_list_dataset_resources_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_dataset_resources(dataset_id: str, format: str = "text") -> str:
        """
        List all resources (files) in a dataset with their metadata.

        Returns resource ID, title, format, size, download URL, and creation/
        last-modified dates for each file. The dates let you tell whether a
        dataset's files are periodic snapshots (compare last_modified across
        resources to find the most recent one) before reading any of them.
        Also flags groups of resources whose names look like a periodic series
        (e.g. weekly files) — that's only a hint that they might need combining
        or picking the latest one; it does not tell you which, since that
        depends on the dataset (some periodic files replace previous ones,
        others complement them).
        Next step: use preview_resource_data on a CSV resource to see its contents,
        or use get_resource_info for detailed metadata.

        Args:
            dataset_id: The dataset ID or slug
            format: text | json
        """
        try:
            dataset = await ckan_client.get_dataset(dataset_id)
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        resources = dataset.get("resources", [])
        resource_rows = [
            {
                "id": res.get("id"),
                "name": res.get("name") or res.get("description") or "Sin título",
                "format": res.get("format"),
                "size": res.get("size"),
                "size_label": _format_size(res.get("size")),
                "mimetype": res.get("mimetype"),
                "description": res.get("description"),
                "url": res.get("url"),
                "created": res.get("created"),
                "last_modified": res.get("last_modified"),
            }
            for res in resources
            if res.get("id")
        ]
        payload = {
            "dataset_id": dataset.get("id", dataset_id),
            "title": dataset.get("title", "Desconocido"),
            "total": len(resources),
            "resources": resource_rows,
            "possible_periodic_series": _detect_periodic_series(resource_rows),
        }

        def to_text(data: dict) -> str:
            rows = data.get("resources") or []
            parts = [
                f"Recursos del dataset: {data.get('title')}",
                f"Dataset ID: {data.get('dataset_id')}",
                f"Total de recursos: {data.get('total', 0)}\n",
            ]
            if not rows:
                parts.append("Este dataset no tiene recursos.")
                return "\n".join(parts)
            for i, res in enumerate(rows, 1):
                parts.append(f"{i}. {res.get('name')}")
                parts.append(f"   Resource ID: {res.get('id')}")
                if res.get("format"):
                    parts.append(f"   Formato: {res['format']}")
                if res.get("size_label"):
                    parts.append(f"   Tamaño: {res['size_label']}")
                if res.get("mimetype"):
                    parts.append(f"   MIME: {res['mimetype']}")
                if res.get("description") and res.get("name"):
                    parts.append(f"   Descripción: {str(res['description'])[:200]}")
                if res.get("url"):
                    parts.append(f"   URL: {res['url']}")
                if res.get("created"):
                    parts.append(f"   Creado: {res['created']}")
                if res.get("last_modified"):
                    parts.append(f"   Última modificación: {res['last_modified']}")
                parts.append("")
            series = data.get("possible_periodic_series") or []
            if series:
                parts.append(
                    f"Nota: {len(series)} recursos parecen ser una serie periódica "
                    "(nombres casi idénticos, solo cambian números/fechas). Antes de "
                    "sumar o comparar valores entre ellos, revisa si cada archivo "
                    "nuevo reemplaza a los anteriores o los complementa."
                )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
