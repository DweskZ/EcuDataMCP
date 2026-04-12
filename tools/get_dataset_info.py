import httpx
from mcp.server.fastmcp import FastMCP

from helpers import ckan_client, env_config
from helpers.logging import log_tool


def register_get_dataset_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_dataset_info(dataset_id: str) -> str:
        """
        Get detailed metadata about a specific dataset from Ecuador's open data portal.

        Returns title, description, organization, tags, resource count,
        creation/update dates, license, and update frequency.

        Args:
            dataset_id: The dataset ID or slug (e.g. "registro-estadistico-de-recursos-y-actividades-de-salud-2019")
        """
        try:
            data = await ckan_client.get_dataset(dataset_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return f"Error: Dataset con ID '{dataset_id}' no encontrado."
            return f"Error: HTTP {e.response.status_code} - {e}"
        except Exception as e:
            return f"Error: {e}"

        site = env_config.get_base_url("ckan_site")
        parts = [f"Dataset: {data.get('title', 'Desconocido')}", ""]

        if data.get("id"):
            parts.append(f"ID: {data['id']}")
        slug = data.get("name", "")
        if slug:
            parts.append(f"Slug: {slug}")
            parts.append(f"URL: {site}dataset/{slug}")

        notes = data.get("notes", "")
        if notes:
            parts.append("")
            parts.append(f"Descripción: {notes[:800]}")

        org = data.get("organization")
        if org and isinstance(org, dict):
            parts.append("")
            parts.append(f"Organización: {org.get('title', 'Desconocida')}")
            if org.get("name"):
                parts.append(f"  ID organización: {org['name']}")

        tags = data.get("tags", [])
        if tags:
            tag_names = [t.get("display_name", t.get("name", "")) for t in tags[:10]]
            parts.append("")
            parts.append(f"Tags: {', '.join(tag_names)}")

        groups = data.get("groups", [])
        if groups:
            group_names = [g.get("title", g.get("display_name", "")) for g in groups]
            parts.append(f"Categorías: {', '.join(group_names)}")

        resources = data.get("resources", [])
        parts.append("")
        parts.append(f"Recursos: {len(resources)} archivo(s)")

        if data.get("metadata_created"):
            parts.append("")
            parts.append(f"Creado: {data['metadata_created']}")
        if data.get("metadata_modified"):
            parts.append(f"Última modificación: {data['metadata_modified']}")

        if data.get("license_title"):
            parts.append("")
            parts.append(f"Licencia: {data['license_title']}")

        freq = data.get("update_frequency")
        if freq:
            if isinstance(freq, list):
                freq = ", ".join(freq)
            parts.append(f"Frecuencia de actualización: {freq}")

        if data.get("author"):
            parts.append("")
            parts.append(f"Autor: {data['author']}")
        if data.get("maintainer"):
            parts.append(f"Mantenedor: {data['maintainer']}")

        return "\n".join(parts)
