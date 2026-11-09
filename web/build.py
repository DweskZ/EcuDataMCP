"""Static site generator for EcuDataMCP's landing page.

Replaces the old static-site pipeline: renders web/templates/{lang}/*.html
via Jinja2 against web/data/*.json, copies web/assets/ verbatim, and writes
everything to web/_site/ (web/_site/en/ for the English tree) -- same
output layout the old pipeline used, so the gh-pages publish flow doesn't
change.

Usage: uv run python build.py
"""

import html as html_lib
import json
import math
import re
import shutil
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
    "es": {"build-local": "build local", "offline": "sin conexión"},
    "en": {"build-local": "local build", "offline": "offline"},
}

TRANSLATIONS = {
    "es": {
        "search": "Buscar",
        "search_placeholder": "Buscar en el sitio…",
        "toggle_nav": "Mostrar u ocultar la navegación",
        "nav_label": "Principal",
        "copied": "¡Copiado!",
        "default_required": "requerido",
        "default_none": "ninguno",
        "default_empty": "vacío",
        "search_no_results": "Sin resultados.",
        "skip_to_content": "Saltar al contenido",
    },
    "en": {
        "search": "Search",
        "search_placeholder": "Search the site…",
        "toggle_nav": "Toggle navigation",
        "nav_label": "Main",
        "copied": "Copied!",
        "default_required": "required",
        "default_none": "none",
        "default_empty": "empty",
        "search_no_results": "No results.",
        "skip_to_content": "Skip to content",
    },
}

# Source status labels on the home explorer (fuentes.html keeps using the
# smaller STATUS_BADGES, which only flags the exceptions).
STATUS_LABELS = {
    "es": {"live": "en línea", "offline": "sin conexión", "build-local": "build local"},
    "en": {"live": "online", "offline": "offline", "build-local": "local build"},
}

# Strings the home page JavaScript needs (search results, terminal, labels).
# Placeholders in {braces} are filled in by home.js.
HOME_UI = {
    "es": {
        "found_one": "<b>{n}</b> fuente podría responder esto:",
        "found_many": "<b>{n}</b> fuentes podrían responder esto:",
        "none": "Ninguna fuente coincide con “{q}”.",
        "explore_themes": "Explora los temas",
        "see_example": "Ver cómo lo respondería tu asistente →",
        "see_answer": "Ver la respuesta guardada →",
        "cleared": "Búsqueda borrada.",
        "src_consulted": "Fuente consultada: ",
        "pause": "Pausar ejemplos",
        "play": "Reanudar ejemplos",
        "theme_word": "tema",
        "no_filter": "Mostrar todas las fuentes",
        "copy": "Copiar",
    },
    "en": {
        "found_one": "<b>{n}</b> source could answer this:",
        "found_many": "<b>{n}</b> sources could answer this:",
        "none": "No source matches “{q}”.",
        "explore_themes": "Explore the themes",
        "see_example": "See how your assistant would answer it →",
        "see_answer": "See the stored answer →",
        "cleared": "Search cleared.",
        "src_consulted": "Source consulted: ",
        "pause": "Pause examples",
        "play": "Resume examples",
        "theme_word": "theme",
        "no_filter": "Show all sources",
        "copy": "Copy",
    },
}

FOOTER = {
    "es": {
        "cta_a": "Datos abiertos del Ecuador,",
        "cta_b": "con tu asistente de IA favorito.",
        "install": "Instalar",
        "github": "Ver en GitHub",
        "product": "Producto",
        "project": "Proyecto",
        "language": "Idioma",
        "product_links": [
            ("Cómo funciona", "index.html#como-funciona"),
            ("Fuentes", "fuentes.html"),
            ("Referencia de tools", "atlas.html"),
            ("Ejemplos", "examples.html"),
        ],
        "project_links": [
            ("Releases", "releases.html"),
            ("Cómo colaborar", "colaborar.html"),
            ("Acerca de", "about.html"),
        ],
        "install_href": "index.html#conectar",
    },
    "en": {
        "cta_a": "Ecuador's open data,",
        "cta_b": "with your favorite AI assistant.",
        "install": "Install",
        "github": "View on GitHub",
        "product": "Product",
        "project": "Project",
        "language": "Language",
        "product_links": [
            ("How it works", "index.html#how-it-works"),
            ("Sources", "fuentes.html"),
            ("Tool reference", "atlas.html"),
            ("Examples", "examples.html"),
        ],
        "project_links": [
            ("Releases", "releases.html"),
            ("Contribute", "colaborar.html"),
            ("About", "about.html"),
        ],
        "install_href": "index.html#connect",
    },
}

