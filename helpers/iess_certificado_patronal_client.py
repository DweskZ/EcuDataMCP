"""Client for the IESS's public "Certificado de Cumplimiento de
Obligaciones Patronales" -- confirmed 2026-09-21 while investigating
whether the IESS exposes any public per-employer data at all (it doesn't
publish an affiliate/employee headcount by company anywhere itself -- see
the tool docstring for that scope note). This certificate is a real,
unauthenticated public service, distinct from that: it states whether an
employer (by RUC or cédula) is current on Seguro Social contributions, not
how many people it employs. The actual employee-count figure DOES exist
publicly, just not from the IESS -- it's Supercías' Ranking dataset's
`n_empleados` field (helpers/supercias_financials.py), self-reported in
each company's annual balance-sheet filing; that field was itself found
to be nulled out for 100% of rows by an unrelated int-conversion bug the
same day this client was built, fixed in
scripts/build_supercias_financials_db.py.

**The page itself says "Este certificado no requiere validación del
IESS"** -- no login, confirmed at
`iess.gob.ec/empleador-web/pages/morapatronal/certificadoCumplimientoPublico.jsf`.
It is legacy JSF (Mojarra/RichFaces, `javax.faces.ViewState`), not a REST
API: fetching it needs a session-bound GET (to seed a fresh ViewState and
JSESSIONID cookie tied to the app-server node) immediately followed by a
POST replaying that exact ViewState in the same session -- the same
"stateful postback" shape as `reportes.arconel.gob.ec` (see
docs/RESEARCH.md § Vigésima pasada), just Java/JSF instead of ASP.NET
WebForms. A stale or mismatched ViewState from a different session fails
silently rather than erroring cleanly, so each call gets its own fresh
GET+POST rather than trying to reuse state across calls.

**The response is a PDF, generated server-side on the POST** -- confirmed
live: `Content-Type: application/pdf`, real content, for a valid RUC. Its
prose states the employer's mora status in one sentence ("el señor(a) X,
representante legal de la empresa Y con RUC Nro. Z y dirección W, NO
registra obligaciones patronales en mora"), which this client parses with
a single regex rather than shipping the PDF bytes -- `helpers.pdf_reader`
does the actual page-to-text extraction, reused as-is rather than
duplicating pypdf handling here.

**Two confirmed failure modes, both silent (no HTTP error, no exception
from the server itself) -- this client must distinguish them from a real
"no debe":**

1. A syntactically invalid identification (confirmed with a RUC that
   fails Ecuador's checksum) returns `200` but with an **F5 BIG-IP
   anti-bot JS challenge page** instead of a PDF (`Content-Type:
   text/html`, an inline `f5_cspm` obfuscated script) -- not a document
   ID that doesn't exist, a genuinely malformed one that the backend
   itself seems to choke on before F5 intercepts the resulting error.
2. A well-formed but non-existent identification returns `200
   application/pdf` with a **real PDF that has zero extractable text** (a
   blank page) -- confirmed against a synthetic cédula. `pypdf` parses it
   fine; there is simply nothing on the page.

Both are mapped to `encontrado: False` here, with `motivo` distinguishing
them, rather than treating either as a normal Python exception -- neither
is a bug in this client, they're two different "not found" shapes the
source itself uses.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urljoin

import httpx

from helpers.logging import MAIN_LOGGER_NAME
from helpers.pdf_reader import extract_text_from_bytes
from helpers.tls import should_retry_insecure
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

CERTIFICADO_URL = (
    "https://www.iess.gob.ec/empleador-web/pages/morapatronal/"
    "certificadoCumplimientoPublico.jsf"
)
_TIMEOUT = 30.0

_FORM_ID = "frmCertificadoCumplimiento"
_FORM_RE = re.compile(
    r'(?P<tag><form\b(?=[^>]*\bid="' + _FORM_ID + r'")[^>]*>)(?P<body>.*?)</form>',
    re.IGNORECASE | re.DOTALL,
)
_ACTION_RE = re.compile(r'\baction="([^"]+)"', re.IGNORECASE)
_INPUT_RE = re.compile(r"<input\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r'\b(name|type|value)="([^"]*)"', re.IGNORECASE)

# Markers of the F5 BIG-IP anti-bot challenge page. Only `f5_cspm` has
# been seen live on the IESS site; the other two are common on F5 ASM
# challenge pages generally.
_F5_MARKERS = ("f5_cspm", "TSPD", "bobcmn")

_CERT_TEXT_RE = re.compile(
    r"el señor\(a\)\s+(?P<persona>.+?),\s*"
    r"(?:representante legal de la empresa\s+(?P<empresa>.+?)\s+con RUC Nro\.|"
    r"con (?:RUC|C\.?I\.?)\s*Nro\.)\s*"
    r"(?P<identificacion>\d{10,13})\s+y dirección\s+(?P<direccion>.+?),\s*"
    r"(?P<estado_texto>NO\s+registra|S[IÍ]\s+registra|registra)\s+"
    r"obligaciones\s+patronales\s+en\s+mora",
    re.IGNORECASE | re.DOTALL,
)
# Stop before "Validez del Certificado" in case both land on one line.
_EMITIDO_RE = re.compile(
    r"Emitido el\s+(.+?)(?=\s*Validez del Certificado|\n|$)", re.IGNORECASE
)
_VALIDEZ_RE = re.compile(r"Validez del Certificado\s+(\d+)\s+días", re.IGNORECASE)


def _validate_identificacion(value: str) -> str:
    digits = re.sub(r"\D", "", str(value))
    if len(digits) not in (10, 13):
        raise ValueError(
            "La identificación debe ser una cédula (10 dígitos) o un RUC (13 dígitos)."
        )
    return digits


async def _get_form(session: httpx.AsyncClient) -> tuple[str, str, dict[str, str]]:
    """GET a fresh copy of the form -- returns (post_url, id_field, fields),
    all read from the certificate form itself and bound to this session's
    cookies/ViewState. Field names (`j_id9`, ...) are JSF-generated and
    change on redeploy, so they're discovered here rather than hardcoded.
    See module docstring for why this can't be cached across calls."""
    resp = await session.get(CERTIFICADO_URL)
    resp.raise_for_status()
    html = resp.text

    form_m = _FORM_RE.search(html)
    if not form_m:
        raise ValueError("No se encontró el formulario del certificado del IESS en la página.")
    action_m = _ACTION_RE.search(form_m.group("tag"))
    if not action_m:
        raise ValueError("El formulario del certificado del IESS no tiene 'action'.")
    post_url = urljoin(str(resp.url), action_m.group(1).replace("&amp;", "&"))

    fields: dict[str, str] = {_FORM_ID: _FORM_ID}
    id_field = submit_field = None
    for tag in _INPUT_RE.findall(form_m.group("body")):
        attrs = {k.lower(): v for k, v in _ATTR_RE.findall(tag)}
        name = attrs.get("name")
        if not name:
            continue
        kind = attrs.get("type", "text").lower()
        if kind == "hidden":
            fields[name] = attrs.get("value", "")
        elif kind == "text" and id_field is None:
            id_field = name
        elif kind == "submit" and submit_field is None:
            submit_field = name
            fields[name] = attrs.get("value", "CONSULTAR")

    if "javax.faces.ViewState" not in fields:
        raise ValueError("No se encontró el ViewState del formulario del IESS.")
    if id_field is None or submit_field is None:
        raise ValueError(
            "El formulario del certificado del IESS cambió: no se encontraron los "
            "campos de identificación y consulta."
        )
    return post_url, id_field, fields


