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
        "supercias_financials_cold_start",
        "base de datos financiera de supercías",
        "automáticamente en segundo plano",
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
)

# httpx's own raise_for_status() message format (confirmed against
# httpx._models.Response.raise_for_status): "Server error '503 Service
# Unavailable' for url '<url>'". A 5xx is by definition the live source
# itself misbehaving (down, overloaded, restarting) -- never something our
# request shape caused -- so this is a generic, host-agnostic degradation
# check rather than one more hardcoded tuple per source. Confirmed live:
# anda.inec.gob.ec 503'd on 2026-09-18's scheduled run and was unreachable/
# inconsistent (timeout, then 403) minutes later -- a flaky host, not a
# regression in this repo.
_HTTPX_SERVER_ERROR_RE = re.compile(
    r"Server error '5\d\d[^']*' for url 'https?://([^/']+)"
)


def degraded_source(text: str) -> str | None:
    """Return a known external degradation label, never a generic error."""
    normalized = text.casefold()
    for name, *markers in _DEGRADED_SOURCES:
        if all(marker.casefold() in normalized for marker in markers):
            return name
    match = _HTTPX_SERVER_ERROR_RE.search(text)
    if match:
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
