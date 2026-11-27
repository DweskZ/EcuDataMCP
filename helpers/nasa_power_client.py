"""NASA POWER: daily and monthly climate at a point.

NASA's POWER project (https://power.larc.nasa.gov) serves meteorology and solar
data computed from satellite observations and weather models (MERRA-2 and
GEOS-IT), on a global grid, free and without a key. Checked live 2026-11-24:

- `/api/temporal/daily/point` returns one value per day from 1981-01-01 to a
  few days before today (the last real day was 2026-11-20 on 2026-11-24).
  Days after that come back with HTTP 200 and the fill value -999, not as an
  error. `header.sources` lists the products behind the requested days:
  `MERRA2` up to its latest complete month and `GEOSIT` (a near-real-time run,
  provisional) for the days after it. Checked 2026-11-27: a range ending
  2026-10-31 named only MERRA2, one ending 2026-11-01 named both, and at the
  Quito point the daily rain went from 4.9 mm on 2026-10-31 to 40.6 mm on
  2026-11-01 while Open-Meteo showed no step. GEOS-IT gives far more rain than
  MERRA-2 in Ecuador, so `_GEOSIT_NOTE` warns about it.
- `/api/temporal/monthly/point` takes whole years (start=2023&end=2024) and
  adds a 13th "month" per year (202313) that is the annual mean; it is
  dropped here. Monthly responses name `MERRA2`.
- A start date before 1981 or an unknown parameter answers HTTP 422 with the
  reason in `messages`.

The point is a grid cell of tens of kilometres, not a weather station, so
values describe the region around the coordinates: a mountain canton's valley
floor and its páramo share a cell. A canton is queried at its polygon centroid
(helpers/geo_data.canton_centroide), which can be offshore for a coastal canton.
"""

from __future__ import annotations

import calendar
import json
import logging
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.ecuador_time import today_ecuador
from helpers.logging import MAIN_LOGGER_NAME

logger = logging.getLogger(MAIN_LOGGER_NAME)

_API = "https://power.larc.nasa.gov/api/temporal"
_PORTAL = "https://power.larc.nasa.gov/"

_NOTA = (
    "Valores de una celda de rejilla de satélite y modelo (decenas de km), no de una "
    "estación meteorológica: sirven para tendencia y contraste regional, no para el "
    "punto exacto. Los días recientes pueden faltar: NASA publica con unos días de rezago."
)

# Seen 2026-11-24 to 11-27. On the 24th the Guayaquil cell's October rain averaged
# 21 mm/day and Quito showed tens of mm a day from October; by the 27th a range
# ending 31 October named only MERRA2 and the same October averaged 8 mm/day in
# Guayaquil and 2.75 in Quito. November, still GEOS-IT, kept 29 and 23 mm/day
# (Open-Meteo: 10 at Quito, with no step on 1 November).
_GEOSIT_NOTE = (
    "Los días más recientes (`fuentes_datos` incluye GEOSIT) son provisionales: NASA los "
    "calcula con GEOS-IT hasta que llega MERRA-2 y entonces los reemplaza. En Ecuador "
    "GEOS-IT da mucha más lluvia: el 1 de noviembre de 2026 la lluvia diaria de la celda de "
    "Quito pasó de 4,9 a 40,6 mm sin que Open-Meteo registrara salto alguno, y la de octubre "
    "en la celda de Guayaquil figuraba con 21 mm/día el 24 de noviembre y con 8 mm/día el 27, "
    "ya con MERRA-2. No compares esos días con los anteriores ni los tomes como un episodio "
    "sin otra fuente."
)

# clave -> (POWER parameter, unit, name). The units are the ones the API
# returns for community=AG.
VARIABLES: dict[str, tuple[str, str, str]] = {
    "lluvia": ("PRECTOTCORR", "mm/día", "Precipitación corregida"),
    "temperatura": ("T2M", "°C", "Temperatura a 2 m (media)"),
    "temp_max": ("T2M_MAX", "°C", "Temperatura a 2 m (máxima)"),
    "temp_min": ("T2M_MIN", "°C", "Temperatura a 2 m (mínima)"),
    "humedad": ("RH2M", "%", "Humedad relativa a 2 m"),
    "viento": ("WS2M", "m/s", "Velocidad del viento a 2 m"),
    "radiacion": ("ALLSKY_SFC_SW_DWN", "MJ/m²/día", "Radiación solar de onda corta en superficie"),
}

FIRST_DATE = date(1981, 1, 1)
MAX_DAILY_DAYS = 366
_FILL_VALUE = -999.0