async def _submit_certificado(
    session: httpx.AsyncClient,
    post_url: str,
    id_field: str,
    fields: dict[str, str],
    identificacion: str,
) -> httpx.Response:
    data = {**fields, id_field: identificacion}
    resp = await session.post(post_url, data=data)
    resp.raise_for_status()
    return resp


def _clean(value: str | None) -> str | None:
    """pypdf's extract_text() keeps the PDF's own line wraps -- collapse
    them to spaces so a name that happened to wrap mid-line doesn't come
    back with an embedded newline."""
    if value is None:
        return None
    return re.sub(r"\s+", " ", value).strip()


def _parse_certificado_text(text: str, identificacion: str) -> dict[str, Any]:
    match = _CERT_TEXT_RE.search(text)
    emitido_m = _EMITIDO_RE.search(text)
    validez_m = _VALIDEZ_RE.search(text)

    result: dict[str, Any] = {
        "encontrado": True,
        "identificacion_consultada": identificacion,
        "fecha_emision": emitido_m.group(1).strip() if emitido_m else None,
        "validez_dias": int(validez_m.group(1)) if validez_m else None,
        "texto_completo": text,
    }
    if match:
        result["persona"] = _clean(match.group("persona"))
        result["empresa"] = _clean(match.group("empresa"))
        result["direccion"] = _clean(match.group("direccion"))
        encontrada = match.group("identificacion")
        if encontrada != identificacion:
            raise ValueError(
                f"El IESS devolvió un certificado para {encontrada}, no para la "
                f"identificación consultada {identificacion}."
            )
        result["moroso"] = _clean(match.group("estado_texto")).upper() != "NO REGISTRA"
    else:
        # Real text, but not in the exact phrasing this regex expects (e.g.
        # a wording variant this client hasn't seen yet) -- surface the raw
        # text instead of silently dropping the fields.
        result["persona"] = None
        result["empresa"] = None
        result["direccion"] = None
        result["moroso"] = None
    return result