MONTHS = {
    "es": [
        "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
        "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ],
    "en": [
        "January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December",
    ],
}

NAV = {
    "es": {
        "left": [
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
        "index": "Datos abiertos de Ecuador para tu asistente de IA",
        "atlas": "Referencia",
        "examples": "Ejemplos",
        "releases": "Releases",
        "about": "Acerca de",
        "colaborar": "Cómo colaborar",
        "fuentes": "Fuentes",
    },
    "en": {
        "index": "Ecuador open data for your AI assistant",
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
        "index": "Servidor MCP de código abierto: {n_sources} fuentes oficiales y {n} tools para consultar los datos abiertos de Ecuador desde tu asistente de IA, con la fuente citada.",
        "atlas": "Los {n} tools de EcuDataMCP, con descripción completa y enlace directo a cada uno.",
        "examples": "Once preguntas reales, respondidas con EcuDataMCP: sin inventar datos de Ecuador.",
        "releases": "Historial de versiones de EcuDataMCP y el ritmo real de los releases.",
        "about": "Qué es EcuDataMCP, de dónde viene y quién lo mantiene.",
        "colaborar": "Cómo proponer una fuente, un tool o un cambio al sitio de EcuDataMCP.",
        "fuentes": "Las {n_sources} fuentes oficiales de EcuDataMCP, agrupadas por tema e institución.",
    },
    "en": {
        "index": "Open-source MCP server: {n_sources} official sources and {n} tools to query Ecuador's open data from your AI assistant, with the source cited.",
        "atlas": "EcuDataMCP's {n} tools, with a full description and a direct link to each one.",
        "examples": "Eleven real questions, answered with EcuDataMCP: no invented data about Ecuador.",
        "releases": "EcuDataMCP's version history and the real pace of its releases.",
        "about": "What EcuDataMCP is, where it comes from, and who maintains it.",
        "colaborar": "How to propose a source, a tool, or a change to the EcuDataMCP site.",
        "fuentes": "EcuDataMCP's {n_sources} official sources, grouped by theme and institution.",
    },
}

OG_IMAGE = "https://dweskz.github.io/EcuDataMCP/assets/og-image.png"

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
    """Sources may be flat (old format) or grouped by theme -> institution
    (current format, used by both es/ and en/ as of the Fuentes/Sources
    page). Normalize to a flat list for anything that only needs a total
    count or a single flat card grid. The flat format is kept supported
    as a fallback, not because any current data file still uses it."""
    if raw and "institutions" in raw[0]:
        return [
            source
            for theme in raw
            for institution in theme["institutions"]
            for source in institution["sources"]
        ]
    return raw


def atlas_search_key(tool: dict) -> Markup:
    """Port of atlas.qmd's search_key: name + description + long_description
    + each param's "name description", lowercased, with quotes HTML-escaped
    so the value can sit inside a data-search="..." attribute."""
    parts = [tool["name"], tool["description"], tool["long_description"]]
    parts += [f"{p['name']} {p['description']}" for p in tool.get("params") or []]
    key = " ".join(parts).lower()
    # Markup: this already does the one escape the attribute needs; letting
    # autoescape run on it again would turn &quot; into &amp;quot;.
    return Markup(key.replace('"', "&quot;"))


_MAIN_RE = re.compile(r"<main[^>]*>(.*?)</main>", re.DOTALL)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)


def extract_main_text(page: str) -> str:
    """Plain text of the page's <main> content only -- excludes the <head>
    (inline <style>, meta tags) and the navbar/footer chrome that every page
    shares, so search results reflect what's actually on that page."""
    match = _MAIN_RE.search(page)
    body = match.group(1) if match else page
    body = _SCRIPT_STYLE_RE.sub(" ", body)
    # Unescape after stripping tags: with autoescape on, quotes in the
    # rendered page are entities, and the search index wants plain text.
    return html_lib.unescape(re.sub(r"<[^>]+>", " ", body))


def load_json(lang: str, name: str):
    path = DATA / name if lang == "es" else WEB / "en" / "data" / name
    return json.loads(path.read_text(encoding="utf-8"))


def load_org_logos(lang: str) -> list[dict]:
    raw = json.loads((DATA / "org_logos.json").read_text(encoding="utf-8"))
    title_key = "title_es" if lang == "es" else "title_en"
    return [
        {
            "file": item["file"],
            "short": item["short"],
            "title": item[title_key],
            "plate": item.get("plate", "light"),
        }
        for item in raw
    ]


def complete_tool_catalog(
    curated: list[dict], signatures: dict[str, dict], lang: str
) -> list[dict]:
    """Keep the human-written Atlas in step with the code.

    `signatures` (data/tool_signatures.json, from scripts/
    extract_tool_signatures.py) is the source of truth for which tools exist
    and what parameters they take. Curated entries keep their translated
    descriptions, but a tool that no longer exists is dropped, and each
    entry's parameter list follows the code (new parameters get the source
    docstring text). Tools with no curated entry appear under one explicit
    supplementary category using their source docstrings, rather than being
    silently omitted until an editorial pass is made. `signatures` is the
    English extraction (docstrings are written in English), so on the
    Spanish site that fallback text is English by construction; the category
    label says so instead of silently mixing languages.
    """
    fallback_description = (
        "Parámetro documentado en el código fuente."
        if lang == "es"
        else "Parameter documented in the source code."
    )

    def param_entry(name: str, signature: dict, existing: dict | None) -> dict:
        code_param = next(p for p in signature["params"] if p["name"] == name)
        description = (
            existing["description"]
            if existing
            else signature["args_doc"].get(name, fallback_description)
        )
        return {**code_param, "description": description}

    catalog = []
    for category in curated:
        tools = []
        for tool in category["tools"]:
            signature = signatures.get(tool["name"])
            if signature is None:
                continue
            existing = {}
            for param in tool["params"]:
                existing.setdefault(param["name"], param)
            params = [
                param_entry(p["name"], signature, existing.get(p["name"]))
                for p in signature["params"]
            ]
            tools.append({**tool, "params": params})
        if tools:
            catalog.append({**category, "tools": tools})

    listed = {tool["name"] for category in catalog for tool in category["tools"]}
    missing = sorted(set(signatures) - listed)
    if not missing:
        return catalog

    generated = []
    for name in missing:
        signature = signatures[name]
        description = signature.get("description") or signature["summary"]
        generated.append(
            {
                "name": name,
                "description": description.split(". ", 1)[0],
                "long_description": signature["summary"],
                "params": [
                    param_entry(p["name"], signature, None)
                    for p in signature["params"]
                ],
            }
        )
    category = {
        "category": (
            "Herramientas incorporadas recientemente (descripción original "
            "en inglés, pendiente de traducir)"
            if lang == "es"
            else "Recently added tools"
        ),
        "tools": generated,
    }
    return [*catalog, category]


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def format_long_date(iso: str, lang: str) -> str:
    """'2026-11-08' -> '8 de noviembre de 2026' / 'November 8, 2026'."""
    year, month, day = (int(part) for part in iso.split("-"))
    name = MONTHS[lang][month - 1]
    return f"{day} de {name} de {year}" if lang == "es" else f"{name} {day}, {year}"


def load_provinces() -> dict:
    return json.loads((DATA / "ecuador_provinces.json").read_text(encoding="utf-8"))


def atlas_dots(count: int, provinces: list[dict]) -> list[tuple[float, float]]:
    """One illustrative position per source: each dot is spread around the
    bounding-box centre of a province on a golden-angle spiral. Deterministic,
    so the same catalog always renders the same map. The position carries no
    geographic meaning (the page says so)."""
    centres = []
    for province in provinces:
        nums = [float(n) for n in _NUM_RE.findall(province["d"])]
        xs, ys = nums[0::2], nums[1::2]
        centres.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
    dots = []
    for k in range(count):
        cx, cy = centres[(k * 7) % len(centres)]
        angle = k * 2.399
        radius = 7 + ((k * 13) % 22)
        dots.append((round(cx + math.cos(angle) * radius, 1), round(cy + math.sin(angle) * radius, 1)))
    return dots


def build_home(lang: str, source_themes: list[dict], tool_count: int) -> dict:
    """Everything the home template and home.js derive from the data files:
    stats, the map, the theme explorer and the JSON island used by the
    client-side search and the terminal."""
    geo = load_provinces()
    answers_raw = load_json(lang, "stored_answers.json")
    transcripts = load_json(lang, "transcripts.json")
    lexicon = load_json(lang, "search_lexicon.json")
    labels = STATUS_LABELS[lang]

    themes = []
    flat = []
    for idx, theme in enumerate(source_themes):
        entries = []
        for institution in theme["institutions"]:
            for source in institution["sources"]:
                entry = {
                    "k": len(flat),
                    "t": idx,
                    "institution": institution["name"],
                    "name": source["name"],
                    "description": source["description"],
                    "url": source.get("url", ""),
                    "status": source["status"],
                    "status_label": labels.get(source["status"], source["status"]),
                    "theme": theme["theme"],
                    "color": theme["color"],
                }
                flat.append(entry)
                entries.append(entry)
        themes.append(
            {
                "idx": idx,
                "id": theme["id"],
                "name": theme["theme"],
                "color": theme["color"],
                "count": len(entries),
                "sources": entries,
            }
        )
    by_size = sorted(themes, key=lambda th: -th["count"])

    dots = atlas_dots(len(flat), geo["provinces"])
    for entry, (x, y) in zip(flat, dots):
        entry["x"], entry["y"] = x, y

    online = sum(1 for entry in flat if entry["status"] == "live")
    answers = answers_raw["answers"]
    data = {
        "themes": [
            {"i": th["idx"], "name": th["name"], "color": th["color"], "n": th["count"]}
            for th in themes
        ],
        "sources": [
            {
                "k": e["k"],
                "t": e["t"],
                "i": e["institution"],
                "n": e["name"],
                "d": e["description"],
                "u": e["url"],
            }
            for e in flat
        ],
        "answers": [
            {"id": a["id"], "q": a["question"], "a": a["answer"], "tools": a["tools"], "src": a["source"]}
            for a in answers
        ],
        "transcripts": transcripts,
        "lexicon": lexicon,
        "ui": HOME_UI[lang],
    }
    return {
        "geo": geo,
        "themes": themes,
        "themes_by_size": by_size,
        "sources": flat,
        "theme_count": len(themes),
        "online_count": online,
        "source_count": len(flat),
        "tool_count": tool_count,
        "answers": answers,
        "extracted_label": format_long_date(answers_raw["extracted_at"], lang),
        "server_version": answers_raw["server_version"],
        "transcripts": transcripts,
        "data": data,
    }


def build_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)),
        # Every {{ }} is escaped unless a filter returns Markup (mdlite,
        # codeescape, atlas_search_key): tool docstrings reach the Atlas via
        # tool_signatures.json and already contain literal "<fuente>" text.
        autoescape=True,
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
    # [] rather than None if sources.json ever reverts to the flat format --
    # fuentes.html/en/fuentes.html iterate this unconditionally, and Jinja
    # raises TypeError on `for x in None` instead of just rendering nothing.
    source_themes = (
        sources_raw if sources_raw and "institutions" in sources_raw[0] else []
    )
    clients = load_json(lang, "clients.json")
    tools = complete_tool_catalog(
        load_json(lang, "tools.json"),
        load_json("es", "tool_signatures.json"),
        lang,
    )
    releases = load_json(lang, "releases.json")

    tool_count = sum(len(cat["tools"]) for cat in tools)
    source_count = len(sources)

    home = build_home(lang, source_themes, tool_count)

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
        # Absolute canonical URL for this page; hreflang alternates are only
        # emitted when the counterpart page really exists in the other language.
        own_prefix = "" if lang == "es" else "en/"
        canonical_url = f"{SITE_URL}/{own_prefix}{page}.html"
        alternate_urls = []
        if has_counterpart:
            alternate_urls = [
                ("es", f"{SITE_URL}/{page}.html"),
                ("en", f"{SITE_URL}/en/{page}.html"),
                ("x-default", f"{SITE_URL}/{page}.html"),
            ]
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
            canonical_url=canonical_url,
            alternate_urls=alternate_urls,
            sources=sources,
            source_themes=source_themes,
            clients=clients,
            tools=tools,
            home=home,
            status_labels=STATUS_LABELS[lang],
            footer=FOOTER[lang],
            releases=releases,
            tool_count=tool_count,
            source_count=source_count,
            org_logos=load_org_logos(lang),
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


