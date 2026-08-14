import httpx
from mcp.server.fastmcp import FastMCP

from helpers import ckan_client, env_config
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_dataset_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_dataset_info(dataset_id: str, format: str = "text") -> str:
        """
        Get detailed metadata about a specific dataset from Ecuador's open data portal.

        Returns title, description, organization, tags, resource count,
        creation/update dates, license, update frequency, the publisher's
        source URL (where the entity keeps the authoritative data, if any),
        and any custom metadata fields the publisher added.

        Args:
            dataset_id: The dataset ID or slug (e.g. "registro-estadistico-de-recursos-y-actividades-de-salud-2019")
            format: text | json
        """
        try:
            data = await ckan_client.get_dataset(dataset_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return render_output(
                    {"error": "not_found", "dataset_id": dataset_id},
                    format,
                    text_builder=lambda d: (
                        f"Error: Dataset con ID '{d['dataset_id']}' no encontrado."
                    ),
                )
            return render_output(
                {"error": f"HTTP {e.response.status_code}", "detail": str(e)},
                format,
                text_builder=lambda d: f"Error: {d['error']} - {d['detail']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        site = env_config.get_base_url("ckan_site").rstrip("/")
        slug = data.get("name", "")
        resources = data.get("resources") or []
        extras = {
            e.get("key"): e.get("value")
            for e in (data.get("extras") or [])
            if e.get("key")
        }
        payload = {
            "id": data.get("id"),
            "name": slug,
            "title": data.get("title"),
            "url": f"{site}/dataset/{slug}" if slug else None,
            "source_url": data.get("url") or None,
            "notes": data.get("notes"),
            "organization": {
                "title": (data.get("organization") or {}).get("title"),
                "name": (data.get("organization") or {}).get("name"),
            }
            if data.get("organization")
            else None,
            "tags": [
                t.get("display_name", t.get("name", ""))
                for t in (data.get("tags") or [])[:20]
            ],
            "groups": [
                g.get("title", g.get("display_name", ""))
                for g in (data.get("groups") or [])
            ],
            "num_resources": len(resources),
            "metadata_created": data.get("metadata_created"),
            "metadata_modified": data.get("metadata_modified"),
            "license_title": data.get("license_title"),
            "update_frequency": data.get("update_frequency"),
            "author": data.get("author"),
            "maintainer": data.get("maintainer"),
            "extras": extras,
        }

        def to_text(p: dict) -> str:
            parts = [f"Dataset: {p.get('title') or 'Desconocido'}", ""]
            if p.get("id"):
                parts.append(f"ID: {p['id']}")
            if p.get("name"):
                parts.append(f"Slug: {p['name']}")
                parts.append(f"URL: {p.get('url')}")
            if p.get("source_url"):
                parts.append(f"Fuente original: {p['source_url']}")
            if p.get("notes"):
                parts.append("")
                parts.append(f"Descripción: {str(p['notes'])[:800]}")
            org = p.get("organization") or {}
            if org.get("title"):
                parts.append("")
                parts.append(f"Organización: {org['title']}")
                if org.get("name"):
                    parts.append(f"  ID organización: {org['name']}")
            if p.get("tags"):
                parts.append("")
                parts.append(f"Tags: {', '.join(p['tags'][:10])}")
            if p.get("groups"):
                parts.append(f"Categorías: {', '.join(p['groups'])}")
            parts.append("")
            parts.append(f"Recursos: {p.get('num_resources', 0)} archivo(s)")
            if p.get("metadata_created"):
                parts.append("")
                parts.append(f"Creado: {p['metadata_created']}")
            if p.get("metadata_modified"):
                parts.append(f"Última modificación: {p['metadata_modified']}")
            if p.get("license_title"):
                parts.append("")
                parts.append(f"Licencia: {p['license_title']}")
            freq = p.get("update_frequency")
            if freq:
                if isinstance(freq, list):
                    freq = ", ".join(freq)
                parts.append(f"Frecuencia de actualización: {freq}")
            if p.get("author"):
                parts.append("")
                parts.append(f"Autor: {p['author']}")
            if p.get("maintainer"):
                parts.append(f"Mantenedor: {p['maintainer']}")
            extras = p.get("extras") or {}
            if extras:
                parts.append("")
                parts.append("Metadatos adicionales:")
                for key, value in extras.items():
                    parts.append(f"  {key}: {value}")
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
