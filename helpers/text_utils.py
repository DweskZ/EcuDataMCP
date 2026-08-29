"""Shared text-normalization helpers used across search/matching code."""

from __future__ import annotations

from unicodedata import category, normalize


def strip_accents(text: str | None, *, lower: bool = True) -> str:
    """Remove diacritics: inscripción -> inscripcion, cédula -> cedula.

    `lower=True` (the default) also lowercases, for case-insensitive
    matching -- most callers want this. Pass `lower=False` to keep case
    (e.g. when the caller already normalized case itself, or needs it
    preserved for display).
    """
    nfkd = normalize("NFKD", text or "")
    stripped = "".join(c for c in nfkd if category(c) != "Mn")
    return stripped.lower() if lower else stripped
