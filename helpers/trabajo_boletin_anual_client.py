"""Client for Ministerio del Trabajo's "Boletín Estadístico Anual: El
Mercado Laboral en el Ecuador" — an annual PDF report analyzing the
Ecuadorian labor market. Not a primary survey: every edition states its
labor-market figures derive from INEC's ENEMDU (Encuesta Nacional de
Empleo, Desempleo y Subempleo), with administrative-registry figures
supplied by the ministry's own units — same "derived analysis, not a new
survey" pattern already documented for this ministry's other labor
figures (RESEARCH.md, "Ministerio del Trabajo / SUT").

**Coverage is intentionally incomplete: 3 editions (2020, 2021, 2022),
hardcoded below.** This is not a login/paywall gap — it is what survives
after exhausting every practical way to enumerate editions:

1. The only page that has ever listed multiple editions is
   `www.trabajo.gob.ec/direccion-de-investigacion-y-estudios-laborales/`
   ("Dirección de Información Laboral, Estadística y Geográfica"). Its
   *current* live HTML (re-verified 2026-09-03) links only the 2022 PDF —
   the 2020 and 2021 links that were on the page in Jan 2024 (see below)
   have since been quietly dropped from the page's content, even though
   both files are still live on the server. So even a working scraper of
   today's page would under-count by 2 editions; this client's 2020/2021
   entries exist *because* they were recovered from an older snapshot,
   not from live scraping.
2. That page cannot be scraped live by this project's own HTTP stack
   either way. `helpers.csv_reader.download_bytes` (httpx) fails on it
   with `RemoteProtocolError: multiple Transfer-Encoding headers` —
   confirmed live 2026-09-03, reproducible every attempt. This is a real
   HTTP/1.1 protocol violation from the origin (trabajo.gob.ec sits
   behind a Citrix NetScaler WAF — see the `X-Via-NSCOPI` response header
   — which appears to double-emit `Transfer-Encoding: chunked` on this
   specific dynamic route only), not a timeout: `curl` tolerates the
   malformed response and gets a 200 with a real body, but httpx's h11
   parser correctly refuses it as a possible request-smuggling vector.
   Static files (the PDFs themselves) never exhibit this — confirmed by
   downloading all three editions below through this exact
   `download_bytes` path with no error, consistent with this project's
   established "trabajo.gob.ec's dynamic pages misbehave, its static
   `/wp-content/uploads/...` files don't" pattern (RESEARCH.md). Prior
   research passes logged this as the page "timing out"; it isn't — it's
   this header bug. (Separately, the bare `trabajo.gob.ec` apex domain
   also fails outright for any client that validates hostnames: the
   site's TLS cert is issued for `*.trabajo.gob.ec` only, which a
   wildcard does not cover for the root domain itself. Always use the
   `www.` host, as every URL below does.)
3. With the live page unusable, the Jan 2024 Wayback Machine snapshot
   (`web.archive.org/web/20240113072843/...`) was checked instead —
   accessible this pass (a prior pass found archive.org itself down at
   the time). It captured the index page with all three editions listed
   by name ("Boletín Estadístico Anual: El Mercado Laboral del Ecuador
   2020/2021/2022"), each pointing at a `/wp-content/uploads/2024/01/...`
   path on an internal `192.168.1.124` address (a server misconfiguration
   baked into that response, not a Wayback artifact) — the real
   `www.trabajo.gob.ec` host plus each filename was substituted back in
   and every resulting URL re-verified live via HEAD (HTTP 200,
   `Content-Type: application/pdf`) 2026-09-03.
4. No 2019 (a "No. 3" numbering on the 2022 edition, per RESEARCH.md,
   implies at most a 2020-start series, so no 2019 edition is expected)
   or 2023/2024/2025 edition was found: not on the live page, not in
   either of the two Wayback snapshots that exist for this URL (CDX
   lookup — only Dec 2023 and Jan 2024 were ever crawled), not via the
   site's own WordPress REST search (`/wp-json/wp/v2/search` and
   `/wp-json/wp/v2/media`, queried for "boletin" and "mercado laboral"),
   and not under a handful of filename variants modeled on the two known
   naming patterns ("Boletin-Anual-YYYY...", "BoletinAnualYYYYok.pdf")
   across plausible upload-year folders (all HTTP 404). Absence of
   evidence isn't proof there's a gap here — it's evidence the ministry
   may not have published past the 2022 edition, or files it elsewhere
   this project hasn't found — but nothing further is recoverable with
   the effort reasonable for a source this thin.

Given all of the above, this is a small, hand-verified, hardcoded set —
same rationale as `helpers/inec_client.py`'s `_EXTRA_TOPICS` and
`helpers/sipa_client.py`'s four fixed module pages — rather than a live
scraper of a page that cannot reliably be fetched and would under-count
even when it can be.
"""

