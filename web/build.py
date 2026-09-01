"""Static site generator for EcuDataMCP's landing page.

Replaces the old static-site pipeline: renders web/templates/{lang}/*.html
via Jinja2 against web/data/*.json, copies web/assets/ verbatim, and writes
everything to web/_site/ (web/_site/en/ for the English tree) -- same
output layout the old pipeline used, so the gh-pages publish flow doesn't
change.

Usage: uv run python build.py
"""

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

import jinja2
from markupsafe import Markup

WEB = Path(__file__).parent
TEMPLATES = WEB / "templates"
DATA = WEB / "data"
ASSETS = WEB / "assets"
SITE = WEB / "_site"

PAGES = ["index", "atlas", "examples", "releases", "about", "colaborar"]

# Pages that only exist in one language so far. Rendered in addition to
# PAGES for that language only; excluded from the other language's sitemap
# and given a language-toggle fallback (see lang_switch_href below) instead
# of a link to a page that doesn't exist yet.
EXTRA_PAGES = {"es": ["fuentes"], "en": ["fuentes"]}

STATUS_BADGES = {
    "es": {"build-local": "build local", "offline": "offline"},
    "en": {"build-local": "local build", "offline": "offline"},
}

TRANSLATIONS = {
    "es": {
        "search": "Buscar",
        "search_placeholder": "Buscar en el sitio…",
        "toggle_nav": "Navegación de palanca",
        "copied": "¡Copiado!",
        "default_required": "requerido",
        "default_none": "ninguno",
        "default_empty": "vacío",
        "search_no_results": "Sin resultados.",
    },
    "en": {
        "search": "Search",
        "search_placeholder": "Search the site…",
        "toggle_nav": "Toggle navigation",
        "copied": "Copied!",
        "default_required": "required",
        "default_none": "none",
        "default_empty": "empty",
        "search_no_results": "No results.",
    },
}

NAV = {
    "es": {
        "left": [
            ("EcuDataMCP", "index.html"),
            ("Cómo funciona", "index.html#como-funciona"),
            ("Fuentes", "fuentes.html"),
            ("Referencia", "atlas.html"),
            ("Ejemplos", "examples.html"),
            ("Releases", "releases.html"),
            ("Acerca de", "about.html"),
            ("Cómo colaborar", "colaborar.html"),
        ],
        "footer_left": (
            "MIT License · Proyecto independiente, no afiliado a ninguna "
            "institución del Estado ecuatoriano."
        ),
    },
    "en": {
        "left": [
            ("EcuDataMCP", "index.html"),
            ("How it works", "index.html#how-it-works"),
            ("Sources", "fuentes.html"),
            ("Reference", "atlas.html"),
            ("Examples", "examples.html"),
            ("Releases", "releases.html"),
            ("About", "about.html"),
            ("Contribute", "colaborar.html"),
        ],
        "footer_left": (
            "MIT License · Independent project, not affiliated with any "
            "Ecuadorian government institution."
        ),
    },
}

PAGE_TITLES = {
    "es": {
        "index": "EcuDataMCP",
        "atlas": "Referencia",
        "examples": "Ejemplos",
        "releases": "Releases",
        "about": "Acerca de",
        "colaborar": "Cómo colaborar",
        "fuentes": "Fuentes",
    },
    "en": {
        "index": "EcuDataMCP",
        "atlas": "Reference",
        "examples": "Examples",
        "releases": "Releases",
        "about": "About",
        "colaborar": "Contribute",
        "fuentes": "Sources",
    },
}

PAGE_DESCRIPTIONS = {
    "es": {
        "index": "Servidor MCP de código abierto para explorar datos abiertos del gobierno de Ecuador desde tu asistente de IA.",
        "atlas": "Los {n} tools de EcuDataMCP, con descripción completa y enlace directo a cada uno.",
        "examples": "Diez preguntas reales, respondidas con EcuDataMCP: sin inventar datos de Ecuador.",
        "releases": "Historial de versiones de EcuDataMCP y el ritmo real de los releases.",
        "about": "Qué es EcuDataMCP, de dónde viene y quién lo mantiene.",
        "colaborar": "Cómo proponer una fuente, un tool o un cambio al sitio de EcuDataMCP.",
        "fuentes": "Las {n_sources} fuentes oficiales de EcuDataMCP, agrupadas por tema e institución.",
    },
    "en": {
        "index": "Open-source MCP server for exploring Ecuador's open government data from your AI assistant.",
        "atlas": "EcuDataMCP's {n} tools, with a full description and a direct link to each one.",
        "examples": "Ten real questions, answered with EcuDataMCP: no invented data about Ecuador.",
        "releases": "EcuDataMCP's version history and the real pace of its releases.",
        "about": "What EcuDataMCP is, where it comes from, and who maintains it.",
        "colaborar": "How to propose a source, a tool, or a change to the EcuDataMCP site.",
        "fuentes": "EcuDataMCP's {n_sources} official sources, grouped by theme and institution.",
    },
}

