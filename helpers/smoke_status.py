"""Classify live-source smoke responses without hiding server regressions."""

from __future__ import annotations

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
)


def degraded_source(text: str) -> str | None:
    """Return a known external degradation label, never a generic error."""
    normalized = text.casefold()
    for name, *markers in _DEGRADED_SOURCES:
        if all(marker.casefold() in normalized for marker in markers):
            return name
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