_cache = TtlCache(ttl_seconds=21600.0, max_entries=128, persist="nasa_power")


def parse_date(value: str, *, end: bool) -> date:
    """AAAA, AAAA-MM or AAAA-MM-DD to a date; a year or month expands to its last day when `end`."""
    text = value.strip().replace("-", "")
    try:
        year = int(text[:4])
        if len(text) == 4:
            month = 12 if end else 1
            day = calendar.monthrange(year, month)[1] if end else 1
        elif len(text) == 6:
            month = int(text[4:6])
            day = calendar.monthrange(year, month)[1] if end else 1
        elif len(text) == 8:
            month, day = int(text[4:6]), int(text[6:8])
        else:
            raise ValueError(value)
        return date(year, month, day)
    except ValueError as exc:
        raise ValueError(
            f"Fecha '{value}' no válida; usa AAAA, AAAA-MM o AAAA-MM-DD."
        ) from exc


def resolve_period(desde: str, hasta: str, frecuencia: str) -> tuple[date, date]:
    """The requested period with defaults filled in and `hasta` held to today."""
    today = today_ecuador()
    stop = min(parse_date(hasta, end=True), today) if hasta.strip() else today
    if desde.strip():
        start = parse_date(desde, end=False)
    elif frecuencia == "diaria":
        start = stop - timedelta(days=29)
    else:
        start = date(today.year - 2, 1, 1)
    if start < FIRST_DATE:
        raise ValueError("NASA POWER empieza el 1981-01-01; usa un `desde` desde 1981.")
    if start > stop:
        raise ValueError(f"`desde` ({start}) es posterior a `hasta` ({stop}).")
    if frecuencia == "diaria" and (stop - start).days + 1 > MAX_DAILY_DAYS:
        raise ValueError(
            f"La serie diaria admite como máximo {MAX_DAILY_DAYS} días por consulta; "
            "acota con desde/hasta o usa frecuencia='mensual' para períodos largos."
        )
    return start, stop


def parse_variables(variables: str) -> list[str]:
    claves = [v.strip().lower() for v in variables.replace(";", ",").split(",") if v.strip()]
    claves = list(dict.fromkeys(claves))
    unknown = [v for v in claves if v not in VARIABLES]
    if unknown or not claves:
        raise ValueError(
            f"Variable(s) no válidas: {', '.join(unknown) or 'ninguna indicada'}. "
            f"Disponibles: {', '.join(VARIABLES)}."
        )
    return claves


def _value(raw: Any) -> float | None:
    if raw is None or raw == _FILL_VALUE:
        return None
    return float(raw)


def build_rows(
    parameter: dict[str, dict[str, float]],
    claves: list[str],
    frecuencia: str,
    start: date,
    stop: date,
) -> list[dict[str, Any]]:
    """One row per day or month inside [start, stop], fill values as None, trailing empty rows dropped."""
    key_len = 8 if frecuencia == "diaria" else 6
    keys = sorted(
        {
            k
            for series in parameter.values()
            for k in series
            if len(k) == key_len and (frecuencia == "diaria" or k[4:6] != "13")
        }
    )
    rows = []
    for key in keys:
        year, month = int(key[:4]), int(key[4:6])
        day = int(key[6:8]) if frecuencia == "diaria" else 1
        period_start = date(year, month, day)
        period_end = date(year, month, day) if frecuencia == "diaria" else date(
            year, month, calendar.monthrange(year, month)[1]
        )
        if period_end < start or period_start > stop:
            continue
        label = f"{key[:4]}-{key[4:6]}-{key[6:8]}" if frecuencia == "diaria" else f"{key[:4]}-{key[4:6]}"
        row: dict[str, Any] = {"periodo": label}
        for clave in claves:
            row[clave] = _value(parameter.get(VARIABLES[clave][0], {}).get(key))
        rows.append(row)
    while rows and all(rows[-1][c] is None for c in claves):
        rows.pop()
    return rows


def summarize(rows: list[dict[str, Any]], claves: list[str], frecuencia: str) -> dict[str, Any]:
    """Mean, minimum and maximum per variable over the rows with a value; rain also gets its total in mm."""
    summary: dict[str, Any] = {}
    for clave in claves:
        values = [r[clave] for r in rows if r[clave] is not None]
        if not values:
            continue
        item: dict[str, Any] = {
            "unidad": VARIABLES[clave][1],
            "periodos_con_dato": len(values),
            "media": round(sum(values) / len(values), 2),
            "minimo": min(values),
            "maximo": max(values),
        }
        if clave == "lluvia":
            if frecuencia == "diaria":
                item["acumulado_mm"] = round(sum(values), 1)
            else:
                days = [
                    calendar.monthrange(int(r["periodo"][:4]), int(r["periodo"][5:7]))[1]
                    for r in rows
                    if r["lluvia"] is not None
                ]
                item["acumulado_mm"] = round(sum(v * d for v, d in zip(values, days, strict=True)), 1)
        summary[clave] = item
    return summary


