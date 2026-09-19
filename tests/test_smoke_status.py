import pytest

from helpers.smoke_status import assess_response, degraded_source
from scripts.smoke_e2e import DegradedChain, chain_step


def test_classifies_ckan_regional_block_as_degraded():
    text = (
        '{"error": "El portal de Datos Abiertos (datosabiertos.gob.ec) '
        'rechazó la conexión (403)."}'
    )

    assessment = assess_response(text, ['"results"'])

    assert assessment.status == "degraded"
    assert assessment.source == "datos_abiertos_ckan"


def test_classifies_cenace_certificate_problem_as_degraded():
    text = (
        "Error executing tool get_cenace_tablero: "
        "https://www.cenace.gob.ec: [SSL: CERTIFICATE_VERIFY_FAILED]"
    )

    assert degraded_source(text) == "cenace_tls"
    assert assess_response(text, ["PRODUCCIÓN"]).status == "degraded"


def test_classifies_sercop_regional_block_as_degraded():
    text = (
        '{"error": "No se pudo conectar al portal de Datos Abiertos de '
        'Compras Públicas (compraspublicas.gob.ec). Esto suele pasar '
        'cuando el servidor se conecta desde fuera de Latinoamérica."}'
    )

    assessment = assess_response(text, ["ocid", "results", "rate_limited", "error"])

    assert assessment.status == "degraded"
    assert assessment.source == "sercop_compras_publicas"


def test_keeps_unknown_errors_as_failures():
    assessment = assess_response("Error: unexpected source response", [])

    assert assessment.status == "failed"


def test_classifies_any_upstream_5xx_as_degraded():
    # Confirmed live 2026-09-18: anda.inec.gob.ec 503'd on the scheduled
    # run. A 5xx is the live source's own server failing, generically, not
    # something specific to ANDA -- so this must not need a hardcoded
    # per-host tuple the way the 403/geoblock cases do.
    text = (
        "Error al buscar en ANDA: Server error '503 Service Unavailable' "
        "for url 'https://anda.inec.gob.ec/anda5/index.php/api/catalog"
        "?ps=50&sk=empleo'"
    )

    assessment = assess_response(text, [], is_error=True)

    assert assessment.status == "degraded"
    assert assessment.source == "upstream_5xx:anda.inec.gob.ec"


def test_upstream_5xx_regex_ignores_client_errors():
    # A 4xx is not automatically a live-source outage -- it can reflect a
    # real bug in this repo's request (bad params, a changed endpoint), so
    # only 5xx gets the generic pass.
    text = "Client error '404 Not Found' for url 'https://example.gob.ec/x'"

    assert degraded_source(text) is None


def test_classifies_anda_inec_regional_block_as_degraded():
    # Confirmed live 2026-09-18: anda.inec.gob.ec 403'd from a second
    # network right after its first 503 -- a consistent geo/bot block, the
    # same INEC-property pattern as censoecuador.gob.ec, not a one-off.
    text = (
        "Error al buscar en ANDA: Client error '403 Forbidden' for url "
        "'https://anda.inec.gob.ec/anda5/index.php/api/catalog"
        "?ps=50&sk=empleo'"
    )

    assessment = assess_response(text, [], is_error=True)

    assert assessment.status == "degraded"
    assert assessment.source == "anda_inec_geoblock"


def test_classifies_gobec_empty_body_as_degraded():
    # Confirmed live 2026-09-19: gob.ec answered a blocked request with
    # HTTP 200 and an empty body rather than a 4xx, so resp.json() raised a
    # bare JSONDecodeError instead of raise_for_status() firing.
    text = (
        "Error al listar instituciones: El portal gob.ec devolvió una "
        "respuesta vacía o no válida. Esto suele pasar cuando el servidor "
        "se conecta desde fuera de Latinoamérica."
    )

    assessment = assess_response(text, [], is_error=True)

    assert assessment.status == "degraded"
    assert assessment.source == "gobec_geoblock"


def test_classifies_censo_ecuador_expired_certificate_as_degraded():
    # Confirmed live 2026-09-19: www.censoecuador.gob.ec's TLS cert expired
    # 2026-09-18 -- a genuine upstream outage, distinct from the missing-
    # intermediate case helpers/tls.py already retries around.
    text = (
        "Error al buscar recursos del Censo Ecuador: "
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
        "certificate has expired (_ssl.c:1000)"
    )

    assessment = assess_response(text, [], is_error=True)

    assert assessment.status == "degraded"
    assert assessment.source == "censo_ecuador_tls_expired"


def test_accepts_matching_normal_response():
    assert assess_response('{"results": []}', ['"results"']).status == "ok"


def test_is_error_flag_degrades_plain_text_tool_error():
    # ToolError messages post-render_structured don't all start with
    # "Error:" (e.g. "Error al buscar datasets: ..."), so a known-degraded
    # source must still classify as degraded via the MCP isError flag alone,
    # not by guessing from the message's literal prefix.
    text = (
        "Error al buscar datasets: El portal de Datos Abiertos "
        "(datosabiertos.gob.ec) rechazó la conexión (403)."
    )

    assessment = assess_response(text, [], is_error=True)

    assert assessment.status == "degraded"
    assert assessment.source == "datos_abiertos_ckan"


def test_is_error_flag_fails_unknown_plain_text_tool_error():
    assessment = assess_response("Error al listar recursos: algo se rompió", [], is_error=True)

    assert assessment.status == "failed"


# -- chain steps ------------------------------------------------------
# The dynamic list -> get chains used to hand-roll their own error check,
# so the recurring datosabiertos.gob.ec 403 failed the workflow even though
# the flat checks classified the identical response as degraded.


def test_chain_step_degrades_on_known_source_block():
    text = (
        '{"error": "El portal de Datos Abiertos (datosabiertos.gob.ec) '
        'rechazó la conexión (403)."}'
    )

    with pytest.raises(DegradedChain) as excinfo:
        chain_step(text)

    assert excinfo.value.source == "datos_abiertos_ckan"


def test_chain_step_still_fails_on_an_unknown_error():
    with pytest.raises(AssertionError):
        chain_step("Error: unexpected source response")


def test_chain_step_returns_a_healthy_response_unchanged():
    text = '{"results": [{"id": "abc"}]}'

    assert chain_step(text, ['"results"']) == text


def test_chain_step_degrades_on_plain_text_tool_error_via_is_error_flag():
    # Regression: chain_ckan_preview crashed with a JSONDecodeError instead
    # of degrading, because the ToolError text here doesn't start with
    # "Error:" and isn't itself JSON -- only the isError flag reveals it's a
    # failure at all.
    text = (
        "Error al buscar datasets: El portal de Datos Abiertos "
        "(datosabiertos.gob.ec) rechazó la conexión (403)."
    )

    with pytest.raises(DegradedChain) as excinfo:
        chain_step(text, is_error=True)

    assert excinfo.value.source == "datos_abiertos_ckan"
