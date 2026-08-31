"""Client for the SRI's public Registro Único de Contribuyentes lookup.

The SRI publishes two unauthenticated pages for an exact RUC lookup:

* the taxpayer's registry record; and
* the registered establishments.

This is a registry lookup, not a way to retrieve an individual's tax returns,
sales, withholdings, or tax payments.  Those details are not exposed by this
public service at the individual-RUC level.

Search by razón social / nombre comercial uses a separate, more modern
unauthenticated JSON REST API (`sri-catastro-sujeto-servicio-internet`)
that backs the "Razón social" tab of https://srienlinea.sri.gob.ec's
current Angular RUC-lookup app -- found by driving that page in a browser
and watching its network calls, since the legacy name-search form at
`/facturacion-internet/consultas/publico/ruc_consulta.jsp` is CAPTCHA-gated
(a visualcaptcha widget) and therefore off-limits here. The modern flow has
no CAPTCHA at all, confirmed with a bare `curl`:

1. `cantidadObtenidaPorRazonSocial?razonSocial=X` -> a match count (capped
   at 100 server-side -- a live query for "BANCO" and for "SA" both
   returned exactly 100, so a count of 100 means "at least 100", not
   necessarily exactly 100).
2. `numerosRucPorRazonSocialToken?razonSocial=X` -> the matching RUC
   numbers (same 100 cap).
3. `obtenerPorNumerosRuc?ruc=A&ruc=B&...` -> full registry records for a
   batch of RUCs in one call -- richer than the HTML-scraped exact-RUC
   lookup above (adds régimen, representantes legales, agente de
   retención, contribuyente fantasma/con transacciones inexistentes).

search_by_razon_social slices step 2's list to max_resultados before the
step-3 batch call, to keep responses agent-sized -- the same "bounded
window, not the whole thing" pattern used elsewhere in this project
(e.g. helpers/bce_indicadores_diarios_client.py).
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Any

import httpx

from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip
from helpers.tls import should_retry_insecure
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

SRI_RUC_INFO_URL = (
    "https://srienlinea.sri.gob.ec/facturacion-internet/consultas/publico/"
    "ruc-datos2.jspa"
)
SRI_RUC_ESTABLECIMIENTOS_URL = (
    "https://srienlinea.sri.gob.ec/facturacion-internet/consultas/publico/"
    "ruc-establec.jspa"
)
SRI_CATASTRO_BASE = "https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente"
_TIMEOUT = 30.0

# The endpoint itself caps matches at 100; this is a further, agent-sized
# cap on how many of those we fetch full detail for and return.
_MAX_RESULTADOS_RAZON_SOCIAL = 25


class _TableRowsParser(HTMLParser):
    """Collect visible table rows without adding a new HTML dependency."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "tr":
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if tag in {"th", "td"} and self._row is not None and self._cell is not None:
            self._row.append(_clean_text(" ".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0 and self._cell is not None:
            self._cell.append(data)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _field_key(label: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", "_", _strip(label)).strip("_").lower()
    return {
        "fecha": "fecha_consulta",
        "razon_social": "razon_social",
        "ruc": "ruc",
        "nombre_comercial": "nombre_comercial",
        "estado_del_contribuyente_en_el_ruc": "estado",
        "clase_de_contribuyente": "clase_contribuyente",
        "tipo_de_contribuyente": "tipo_contribuyente",
        "obligado_a_llevar_contabilidad": "obligado_contabilidad",
        "actividad_economica_principal": "actividad_economica_principal",
        "fecha_de_inicio_de_actividades": "fecha_inicio_actividades",
        "fecha_de_cese_de_actividades": "fecha_cese_actividades",
        "fecha_reinicio_de_actividades": "fecha_reinicio_actividades",
        "fecha_actualizacion": "fecha_actualizacion",
        "categoria_mi_pymes": "categoria_mipymes",
    }.get(normalized)


def _parse_info_page(html: str, ruc: str) -> dict[str, Any] | None:
    parser = _TableRowsParser()
    parser.feed(html)
    data: dict[str, Any] = {"ruc": ruc}
    for row in parser.rows:
        if len(row) < 2:
            continue
        key = _field_key(row[0])
        if key:
            data[key] = row[1] or None

    if not data.get("razon_social"):
        return None
    data["ruc"] = data.get("ruc") or ruc
    return data


def _parse_establishments_page(html: str) -> list[dict[str, str]]:
    parser = _TableRowsParser()
    parser.feed(html)
    establishments: list[dict[str, str]] = []
    for row in parser.rows:
        if len(row) != 4 or not re.fullmatch(r"\d{3}", row[0]):
            continue
        establishments.append(
            {
                "numero": row[0],
                "nombre_comercial": row[1],
                "ubicacion": row[2],
                "estado": row[3],
            }
        )
    return establishments


def _validate_ruc(ruc: str) -> str:
    value = str(ruc).strip()
    if not re.fullmatch(r"\d{13}", value):
        raise ValueError("El RUC debe contener exactamente 13 dígitos.")
    return value


async def _fetch_page(url: str, ruc: str, verify: bool = True) -> str:
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=_TIMEOUT,
        verify=verify,
    ) as session:
        response = await session.get(url, params={"ruc": ruc})
        response.raise_for_status()
        return response.text


async def _fetch_public_page(url: str, ruc: str) -> str:
    try:
        return await _fetch_page(url, ruc)
    except httpx.ConnectError as exc:
        if not should_retry_insecure(exc, url):
            raise
        logger.warning("Falló la verificación TLS para la página pública del SRI")
        return await _fetch_page(url, ruc, verify=False)


async def get_ruc_info(
    ruc: str, include_establecimientos: bool = True
) -> dict[str, Any] | None:
    """Return public SRI registry information for an exact 13-digit RUC."""
    ruc = _validate_ruc(ruc)
    html = await _fetch_public_page(SRI_RUC_INFO_URL, ruc)
    data = _parse_info_page(html, ruc)
    if data is None:
        return None

    data["url_fuente"] = SRI_RUC_INFO_URL
    data["incluye_declaraciones_individuales"] = False
    data["nota_alcance"] = (
        "La consulta pública muestra información registral del RUC; no expone "
        "declaraciones, ventas, retenciones ni pagos tributarios individuales."
    )

    if include_establecimientos:
        establishments_html = await _fetch_public_page(
            SRI_RUC_ESTABLECIMIENTOS_URL, ruc
        )
        data["establecimientos"] = _parse_establishments_page(establishments_html)
        data["url_establecimientos"] = SRI_RUC_ESTABLECIMIENTOS_URL

    return data


async def _fetch_catastro_json(path: str, params: list[tuple[str, str]], verify: bool = True) -> Any:
    url = f"{SRI_CATASTRO_BASE}/{path}"
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=_TIMEOUT,
        verify=verify,
    ) as session:
        response = await session.get(url, params=params)
        response.raise_for_status()
        return response.json()


async def _fetch_catastro_public(path: str, params: list[tuple[str, str]]) -> Any:
    url = f"{SRI_CATASTRO_BASE}/{path}"
    try:
        return await _fetch_catastro_json(path, params)
    except httpx.ConnectError as exc:
        if not should_retry_insecure(exc, url):
            raise
        logger.warning("Falló la verificación TLS para la API pública de catastro del SRI")
        return await _fetch_catastro_json(path, params, verify=False)


def _fecha(value: str | None) -> str | None:
    return value.split(" ")[0] if value else None


def _map_contribuyente(raw: dict[str, Any]) -> dict[str, Any]:
    fechas = raw.get("informacionFechasContribuyente") or {}
    return {
        "ruc": raw.get("numeroRuc"),
        "razon_social": raw.get("razonSocial"),
        "estado": raw.get("estadoContribuyenteRuc"),
        "tipo_contribuyente": raw.get("tipoContribuyente"),
        "regimen": raw.get("regimen"),
        "categoria_mipymes": raw.get("categoria"),
        "actividad_economica_principal": raw.get("actividadEconomicaPrincipal"),
        "obligado_contabilidad": raw.get("obligadoLlevarContabilidad"),
        "agente_retencion": raw.get("agenteRetencion"),
        "contribuyente_especial": raw.get("contribuyenteEspecial"),
        "contribuyente_fantasma": raw.get("contribuyenteFantasma"),
        "transacciones_inexistentes": raw.get("transaccionesInexistente"),
        "motivo_cancelacion_suspension": raw.get("motivoCancelacionSuspension"),
        "fecha_inicio_actividades": _fecha(fechas.get("fechaInicioActividades")),
        "fecha_cese_actividades": _fecha(fechas.get("fechaCese")),
        "fecha_reinicio_actividades": _fecha(fechas.get("fechaReinicioActividades")),
        "fecha_actualizacion": _fecha(fechas.get("fechaActualizacion")),
        "representantes_legales": [
            {"identificacion": r.get("identificacion"), "nombre": r.get("nombre")}
            for r in raw.get("representantesLegales") or []
        ],
    }


def _validate_razon_social(texto: str) -> str:
    value = str(texto).strip()
    if len(value) < 4:
        raise ValueError("El texto de búsqueda debe tener al menos 4 caracteres.")
    return value


async def search_by_razon_social(
    razon_social: str, max_resultados: int = _MAX_RESULTADOS_RAZON_SOCIAL
) -> dict[str, Any]:
    """Search SRI's public taxpayer registry by (partial) razón social /
    nombre comercial -- unlike get_ruc_info, this doesn't require knowing
    the RUC already."""
    texto = _validate_razon_social(razon_social)
    n = max(1, min(max_resultados, 100))

    total = await _fetch_catastro_public("cantidadObtenidaPorRazonSocial", [("razonSocial", texto)])
    rucs = await _fetch_catastro_public("numerosRucPorRazonSocialToken", [("razonSocial", texto)])
    rucs = rucs[:n]

    resultados: list[dict[str, Any]] = []
    if rucs:
        raw = await _fetch_catastro_public("obtenerPorNumerosRuc", [("ruc", r) for r in rucs])
        resultados = [_map_contribuyente(r) for r in raw]

    return {
        "razon_social_buscada": texto,
        "total_reportado": total,
        "resultados": resultados,
        "nota": (
            "El SRI limita esta búsqueda a 100 coincidencias por consulta; "
            "total_reportado=100 puede significar que hay más de 100 "
            "contribuyentes con ese texto, no necesariamente exactamente 100."
            if total >= 100
            else None
        ),
        "url_fuente": f"{SRI_CATASTRO_BASE}/obtenerPorNumerosRuc",
    }
