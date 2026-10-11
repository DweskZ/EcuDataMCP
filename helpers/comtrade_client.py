"""Client for the UN Comtrade public *preview* API
(`comtradeapi.un.org/public/v1/preview`), no key. Verified live 2026-10-10
(docs/RESEARCH.md § Trigésimo séptima pasada).

NOT Ecuador-only: bilateral merchandise trade for ~200 reporters; the
reporter defaults to Ecuador (M49 code 218).

Limits of the keyless preview, all observed live:
- at most 500 rows per call (a `cmd` list or all-partner pull can hit it);
- exactly ONE period per call ("Maximum number of periods for preview is 1");
- about one request per 2 s: a faster one gets HTTP 429 "Rate limit is
  exceeded. Try again in 2 seconds.", which `helpers.intl_http` honours with
  a wait and retries;
- descriptions (`reporterDesc`, `cmdDesc`...) come back null, so this client
  reports codes only.
Values are in US dollars (`primaryValue`: FOB for exports, CIF for imports).
"""

from __future__ import annotations

import re
from typing import Any

from helpers.cache import TtlCache
from helpers.intl_http import get_json

_BASE = "https://comtradeapi.un.org/public/v1/preview/C"
ROW_CAP = 500

_data_cache = TtlCache(ttl_seconds=3600.0, max_entries=128)

# Comtrade uses M49 numeric codes, which differ from ISO numeric for a few
# economies (USA 842, India 699, France 251). Common Ecuadorian partners:
PAISES = {
    "ECU": "218", "USA": "842", "CHN": "156", "COL": "170", "PER": "604", "PAN": "591",
    "CHL": "152", "ESP": "724", "ITA": "380", "NLD": "528", "DEU": "276", "RUS": "643",
    "JPN": "392", "BRA": "76", "MEX": "484", "VEN": "862", "ARG": "32", "KOR": "410",
    "IND": "699", "GBR": "826", "FRA": "251", "TUR": "792", "EGY": "818", "VNM": "704",
    "BOL": "68", "WLD": "0", "MUNDO": "0",
}
_FLOWS = {
    "x": "X", "exportaciones": "X", "m": "M", "importaciones": "M",
    "ambos": "X,M", "both": "X,M", "": "X,M",
}
_FLOW_NAMES = {"X": "exportaciones", "M": "importaciones"}
_CODE = re.compile(r"^\d{1,4}$")
_CMD = re.compile(r"^(TOTAL|\d{2}|\d{4}|\d{6})$", re.IGNORECASE)


def _country_code(value: str, name: str) -> str:
    text = value.strip().upper()
    if text in PAISES:
        return PAISES[text]
    if _CODE.match(text):
        return str(int(text))
    raise ValueError(
        f"`{name}` debe ser un código numérico M49 (ej. 842) o ISO3 de la lista: "
        f"{', '.join(k for k in PAISES if k != 'MUNDO')}."
    )


async def get_comercio(
    pais: str = "ECU",
    periodo: str = "",
    socio: str = "0",
    cmd: str = "TOTAL",
    flujo: str = "ambos",
    frecuencia: str = "A",
) -> dict[str, Any]:
    """Merchandise trade of reporter `pais` with partner `socio` for one
    period (YYYY if frecuencia A, YYYYMM if M)."""
    freq = frecuencia.strip().upper() or "A"
    if freq not in ("A", "M"):
        raise ValueError("`frecuencia` debe ser A (anual) o M (mensual).")
    pattern = r"\d{4}" if freq == "A" else r"\d{6}"
    if not re.fullmatch(pattern, periodo.strip()):
        raise ValueError(
            "Comtrade requiere `periodo` de un solo período: "
            + ("AAAA (anual)." if freq == "A" else "AAAAMM (mensual), ej. 202401.")
        )
    flow = _FLOWS.get(flujo.strip().lower())
    if flow is None:
        raise ValueError("`flujo` debe ser X (exportaciones), M (importaciones) o ambos.")
    code = cmd.strip().upper() or "TOTAL"
    if not _CMD.match(code):
        raise ValueError("`cmd` debe ser TOTAL o un código HS de 2, 4 o 6 dígitos (ej. 03 o 0306).")
    reporter = _country_code(pais, "pais")
    partner = _country_code(socio or "0", "socio")
    params = {
        "reporterCode": reporter,
        "period": periodo.strip(),
        "partnerCode": partner,
        "cmdCode": code,
        "flowCode": flow,
    }
    cache_key = (freq, *sorted(params.items()))
    cached = _data_cache.get(cache_key)
    if cached is not None:
        return cached

    payload = await get_json(f"{_BASE}/{freq}/HS", fuente="UN Comtrade", params=params)
    data = (payload or {}).get("data") or []
    rows = [
        {
            "periodo": r.get("period"),
            "flujo": _FLOW_NAMES.get(r.get("flowCode"), r.get("flowCode")),
            "socio_codigo": r.get("partnerCode"),
            "producto_hs": r.get("cmdCode"),
            "valor_usd": r.get("primaryValue"),
            "peso_neto_kg": r.get("netWgt"),
            "cantidad": r.get("qty"),
        }
        for r in data
    ]
    rows.sort(key=lambda r: (r["flujo"] or "", -(r["valor_usd"] or 0)))
    result = {
        "reportero": reporter,
        "frecuencia": freq,
        "total_registros": len(rows),
        "truncado_500": len(rows) >= ROW_CAP,
        "registros": rows,
        "source": "UN Comtrade (preview público)",
        "url_fuente": "https://comtradeplus.un.org/TradeFlow",
    }
    if rows:
        _data_cache.set(cache_key, result)
    return result
