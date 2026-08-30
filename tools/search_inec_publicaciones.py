from mcp.server.fastmcp import FastMCP

from helpers import inec_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_inec_publicaciones_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_inec_publicaciones(
        query: str = "",
        limit: int = 20,
        offset: int = 0,
        format: str = "text",
    ) -> str:
        """
        Search every post INEC has published on Ecuador en Cifras, via its
        public WordPress REST API -- always current, newest first.

        Complements search_inec_estadisticas: that tool's topic pages are
        curated landing pages that can go stale for months or years even
        while INEC keeps publishing the same operation (confirmed live:
        ENEMDU's old "Empleo" topic page stopped at April 2023 while INEC
        kept releasing it monthly under dated posts this tool finds). Use
        this tool for "what's the latest bulletin/release for X" questions.
        Use search_inec_estadisticas/get_inec_estadistica_files instead when
        you want one operation's fixed overview page rather than a specific
        dated release.

        Follow up with get_inec_publicacion_archivos(id) for one
        publication's file links.

        Args:
            query: Free text matched against title/content (e.g. "ENEMDU
                anual 2025", "inflación julio", "censo"). Empty returns the
                most recent posts regardless of topic.
            limit: Max results (default 20, max 100).
            offset: Pagination offset over the matched set.
            format: text | json
        """
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)

        try:
            result = await inec_client.search_publicaciones(
                query=query, limit=limit, offset=offset
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al buscar publicaciones de Ecuador en Cifras (INEC): {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            posts = data.get("publicaciones") or []
            total = data.get("total")
            header = (
                f"Publicaciones de Ecuador en Cifras (INEC) — {total} resultado(s) "
                f"(mostrando {len(posts)}, offset={data['offset']})"
                if total is not None
                else f"Publicaciones de Ecuador en Cifras (INEC) — mostrando {len(posts)}"
            )
            parts = [header, ""]
            if not posts:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, p in enumerate(posts, 1):
                parts.append(f"{i}. {p.get('titulo')}")
                parts.append(f"   ID: {p.get('id')} · Publicado: {p.get('fecha_publicacion')}")
                categorias = p.get("categorias") or []
                if categorias:
                    parts.append(f"   Categorías: {', '.join(categorias)}")
                parts.append(f"   {p.get('url')}")
                parts.append("")
            parts.append(
                "Usa get_inec_publicacion_archivos(post=...) para los archivos de una publicación."
            )
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)