async def _run(identificacion: str, verify: bool = True) -> httpx.Response:
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=_TIMEOUT,
        verify=verify,
    ) as session:
        post_url, id_field, fields = await _get_form(session)
        return await _submit_certificado(session, post_url, id_field, fields, identificacion)


async def get_certificado_cumplimiento_patronal(identificacion: str) -> dict[str, Any]:
    """Check whether an employer (by 13-digit RUC) or individual (by
    10-digit cédula) is current on Seguro Social contributions, via the
    IESS's public "Certificado de Cumplimiento de Obligaciones
    Patronales". Does NOT return employee/affiliate counts -- the IESS
    does not publish that publicly by employer; this is a mora/no-mora
    compliance check only.
    """
    identificacion = _validate_identificacion(identificacion)

    try:
        resp = await _run(identificacion)
    except httpx.ConnectError as exc:
        if not should_retry_insecure(exc, CERTIFICADO_URL):
            raise
        logger.warning("Falló la verificación TLS para el certificado patronal del IESS")
        resp = await _run(identificacion, verify=False)

    content_type = resp.headers.get("content-type", "")
    if "pdf" not in content_type.lower():
        body = resp.text
        if any(marker in body for marker in _F5_MARKERS):
            return {
                "encontrado": False,
                "identificacion_consultada": identificacion,
                "motivo": (
                    "El firewall del IESS devolvió una página anti-bot en lugar del "
                    "certificado (visto con identificaciones de formato inválido). Esto "
                    "NO prueba que la identificación no esté registrada."
                ),
            }
        # Anything else (expired session, JSF validation error, changed form)
        # is a failure, not a "not found" -- don't mask it as one.
        logger.warning("IESS certificado: respuesta inesperada %s", content_type)
        raise ValueError(
            f"El IESS devolvió una respuesta inesperada ({content_type or 'sin tipo'}) "
            "en lugar del certificado en PDF."
        )

    # pypdf is CPU-bound; keep it off the event loop.
    extracted = await asyncio.to_thread(extract_text_from_bytes, resp.content, pages="1")
    pages = extracted.get("pages") or []
    text = pages[0]["text"] if pages else ""
    if not text.strip():
        return {
            "encontrado": False,
            "identificacion_consultada": identificacion,
            "motivo": "El IESS generó un certificado en blanco: la identificación no está registrada.",
        }

    result = _parse_certificado_text(text, identificacion)
    result["url_fuente"] = CERTIFICADO_URL
    result["nota_alcance"] = (
        "Este certificado indica si el empleador está al día en obligaciones patronales "
        "(mora), no el número de empleados/afiliados -- el IESS no publica esa cifra "
        "públicamente por empresa. Para el número de empleados, usa "
        "get_financials/search_ranking (campo n_empleados, autorreportado a Supercías)."
    )
    return result