def _explain_error(raw: bytes) -> str:
    try:
        messages = json.loads(raw.decode("utf-8", errors="replace")).get("messages")
    except (json.JSONDecodeError, AttributeError):
        messages = None
    if isinstance(messages, list) and messages:
        return "; ".join(str(m) for m in messages)
    return raw.decode("utf-8", errors="replace")[:200]


async def _fetch_fresh(url: str) -> dict[str, Any]:
    cached = _cache.get(url)
    if cached is not None:
        return cached
    raw, truncated = await download_bytes(url, raise_for_status=frozenset({422}))
    if truncated:
        raise ValueError("La respuesta de NASA POWER superó el límite de descarga; acota el período.")
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"NASA POWER no devolvió JSON: {_explain_error(raw)}") from exc
    if not isinstance(payload, dict) or "properties" not in payload:
        raise ValueError(f"NASA POWER rechazó la consulta: {_explain_error(raw)}")
    _cache.set(url, payload)
    return payload


async def _fetch(url: str) -> dict[str, Any]:
    """Fresh fetch, or the last good copy when the source fails (see TtlCache.serve_stale)."""
    try:
        return await _fetch_fresh(url)
    except Exception as exc:
        # A 422 is the source answering "no": serving an old copy would hide it.
        if isinstance(exc, ValueError):
            raise
        stale = _cache.serve_stale(url, exc)
        if stale is None:
            raise
        return stale


async def get_clima(
    latitud: float,
    longitud: float,
    desde: str = "",
    hasta: str = "",
    frecuencia: str = "mensual",
    variables: str = "lluvia,temperatura",
) -> dict[str, Any]:
    """Daily or monthly values of the chosen variables at a point, with a summary."""
    if not -90 <= latitud <= 90 or not -180 <= longitud <= 180:
        raise ValueError("Coordenadas fuera de rango: latitud -90 a 90, longitud -180 a 180.")
    if frecuencia not in ("diaria", "mensual"):
        raise ValueError("`frecuencia` debe ser 'diaria' o 'mensual'.")
    claves = parse_variables(variables)
    start, stop = resolve_period(desde, hasta, frecuencia)

    daily = frecuencia == "diaria"
    query = {
        "parameters": ",".join(VARIABLES[c][0] for c in claves),
        "community": "AG",
        "longitude": longitud,
        "latitude": latitud,
        "start": start.strftime("%Y%m%d") if daily else start.year,
        "end": stop.strftime("%Y%m%d") if daily else stop.year,
        "format": "JSON",
    }
    url = f"{_API}/{'daily' if daily else 'monthly'}/point?" + urlencode(query)
    logger.info("Consultando NASA POWER %s en %.3f,%.3f (%s a %s)", frecuencia, latitud, longitud, start, stop)
    payload = await _fetch(url)

    parameter = (payload.get("properties") or {}).get("parameter") or {}
    rows = build_rows(parameter, claves, frecuencia, start, stop)
    coordinates = (payload.get("geometry") or {}).get("coordinates") or []
    last = rows[-1]["periodo"] if rows else None
    sources = (payload.get("header") or {}).get("sources")
    nota = _NOTA
    if daily and "lluvia" in claves and "GEOSIT" in (sources or []):
        nota = f"{_NOTA} {_GEOSIT_NOTE}"
    return {
        "source": "NASA POWER (Prediction Of Worldwide Energy Resources)",
        "url_fuente": _PORTAL,
        "punto": {
            "latitud": latitud,
            "longitud": longitud,
            "elevacion_m": coordinates[2] if len(coordinates) > 2 else None,
        },
        "frecuencia": frecuencia,
        "desde": start.isoformat(),
        "hasta": stop.isoformat(),
        "ultimo_periodo_con_dato": last,
        "variables": [
            {"clave": c, "parametro": VARIABLES[c][0], "nombre": VARIABLES[c][2], "unidad": VARIABLES[c][1]}
            for c in claves
        ],
        "total_registros": len(rows),
        "registros": rows,
        "resumen": summarize(rows, claves, frecuencia),
        "fuentes_datos": sources,
        "nota": nota,
        "url_consulta": url,
        "metadatos": {"fecha_corte": last},
    }
