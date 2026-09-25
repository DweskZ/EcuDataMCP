import re

import pytest

from helpers import iess_certificado_patronal_client as client

_ACTION = "/empleador-web/pages/morapatronal/certificadoCumplimientoPublico.jsf;jsessionid=ABC123"
_VIEW_STATE_1 = "vs-form-one"
_VIEW_STATE_2 = "vs-frmCertificadoCumplimiento"

# Trimmed but structurally faithful excerpt of the real page (two JSF
# forms, each with its own javax.faces.ViewState -- confirmed live
# 2026-09-21, see module docstring).
_FORM_HTML = f"""
<html><body>
<form id="formContenido" method="post" action="/empleador-web/other.jsf">
<input type="hidden" name="javax.faces.ViewState" value="{_VIEW_STATE_1}" />
</form>
<form id="frmCertificadoCumplimiento" name="frmCertificadoCumplimiento" method="post"
      action="{_ACTION}">
<input type="hidden" name="frmCertificadoCumplimiento" value="frmCertificadoCumplimiento" />
<input type="text" name="frmCertificadoCumplimiento:j_id9" maxlength="13" />
<input type="submit" name="frmCertificadoCumplimiento:j_id11" value="CONSULTAR" />
<input type="hidden" name="javax.faces.ViewState" value="{_VIEW_STATE_2}" />
</form>
</body></html>
"""

# The real certificate's prose (see module docstring for the exact
# confirmed sentence shape), embedded here as a minimal one-page PDF so
# pypdf can extract it back out. Built once at import time.
_REAL_CERT_TEXT = (
    "CERTIFICADO DE CUMPLIMIENTO DE OBLIGACIONES PATRONALES\n"
    "El Instituto Ecuatoriano de Seguridad Social (IESS) certifica que, revisados los "
    "archivos del Sistema de Historia Laboral, el señor(a) BASANTES FREIRE FERNANDO "
    "ALEXANDER, representante legal de la empresa ACQUAD'OR C.A. con RUC Nro. "
    "0992216735001 y dirección LA PROSPERINA KM 6,5, NO registra obligaciones "
    "patronales en mora; información verificada a la fecha de emisión del presente "
    "certificado.\n"
    "Emitido el 21 de septiembre de 2026\n"
    "Validez del Certificado 30 días"
)