from __future__ import annotations

from typing import Any

from helpers.text_utils import strip_accents as _strip

# Confirmed live via HEAD (HTTP 200, Content-Type: application/pdf)
# 2026-09-03. All three sit under the same upload path even though only
# the 2022 file is still linked from the live index page today -- see the
# module docstring for how 2020/2021 were recovered (Wayback Machine,
# Jan 2024 snapshot of that same index page) and re-verified.
_EDICIONES: tuple[dict[str, Any], ...] = (
    {
        "anio": "2020",
        "titulo": "Boletín Estadístico Anual: El Mercado Laboral del Ecuador 2020",
        "url": "https://www.trabajo.gob.ec/wp-content/uploads/2024/01/BoletinAnual2020ok.pdf",
        "formato": "PDF",
        "tamano_bytes": 4078672,
        "ultima_modificacion": "2024-01-02",
        "enlazado_en_pagina_indice": False,
    },
    {
        "anio": "2021",
        "titulo": "Boletín Estadístico Anual: El Mercado Laboral del Ecuador 2021",
        "url": (
            "https://www.trabajo.gob.ec/wp-content/uploads/2024/01/"
            "BoletinAnual_2021_compressed-1.pdf"
        ),
        "formato": "PDF",
        "tamano_bytes": 3883478,
        "ultima_modificacion": "2024-01-02",
        "enlazado_en_pagina_indice": False,
    },
    {
        "anio": "2022",
        "titulo": "Boletín Estadístico Anual: El Mercado Laboral del Ecuador 2022",
        "url": (
            "https://www.trabajo.gob.ec/wp-content/uploads/2024/01/"
            "Boletin-Anual-2022-1_compressed.pdf"
        ),
        "formato": "PDF",
        "tamano_bytes": 4041210,
        "ultima_modificacion": "2024-01-02",
        "enlazado_en_pagina_indice": True,
    },
)

_INDICE_URL = "https://www.trabajo.gob.ec/direccion-de-investigacion-y-estudios-laborales/"


async def search_boletines(query: str = "") -> dict[str, Any]:
    """
    List (optionally filtered) known editions of the Ministerio del
    Trabajo's "Boletín Estadístico Anual: El Mercado Laboral en el
    Ecuador".

    Only 3 editions (2020, 2021, 2022) are known to this client -- see
    the module docstring for why this archive is not a full historical
    series and what was tried to extend it.

    Args:
        query: Free text matched (accent-insensitive) against the
            edition's year, title, or URL, e.g. "2021". Empty returns
            all known editions.
    """
    q = _strip(query)
    matched = [
        e
        for e in _EDICIONES
        if not q
        or q in _strip(e["anio"])
        or q in _strip(e["titulo"])
        or q in _strip(e["url"])
    ]
    return {
        "total": len(matched),
        "total_conocido": len(_EDICIONES),
        "source": (
            "Ministerio del Trabajo — Boletín Estadístico Anual: "
            "El Mercado Laboral en el Ecuador"
        ),
        "url_indice": _INDICE_URL,
        "cobertura_incompleta": True,
        "nota_cobertura": (
            "Solo se confirmaron 3 ediciones (2020-2022). La página índice no "
            "puede recorrerse en vivo (viola HTTP/1.1 con cabeceras "
            "Transfer-Encoding duplicadas) y hoy solo enlaza la edición 2022; "
            "2020/2021 se recuperaron de un snapshot de Wayback Machine de "
            "enero de 2024 y se reverificaron vivos. No se halló ninguna "
            "edición 2023-2025. Ver el docstring del módulo para el detalle."
        ),
        "ediciones": matched,
    }