OG_IMAGE = "https://dsanchezp18.github.io/EcuDataMCP/assets/og-image.png"

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_RE = re.compile(r"`(.+?)`")


def mdlite(text: str) -> Markup:
    """Minimal markdown: **bold** and `code` only (mirrors the R stringr port)."""
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _CODE_RE.sub(r"<code>\1</code>", text)
    return Markup(text)


def codeescape(text: str) -> Markup:
    """Escape only &, <, > -- matches the R str_replace_all(c("&"=...)) call."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Markup(text)


def clean_default(value, t: dict) -> str:
    """Port of atlas.qmd's clean_default(): unwrap a quoted repr, translate
    the None/empty-string special cases, leave everything else as-is."""
    if value is None:
        return t["default_required"]
    cleaned = re.sub(r"^'(.*)'$", r"\1", value)
    if cleaned == "None":
        return t["default_none"]
    if cleaned == "":
        return t["default_empty"]
    return cleaned


def flatten_sources(raw: list[dict]) -> list[dict]:
    """Sources may be flat (old format, still used by en/) or grouped by
    theme -> institution (new format, es/). Normalize to a flat list for
    anything that only needs a total count or a single flat card grid."""
    if raw and "institutions" in raw[0]:
        return [
            source
            for theme in raw
            for institution in theme["institutions"]
            for source in institution["sources"]
        ]
    return raw


def atlas_search_key(tool: dict) -> str:
    """Port of atlas.qmd's search_key: name + description + long_description
    + each param's "name description", lowercased, with quotes HTML-escaped
    so the value can sit inside a data-search="..." attribute."""
    parts = [tool["name"], tool["description"], tool["long_description"]]
    parts += [f"{p['name']} {p['description']}" for p in tool.get("params") or []]
    key = " ".join(parts).lower()
    return key.replace('"', "&quot;")


_MAIN_RE = re.compile(r"<main>(.*?)</main>", re.DOTALL)


def extract_main_text(html: str) -> str:
    """Plain text of the page's <main> content only -- excludes the <head>
    (inline <style>, meta tags) and the navbar/footer chrome that every page
    shares, so search results reflect what's actually on that page."""
    match = _MAIN_RE.search(html)
    body = match.group(1) if match else html
    return re.sub(r"<[^>]+>", " ", body)


def load_json(lang: str, name: str):
    path = DATA / name if lang == "es" else WEB / "en" / "data" / name
    return json.loads(path.read_text(encoding="utf-8"))


def complete_tool_catalog(
    curated: list[dict], signatures: dict[str, dict], lang: str
) -> list[dict]:
    """Keep the human-written Atlas current when new tools are added.

    The curated entries retain their translated descriptions. New tools appear
    under one explicit supplementary category using their source docstrings,
    rather than being silently omitted until a full editorial pass is made.
    """
    listed = {tool["name"] for category in curated for tool in category["tools"]}
    missing = sorted(set(signatures) - listed)
    if not missing:
        return curated

    fallback_description = (
        "Parámetro documentado en el código fuente."
        if lang == "es"
        else "Parameter documented in the source code."
    )
    generated = []
    for name in missing:
        signature = signatures[name]
        generated.append(
            {
                "name": name,
                "description": signature["summary"].split(". ", 1)[0],
                "long_description": signature["summary"],
                "params": [
                    {
                        **parameter,
                        "description": signature["args_doc"].get(
                            parameter["name"], fallback_description
                        ),
                    }
                    for parameter in signature["params"]
                ],
            }
        )
    category = {
        "category": (
            "Herramientas incorporadas recientemente"
            if lang == "es"
            else "Recently added tools"
        ),
        "tools": generated,
    }
    return [*curated, category]


