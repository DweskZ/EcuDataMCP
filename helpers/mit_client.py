"""MIT (Ministerio de Infraestructura y Tecnología, formerly MTOP): the
daily state-road status report.

The ministry posts one "Informe Red Vial Estatal" PDF a day (closed roads,
one-lane passage and controlled passage by province, ~10 text pages),
linked from the home-page banner as
`wp-content/uploads/downloads/YYYY/MM/RVE_{DÍA}{DD}{MES}.pdf`. Earlier
days' files are taken down (404 when checked 2026-11-07), so this is a
current snapshot, not a series; read it with read_pdf. Traffic counts,
tolls and the road-network GIS are not published openly (their hosts fail
DNS/TLS or answer 503), and the housing portal API needs a login.
"""

from __future__ import annotations

import re
from typing import Any

from helpers.csv_reader import _decode_text, download_bytes

_HOME_URL = "https://www.mit.gob.ec/"
_RVE_RE = re.compile(
    r'href="(https?://www\.mit\.gob\.ec/wp-content/uploads/downloads/(\d{4})/(\d{2})/RVE_([A-Z]{3})(\d{1,2})([A-Z]{3})[^"]*\.pdf)"',
    re.IGNORECASE,
)


def parse_home(page: str) -> list[dict[str, Any]]:
    """The road-status PDF(s) linked from the MIT home page."""
    out = []
    seen: set[str] = set()
    for url, year, month, _dow, day, mon in _RVE_RE.findall(page):
        if url in seen:
            continue
        seen.add(url)
        out.append(
            {
                "titulo": f"Informe Red Vial Estatal {int(day):02d} {mon.upper()} {year}",
                "url": url.replace("http://", "https://", 1),
                "formato": "PDF",
                "fecha": f"{year}-{month}-{int(day):02d}",
            }
        )
    return out


async def search_estado_vias(query: str = "") -> dict[str, Any]:
    raw, truncated = await download_bytes(_HOME_URL)
    if truncated:
        raise ValueError("La portada de mit.gob.ec superó el límite de descarga.")
    archivos = parse_home(_decode_text(raw))
    return {
        "source": "MIT — Informe diario de la Red Vial Estatal",
        "url_fuente": _HOME_URL,
        "nota": (
            "Solo el informe del día: vías cerradas, con paso a un carril y con paso "
            "controlado por provincia. Los días anteriores se retiran del sitio. Léelo "
            "con read_pdf."
            if archivos
            else "La portada no enlaza hoy un informe RVE; reintenta más tarde."
        ),
        "archivos": archivos,
    }
