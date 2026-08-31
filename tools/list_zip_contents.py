from mcp.server.fastmcp import FastMCP

from helpers.csv_reader import list_zip_contents as _list_zip_contents
from helpers.format_out import render_output
from helpers.logging import log_tool


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def register_list_zip_contents_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_zip_contents(
        url: str,
        limit: int = 200,
        offset: int = 0,
        format: str = "text",
    ) -> str:
        """
        List a .zip archive's member files (name, size) from a direct URL,
        without downloading the archive.

        Reads only the End Of Central Directory record and the central
        directory via HTTP Range requests, so it works for archives far
        larger than the 5 MB preview_zip/download_resource cap -- e.g. INEC
        or censo microdata ZIPs of multiple hundred MB. Requires the server
        to honor Range requests; fails with a clear error otherwise. Does
        not support ZIP64 archives. Listing names is cheap this way, but
        previewing a specific member's rows is not (still needs decompressing
        from that member's offset onward) -- this tool only lists metadata.

        Args:
            url: Direct URL to a .zip file (from another tool's result, e.g.
                get_inec_publicacion_archivos, search_censo_recursos).
            limit: Max members returned (default 200, max 1000).
            offset: Pagination offset over the member list.
            format: text | json
        """
        limit = min(max(limit, 1), 1000)
        offset = max(offset, 0)

        try:
            result = await _list_zip_contents(url)
        except ValueError as e:
            return render_output(
                {"error": str(e), "url": url},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "url": url},
                format,
                text_builder=lambda d: f"Error al listar el .zip: {d['error']}",
            )

        all_members = result["members"]
        page = all_members[offset : offset + limit]
        payload = {
            "url": url,
            "total_size_bytes": result["total_size_bytes"],
            "total_entries": result["total_entries"],
            "offset": offset,
            "members": page,
        }

        def to_text(data: dict) -> str:
            parts = [
                f"Archivo: {data['url']}",
                f"Tamaño total: {_human_size(data['total_size_bytes'])}",
                (
                    f"Miembros: {data['total_entries']} total, mostrando "
                    f"{len(data['members'])} desde offset={data['offset']}"
                ),
                "",
            ]
            if not data["members"]:
                parts.append("Sin miembros en este rango.")
                return "\n".join(parts)
            for m in data["members"]:
                tag = "/" if m["is_dir"] else ""
                parts.append(
                    f"- {m['name']}{tag} "
                    f"({_human_size(m['uncompressed_size'])}, {m['compression']})"
                )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
