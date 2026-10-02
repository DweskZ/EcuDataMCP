"""Optional egress proxy for sources that block traffic from outside LatAm.

Set ECUADOR_MCP_GEO_PROXY (http://, https:// or socks5:// URL) to send
requests to the geoblocked hosts through an egress inside the region. Hosts
not on the list always connect directly. With no proxy set, behavior is
unchanged. See docs/GEOBLOCK_PLAN.md.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

# Confirmed blocked from Render's network on 2026-09-30 (CKAN 403, ANDA 403,
# ARCONEL reportes 504) or documented in docs/RESEARCH.md. www.gob.ec (reset)
# and censoecuador.gob.ec (403) were confirmed from a Canadian home IP on
# 2026-10-02; listed as www.gob.ec, not gob.ec, so the suffix match doesn't
# send every *.gob.ec host through the proxy.
_DEFAULT_GEO_HOSTS = (
    "datosabiertos.gob.ec",
    "www.gob.ec",
    "censoecuador.gob.ec",
    "anda.inec.gob.ec",
    "reportes.arconel.gob.ec",
    "sisdatbi.arconel.gob.ec",
    "compraspublicas.gob.ec",
    "eerssa.gob.ec",
)


def get_geo_proxy() -> str | None:
    value = os.getenv("ECUADOR_MCP_GEO_PROXY", "").strip()
    return value or None


def get_geo_hosts() -> tuple[str, ...]:
    raw = os.getenv("ECUADOR_MCP_GEO_HOSTS", "").strip()
    if not raw:
        return _DEFAULT_GEO_HOSTS
    return tuple(h.strip().lower() for h in raw.split(",") if h.strip())


def proxy_for(url: str) -> str | None:
    """Return the geo proxy URL when ``url`` targets a listed host."""
    proxy = get_geo_proxy()
    if proxy is None:
        return None
    host = (urlsplit(url).hostname or "").lower()
    for listed in get_geo_hosts():
        if host == listed or host.endswith("." + listed):
            return proxy
    return None
