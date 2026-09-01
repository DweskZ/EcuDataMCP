"""Conservative label-based comparison between BCEData and IEM catalogs."""

from __future__ import annotations

import re
from typing import Any

from helpers.text_utils import strip_accents

_STOPWORDS = {
    "al", "de", "del", "el", "en", "la", "las", "los", "por", "para",
    "y", "e", "un", "una", "uno", "con", "sin", "segun", "desde", "hasta",
}
_GENERIC = {
    "indicador", "indicadores", "indice", "indices", "estadistica", "estadisticas",
    "mensual", "trimestral", "anual", "nacional", "ecuador", "ecuatoriano",
    "ecuatoriana", "serie", "cuadro", "tabla", "total",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(value: Any) -> set[str]:
    text = strip_accents(str(value or "")).lower()
    return {
        token
        for token in _TOKEN_RE.findall(text)
        if token not in _STOPWORDS and len(token) > 1
    }


def _candidate_tokens(*values: Any) -> set[str]:
    tokens = set().union(*(_tokens(value) for value in values))
    return tokens - _GENERIC


def _score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = left & right
    return len(overlap) / len(left | right)


def _bce_candidates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for group in snapshot.get("grupos") or []:
        if not isinstance(group, dict) or not group.get("bundle_ok", True):
            continue
        context = {
            "id_grupo": group.get("id_grupo"),
            "grupo": group.get("descripcion", ""),
            "nombre": group.get("nombre", ""),
            "frecuencias": group.get("frecuencias") or [],
            "unidades": group.get("unidades") or {},
            "rango": group.get("rango") or {},
        }
        group_label = group.get("nombre") or group.get("descripcion") or ""
        candidates.append(
            {
                **context,
                "tipo": "grupo",
                "etiqueta": group_label,
                "tokens": _candidate_tokens(
                    group.get("descripcion"), group.get("nombre"), group.get("seccion")
                ),
            }
        )
        for series in group.get("series") or []:
            candidates.append(
                {
                    **context,
                    "tipo": "serie",
                    "etiqueta": series,
                    "tokens": _candidate_tokens(
                        series, group.get("descripcion"), group.get("nombre")
                    ),
                }
            )
    return candidates


def build_equivalence_map(
    bce_snapshot: dict[str, Any], iem_catalog: dict[str, Any]
) -> dict[str, Any]:
    """Return cautious candidate overlaps and explicit source-only entries.

    Titles alone cannot establish that two series have the same definition.
    Every match therefore carries the token overlap score and a review label;
    values, units, revisions and coverage still need analyst confirmation.
    """
    bce = _bce_candidates(bce_snapshot)
    iem = [item for item in iem_catalog.get("tablas") or [] if isinstance(item, dict)]
    matches: list[dict[str, Any]] = []
    matched_bce: set[tuple[str, str]] = set()

    for table in iem:
        table_tokens = _candidate_tokens(table.get("titulo"), table.get("seccion"))
        ranked = sorted(
            ((_score(table_tokens, candidate["tokens"]), candidate) for candidate in bce),
            key=lambda item: item[0],
            reverse=True,
        )
        score, candidate = ranked[0] if ranked else (0.0, None)
        if candidate is None or score < 0.25:
            continue
        key = (str(candidate.get("id_grupo")), candidate["etiqueta"])
        matched_bce.add(key)
        if score >= 0.60:
            relation = "posible_duplicado_o_ampliacion"
        else:
            relation = "posible_traslape"
        matches.append(
            {
                "iem": {
                    key: table.get(key)
                    for key in ("table_id", "titulo", "seccion", "url", "boletin_numero")
                },
                "bcedata": {
                    key: candidate.get(key)
                    for key in (
                        "id_grupo", "tipo", "etiqueta", "grupo", "frecuencias", "unidades", "rango"
                    )
                },
                "puntuacion_etiquetas": round(score, 3),
                "relacion": relation,
                "advertencia": (
                    "Candidato generado por etiquetas; confirmar definición, "
                    "unidad, frecuencia, cobertura y revisión antes de combinar."
                ),
            }
        )

    matched_iem_ids = {str(item["iem"].get("table_id")) for item in matches}
    iem_only = [
        {
            key: table.get(key)
            for key in ("table_id", "titulo", "seccion", "url", "boletin_numero")
        }
        for table in iem
        if str(table.get("table_id")) not in matched_iem_ids
    ]
    bce_only = [
        {
            key: candidate.get(key)
            for key in ("id_grupo", "tipo", "etiqueta", "grupo", "frecuencias", "unidades", "rango")
        }
        for candidate in bce
        if (str(candidate.get("id_grupo")), candidate["etiqueta"]) not in matched_bce
    ]
    return {
        "metodo": "traslape de etiquetas normalizadas; no sustituye revisión metodológica",
        "bcedata_candidatos": len(bce),
        "iem_tablas": len(iem),
        "equivalencias_candidatas": matches,
        "iem_solo_por_etiquetas": iem_only,
        "bcedata_solo_por_etiquetas": bce_only,
        "nota": (
            "Una coincidencia de título no prueba igualdad. Revisar valores, "
            "unidad, frecuencia, fecha de corte y revisión en ambas fuentes."
        ),
    }