def build_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)),
        autoescape=False,
        undefined=jinja2.StrictUndefined,
    )
    env.filters["mdlite"] = mdlite
    env.filters["codeescape"] = codeescape
    env.filters["clean_default"] = clean_default
    env.filters["atlas_search_key"] = atlas_search_key
    return env


def render_lang(env: jinja2.Environment, lang: str) -> list[dict]:
    out_dir = SITE if lang == "es" else SITE / "en"
    out_dir.mkdir(parents=True, exist_ok=True)
    # NAV/search hrefs (e.g. "atlas.html") are relative to the current
    # language's own output directory, which is always where the current
    # page itself lives -- so root must stay empty for BOTH languages, or
    # every in-page/nav link on the English site escapes into es/. Only
    # the assets/ directory actually lives a level up from en/.
    root = ""
    assets_prefix = "assets/" if lang == "es" else "../assets/"

    sources_raw = load_json(lang, "sources.json")
    sources = flatten_sources(sources_raw)
    source_themes = sources_raw if sources_raw and "institutions" in sources_raw[0] else None
    clients = load_json(lang, "clients.json")
    tools = complete_tool_catalog(
        load_json(lang, "tools.json"),
        load_json("es", "tool_signatures.json"),
        lang,
    )
    questions = load_json(lang, "questions.json")
    releases = load_json(lang, "releases.json")

    tool_count = sum(len(cat["tools"]) for cat in tools)
    source_count = len(sources)

    search_entries = []

    other_lang = "en" if lang == "es" else "es"
    other_root = "en/" if lang == "es" else "../"

    for page in PAGES + EXTRA_PAGES[lang]:
        template = env.get_template(f"{lang}/{page}.html")
        title = PAGE_TITLES[lang][page]
        description = PAGE_DESCRIPTIONS[lang][page].format(
            n=tool_count, n_sources=source_count
        )
        # A page only rendered for this language and not (yet) the other one
        # has no counterpart to switch to -- fall back to the other
        # language's homepage instead of linking a 404.
        has_counterpart = page in PAGES or page in EXTRA_PAGES[other_lang]
        other_page = page if has_counterpart else "index"
        html = template.render(
            lang=lang,
            root=root,
            assets=assets_prefix,
            nav=NAV[lang],
            lang_switch_href=f"{other_root}{other_page}.html",
            t=TRANSLATIONS[lang],
            status_badges=STATUS_BADGES[lang],
            current_page=page,
            page_title=title,
            page_description=description,
            og_image=OG_IMAGE,
            sources=sources,
            source_themes=source_themes,
            clients=clients,
            tools=tools,
            questions=questions,
            releases=releases,
            tool_count=tool_count,
            source_count=source_count,
        )
        (out_dir / f"{page}.html").write_text(html, encoding="utf-8")

        text = re.sub(r"\s+", " ", extract_main_text(html)).strip()
        search_entries.append(
            {
                "objectID": f"{page}.html",
                "href": f"{page}.html",
                "title": title,
                "section": "",
                "text": text,
            }
        )

    (out_dir / "search.json").write_text(
        json.dumps(search_entries, ensure_ascii=False), encoding="utf-8"
    )
    return search_entries


def copy_assets():
    dest = SITE / "assets"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(ASSETS, dest)


SITE_URL = "https://dweskz.github.io/EcuDataMCP"


def write_seo_files():
    """robots.txt + sitemap.xml against the real deployed domain -- the old
    site build pointed both at a stale, seemingly-unused netlify.app URL."""
    (SITE / "robots.txt").write_text(
        f"Sitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8"
    )
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    urls = []
    for page in PAGES + EXTRA_PAGES["es"]:
        urls.append(f"{SITE_URL}/{page}.html")
    for page in PAGES + EXTRA_PAGES["en"]:
        urls.append(f"{SITE_URL}/en/{page}.html")
    entries = "\n".join(
        f"  <url>\n    <loc>{u}</loc>\n    <lastmod>{now}</lastmod>\n  </url>"
        for u in urls
    )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n"
        "</urlset>\n"
    )
    (SITE / "sitemap.xml").write_text(sitemap, encoding="utf-8")


def main():
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    env = build_env()
    render_lang(env, "es")
    render_lang(env, "en")
    copy_assets()
    write_seo_files()

    print(f"Built site -> {SITE}")


if __name__ == "__main__":
    main()