def _build_minimal_pdf(text: str) -> bytes:
    """A hand-built, single-page PDF with one Tj text-showing operator per
    line -- avoids adding a PDF-writing dependency just for tests."""
    lines = text.split("\n")
    content_lines = ["BT", "/F1 10 Tf", "50 750 Td", "12 TL"]
    for line in lines:
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        content_lines.append(f"({escaped}) Tj")
        content_lines.append("T*")
    content_lines.append("ET")
    content = "\n".join(content_lines).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
            b"/MediaBox [0 0 612 792] /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    out = [b"%PDF-1.4\n"]
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(sum(len(chunk) for chunk in out))
        out.append(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = sum(len(chunk) for chunk in out)
    out.append(f"xref\n0 {len(objects) + 1}\n".encode())
    out.append(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.append(f"{off:010d} 00000 n \n".encode())
    out.append(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
        .encode()
    )
    return b"".join(out)


_REAL_CERT_PDF = _build_minimal_pdf(_REAL_CERT_TEXT)
_BLANK_PDF = _build_minimal_pdf("")


def _post_url() -> str:
    return f"https://www.iess.gob.ec{_ACTION.replace('&amp;', '&')}"


@pytest.mark.asyncio
async def test_get_certificado_parses_a_real_result(httpx_mock):
    httpx_mock.add_response(url=client.CERTIFICADO_URL, html=_FORM_HTML)
    httpx_mock.add_response(
        url=_post_url(),
        method="POST",
        content=_REAL_CERT_PDF,
        headers={"Content-Type": "application/pdf"},
    )

    result = await client.get_certificado_cumplimiento_patronal("0992216735001")

    assert result["encontrado"] is True
    assert result["moroso"] is False
    assert result["persona"] == "BASANTES FREIRE FERNANDO ALEXANDER"
    assert result["empresa"] == "ACQUAD'OR C.A."
    assert result["validez_dias"] == 30


@pytest.mark.asyncio
async def test_get_certificado_treats_blank_pdf_as_not_found(httpx_mock):
    httpx_mock.add_response(url=client.CERTIFICADO_URL, html=_FORM_HTML)
    httpx_mock.add_response(
        url=_post_url(),
        method="POST",
        content=_BLANK_PDF,
        headers={"Content-Type": "application/pdf"},
    )

    result = await client.get_certificado_cumplimiento_patronal("1710034065")

    assert result["encontrado"] is False
    assert "en blanco" in result["motivo"]


@pytest.mark.asyncio
async def test_get_certificado_treats_non_pdf_response_as_not_found(httpx_mock):
    # The F5 anti-bot JS-challenge shape confirmed live for a
    # checksum-invalid RUC -- Content-Type text/html instead of a PDF.
    httpx_mock.add_response(url=client.CERTIFICADO_URL, html=_FORM_HTML)
    httpx_mock.add_response(
        url=_post_url(),
        method="POST",
        html="<html><script>var f5_cspm={...}</script></html>",
    )

    result = await client.get_certificado_cumplimiento_patronal("1710034073")

    assert result["encontrado"] is False
    assert "bloqueo" in result["motivo"] or "inválido" in result["motivo"]


@pytest.mark.asyncio
async def test_rejects_wrong_length_identificacion():
    with pytest.raises(ValueError, match=re.escape("10 dígitos")):
        await client.get_certificado_cumplimiento_patronal("12345")


def _cert_text(estado: str, ruc: str = "0992216735001") -> str:
    return _REAL_CERT_TEXT.replace("0992216735001", ruc).replace(
        "NO registra obligaciones\npatronales en mora".replace("\n", " "), estado
    )


async def _run_with_pdf(httpx_mock, text: str, ruc: str = "0992216735001") -> dict:
    httpx_mock.add_response(url=client.CERTIFICADO_URL, html=_FORM_HTML)
    httpx_mock.add_response(
        url=_post_url(),
        method="POST",
        content=_build_minimal_pdf(text),
        headers={"Content-Type": "application/pdf"},
    )
    return await client.get_certificado_cumplimiento_patronal(ruc)


@pytest.mark.asyncio
async def test_posts_certificate_form_viewstate_and_discovered_fields(httpx_mock):
    await _run_with_pdf(httpx_mock, _REAL_CERT_TEXT)
    post = httpx_mock.get_requests(method="POST")[0]
    body = post.content.decode()
    assert _VIEW_STATE_2 in body
    assert _VIEW_STATE_1 not in body
    assert "frmCertificadoCumplimiento%3Aj_id9=0992216735001" in body


@pytest.mark.asyncio
async def test_si_registra_with_accent_and_line_breaks_is_moroso(httpx_mock):
    text = _cert_text("SÍ\nregistra obligaciones patronales\nen mora")
    result = await _run_with_pdf(httpx_mock, text)
    assert result["moroso"] is True


@pytest.mark.asyncio
async def test_no_registra_split_across_lines_is_not_moroso(httpx_mock):
    text = _cert_text("NO\nregistra obligaciones patronales en mora")
    result = await _run_with_pdf(httpx_mock, text)
    assert result["moroso"] is False


@pytest.mark.asyncio
async def test_unparseable_certificate_leaves_moroso_unknown(httpx_mock):
    result = await _run_with_pdf(httpx_mock, "CERTIFICADO\nTexto con otra redacción")
    assert result["encontrado"] is True
    assert result["moroso"] is None


@pytest.mark.asyncio
async def test_certificate_for_another_ruc_raises(httpx_mock):
    text = _REAL_CERT_TEXT.replace("0992216735001", "1790013731001")
    with pytest.raises(ValueError, match="1790013731001"):
        await _run_with_pdf(httpx_mock, text)


@pytest.mark.asyncio
async def test_non_f5_html_response_raises_instead_of_not_found(httpx_mock):
    httpx_mock.add_response(url=client.CERTIFICADO_URL, html=_FORM_HTML)
    httpx_mock.add_response(
        url=_post_url(), method="POST", html="<html>ViewExpiredException</html>"
    )
    with pytest.raises(ValueError, match="respuesta inesperada"):
        await client.get_certificado_cumplimiento_patronal("0992216735001")


def test_emitido_stops_before_validez_on_same_line():
    text = _REAL_CERT_TEXT.replace("2026\nValidez", "2026 Validez")
    result = client._parse_certificado_text(text, "0992216735001")
    assert result["fecha_emision"] == "21 de septiembre de 2026"
    assert result["validez_dias"] == 30


def test_absolute_form_action_is_not_double_prefixed():
    html = _FORM_HTML.replace(_ACTION, "https://www.iess.gob.ec" + _ACTION)
    m = client._FORM_RE.search(html)
    action = client._ACTION_RE.search(m.group("tag")).group(1)
    from urllib.parse import urljoin

    assert urljoin(client.CERTIFICADO_URL, action) == _post_url()
