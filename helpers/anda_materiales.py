"""List ANDA related materials, including aggregate-only statistical studies."""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from helpers import env_config
from helpers.geo_proxy import proxy_for
from helpers.user_agent import USER_AGENT


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs = dict(attrs)
            self.current = {"href": attrs.get("href", ""), "title": attrs.get("title", ""), "text": []}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current is not None:
            self.links.append(self.current)
            self.current = None


def parse_material_links(html: str, base_url: str, survey_id: str) -> list[dict]:
    """Return only ANDA downloads belonging to this catalog entry."""
    parser = _Links()
    parser.feed(html)
    found = {}
    for item in parser.links:
        url = urljoin(base_url, item["href"])
        parts = urlsplit(url)
        if parts.hostname != "anda.inec.gob.ec":
            continue
        if not re.fullmatch(rf"/anda5/index\.php/catalog/{survey_id}/download/\d+/?", parts.path):
            continue
        name = " ".join(" ".join(item["text"]).split()) or item["title"] or "Material relacionado"
        found.setdefault(url, {"nombre": name, "url": url})
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
        response.raise_for_status()
        files = parse_material_links(response.text, str(response.url), survey_id)
        return {"fuente": "INEC ANDA", "url_fuente": url, "id": survey_id,
                "total": len(files), "archivos": files,
                "nota": "Enlaces de materiales relacionados; no implica acceso a microdatos ni lectura del contenido."}
    finally:
        if own:
            await session.aclose()
