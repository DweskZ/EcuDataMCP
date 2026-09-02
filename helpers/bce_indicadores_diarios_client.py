"""Client for a family of daily/monthly "indicador" widgets published by
BCE outside both BCEData and IEM (`contenido.bce.fin.ec`, the same host
already used for those two, but a separate, undocumented corner of it).

Found 2026-08-31 after being asked to cover Riesgo País specifically:
BCEData only had it as a monthly end-of-period aggregate, for something
BCE itself republishes on every business day. Several pages of
`contenido.bce.fin.ec` (estadisticas-de-publicaciones-generales,
estadisticas-del-sector-medios-y-sistemas-de-pagos,
estadisticas-del-sector-real, estadisticas-del-sector-externo-d) embed a
Highcharts widget per indicator (`data-dd-title="Riesgo País"` etc.),
each widget's own HTML page (`.../indicadores/{Nombre}.html`) declaring a
JS variable naming a plain JSON file with the actual data -- no API key,
no session, confirmed with a bare download. Several widgets share one
file (e.g. Riesgo País and Precio del Oro both live in
datos_formulario.json).

Each JSON file is a flat array of rows shaped like:
    {"Indicador": "Riesgo País", "Código Variable Dinámica": "val_ind_0003",
     "Fecha": "2026-08-28", "Carga": "2026-08-29", "Periodicidad": "D",
     "Valor": "438", "Medida": "Puntos Básicos", "Segmento": "..."}
...except datos_ipc.json (Inflación), which has no "Valor" field at all --
just three parallel series "Mensual"/"Anual"/"Acumulada" (confirmed
against the indicator's own widget, which charts all three, not one
"the" value). get_indicador_diario handles both shapes: one value field
comes back as {"fecha", "valor"}; anything else comes back as
{"fecha", "valores": {...}} with every non-metadata field included,
rather than assuming "Valor" and silently returning None where it
doesn't exist.

"Código Variable Dinámica" is only unique WITHIN one file, not across
files (val_ind_0001 means "Precio Petróleo (WTI)" in datos_diarios.json
but "Sistema de Pagos Interbancarios" in datos_pagos.json) -- so the
catalog here is discovered from each file's own rows (Indicador/
Periodicidad/Medida/date range), not a hardcoded name-to-code mapping.
Genuinely daily series confirmed live: Riesgo País (2004-present),
Precio del Oro (1999-present), Petróleo WTI, Índice Dow Jones, Tasa SOFR,
Tasa LIBOR (discontinued 2024), sovereign bonds Ecuador 2030/2035/2040,
and Producción Petrolera Nacional. The rest (sistemas de pago, inflación,
desempleo, PIB, confianza del consumidor) are monthly/quarterly/annual
and likely duplicate BCEData, but come from a single clean file here.

2026-09-02: swept the rest of the "Estadísticas" mega-menu (only 4 of 7
top-level sections had been checked before). Two sections not checked at
all (estadisticas-del-sector-monetario-d-2, estadisticas-del-sector-
fiscal) turned out to have the widget too, plus estadisticas-del-sector-
externo-d -- already "checked" -- had 7 more widgets on it that the
original pass missed by only following ones that shared a file with
already-known indicators. 4 new files:
  - datos.json ("view_ind_monetario"): Reservas Internacionales, Liquidez
    Total M2, Crédito al Sector Privado (empresas y hogares), Captaciones
    OSD (Total), Tasa Activa/Pasiva Referencial -- monthly,
    2000/2003/2015-present.
  - datos_fiscales.json ("view_ind_fiscales"): Total Ingresos SPNF, Total
    Erogaciones SPNF, Resultado Global SPNF (% del PIB), Saldo Deuda
    Pública Interna -- monthly, 2000-present.
  - datos_bpa.json ("view_ind_externo_bpa"): Cuenta Corriente, Remesas de
    Trabajadores Recibidas (both quarterly, 2016-present), Índice Tipo de
    Cambio Efectivo Real (monthly, 1995-present).
  - datos_cxt.json ("view_ind_externo_cxt"): Saldo Balanza Comercial,
    Balanza Comercial no Petrolera, Exportaciones de Bienes, Importaciones
    de Bienes -- monthly, 1990-present. Uses "Código Variable Dinámica"
    like the original 9 files, not "id_serie".
Verified complete: contenido.bce.fin.ec's own homepage aggregates every
section's widgets in one place (40 distinct `data-dd-title` values as of
this sweep) -- every one of the 40 now resolves to a file in _ARCHIVOS.

Series can run into the thousands of rows (Riesgo País: 7369+) --
get_indicador_diario never returns the full series, only a bounded
window (most recent N observations, or an explicit date range), plus the
series' full date range as metadata so an agent knows what it's not
seeing.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://contenido.bce.fin.ec/wp-content/uploads/ESTADISTICAS-ECONOMICAS/indicadores"

# Every file found live sharing this widget infrastructure. Order matters
# only for list_indicadores' output order (grouped by file).
#
# datos.json, datos_fiscales.json, and datos_bpa.json (found 2026-09-02,
# see module docstring) are a newer generation of this same widget: same
# per-indicator HTML page pointing at a plain JSON file, but the JSON rows
# use "id_serie" (an int) instead of "Código Variable Dinámica", and add a
# "Grupo" field. datos_cxt.json (also found 2026-09-02) uses the original
# "Código Variable Dinámica" shape. See _codigo() below for how both
# shapes are read through one interface.
_ARCHIVOS: list[str] = [
    "datos_formulario.json",
    "datos_diarios.json",
    "datos_bonos_soberanos.json",
    "datos_pagos.json",
    "datos_ipc.json",
    "datos_hid.json",
    "datos_tes.json",
    "datos_icc.json",
    "datos_cna.json",
    "datos.json",
    "datos_fiscales.json",
    "datos_bpa.json",
    "datos_cxt.json",
]
_ARCHIVOS_SET = set(_ARCHIVOS)

_MAX_VENTANA = 366  # a year of daily data -- keeps responses agent-sized

# Every non-value field seen across all 9 files -- used to find the actual
# value column(s) generically instead of assuming every file uses "Valor".
# datos_ipc.json (Inflación) doesn't: it has no "Valor" at all, only three
# parallel series "Mensual"/"Anual"/"Acumulada" (confirmed against the
# indicator's own widget JS, which charts all three as separate lines --
# there's no single "the" value to pick). Blindly reading row["Valor"]
# there silently returned None for every single observation; caught by
# checking this file's actual field set instead of trusting the 8-file
# pattern to hold universally.
_METADATA_FIELDS = {
    "Indicador",
    "Código Variable Dinámica",
    "Fecha",
    "Carga",
    "Periodicidad",
    "Medida",
    "Segmento",
    "Estado",
    "Sector",
    "Grupo",
    "id_serie",
}


def _codigo(row: dict[str, Any]) -> str:
    """Row-level series identifier. "Código Variable Dinámica" in the
    original 9 files; "id_serie" (an int) in datos.json/datos_fiscales.json,
    which have no "Código Variable Dinámica" field at all. Normalized to
    str so callers never need to know which key a given file uses."""
    codigo = row.get("Código Variable Dinámica")
    if codigo is not None:
        return codigo
    return str(row.get("id_serie"))


def _datapoint(row: dict[str, Any]) -> dict[str, Any]:
    valores = {k: v for k, v in row.items() if k not in _METADATA_FIELDS}
    if list(valores.keys()) == ["Valor"]:
        return {"fecha": row["Fecha"], "valor": valores["Valor"]}
    return {"fecha": row["Fecha"], "valores": valores}

# Files change at most once a day (some less often); cache accordingly.
_files_cache = TtlCache(ttl_seconds=21600.0, max_entries=len(_ARCHIVOS))
_fetch_lock = asyncio.Lock()


async def _get_archivo(archivo: str) -> list[dict[str, Any]]:
    if archivo not in _ARCHIVOS_SET:
        raise ValueError(f"Archivo '{archivo}' no reconocido. Válidos: {', '.join(_ARCHIVOS)}")

    cached = _files_cache.get(archivo)
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _files_cache.get(archivo)
        if cached is not None:
            return cached

        logger.info("Descargando archivo de indicadores BCE: %s", archivo)
        content, truncated = await download_bytes(f"{_BASE}/{archivo}")
        if truncated:
            raise ValueError(f"El archivo {archivo} superó el límite de descarga.")
        data = json.loads(content.decode("utf-8"))
        # The top-level key varies by file (view_ind_formulario,
        # view_ind_generales, view_ind_pagos) -- there is always exactly
        # one, so take it positionally instead of hardcoding every name.
        rows = next(iter(data.values())) if data else []
        if rows:
            _files_cache.set(archivo, rows)
        return rows


def list_archivos() -> list[str]:
    """The fixed set of known indicator files."""
    return list(_ARCHIVOS)


async def list_indicadores() -> list[dict[str, Any]]:
    """Every indicator found across all known files, discovered from the
    data itself (name, periodicity, unit, full date range, row count) --
    not a hardcoded catalog, since a code's meaning depends on which file
    it came from."""
    results = await asyncio.gather(*(_get_archivo(a) for a in _ARCHIVOS), return_exceptions=True)

    catalog: list[dict[str, Any]] = []
    for archivo, rows_or_exc in zip(_ARCHIVOS, results):
        if isinstance(rows_or_exc, BaseException):
            logger.warning("No se pudo leer %s: %s", archivo, rows_or_exc)
            continue
        by_codigo: dict[str, dict[str, Any]] = {}
        for r in rows_or_exc:
            codigo = _codigo(r)
            fecha = r.get("Fecha")
            entry = by_codigo.get(codigo)
            if entry is None:
                by_codigo[codigo] = {
                    "archivo": archivo,
                    "codigo": codigo,
                    "indicador": r.get("Indicador"),
                    "periodicidad": r.get("Periodicidad"),
                    "unidad": r.get("Medida"),
                    "fecha_desde": fecha,
                    "fecha_hasta": fecha,
                    "n_datos": 1,
                }
            else:
                entry["fecha_desde"] = min(entry["fecha_desde"], fecha)
                entry["fecha_hasta"] = max(entry["fecha_hasta"], fecha)
                entry["n_datos"] += 1
        catalog.extend(by_codigo.values())
    return catalog


async def get_indicador_diario(
    archivo: str,
    codigo: str,
    ultimos_n: int = 30,
    desde: str | None = None,
    hasta: str | None = None,
) -> dict[str, Any]:
    """
    Fetch one indicator's time series, bounded to a window -- either the
    most recent N observations or an explicit [desde, hasta] date range.

    Args:
        archivo: A file name from list_archivos().
        codigo: A "Código Variable Dinámica" from list_indicadores() for
            that same archivo (codes are only unique within one file).
        ultimos_n: Most recent N observations to return when desde/hasta
            are not given. Capped at 366 (a year of daily data).
        desde: Optional start date (YYYY-MM-DD, inclusive).
        hasta: Optional end date (YYYY-MM-DD, inclusive).
    """
    rows = await _get_archivo(archivo)
    matching = [r for r in rows if _codigo(r) == codigo]
    if not matching:
        raise ValueError(
            f"Código '{codigo}' no encontrado en '{archivo}'. "
            "Usa list_bce_indicadores_diarios para ver los códigos válidos."
        )
    matching.sort(key=lambda r: r["Fecha"])

    if desde or hasta:
        ventana = [r for r in matching if (not desde or r["Fecha"] >= desde) and (not hasta or r["Fecha"] <= hasta)]
        if len(ventana) > _MAX_VENTANA:
            ventana = ventana[-_MAX_VENTANA:]
    else:
        n = max(1, min(ultimos_n, _MAX_VENTANA))
        ventana = matching[-n:]

    first, last = matching[0], matching[-1]
    return {
        "archivo": archivo,
        "codigo": codigo,
        "indicador": first.get("Indicador"),
        "periodicidad": first.get("Periodicidad"),
        "unidad": first.get("Medida"),
        "rango_completo": {"desde": first["Fecha"], "hasta": last["Fecha"], "n_datos": len(matching)},
        "datos": [_datapoint(r) for r in ventana],
    }
