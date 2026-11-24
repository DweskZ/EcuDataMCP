"""List ANDA related materials, including aggregate-only statistical studies."""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from helpers import env_config
from helpers.geo_proxy import proxy_for
from helpers.user_agent import USER_AGENT

# The visible text of every download button is "Descargar [ZIP, 474.32 KB]".
_BUTTON_RE = re.compile(r"\[\s*([^,\]]+?)\s*,\s*([^\]]+?)\s*\]")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs = {key: value or "" for key, value in attrs}
            self.current = {
                "href": attrs.get("href", ""),
                "title": attrs.get("title", ""),
                "filename": attrs.get("data-filename", ""),
                "text": [],
            }

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current is not None:
            self.links.append(self.current)
            self.current = None


def parse_material_links(
    html: str, page_url: str, survey_id: str, site_base: str | None = None
) -> list[dict]:
    """Return only ANDA downloads belonging to this catalog entry.

    Each result has ``nombre`` and ``url``, plus ``formato`` and ``tamano``
    when the download button says them. The name is the file's own name: the
    button text is always just "Descargar [ZIP, 8.01 MB]", while the link's
    ``data-filename`` / ``title`` carry e.g. "1. Serie Historica del IPC.zip".
    ``site_base`` is the configured ANDA site root; by default it is taken
    from ``page_url``.
    """
    site = urlsplit(site_base or page_url.split("index.php", 1)[0])
    prefix = site.path.rstrip("/") + "/index.php/catalog/"
    path_re = re.compile(rf"{re.escape(prefix)}{survey_id}/download/\d+/?")
    parser = _Links()
    parser.feed(html)
    found = {}
    for item in parser.links:
        url = urljoin(page_url, item["href"])
        parts = urlsplit(url)
        if parts.hostname != site.hostname or not path_re.fullmatch(parts.path):
            continue
        text = " ".join(" ".join(item["text"]).split())
        name = item["filename"].strip() or item["title"].strip() or text or "Material relacionado"
        entry = {"nombre": name, "url": url}
        button = _BUTTON_RE.search(text)
        if button:
            entry["formato"], entry["tamano"] = button.group(1), button.group(2)
        found.setdefault(url, entry)
    return list(found.values())


async def get_related_materials(survey_id: str, session: httpx.AsyncClient | None = None) -> dict:
    if not survey_id.isascii() or not survey_id.isdigit():
        raise ValueError("El id debe ser el identificador numérico del catálogo ANDA.")
    base = env_config.get_base_url("anda_site")
    url = f"{base}index.php/catalog/{survey_id}/related-materials"
    own = session is None
    if own:
        session = httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, proxy=proxy_for(base))
    try:
        response = await session.get(url, follow_redirects=True, timeout=20.0)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (404, 500):
                # ANDA answers 500, not 404, for a catalog id it does not have.
                raise ValueError(
                    f"ANDA no devolvió el catálogo {survey_id} (HTTP {exc.response.status_code}): "
                    "el id no existe o ANDA falló; usa el id numérico que da search_anda."
                ) from exc
            raise
        files = parse_material_links(response.text, str(response.url), survey_id, site_base=base)
        return {"fuente": "INEC ANDA", "url_fuente": url, "id": survey_id,
                "total": len(files), "archivos": files,
                "nota": "Enlaces de materiales relacionados; no implica acceso a microdatos ni lectura del contenido."}
    finally:
        if own:
            await session.aclose()