def write_404(env: jinja2.Environment):
    """Bilingual 404 for GitHub Pages. It is served from any path, so every
    URL on it is root-relative to the Pages base, not relative to the file."""
    base = f"/{SITE_URL.rsplit('/', 1)[1]}/"
    page = env.get_template("404.html").render(
        lang="es",
        root=base,
        assets=f"{base}assets/",
        nav=NAV["es"],
        lang_switch_href=f"{base}en/index.html",
        t=TRANSLATIONS["es"],
        status_badges=STATUS_BADGES["es"],
        footer=FOOTER["es"],
        current_page="404",
        page_title="Página no encontrada / Page not found",
        page_description="La página que buscas no existe. / The page you are looking for does not exist.",
        og_image=OG_IMAGE,
        canonical_url=f"{SITE_URL}/404.html",
        alternate_urls=[],
    )
    (SITE / "404.html").write_text(page, encoding="utf-8")


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
        f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n",
        encoding="utf-8",
    )
    urls = []
    for page in PAGES + EXTRA_PAGES["es"]:
        urls.append(f"{SITE_URL}/{page}.html")
    for page in PAGES + EXTRA_PAGES["en"]:
        urls.append(f"{SITE_URL}/en/{page}.html")
    entries = "\n".join(
        f"  <url>\n    <loc>{u}</loc>\n  </url>"
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
    write_404(env)
    copy_assets()
    write_seo_files()
    # GitHub Pages runs Jekyll by default; this disables it so files like
    # search.json and any future underscore-prefixed paths are served as-is.
    (SITE / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Built site -> {SITE}")


if __name__ == "__main__":
    main()
