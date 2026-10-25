"""Classify live-source smoke responses without hiding server regressions."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SmokeAssessment:
    """One smoke assertion outcome."""

    status: str
    detail: str = ""
    source: str | None = None


_DEGRADED_SOURCES = (
    (
        "datos_abiertos_ckan",
        "datosabiertos.gob.ec",
        "rechazó la conexión (403)",
    ),
    (
        "cenace_tls",
        "cenace.gob.ec",
        "certificate_verify_failed",
    ),
    (
        "sercop_compras_publicas",
        "compraspublicas.gob.ec",
        "fuera de latinoamérica",
    ),
    (
        "censo_ecuador_geoblock",
        "censoecuador.gob.ec",
        "bloqueo geográfico",
    ),
    (
        # Seen 2026-10-08 and 2026-10-10: the ~37 MB directory download on a
        # cold runner outlasts search_companias's inline wait.
        "supercias_directory_cold_start",
        "directorio de supercías",
        "segundo plano",
    ),
    (
        # "no existe todavía" is the first-build wording. The schema-version
        # mismatch message shares the "segundo plano" suffix but is a
        # regression signal (a stale DB that needs rebuilding), not a
        # cold start.
        "supercias_financials_cold_start",
        "base de datos financiera de supercías",
        "no existe todavía",
        "automáticamente en segundo plano",
    ),
    (
        # Seen 2026-10-17 on the runner: both Supercías hosts
        # (mercadodevalores, appscvsmovil) drop the TCP handshake from
        # datacenter IPs (geo_proxy._DEFAULT_GEO_HOSTS), so search_companias,
        # search_auditores and the financials build all end in a
        # ConnectTimeout. A geo block, not a regression.
        "supercias_geoblock",
        "supercias.gob.ec",
        "no se pudo conectar",
    ),
    (
        # Seen 2026-10-23 and 2026-10-24 on the runner: infoMIES never
        # completes the TCP handshake from datacenter IPs (30 s timeout), the
        # same block Render hits. A geo block, not a regression.
        "infomies_geoblock",
        "info.desarrollohumano.gob.ec",
        "no se pudo conectar",
    ),
    (
        # Confirmed live 2026-09-18: search_anda 503'd on one run, then
        # 403'd on the next from a different network -- the same
        # GitHub-Actions-runner geo/bot block already seen on INEC's other
        # censoecuador.gob.ec property, not a transient blip (the generic
        # 5xx check below wouldn't have caught this consistent 403).
        "anda_inec_geoblock",
        "anda.inec.gob.ec",
        "403 forbidden",
    ),
    (
        # Confirmed live 2026-09-19: list_instituciones/search_tramites/
        # search_regulaciones/get_regulacion_info all failed the same way in
        # one run -- gob.ec answered a (likely geo/bot-blocked) request with
        # HTTP 200 and an empty/non-JSON body rather than a 4xx, so
        # resp.json() raised instead of raise_for_status(). See
        # gobec_client._fetch_json, which now wraps that into this message.
        "gobec_geoblock",
        "el portal gob.ec devolvió una respuesta vacía o no válida",
    ),
    (
        # Confirmed live 2026-09-19: www.censoecuador.gob.ec's TLS
        # certificate (notAfter 2026-09-18 23:59:59 GMT, per `openssl
        # s_client`) expired the day before this run -- a genuine upstream
        # outage, not the missing-intermediate case helpers/tls.py's
        # _OS_TRUST_HOST_SUFFIXES retry already handles (that retry still
        # fully verifies the chain, so it fails the same way once the leaf
        # itself is expired).
        "censo_ecuador_tls_expired",
        "censo ecuador",
        "certificate has expired",
    ),
    (
        # Seen 2026-10-11 on the runner: www.superbancos.gob.ec serves a leaf
        # valid until 2027-04 but omits its intermediate, and the verification
        # chain the runner builds ends in an expired certificate. An upstream
        # TLS chain problem, not a regression here.
        "superbancos_tls_chain",
        "superbancos",
        "certificate has expired",
    ),
    (
        # Same host, same missing intermediate; the runner's trust store
        # reports it as an unknown issuer on some runs instead of expired.
        "superbancos_tls_chain",
        "superbancos",
        "unable to get local issuer certificate",
    ),
)

# Sources blocked by country or datacenter IP. Without a LatAm egress
# (ECUADOR_MCP_GEO_PROXY, see docs/GEOBLOCK_PLAN.md) these are expected to
# fail, so the smoke run reports them as skipped rather than degraded.
GEOBLOCKED_SOURCES = frozenset(
    {
        "datos_abiertos_ckan",
        "sercop_compras_publicas",
        "censo_ecuador_geoblock",
        "anda_inec_geoblock",
        "gobec_geoblock",
        "supercias_geoblock",
        "infomies_geoblock",
    }
)

# httpx's own raise_for_status() message format (confirmed against
# httpx._models.Response.raise_for_status): "Server error '503 Service
# Unavailable' for url '<url>'". A 5xx from a known-flaky live source is
# that source misbehaving (down, overloaded, restarting). Confirmed live:
# anda.inec.gob.ec 503'd on 2026-09-18's scheduled run and was unreachable/
# inconsistent (timeout, then 403) minutes later -- a flaky host, not a
# regression in this repo.
_HTTPX_SERVER_ERROR_RE = re.compile(
    r"Server error '5\d\d[^']*' for url 'https?://([^/']+)"
)

# Only hosts already named by a known-degradation entry above get the 5xx
# pass. A 5xx from any other host can be a changed endpoint or a request
# this repo builds wrongly (a 500 on a malformed query), so it stays a
# failure until it is understood and added to _DEGRADED_SOURCES.
_HOST_MARKER_RE = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)+")
_UPSTREAM_5XX_HOSTS = frozenset(
    marker
    for _name, *markers in _DEGRADED_SOURCES
    for marker in markers
    if _HOST_MARKER_RE.fullmatch(marker)
)


def _known_5xx_host(host: str) -> bool:
    host = host.casefold().rsplit(":", 1)[0]
    return any(
        host == known or host.endswith(f".{known}") for known in _UPSTREAM_5XX_HOSTS
    )


def degraded_source(text: str) -> str | None:
    """Return a known external degradation label, never a generic error."""
    normalized = text.casefold()
    for name, *markers in _DEGRADED_SOURCES:
        if all(marker.casefold() in normalized for marker in markers):
            return name
    match = _HTTPX_SERVER_ERROR_RE.search(text)
    if match and _known_5xx_host(match.group(1)):
        return f"upstream_5xx:{match.group(1)}"
    return None


def assess_response(
    text: str, required: list[str], is_error: bool = False
) -> SmokeAssessment:
    """Classify one MCP tool response for the live smoke workflow.

    A known upstream restriction is ``degraded``. Everything else that does
    not meet the assertion is a real smoke failure, so the workflow remains a
    guard against regressions in this server and unexpected source changes.

    ``is_error`` should carry the MCP result's own ``isError`` flag when the
    caller has it. Tool failures raise ``ToolError`` with a per-tool message
    ("Error al buscar datasets: ...", "Error: ...", a bare RuntimeError
    string, ...) that does not reliably start with "Error:" or contain a
    literal ``"error"`` JSON key, so guessing failure from the text alone
    (the pre-``isError`` fallback below, kept for callers that only have
    text) can misclassify a real failure as ``ok`` -- which then crashes a
    caller that expects the text to be parseable JSON.
    """
    source = degraded_source(text)
    if "traceback" in text[:300].casefold():
        return SmokeAssessment("failed", "traceback in response")
    if is_error:
        if source:
            return SmokeAssessment("degraded", text[:240], source)
        return SmokeAssessment("failed", text[:240])
    if required and not any(token.casefold() in text.casefold() for token in required):
        if source:
            return SmokeAssessment("degraded", "required fields unavailable", source)
        return SmokeAssessment(
            "failed", f"none of {required!r} found: {text[:240]}"
        )
    stripped = text.strip()
    if stripped.startswith(("Error:", "ERROR:")) or '"error"' in stripped[:300]:
        if source:
            return SmokeAssessment("degraded", stripped[:240], source)
        return SmokeAssessment("failed", stripped[:240])
    return SmokeAssessment("ok")
