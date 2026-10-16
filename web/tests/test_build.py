"""Fast checks on the static site build (run from web/: ``uv run pytest``)."""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB))

import build

PAGES_BASE = "/EcuDataMCP/"


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("site")
    original = build.SITE
    build.SITE = out
    try:
        env = build.build_env()
        build.render_lang(env, "es")
        build.render_lang(env, "en")
        build.write_404(env)
        build.copy_assets()
    finally:
        build.SITE = original
    return out


def test_extract_main_text_skips_chrome_scripts_and_unescapes():
    html = (
        "<head><script>localStorage.x</script></head><nav>NAVTEXT</nav>"
        '<main id="main"><style>.a{}</style><p>Tom &amp; Jerry</p>'
        '<script>{"role": "user"}</script></main><footer>FOOT</footer>'
    )
    text = " ".join(build.extract_main_text(html).split())
    assert text == "Tom & Jerry"


def test_search_index_contains_only_main_text(site):
    for rel in ("search.json", "en/search.json"):
        raw = (site / rel).read_text(encoding="utf-8")
        assert "localStorage" not in raw
        assert '\\"role\\"' not in raw


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.urls.append(value)


def test_internal_links_resolve(site):
    missing = []
    for page in site.rglob("*.html"):
        parser = _Links()
        parser.feed(page.read_text(encoding="utf-8"))
        for url in parser.urls:
            parts = urlparse(url)
            if parts.scheme or parts.netloc or not parts.path:
                continue  # external, mailto:, or fragment-only
            path = unquote(parts.path)
            if path.startswith(PAGES_BASE):
                target = site / path[len(PAGES_BASE):]
            elif path.startswith("/"):
                target = site / path.lstrip("/")
            else:
                target = page.parent / path
            if target.is_dir():
                target = target / "index.html"
            if not target.exists():
                missing.append(f"{page.relative_to(site)} -> {url}")
    assert not missing, missing


def test_404_and_og_locale(site):
    page = (site / "404.html").read_text(encoding="utf-8")
    assert f'href="{PAGES_BASE}index.html"' in page
    assert f'href="{PAGES_BASE}en/index.html"' in page
    assert 'og:locale" content="es_EC"' in (site / "index.html").read_text(
        encoding="utf-8"
    )
    en = (site / "en" / "index.html").read_text(encoding="utf-8")
    assert 'og:locale" content="en_US"' in en
    assert 'og:locale:alternate" content="es_EC"' in en


@pytest.mark.parametrize("lang", ["es", "en"])
def test_home_counts_match_data(site, lang):
    tools = build.complete_tool_catalog(
        build.load_json(lang, "tools.json"),
        build.load_json("es", "tool_signatures.json"),
        lang,
    )
    tool_count = sum(len(cat["tools"]) for cat in tools)
    source_count = len(build.flatten_sources(build.load_json(lang, "sources.json")))
    home = site / ("index.html" if lang == "es" else "en/index.html")
    nums = re.findall(
        r'<span class="num">(\d+)</span>', home.read_text(encoding="utf-8")
    )
    assert str(tool_count) in nums
    assert str(source_count) in nums
