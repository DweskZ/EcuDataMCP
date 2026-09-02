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
)


def degraded_source(text: str) -> str | None:
    """Return a known external degradation label, never a generic error."""
    normalized = text.casefold()
    for name, *markers in _DEGRADED_SOURCES:
        if all(marker.casefold() in normalized for marker in markers):
            return name
    return None


def assess_response(text: str, required: list[str]) -> SmokeAssessment:
    """Classify one MCP tool response for the live smoke workflow.

    A known upstream restriction is ``degraded``. Everything else that does
    not meet the assertion is a real smoke failure, so the workflow remains a
    guard against regressions in this server and unexpected source changes.
    """
    source = degraded_source(text)
    if "traceback" in text[:300].casefold():
        return SmokeAssessment("failed", "traceback in response")
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
