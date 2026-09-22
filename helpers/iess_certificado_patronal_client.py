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

import logging
import re
from typing import Any

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

_ACTION_RE = re.compile(
    r'<form[^>]*id="frmCertificadoCumplimiento"[^>]*action="([^"]+)"'
)
_VIEWSTATE_RE = re.compile(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"')

_CERT_TEXT_RE = re.compile(
    r"el señor\(a\)\s+(?P<persona>.+?),\s*"
    r"(?:representante legal de la empresa\s+(?P<empresa>.+?)\s+con RUC Nro\.|"
    r"con (?:RUC|C\.?I\.?)\s*Nro\.)\s*"
    r"(?P<identificacion>\d{10,13})\s+y dirección\s+(?P<direccion>.+?),\s*"
    r"(?P<estado_texto>NO registra|SI registra|registra)\s+obligaciones patronales en mora",
    re.IGNORECASE | re.DOTALL,
)
_EMITIDO_RE = re.compile(r"Emitido el\s+([^\n]+)", re.IGNORECASE)
_VALIDEZ_RE = re.compile(r"Validez del Certificado\s+(\d+)\s+días", re.IGNORECASE)


def _validate_identificacion(value: str) -> str:
    digits = re.sub(r"\D", "", str(value))
    if len(digits) not in (10, 13):
        raise ValueError(
            "La identificación debe ser una cédula (10 dígitos) o un RUC (13 dígitos)."
        )
    return digits


async def _get_form(session: httpx.AsyncClient) -> tuple[str, str]:
    """GET a fresh copy of the form -- returns (post_url, view_state), both
    bound to this session's cookies/ViewState. See module docstring for
    why this can't be cached or reused across calls."""
    resp = await session.get(CERTIFICADO_URL)
    resp.raise_for_status()
    html = resp.text

    action_m = _ACTION_RE.search(html)
    if not action_m:
        raise ValueError("No se encontró el formulario del certificado del IESS en la página.")
    action = action_m.group(1).replace("&amp;", "&")
    post_url = f"https://www.iess.gob.ec{action}"

    view_states = _VIEWSTATE_RE.findall(html)
    if not view_states:
        raise ValueError("No se encontró el ViewState del formulario del IESS.")
    # The page has two JSF forms; the certificate form's own ViewState is
    # the last one in document order (see module docstring).
    return post_url, view_states[-1]


async def _submit_certificado(
    session: httpx.AsyncClient, post_url: str, view_state: str, identificacion: str
) -> httpx.Response:
    data = {
        "frmCertificadoCumplimiento": "frmCertificadoCumplimiento",
        "frmCertificadoCumplimiento:j_id9": identificacion,
        "frmCertificadoCumplimiento:j_id11": "CONSULTAR",
        "javax.faces.ViewState": view_state,
    }
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
        result["moroso"] = match.group("estado_texto").strip().upper() != "NO REGISTRA"
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
        post_url, view_state = await _get_form(session)
        return await _submit_certificado(session, post_url, view_state, identificacion)


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
        return {
            "encontrado": False,
            "identificacion_consultada": identificacion,
            "motivo": (
                "El IESS no devolvió un certificado (posible identificación con formato "
                "inválido o un bloqueo temporal del servidor) en lugar de un 'no encontrado' "
                "normal."
            ),
        }

    extracted = extract_text_from_bytes(resp.content, pages="1")
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
