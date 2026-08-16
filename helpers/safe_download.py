"""SSRF guard for downloading URLs sourced from external, untrusted metadata.

`preview_resource_data` downloads whatever URL a CKAN resource's `url` field
contains -- and that field is set by whoever published or last edited that
dataset on the portal, not by this codebase. A malicious or compromised
publisher account could point it at `http://localhost/...`, an RFC1918
address, a link-local address, or a cloud metadata endpoint
(`169.254.169.254`) and use this server as an SSRF proxy into whatever
network it's deployed on.

`assert_public_url` / `safe_stream` below must be used for any download
whose URL comes from such external metadata. Hardcoded, first-party URLs
defined as module constants elsewhere in this codebase (e.g. Supercías'
own export endpoints) don't need this: they're not attacker-influenceable,
so there's no boundary to guard.

What this does and doesn't cover: this validates the initial URL and every
redirect hop (`follow_redirects=True` alone would happily follow a public
URL's redirect to an internal address), which blocks the straightforward
cases. It does NOT protect against DNS rebinding -- a hostname resolving to
a public IP at validation time and a private one at actual connection time,
a moment later. Closing that gap needs pinning the validated IP and
connecting directly to it, which is a deeper change; flagged here rather
than silently implied as covered.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import httpx

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_REDIRECTS = 5


class UnsafeUrlError(ValueError):
    """A URL was rejected by the SSRF guard: bad scheme, unresolvable host,
    a non-public target IP, or too many redirects."""


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_public_url(url: str) -> None:
    """Raise UnsafeUrlError unless `url` is http(s) and resolves only to public IPs."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"Esquema de URL no permitido: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("URL sin host")

    try:
        addr_infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"No se pudo resolver el host: {host}") from exc
    if not addr_infos:
        raise UnsafeUrlError(f"El host no resolvió a ninguna IP: {host}")

    for info in addr_infos:
        ip = ipaddress.ip_address(info[4][0])
        if not _is_public_ip(ip):
            raise UnsafeUrlError(
                f"El host '{host}' resuelve a una IP no pública ({ip}); "
                "descarga rechazada"
            )


@asynccontextmanager
async def safe_stream(
    session: httpx.AsyncClient,
    url: str,
    max_redirects: int = _MAX_REDIRECTS,
    **kwargs: object,
) -> AsyncIterator[httpx.Response]:
    """Drop-in replacement for `session.stream("GET", url)` that validates
    the URL and every redirect hop before following it.

    Usage matches session.stream() exactly (extra kwargs, e.g. `timeout`,
    are forwarded as-is; `follow_redirects` is not accepted since this
    function owns redirect handling itself):
        async with safe_stream(session, url, timeout=30.0) as resp:
            async for chunk in resp.aiter_bytes(): ...
    """
    current = url
    for hop in range(max_redirects + 1):
        assert_public_url(current)
        async with session.stream(
            "GET", current, follow_redirects=False, **kwargs
        ) as resp:
            if resp.is_redirect:
                if hop == max_redirects:
                    raise UnsafeUrlError(
                        f"Demasiadas redirecciones (más de {max_redirects})"
                    )
                location = resp.headers.get("location")
                if not location:
                    raise UnsafeUrlError("Redirect sin header Location")
                current = str(httpx.URL(current).join(location))
                continue
            yield resp
            return
