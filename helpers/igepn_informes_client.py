"""Client for the IG-EPN "Búsqueda de Informes" archive
(https://www.igepn.edu.ec/servicios/busqueda-informes), a JSF/PrimeFaces
app served from a separate subdomain (`informes.igepn.edu.ec`). Distinct
from `igepn_client.py`, which reads the live earthquake-catalog CSV feed:
this one searches the PDF report archive (daily/weekly/special seismic
bulletins, volcanic "IG Al Instante" alerts, annual reports, etc.).

Unlike every other scraper in this project, there is no stable per-document
URL to hand off to `read_pdf`/`download_resource` -- each report is only
reachable via a session-bound PrimeFaces AJAX flow:

1. GET the page to obtain a session cookie and the initial
   `javax.faces.ViewState` token (server-side state saving -- the token is
   an opaque key into state held on the server for this session, not a
   value we compute).
2. POST an AJAX-style submit of the "Buscar" button (`form:nuevoBotonId`)
   with the desired filters, `Faces-Request: partial/ajax`. The response is
   a `partial-response` XML fragment that re-renders the whole form
   (`<update id="form">`), including the result list and a fresh
   ViewState.
3. Each result row has its own "Descargar Informe" submit button
   (`form:j_idt42:{row}:j_idt64` -- the numeric suffixes are stable across
   requests for a given PrimeFaces/template version, confirmed live). A
   plain (non-AJAX) POST of that button name, reusing the same session
   cookie and the ViewState from step 2, streams the PDF back directly
   (`Content-Type: application/pdf`, confirmed with a real 137 KB report).

Two search filters ("Tipo de informe" and "Volcán") are wired up in the
form's JS but were confirmed live (2026-08-31) to NOT narrow results
server-side even when the exact AJAX payload a real browser sends is
replayed byte-for-byte (captured via a `jQuery.ajax` hook) -- e.g.
`volcanId_input=83` (Tungurahua) still returns Cotopaxi/Reventador/Sangay
rows mixed in. Only "Tipo" (Sísmico=78/Volcánico=79, `departamentoId`) and
"Año" reliably filter server-side. So `search_informes` only sends those
two, fetches the first page (sorted newest-first by the server, confirmed),
and does the "Tipo de informe"/"Volcán"/free-text narrowing client-side
against that page -- the same recency-biased, non-exhaustive approach
`igepn_client.list_earthquakes` already uses, not a claim of full coverage.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_URL = "https://informes.igepn.edu.ec/igepn-registro-web/pages/public/Informes.jsf"
_TIMEOUT = 30.0
_ROWS_PER_PAGE = 30  # the widget's own max option; one page only (see module docstring)

_GRUPOS: dict[str, str] = {"sismico": "78", "volcanico": "79"}

_VIEWSTATE_UPDATE_RE = re.compile(
    r"javax\.faces\.ViewState[^>]*>\s*<!\[CDATA\[(?P<vs>[^\]]+)\]\]>"
)
_VIEWSTATE_INITIAL_RE = re.compile(r'javax\.faces\.ViewState:0" value="(?P<vs>[^"]+)"')
_ROW_RE = re.compile(r'<li class="ui-dataview-row">(?P<row>.*?)</li>', re.DOTALL)
_BUTTON_RE = re.compile(r'<button id="(?P<id>form:j_idt42:\d+:[^"]+)"')


def _field(row: str, label: str) -> str | None:
    m = re.search(rf"{label}:</label></td><td[^>]*><label[^>]*>([^<]*)<", row)
    return m.group(1).strip() if m else None


def _extract_viewstate(text: str) -> str | None:
    m = _VIEWSTATE_UPDATE_RE.search(text)
    if m:
        return m.group("vs")
    m = _VIEWSTATE_INITIAL_RE.search(text)
    return m.group("vs") if m else None


def _extract_rows(html: str) -> list[dict[str, Any]]:
    rows = []
    for m in _ROW_RE.finditer(html):
        row = m.group("row")
        nombre = _field(row, "Nombre")
        if not nombre:
            continue
        btn = _BUTTON_RE.search(row)
        rows.append(
            {
                "nombre": nombre,
                "volcan": _field(row, "Volcán"),
                "version": _field(row, "Versión"),
                "fecha_publicacion": _field(row, "Fecha Publicación Informe"),
                "_button_id": btn.group("id") if btn else None,
            }
        )
    return rows


def _grupo_id(grupo: str) -> str:
    key = _strip(grupo)
    if not key:
        return "0"
    if key not in _GRUPOS:
        valid = ", ".join(_GRUPOS)
        raise ValueError(f"grupo '{grupo}' inválido. Usa uno de: {valid}, o vacío para ambos.")
    return _GRUPOS[key]


async def _get_viewstate(client: httpx.AsyncClient) -> str:
    r = await client.get(_URL)
    r.raise_for_status()
    vs = _extract_viewstate(r.text)
    if vs is None:
        raise ValueError("No se pudo obtener el estado inicial de IG-EPN (ViewState).")
    return vs


async def _search_page(
    client: httpx.AsyncClient, viewstate: str, grupo_id: str, anio: int
) -> str:
    data = {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "form:nuevoBotonId",
        "javax.faces.partial.execute": "@all",
        "javax.faces.partial.render": "form",
        "form": "form",
        "form:departamentoId_focus": "",
        "form:departamentoId_input": grupo_id,
        "form:viewId:anioId_focus": "",
        "form:viewId:anioId_input": str(anio),
        "form:viewId:fechaId_input": "",
        "form:viewId:fechaInicioId_input": "",
        "form:viewId:fechaFinId_input": "",
        "form:viewId_activeIndex": "0",
        "form:tipoInformeId_focus": "",
        "form:tipoInformeId_input": "0",
        "form:volcanId_focus": "",
        "form:volcanId_input": "0",
        "form:j_idt42": "list",
        "form:j_idt42_rppDD": str(_ROWS_PER_PAGE),
        "form:nuevoBotonId": "form:nuevoBotonId",
        "javax.faces.ViewState": viewstate,
    }
    headers = {
        "Faces-Request": "partial/ajax",
        "X-Requested-With": "XMLHttpRequest",
    }
    r = await client.post(_URL, data=data, headers=headers)
    r.raise_for_status()
    return r.text


async def search_informes(
    query: str = "",
    grupo: str = "",
    anio: int = 0,
    limit: int = 15,
) -> dict[str, Any]:
    """
    Search the IG-EPN PDF report archive (daily/weekly/special seismic
    bulletins, volcanic alerts, annual reports...).

    Args:
        query: Free text matched (accent-insensitive) against report name
            and volcano, e.g. "cotopaxi" or "trimestral"
        grupo: "sismico" | "volcanico" | "" (both)
        anio: Report year (0 = current year)
        limit: Max reports to return (the underlying page holds up to 30)
    """
    anio = anio or datetime.now(UTC).year
    grupo_id = _grupo_id(grupo)

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=_TIMEOUT, headers={"User-Agent": USER_AGENT}
    ) as client:
        viewstate = await _get_viewstate(client)
        html = await _search_page(client, viewstate, grupo_id, anio)
        rows = _extract_rows(html)

    q = _strip(query)
    matched = [
        row
        for row in rows
        if not q or q in _strip(f"{row['nombre']} {row.get('volcan') or ''}")
    ]

    limit = min(max(limit, 1), _ROWS_PER_PAGE)
    return {
        "grupo": grupo or "todos",
        "anio": anio,
        "total_en_pagina": len(rows),
        "coincidencias": len(matched),
        "informes": [{k: v for k, v in row.items() if not k.startswith("_")} for row in matched[:limit]],
        "nota": (
            "Solo se consulta la página más reciente del archivo (hasta 30 "
            "informes, orden descendente por fecha de publicación) para el "
            "grupo/año indicados; 'query' filtra ese lote localmente. El "
            "filtro por volcán/tipo de informe del propio sitio no acota "
            "resultados en el servidor (confirmado en vivo), así que no se "
            "usa -- si el informe buscado no aparece, prueba acotar por año "
            "o revisar directamente https://www.igepn.edu.ec/servicios/busqueda-informes"
        ),
    }


async def download_informe(
    nombre: str, volcan: str = "", grupo: str = "", anio: int = 0
) -> tuple[bytes, str]:
    """
    Download one report's PDF bytes by exact `nombre` (as returned by
    search_informes). Re-runs the same search to relocate the row and its
    session-bound download button within a fresh session, since IG-EPN has
    no stable per-document URL. Some report names repeat across volcanoes
    on the same day (e.g. "Informe Diario 2022-365" for both El Reventador
    and Sangay) -- pass `volcan` to disambiguate when that happens.

    Returns (pdf_bytes, nombre).
    """
    anio = anio or datetime.now(UTC).year
    grupo_id = _grupo_id(grupo)

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=_TIMEOUT, headers={"User-Agent": USER_AGENT}
    ) as client:
        viewstate = await _get_viewstate(client)
        html = await _search_page(client, viewstate, grupo_id, anio)
        rows = _extract_rows(html)

        candidates = [row for row in rows if row["nombre"] == nombre]
        if volcan:
            v = _strip(volcan)
            candidates = [
                row for row in candidates if row.get("volcan") and _strip(row["volcan"]) == v
            ]
        if not candidates:
            valid = ", ".join(
                f"{row['nombre']} ({row.get('volcan') or 'sin volcán'})" for row in rows
            ) or "(ninguno en esta página)"
            raise ValueError(
                f"No se encontró el informe '{nombre}'"
                + (f" (volcán: {volcan})" if volcan else "")
                + f" en la página más reciente de grupo={grupo or 'todos'}, año={anio}. "
                f"Disponibles ahí: {valid}"
            )
        if len(candidates) > 1:
            opciones = ", ".join(f"{row.get('volcan') or 'sin volcán'}" for row in candidates)
            raise ValueError(
                f"Hay {len(candidates)} informes llamados '{nombre}' en esta página; "
                f"especifica 'volcan' para desambiguar. Opciones: {opciones}"
            )
        match = candidates[0]
        if not match["_button_id"]:
            raise ValueError(
                f"El informe '{nombre}' no tiene botón de descarga en la respuesta "
                "de IG-EPN (posible cambio de formato de la página)."
            )

        viewstate = _extract_viewstate(html) or viewstate
        data = {
            "form": "form",
            "form:departamentoId_focus": "",
            "form:departamentoId_input": grupo_id,
            "form:viewId:anioId_focus": "",
            "form:viewId:anioId_input": str(anio),
            "form:viewId:fechaId_input": "",
            "form:viewId:fechaInicioId_input": "",
            "form:viewId:fechaFinId_input": "",
            "form:viewId_activeIndex": "0",
            "form:tipoInformeId_focus": "",
            "form:tipoInformeId_input": "0",
            "form:volcanId_focus": "",
            "form:volcanId_input": "0",
            "form:j_idt42": "list",
            "form:j_idt42_rppDD": str(_ROWS_PER_PAGE),
            match["_button_id"]: match["_button_id"],
            "javax.faces.ViewState": viewstate,
        }
        r = await client.post(_URL, data=data)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "pdf" not in content_type.lower():
            raise ValueError(
                f"IG-EPN no devolvió un PDF para '{nombre}' (Content-Type: "
                f"{content_type or 'desconocido'}); el archivo pudo haberse movido."
            )
        return r.content, nombre
